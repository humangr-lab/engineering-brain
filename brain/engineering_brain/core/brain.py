"""Brain — Main orchestrator for the Engineering Knowledge Brain.

The Brain class is the single entry point for all operations:
- add_rule, add_principle, add_pattern: Insert knowledge
- query: Retrieve relevant knowledge for a task
- learn_from_finding: Auto-evolve from code review findings
- ingest, ingest_directory: Bulk load from YAML seed files
- seed: Load all built-in seed data
- stats: Get brain statistics
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC
from pathlib import Path
from typing import Any

import yaml

from engineering_brain.adapters.base import CacheAdapter, GraphAdapter, VectorAdapter
from engineering_brain.adapters.memory import (
    MemoryCacheAdapter,
    MemoryGraphAdapter,
    MemoryVectorAdapter,
    MultiTierCache,
)
from engineering_brain.adapters.sharding import ShardRouter
from engineering_brain.core.config import BrainConfig, get_brain_config
from engineering_brain.core.schema import EdgeType, Layer, NodeType
from engineering_brain.core.types import (
    Axiom,
    EnhancedKnowledgeResult,
    KnowledgeQuery,
    KnowledgeResult,
    MaterializedPack,
    Pack,
    Pattern,
    Principle,
    ReasoningResult,
    Rule,
    SeedFile,
    Source,
)
from engineering_brain.learning.crystallizer import KnowledgeCrystallizer
from engineering_brain.learning.promoter import KnowledgePromoter
from engineering_brain.learning.pruner import KnowledgePruner
from engineering_brain.learning.reinforcer import EvidenceReinforcer
from engineering_brain.retrieval.router import QueryRouter

logger = logging.getLogger(__name__)


class Brain:
    """The Engineering Knowledge Brain — industrial-scale knowledge graph.

    Provides a ridiculously easy API for adding, querying, and evolving
    engineering knowledge. Supports pluggable storage backends (FalkorDB,
    Qdrant, Redis, in-memory).

    Usage:
        brain = Brain()  # In-memory by default
        brain.seed()     # Load built-in knowledge
        result = brain.query("Write Flask server with WebSocket")
        print(result.formatted_text)
    """

    def __init__(
        self,
        adapter: str | None = None,
        config: BrainConfig | None = None,
        graph: GraphAdapter | None = None,
        vector: VectorAdapter | None = None,
        cache: CacheAdapter | None = None,
    ) -> None:
        self._config = config or get_brain_config()
        adapter_name = adapter or self._config.adapter

        # Initialize adapters
        if graph:
            self._graph = graph
        elif adapter_name == "falkordb":
            from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

            self._graph = FalkorDBGraphAdapter(self._config)
        elif adapter_name == "neo4j":
            from engineering_brain.adapters.neo4j import Neo4jGraphAdapter

            self._graph = Neo4jGraphAdapter(self._config)
        else:
            self._graph = MemoryGraphAdapter()

        if vector:
            self._vector = vector
        elif adapter_name == "neo4j":
            try:
                from engineering_brain.adapters.neo4j import Neo4jVectorAdapter

                self._vector = Neo4jVectorAdapter(self._config)
            except Exception as exc:
                logger.warning("Neo4j vector adapter unavailable, falling back to memory: %s", exc)
                self._vector = MemoryVectorAdapter()
        elif adapter_name in ("falkordb", "qdrant", "full"):
            try:
                from engineering_brain.adapters.qdrant import QdrantVectorAdapter

                self._vector = QdrantVectorAdapter(self._config)
            except Exception as exc:
                logger.warning("Qdrant vector adapter unavailable, falling back to memory: %s", exc)
                self._vector = MemoryVectorAdapter()
        else:
            self._vector = MemoryVectorAdapter()

        if cache:
            self._cache = cache
        elif adapter_name in ("falkordb", "neo4j", "redis", "full"):
            l1 = MemoryCacheAdapter(
                max_size=self._config.memory_cache_size,
                default_ttl=self._config.memory_cache_ttl,
            )
            try:
                from engineering_brain.adapters.redis_cache import RedisCacheAdapter

                l2 = RedisCacheAdapter(self._config)
                self._cache = MultiTierCache(l1=l1, l2=l2)
            except Exception as exc:
                logger.warning(
                    "Redis cache adapter unavailable, falling back to memory-only cache: %s", exc
                )
                self._cache = l1
        else:
            self._cache = MemoryCacheAdapter(
                max_size=self._config.memory_cache_size,
                default_ttl=self._config.memory_cache_ttl,
            )

        # Initialize observation log
        self._observation_log = None
        if self._config.observation_log_enabled:
            try:
                from engineering_brain.observation.log import ObservationLog

                self._observation_log = ObservationLog(self._config.observation_log_path)
            except Exception as exc:
                logger.debug("ObservationLog init failed (non-blocking): %s", exc)

        # Initialize embedder (lazy, never blocks)
        self._embedder = None
        if self._config.embedding_enabled:
            try:
                from engineering_brain.retrieval.embedder import BrainEmbedder

                self._embedder = BrainEmbedder(self._vector, self._config)
            except Exception as exc:
                logger.debug("BrainEmbedder init failed (non-blocking): %s", exc)

        # Initialize components
        self._shard_router = ShardRouter(
            enabled=self._config.sharding_enabled,
            max_parallel=self._config.max_parallel_shard_queries,
        )
        self._query_router = QueryRouter(
            graph=self._graph,
            vector=self._vector,
            cache=self._cache,
            shard_router=self._shard_router,
            config=self._config,
        )
        self._crystallizer = KnowledgeCrystallizer(self._graph, embedder=self._embedder)
        self._reinforcer = EvidenceReinforcer(self._graph, observation_log=self._observation_log)
        self._promoter = KnowledgePromoter(self._graph, self._config)
        self._pruner = KnowledgePruner(self._graph, self._config)

        # --- Graph improvement gap components (lazy, opt-in) ---
        self._adaptive_weights = None
        if self._config.adaptive_weights_enabled and self._observation_log:
            try:
                from engineering_brain.learning.adaptive_weights import AdaptiveWeightOptimizer

                self._adaptive_weights = AdaptiveWeightOptimizer(
                    self._observation_log, self._config
                )
                # Wire optimizer into the query pipeline (Gap 4)
                self._query_router._weight_optimizer = self._adaptive_weights
            except Exception as exc:
                logger.debug("AdaptiveWeightOptimizer init failed (non-blocking): %s", exc)

        self._adaptive_promotion = None
        if self._config.adaptive_promotion_enabled and self._observation_log:
            try:
                from engineering_brain.learning.adaptive_promotion import AdaptivePromotionPolicy

                self._adaptive_promotion = AdaptivePromotionPolicy(
                    observation_log=self._observation_log,
                    config=self._config,
                )
                self._promoter._adaptive_policy = self._adaptive_promotion
            except Exception as exc:
                logger.debug("AdaptivePromotionPolicy init failed (non-blocking): %s", exc)

        self._link_predictor = None  # Initialized after seed() when embedder is ready
        self._cross_layer_inferrer = None  # Initialized after seed() when embedder is ready

        # Monotonic write counter for epoch versioning (pull model)
        self._write_counter: int = 0

        # Seed version tracking — skip re-loading unchanged seeds
        self._loaded_seeds: dict[str, str] = {}  # {file_path: version_hash}

        # Suspend per-node embeddings during bulk ingest (seed/ingest_directory)
        self._ingesting: bool = False

        # Auto-maintenance scheduling (O-08)
        self._last_maintenance_at: float = time.time()
        self._last_maintenance_version: int = 0

    @property
    def graph(self) -> GraphAdapter:
        """Public read-only access to the graph adapter."""
        return self._graph

    @property
    def version(self) -> int:
        """Monotonic write counter. Increments on every knowledge mutation.

        Useful for detecting new knowledge: snapshot version before a batch,
        check delta after to see if the graph was updated.
        """
        return self._write_counter

    # =========================================================================
    # Query API
    # =========================================================================

    def query(
        self,
        task_description: str,
        technologies: list[str] | None = None,
        file_type: str = "",
        phase: str = "exec",
        domains: list[str] | None = None,
        budget_chars: int | None = None,
    ) -> KnowledgeResult:
        """Query the brain for relevant engineering knowledge.

        Args:
            task_description: What the agent is trying to do
            technologies: Explicit technology list (auto-detected if empty)
            file_type: File extension being worked on (.py, .js, etc.)
            phase: Workflow phase (spec, exec, qa)
            domains: Explicit domain list (auto-detected if empty)
            budget_chars: Override context budget (default from config)

        Returns:
            KnowledgeResult with formatted_text ready for prompt injection
        """
        request = KnowledgeQuery(
            task_description=task_description,
            technologies=technologies or [],
            file_type=file_type,
            phase=phase,
            domains=domains or [],
            budget_chars=budget_chars,
        )
        return self._query_router.query(request)

    def think(
        self,
        task_description: str,
        technologies: list[str] | None = None,
        file_type: str = "",
        phase: str = "exec",
        domains: list[str] | None = None,
        budget_chars: int | None = None,
    ) -> EnhancedKnowledgeResult:
        """Enhanced query with epistemic reasoning.

        Like query(), but enriches results with confidence tiers,
        contradiction detection, gap identification, and metacognitive
        assessment. Returns epistemically-annotated knowledge that lets
        frontier models understand what the brain knows AND doesn't know.

        Args:
            task_description: What the agent is trying to do
            technologies: Explicit technology list (auto-detected if empty)
            file_type: File extension being worked on (.py, .js, etc.)
            phase: Workflow phase (spec, exec, qa)
            domains: Explicit domain list (auto-detected if empty)
            budget_chars: Override enhanced context budget (default 4500)

        Returns:
            EnhancedKnowledgeResult with epistemic context
        """
        from engineering_brain.retrieval.context_extractor import extract_context
        from engineering_brain.retrieval.thought_enhancer import ThoughtEnhancer

        request = KnowledgeQuery(
            task_description=task_description,
            technologies=technologies or [],
            file_type=file_type,
            phase=phase,
            domains=domains or [],
            budget_chars=budget_chars,
        )

        base_result, scored_nodes = self._query_router.query_with_scored_nodes(request)

        ctx = extract_context(
            task_description,
            technologies=technologies or [],
            file_type=file_type,
            phase=phase,
            domains=domains or [],
        )

        enhancer = ThoughtEnhancer(graph=self._graph, config=self._config)
        return enhancer.enhance(
            query=request,
            query_context=ctx,
            scored_nodes=scored_nodes,
            base_result=base_result,
            budget_chars=budget_chars,
        )

    # =========================================================================
    # ERG — Structured Epistemic Reasoning
    # =========================================================================

    def reason(
        self,
        task_description: str,
        technologies: list[str] | None = None,
        file_type: str = "",
        phase: str = "exec",
        domains: list[str] | None = None,
        profile: str | None = None,
        max_chains: int | None = None,
    ) -> ReasoningResult:
        """Structured epistemic reasoning with chains, packs, and synthesis.

        Builds reasoning chains with causal edges (PREREQUISITE, DEEPENS,
        ALTERNATIVE), confidence tiers per step, cross-chain synthesis via
        Dempster-Shafer theory, contradiction detection, and gap analysis.

        Zero LLM calls — everything is graph traversal + scoring + epistemic math.

        Args:
            task_description: What you need to reason about
            technologies: Technologies involved
            file_type: File extension (.py, .js, etc.)
            phase: Workflow phase (spec, exec, qa)
            domains: Relevant domains
            profile: Reasoning profile (data_engineer, security_engineer, fullstack)
            max_chains: Max reasoning chains (default 3)

        Returns:
            ReasoningResult with chains, synthesis, contradictions, gaps
        """
        from engineering_brain.retrieval.context_extractor import extract_context
        from engineering_brain.retrieval.reasoning_engine import ReasoningEngine

        ctx = extract_context(
            task_description,
            technologies=technologies,
            file_type=file_type,
            phase=phase,
            domains=domains,
        )

        # Load profile if specified
        brain_profile = None
        if profile:
            from engineering_brain.retrieval.brain_profiles import load_profile

            brain_profile = load_profile(profile)

        engine = ReasoningEngine(
            graph=self._graph,
            vector=self._vector,
            cache=self._cache,
            config=self._config,
            query_router=self._query_router,
        )
        return engine.reason(ctx, profile=brain_profile, max_chains=max_chains)

    def create_pack(
        self,
        description: str,
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
        min_score: float = 0.3,
        max_nodes: int = 80,
    ) -> Pack:
        """Create a knowledge pack from a natural language description.

        A pack is a "frozen query" — a materialized subgraph with reasoning edges.

        When BRAIN_PACK_V2_ENABLED=true, uses ScalablePackManager with O(log N)
        vector-first retrieval. Otherwise uses PackManager v1 with full scan.

        Args:
            description: Natural language description (e.g. "Kafka exactly-once patterns")
            technologies: Filter by technologies
            domains: Filter by domains
            min_score: Minimum relevance score threshold (0.0-1.0)
            max_nodes: Maximum nodes in the pack

        Returns:
            Pack with nodes, reasoning edges, and quality score
        """
        if self._config.pack_v2_enabled:
            from engineering_brain.retrieval.pack_manager_v2 import ScalablePackManager

            mgr = ScalablePackManager(
                self._graph,
                self._vector,
                self._config,
                query_router=self._query_router,
                embedder=self._embedder,
            )
        else:
            from engineering_brain.retrieval.pack_manager import PackManager

            mgr = PackManager(self._graph, self._vector, self._config, self._query_router)
        return mgr.create_pack(
            description,
            technologies=technologies,
            domains=domains,
            min_score=min_score,
            max_nodes=max_nodes,
        )

    def pack(
        self,
        template_id: str,
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
        **kwargs: Any,
    ) -> MaterializedPack:
        """Create a knowledge pack from a template — one-liner API.

        Args:
            template_id: Template to use (e.g. "security-review", "code-review")
            technologies: Technology filter (overrides template default)
            domains: Domain filter (overrides template default)
            **kwargs: Additional template parameter overrides

        Returns:
            MaterializedPack with full node data, ready for serve/export

        Example:
            pack = brain.pack("security-review", technologies=["flask"])
            pack.export("/tmp/flask-security/")
        """
        from engineering_brain.retrieval.pack_materializer import PackMaterializer
        from engineering_brain.retrieval.pack_templates import get_template_registry

        registry = get_template_registry(self._config)
        template = registry.get(template_id)

        materializer = PackMaterializer(
            graph=self._graph,
            vector=self._vector,
            config=self._config,
            query_router=self._query_router,
            embedder=self._embedder,
        )
        return materializer.materialize(
            template,
            technologies=technologies,
            domains=domains,
            **kwargs,
        )

    def compose(
        self,
        template_ids: list[str],
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
        **kwargs: Any,
    ) -> MaterializedPack:
        """Compose multiple template packs into one.

        Args:
            template_ids: List of template IDs to compose
            technologies: Shared technology filter
            domains: Shared domain filter

        Returns:
            Merged MaterializedPack
        """
        from engineering_brain.retrieval.pack_materializer import PackMaterializer

        materializer = PackMaterializer(
            graph=self._graph,
            vector=self._vector,
            config=self._config,
            query_router=self._query_router,
            embedder=self._embedder,
        )
        packs = [
            self.pack(tid, technologies=technologies, domains=domains, **kwargs)
            for tid in template_ids
        ]
        return materializer.compose(packs)

    def auto_generate_packs(self) -> list[Pack]:
        """Auto-generate packs from knowledge graph structure.

        Groups nodes by (technology, domain) pairs and creates packs
        with reasoning edges and quality scores. Zero input required.

        Returns:
            List of Pack objects, sorted by quality score descending
        """
        from engineering_brain.retrieval.pack_manager import PackManager

        mgr = PackManager(self._graph, self._vector, self._config, self._query_router)
        return mgr.auto_generate_packs()

    # =========================================================================
    # Write API — Ridiculously easy knowledge insertion
    # =========================================================================

    @staticmethod
    def _validate_rule(text: str, why: str, severity: str, technologies: list[str]) -> None:
        """Validate rule structure on write. Raises ValueError on invalid input."""
        if not text or not text.strip():
            raise ValueError("Rule text must be non-empty")
        if not why or not why.strip():
            raise ValueError("Rule 'why' must be non-empty — rules without reasoning are useless")
        valid_severities = {"critical", "high", "medium", "low"}
        if severity not in valid_severities:
            raise ValueError(f"Severity must be one of {valid_severities}, got '{severity}'")

    def add_axiom(self, statement: str, domain: str = "general", **kwargs: Any) -> str:
        """Add an L0 axiom (immutable truth)."""
        axiom = Axiom(
            id=kwargs.get("id", f"AX-{_short_hash(statement)}"),
            statement=statement,
            domain=domain,
            **{k: v for k, v in kwargs.items() if k != "id"},
        )
        self._graph.add_node(NodeType.AXIOM.value, axiom.id, axiom.model_dump(mode="json"))
        if self._embedder and not self._ingesting:
            try:
                from engineering_brain.core.schema import VECTOR_COLLECTIONS

                coll = VECTOR_COLLECTIONS.get("L0", "brain_axioms")
                self._embedder.embed_and_store(axiom.model_dump(mode="json"), coll)
            except Exception as exc:
                logger.debug("Axiom vector embedding failed (non-blocking): %s", exc)
        self._write_counter += 1
        return axiom.id

    def add_principle(
        self,
        name: str,
        why: str,
        how: str,
        mental_model: str = "",
        domains: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Add an L1 principle (stable wisdom).

        Args:
            name: Short memorable name
            why: WHY this matters — the deeper understanding
            how: HOW to apply — actionable steps
            mental_model: Analogy for intuitive understanding
            domains: Applicable domains
        """
        pid = kwargs.get("id", f"P-{_short_hash(name)}")
        principle = Principle(
            id=pid,
            name=name,
            why=why,
            how_to_apply=how,
            mental_model=mental_model,
            domains=domains or [],
            **{k: v for k, v in kwargs.items() if k not in ("id", "domains")},
        )
        self._graph.add_node(NodeType.PRINCIPLE.value, pid, principle.model_dump(mode="json"))
        for domain in domains or []:
            did = f"domain:{domain.lower()}"
            self._graph.add_node(NodeType.DOMAIN.value, did, {"id": did, "name": domain})
            self._graph.add_edge(pid, did, EdgeType.IN_DOMAIN.value)
        if self._embedder and not self._ingesting:
            try:
                from engineering_brain.core.schema import VECTOR_COLLECTIONS

                coll = VECTOR_COLLECTIONS.get("L1", "brain_principles")
                self._embedder.embed_and_store(principle.model_dump(mode="json"), coll)
            except Exception as exc:
                logger.debug("Principle vector embedding failed (non-blocking): %s", exc)
        self._write_counter += 1
        return pid

    def add_pattern(
        self,
        name: str,
        intent: str,
        when_to_use: str,
        when_not_to_use: str = "",
        languages: list[str] | None = None,
        example_good: str = "",
        example_bad: str = "",
        **kwargs: Any,
    ) -> str:
        """Add an L2 pattern (established practice)."""
        pid = kwargs.get("id", f"PAT-{_short_hash(name)}")
        pattern = Pattern(
            id=pid,
            name=name,
            intent=intent,
            when_to_use=when_to_use,
            when_not_to_use=when_not_to_use,
            languages=languages or [],
            example_good=example_good,
            example_bad=example_bad,
            **{k: v for k, v in kwargs.items() if k not in ("id", "languages")},
        )
        self._graph.add_node(NodeType.PATTERN.value, pid, pattern.model_dump(mode="json"))
        for lang in languages or []:
            tid = f"tech:{lang.lower()}"
            self._graph.add_node(NodeType.TECHNOLOGY.value, tid, {"id": tid, "name": lang})
            self._graph.add_edge(pid, tid, EdgeType.USED_IN.value)
        if self._embedder and not self._ingesting:
            try:
                from engineering_brain.core.schema import VECTOR_COLLECTIONS

                coll = VECTOR_COLLECTIONS.get("L2", "brain_patterns")
                self._embedder.embed_and_store(pattern.model_dump(mode="json"), coll)
            except Exception as exc:
                logger.debug("Pattern vector embedding failed (non-blocking): %s", exc)
        self._write_counter += 1
        return pid

    def add_rule(
        self,
        text: str,
        why: str = "",
        how: str = "",
        severity: str = "medium",
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
        example_good: str = "",
        example_bad: str = "",
        **kwargs: Any,
    ) -> str:
        """Add an L3 rule (learned constraint with WHY + HOW).

        Args:
            text: The rule statement
            why: WHY this rule exists — the understanding
            how: HOW to do it correctly — actionable steps
            severity: critical|high|medium|low
            technologies: Applicable technologies
            domains: Applicable domains
        """
        # Validate structure (skip for seed ingestion where why may be empty)
        if why and text:
            self._validate_rule(text, why, severity, technologies or [])
        rid = kwargs.get("id", f"CR-{_short_hash(text)}")
        # Determine shard target for this write
        shard_domain = (domains[0] if domains else "general").lower()
        shard_target = self._shard_router.route_write(shard_domain, Layer.L3_RULES)
        rule = Rule(
            id=rid,
            text=text,
            why=why,
            how_to_do_right=how,
            severity=severity,
            technologies=technologies or [],
            domains=domains or [],
            example_good=example_good,
            example_bad=example_bad,
            shard_id=shard_target.shard_key,
            **{k: v for k, v in kwargs.items() if k not in ("id", "technologies", "domains")},
        )
        self._graph.add_node(NodeType.RULE.value, rid, rule.model_dump(mode="json"))
        for tech in technologies or []:
            tid = f"tech:{tech.lower()}"
            self._graph.add_node(NodeType.TECHNOLOGY.value, tid, {"id": tid, "name": tech})
            self._graph.add_edge(rid, tid, EdgeType.APPLIES_TO.value)
        for domain in domains or []:
            did = f"domain:{domain.lower()}"
            self._graph.add_node(NodeType.DOMAIN.value, did, {"id": did, "name": domain})
            self._graph.add_edge(rid, did, EdgeType.IN_DOMAIN.value)
        # Embed for vector search (non-blocking)
        if self._embedder and not self._ingesting:
            try:
                from engineering_brain.core.schema import VECTOR_COLLECTIONS

                coll = VECTOR_COLLECTIONS.get("L3", "brain_rules")
                self._embedder.embed_and_store(rule.model_dump(mode="json"), coll)
            except Exception as exc:
                logger.debug("Rule vector embedding failed (non-blocking): %s", exc)
        self._write_counter += 1
        return rid

    # =========================================================================
    # Batch Write API
    # =========================================================================

    def batch_add_rules(self, rules_data: list[dict[str, Any]]) -> list[str]:
        """Batch add L3 rules. Increments write counter once per batch.

        Each dict should have: text, why, how, severity, technologies, domains,
        example_good, example_bad, and optionally id.
        """
        ids: list[str] = []
        nodes: list[dict[str, Any]] = []
        edge_ops: list[tuple[str, str, str]] = []  # (from_id, to_id, edge_type)

        for rd in rules_data:
            text = rd.get("text", "")
            rid = rd.get("id", f"CR-{_short_hash(text)}")
            rule = Rule(
                id=rid,
                text=text,
                why=rd.get("why", ""),
                how_to_do_right=rd.get("how", rd.get("how_to_do_right", "")),
                severity=rd.get("severity", "medium"),
                technologies=rd.get("technologies", []),
                domains=rd.get("domains", []),
                example_good=rd.get("example_good", ""),
                example_bad=rd.get("example_bad", ""),
            )
            nodes.append(rule.model_dump(mode="json"))
            ids.append(rid)
            for tech in rd.get("technologies") or []:
                tid = f"tech:{tech.lower()}"
                edge_ops.append((rid, tid, EdgeType.APPLIES_TO.value))
            for domain in rd.get("domains") or []:
                did = f"domain:{domain.lower()}"
                edge_ops.append((rid, did, EdgeType.IN_DOMAIN.value))

        if nodes:
            self._graph.batch_add_nodes(NodeType.RULE.value, nodes)
            for from_id, to_id, etype in edge_ops:
                self._graph.add_edge(from_id, to_id, etype)
            self._write_counter += 1
        return ids

    def batch_add_patterns(self, patterns_data: list[dict[str, Any]]) -> list[str]:
        """Batch add L2 patterns. Increments write counter once per batch."""
        ids: list[str] = []
        nodes: list[dict[str, Any]] = []
        edge_ops: list[tuple[str, str, str]] = []

        for pd in patterns_data:
            name = pd.get("name", "")
            pid = pd.get("id", f"PAT-{_short_hash(name)}")
            pattern = Pattern(
                id=pid,
                name=name,
                intent=pd.get("intent", ""),
                when_to_use=pd.get("when_to_use", ""),
                when_not_to_use=pd.get("when_not_to_use", ""),
                languages=pd.get("languages", []),
                example_good=pd.get("example_good", ""),
                example_bad=pd.get("example_bad", ""),
            )
            nodes.append(pattern.model_dump(mode="json"))
            ids.append(pid)
            for lang in pd.get("languages") or []:
                tid = f"tech:{lang.lower()}"
                edge_ops.append((pid, tid, EdgeType.USED_IN.value))

        if nodes:
            self._graph.batch_add_nodes(NodeType.PATTERN.value, nodes)
            for from_id, to_id, etype in edge_ops:
                self._graph.add_edge(from_id, to_id, etype)
            self._write_counter += 1
        return ids

    def batch_add_principles(self, principles_data: list[dict[str, Any]]) -> list[str]:
        """Batch add L1 principles. Increments write counter once per batch."""
        ids: list[str] = []
        nodes: list[dict[str, Any]] = []
        edge_ops: list[tuple[str, str, str]] = []

        for pd in principles_data:
            name = pd.get("name", "")
            pid = pd.get("id", f"P-{_short_hash(name)}")
            principle = Principle(
                id=pid,
                name=name,
                why=pd.get("why", ""),
                how_to_apply=pd.get("how", pd.get("how_to_apply", "")),
                mental_model=pd.get("mental_model", ""),
                domains=pd.get("domains", []),
            )
            nodes.append(principle.model_dump(mode="json"))
            ids.append(pid)
            for domain in pd.get("domains") or []:
                did = f"domain:{domain.lower()}"
                edge_ops.append((pid, did, EdgeType.IN_DOMAIN.value))

        if nodes:
            self._graph.batch_add_nodes(NodeType.PRINCIPLE.value, nodes)
            for from_id, to_id, etype in edge_ops:
                self._graph.add_edge(from_id, to_id, etype)
            self._write_counter += 1
        return ids

    # =========================================================================
    # Learning API
    # =========================================================================

    def learn_from_finding(self, description: str, **kwargs: Any) -> str | None:
        """Learn from a finding — auto-evolve the knowledge graph."""
        result = self._crystallizer.learn_from_finding(description, **kwargs)
        if result:
            self._write_counter += 1
        if self._observation_log is not None and result:
            try:
                self._observation_log.record_finding(
                    rule_ids=[result],
                    description=description,
                    severity=kwargs.get("severity", "medium"),
                )
            except Exception as exc:
                logger.debug("Finding observation recording failed (non-blocking): %s", exc)
        return result

    # =========================================================================
    # Maintenance API
    # =========================================================================

    def maintenance(
        self,
        crystallize: bool | None = None,
        promote: bool | None = None,
        prune: bool | None = None,
    ) -> dict[str, Any]:
        """Run maintenance cycle: crystallize → promote → prune.

        Respects config flags unless explicitly overridden.
        Also runs adaptive weight updates (Gap 4) and adaptive promotion
        outcome recording (Gap 7) if enabled.
        """
        cfg = self._config
        results: dict[str, Any] = {}
        if crystallize if crystallize is not None else cfg.maintenance_crystallize:
            results["crystallized"] = self.crystallize()
        if promote if promote is not None else cfg.maintenance_promote:
            results["promoted"] = self.promote()
        if prune if prune is not None else cfg.maintenance_prune:
            results["pruned"] = self.prune()

        # Gap 4: Update adaptive weights from observation log feedback
        if self._adaptive_weights:
            try:
                self._adaptive_weights._update_from_log()
                results["adaptive_weights"] = self._adaptive_weights.stats()
            except Exception as exc:
                logger.debug(
                    "Adaptive weights update failed during maintenance (non-blocking): %s", exc
                )

        # Gap 7: Record promotion outcomes for adaptive thresholds
        if self._adaptive_promotion:
            try:
                results["adaptive_promotion"] = self._adaptive_promotion.stats()
            except Exception as exc:
                logger.debug(
                    "Adaptive promotion stats failed during maintenance (non-blocking): %s", exc
                )

        return results

    def reinforce(self, rule_id: str, evidence_id: str, positive: bool = True) -> bool:
        """Reinforce or weaken a rule based on evidence."""
        return self._reinforcer.reinforce(rule_id, evidence_id, positive)

    def observe_query(
        self,
        rule_ids: list[str],
        query: str = "",
        technologies: list[str] | None = None,
        file_type: str = "",
    ) -> None:
        """Record a query_served observation (non-blocking)."""
        if self._observation_log is not None:
            try:
                self._observation_log.record_query(
                    rule_ids=rule_ids,
                    query=query,
                    technologies=technologies or [],
                    file_type=file_type,
                )
            except Exception as exc:
                logger.debug("Query observation recording failed (non-blocking): %s", exc)

    def record_prediction_outcome(self, rule_id: str, success: bool) -> bool:
        """Record whether a rule's prediction was confirmed or refuted."""
        rule = self._graph.get_node(rule_id)
        if rule is None:
            return False
        tested = int(rule.get("prediction_tested_count", 0)) + 1
        succeeded = int(rule.get("prediction_success_count", 0)) + (1 if success else 0)
        confidence = float(rule.get("confidence", 0.5))
        label = _node_type_for_id(rule_id)
        self._graph.add_node(
            label,
            rule_id,
            {
                **rule,
                "prediction_tested_count": tested,
                "prediction_success_count": succeeded,
            },
        )
        if self._observation_log is not None:
            try:
                self._observation_log.record_prediction_test(
                    rule_id=rule_id,
                    success=success,
                    confidence_at_time=confidence,
                )
            except Exception as exc:
                logger.debug("Prediction test observation recording failed (non-blocking): %s", exc)
        return True

    def calibrate(self) -> list[Any]:
        """Compute and return calibration data from observation history."""
        if self._observation_log is None:
            return []
        from engineering_brain.observation.calibrator import ConfidenceCalibrator

        calibrator = ConfidenceCalibrator(self._observation_log)
        return calibrator.compute_calibration()

    def observe_query_outcome(
        self,
        query_id: str,
        node_ids: list[str],
        helpful: bool,
        signal_name: str = "",
    ) -> int:
        """Record whether query results were helpful — closes the feedback loop.

        Wires into:
        1. observe_query() — records the serving event
        2. adaptive_weights.record_feedback() — updates Thompson Sampling
        3. observation_log — persists for offline analysis

        Args:
            query_id: Identifier for the query (can be any string).
            node_ids: Node IDs that were returned to the user.
            helpful: Whether the results were helpful.
            signal_name: Optional signal name for targeted weight learning.

        Returns:
            Number of feedback records written.
        """
        count = 0

        # 1. Record the serving event
        self.observe_query(rule_ids=node_ids, query=query_id)

        # 2. Update adaptive weights (Thompson Sampling) if enabled
        if self._adaptive_weights is not None:
            for nid in node_ids:
                node = self._graph.get_node(nid)
                if node is None:
                    continue
                try:
                    self._adaptive_weights.record_feedback(nid, helpful)
                    count += 1
                except Exception as exc:
                    logger.debug(
                        "Adaptive weight feedback recording failed for node %s (non-blocking): %s",
                        nid,
                        exc,
                    )

        # 3. Record in observation log
        if self._observation_log is not None:
            try:
                self._observation_log.record_query(
                    rule_ids=node_ids,
                    query=query_id,
                    technologies=[],
                    file_type="",
                )
                if not self._adaptive_weights:
                    count += len(node_ids)
            except Exception as exc:
                logger.debug("Query outcome observation recording failed (non-blocking): %s", exc)

        return count

    def record_promotion_outcome(
        self,
        domain: str,
        node_id: str,
        promoted: bool,
        survived: bool,
    ) -> bool:
        """Record whether a promoted node survived — feeds adaptive promotion.

        Args:
            domain: Knowledge domain (e.g. 'security', 'api').
            node_id: The promoted node's ID.
            promoted: Whether the node was promoted.
            survived: Whether the promoted node survived (stayed useful).

        Returns:
            True if recorded successfully.
        """
        if self._adaptive_promotion is None:
            return False
        try:
            self._adaptive_promotion.record_outcome(domain, promoted, survived)
            return True
        except Exception as exc:
            logger.warning("Failed to record adaptive promotion outcome: %s", exc)
            return False

    # =========================================================================
    # Graph Improvement API (Gaps 1-7)
    # =========================================================================

    def mine_code(self, path: str, min_frequency: int = 3) -> list[dict[str, Any]]:
        """Mine patterns from a codebase and propose L4 Findings.

        Parses Python files via AST, extracts recurring patterns (error handling,
        API conventions, security patterns), and proposes L4 Finding candidates.

        Args:
            path: Directory path to mine
            min_frequency: Minimum pattern frequency to become a Finding proposal

        Returns:
            List of Finding proposals with pattern_type, description, confidence
        """
        from engineering_brain.learning.code_pattern_miner import CodePatternMiner

        miner = CodePatternMiner(self._graph, self._config)
        miner.mine_directory(path, batch_size=10)
        findings = miner.propose_findings(min_frequency=min_frequency)
        logger.info(
            "Mined %d finding proposals from %s (stats: %s)",
            len(findings),
            path,
            miner.stats(),
        )
        return findings

    def predict_links(self, top_k: int = 50) -> list[dict[str, Any]]:
        """Predict missing edges in the knowledge graph.

        Uses embedding similarity + type constraints to find edges that
        should exist but don't. Requires link_prediction_enabled=True
        and seed() to have been called.

        Args:
            top_k: Maximum predictions to return

        Returns:
            List of predicted links with source_id, target_id, edge_type, confidence
        """
        if not self._link_predictor:
            logger.warning(
                "Link predictor not initialized (enable BRAIN_LINK_PREDICTION=true and call seed())"
            )
            return []
        predictions = self._link_predictor.predict_links(top_k=top_k)
        return [
            {
                "source_id": p.source_id,
                "target_id": p.target_id,
                "edge_type": p.edge_type.value,
                "confidence": round(p.confidence, 4),
                "cosine_score": round(p.cosine_score, 4),
                "hake_score": round(p.hake_score, 4),
            }
            for p in predictions
        ]

    def align_ontology(self, skos_file: str | None = None) -> dict[str, Any]:
        """Align taxonomy tags with external ontologies via SKOS mappings.

        If skos_file is provided, imports alignments from YAML/JSON.
        Otherwise, returns current alignment statistics.

        Args:
            skos_file: Optional path to SKOS alignment YAML/JSON file

        Returns:
            Alignment statistics or import results
        """
        from engineering_brain.core.taxonomy import get_registry
        from engineering_brain.retrieval.ontology_aligner import OntologyAligner

        registry = get_registry()
        aligner = OntologyAligner(registry, self._embedder)

        if skos_file:
            imported = aligner.import_skos_file(skos_file)
            return {"imported": imported, **aligner.stats()}

        return aligner.stats()

    def crystallize(self) -> list[str]:
        """Run additive cluster crystallization (without single-rule promotion)."""
        if not self._config.crystallize_enabled:
            return []
        from engineering_brain.learning.cluster_promoter import ClusterPromoter

        cp = ClusterPromoter(self._graph, self._config)
        return cp.crystallize()

    def promote(self) -> list[str]:
        """Check for and execute knowledge promotions (L4→L3→L2)."""
        return self._promoter.check_and_promote()

    def prune(self) -> dict[str, int]:
        """Remove stale and contradicted knowledge."""
        return self._pruner.prune()

    async def validate(
        self,
        node_id: str | None = None,
        force_refresh: bool = False,
        dry_run: bool = False,
        layer_filter: str = "",
        progress_callback: Any = None,
    ) -> Any:
        """Validate knowledge against external sources.

        Args:
            node_id: Validate a single node (or all if None)
            force_refresh: Ignore cache
            dry_run: Plan only, no API calls
            layer_filter: Only validate specific layer (L0, L1, L2, L3)
            progress_callback: Called with (completed, total)

        Returns:
            ValidationReport (all) or dict (single node)
        """
        from engineering_brain.validation.orchestrator import validate_all as _validate_all
        from engineering_brain.validation.orchestrator import validate_node as _validate_node

        if node_id:
            return await _validate_node(
                self,
                node_id,
                config=self._config,
                force_refresh=force_refresh,
            )
        else:
            return await _validate_all(
                self,
                config=self._config,
                force_refresh=force_refresh,
                dry_run=dry_run,
                layer_filter=layer_filter,
                progress_callback=progress_callback,
            )

    # =========================================================================
    # Ingestion API
    # =========================================================================

    def ingest(self, path: str, force: bool = False) -> int:
        """Ingest knowledge from a YAML seed file. Returns count of nodes added.

        Tracks seed file versions via content hash. If the same file has
        already been ingested at the same version, skips it (idempotent).
        Use force=True to reload regardless.
        """
        import hashlib as _hl

        try:
            with open(path) as f:
                content = f.read()
            version_hash = _hl.sha256(content.encode()).hexdigest()[:16]

            # Skip if already loaded at same version
            if not force and self._loaded_seeds.get(path) == version_hash:
                logger.debug("Skipping unchanged seed: %s", path)
                return 0

            raw = yaml.safe_load(content)
            if not raw:
                return 0
            seed = SeedFile(**raw)
            count = self._ingest_seed(seed)
            self._loaded_seeds[path] = version_hash
            return count
        except Exception as e:
            logger.error("Failed to ingest %s: %s", path, e)
            return 0

    def ingest_directory(self, directory: str) -> int:
        """Ingest all YAML files in a directory. Returns total count.

        Suspends per-node embeddings during bulk ingest for performance.
        Embeddings are done in a single batch after seed() or on-demand at query time.
        """
        total = 0
        dir_path = Path(directory)
        if not dir_path.is_dir():
            logger.warning("Not a directory: %s", directory)
            return 0
        self._ingesting = True
        try:
            for yaml_file in sorted(dir_path.glob("*.yaml")):
                # Skip non-seed files (e.g. TAXONOMY.yaml, SKOS_ALIGNMENTS.yaml)
                if yaml_file.name in ("TAXONOMY.yaml", "SKOS_ALIGNMENTS.yaml"):
                    continue
                count = self.ingest(str(yaml_file))
                total += count
                if count > 0:
                    logger.info("Ingested %d nodes from %s", count, yaml_file.name)
        finally:
            self._ingesting = False
        return total

    def seed(self, *, skip_bulk_embed: bool = False) -> int:
        """Load all built-in seed data from the seeds directory.

        Args:
            skip_bulk_embed: If True, skip the expensive embed_all_nodes() call.
                Individual query-time embeddings via embed_text() still work.
                Use this when multiple Brain instances may run in parallel
                (e.g., pipeline agents, MCP servers) to avoid CPU/RAM bombs.
        """
        seeds_dir = self._config.seeds_directory
        if not os.path.isdir(seeds_dir):
            logger.warning("Seeds directory not found: %s", seeds_dir)
            return 0
        count = self.ingest_directory(seeds_dir)
        edge_count = self._build_cross_layer_edges()
        if edge_count > 0:
            logger.info("Created %d cross-layer edges", edge_count)

        # Gap 1: Infer additional cross-layer edges via embeddings
        if self._config.cross_layer_inference_enabled and self._embedder and not skip_bulk_embed:
            try:
                from engineering_brain.learning.cross_layer_inferrer import CrossLayerEdgeInferrer

                inferrer = CrossLayerEdgeInferrer(self._graph, self._embedder, self._config)
                self._cross_layer_inferrer = inferrer
                inferred = inferrer.infer_edges(batch_size=20)
                inferred_count = 0
                for edge in inferred:
                    if not self._graph.has_edge(edge.source_id, edge.target_id):
                        self._graph.add_edge(edge.source_id, edge.target_id, edge.edge_type.value)
                        inferred_count += 1
                if inferred_count > 0:
                    logger.info(
                        "Inferred %d cross-layer edges (threshold=%.2f)",
                        inferred_count,
                        self._config.cross_layer_similarity_threshold,
                    )
            except Exception as e:
                logger.warning("Cross-layer inference failed (non-blocking): %s", e)

        # Auto-build technology detection index from all loaded nodes
        self._build_dynamic_tech_index()

        # Build faceted taxonomy DAG from TAXONOMY.yaml + node data
        self._build_tag_registry(seeds_dir, skip_embeddings=skip_bulk_embed)

        # Embed all nodes for vector search (non-blocking)
        if self._embedder and not skip_bulk_embed:
            try:
                stats = self._embedder.embed_all_nodes(self._graph)
                logger.info(
                    "Embedded %d nodes (%d skipped, %d failed)",
                    stats.get("embedded", 0),
                    stats.get("skipped", 0),
                    stats.get("failed", 0),
                )
            except Exception as e:
                logger.warning("Embedding failed (non-blocking): %s", e)
        elif skip_bulk_embed:
            logger.debug("Bulk embedding skipped (skip_bulk_embed=True)")

        # Gap 5: Initialize link predictor (needs embedder ready)
        if self._config.link_prediction_enabled and self._embedder:
            try:
                from engineering_brain.learning.link_predictor import LinkPredictor

                hake = None
                if self._config.hake_enabled:
                    try:
                        from engineering_brain.retrieval.hake_embeddings import HAKEEncoder

                        hake = HAKEEncoder(self._config)
                    except Exception as exc:
                        logger.debug(
                            "HAKEEncoder init failed, falling back to cosine-only link prediction: %s",
                            exc,
                        )
                self._link_predictor = LinkPredictor(
                    self._graph,
                    self._embedder,
                    hake=hake,
                    config=self._config,
                )
            except Exception as e:
                logger.warning("Link predictor init failed (non-blocking): %s", e)

        return count

    def _build_dynamic_tech_index(self) -> None:
        """Build dynamic tech detection index from all loaded knowledge nodes.

        This makes the context extractor auto-discover ALL technologies
        in the brain — no hardcoded keyword lists needed.
        Uses paginated iteration for memory-efficient processing at scale.
        """
        from engineering_brain.retrieval.context_extractor import build_tech_index_from_nodes

        all_nodes: list[dict[str, Any]] = []
        for page in self._graph.get_nodes_paginated(page_size=500):
            all_nodes.extend(page)
        build_tech_index_from_nodes(all_nodes)
        from engineering_brain.retrieval.context_extractor import _dynamic_tech_index

        logger.info(
            "Built dynamic tech index: %d technologies from %d nodes",
            len(_dynamic_tech_index),
            len(all_nodes),
        )

    def _build_tag_registry(self, seeds_dir: str, *, skip_embeddings: bool = False) -> None:
        """Build the faceted taxonomy DAG from TAXONOMY.yaml and loaded nodes.

        Populates the global TagRegistry singleton with tags discovered from
        both the static TAXONOMY.yaml tree and the actual node data.
        """
        from engineering_brain.core.taxonomy import set_registry
        from engineering_brain.core.taxonomy_bootstrap import bootstrap_registry

        all_nodes: list[dict[str, Any]] = []
        for page in self._graph.get_nodes_paginated(page_size=500):
            all_nodes.extend(page)

        registry = bootstrap_registry(seeds_dir, all_nodes)
        set_registry(registry)
        logger.info(
            "Built tag registry: %d tags from TAXONOMY.yaml + %d nodes",
            registry.size,
            len(all_nodes),
        )

        # Tier 1: Embed tags in Qdrant for semantic matching (non-blocking)
        if self._embedder and self._config.embedding_enabled and not skip_embeddings:
            try:
                from engineering_brain.retrieval.tag_embeddings import (
                    TagEmbeddingIndex,
                    set_tag_index,
                )

                tag_index = TagEmbeddingIndex(self._embedder, registry)
                stats = tag_index.index_all(batch_size=20)
                set_tag_index(tag_index)
                logger.info(
                    "Tag embeddings: %d indexed, %d skipped",
                    stats.get("indexed", 0),
                    stats.get("skipped", 0),
                )
            except Exception as e:
                logger.warning("Tag embedding failed (non-blocking): %s", e)

        # Tier 2: Auto-expansion pipeline (suggest polyhierarchy links)
        if self._config.auto_expand_enabled and self._embedder and self._config.embedding_enabled:
            try:
                from engineering_brain.retrieval.tag_embeddings import get_tag_index
                from engineering_brain.retrieval.taxonomy_expander import (
                    TaxonomyExpander,
                    set_expander,
                )

                tag_index = get_tag_index()
                if tag_index and tag_index.is_indexed:
                    expander = TaxonomyExpander(registry, tag_index)
                    suggestions = expander.suggest_polyhierarchy_links(
                        min_similarity=self._config.auto_expand_similarity_threshold,
                    )
                    if suggestions:
                        applied = expander.apply_suggestions(
                            suggestions,
                            min_confidence=self._config.auto_expand_min_confidence,
                        )
                        logger.info(
                            "Auto-expanded %d polyhierarchy links from %d suggestions",
                            applied,
                            len(suggestions),
                        )
                    set_expander(expander)
            except Exception as e:
                logger.warning("Taxonomy auto-expansion failed (non-blocking): %s", e)

        # Tier 3: Relationship learning from co-occurrence
        if self._config.relationship_learning_enabled:
            try:
                from engineering_brain.learning.relationship_learner import RelationshipLearner

                learner = RelationshipLearner(registry)
                learner.observe_batch(all_nodes, batch_size=50)
                suggestions = learner.suggest_relationships(min_cooccurrence=3)
                learner.update_weights()
                if suggestions:
                    logger.info(
                        "Relationship learner: %d suggestions from %d nodes",
                        len(suggestions),
                        learner.stats["nodes_observed"],
                    )
            except Exception as e:
                logger.warning("Relationship learning failed (non-blocking): %s", e)

    def _build_cross_layer_edges(self) -> int:
        """Build cross-layer edges between axioms, principles, patterns, and rules.

        Creates the knowledge hierarchy that makes the brain a GRAPH, not just a list:
        - GROUNDS: Axiom → Principle (theoretical foundation)
        - INFORMS: Principle → Pattern (guides design)
        - INSTANTIATES: Pattern → Rule (concrete implementation)
        """
        count = 0
        add = self._graph.add_edge

        # =====================================================================
        # GROUNDS edges: Axiom → Principle
        # "This axiom is the theoretical foundation for this principle"
        # =====================================================================
        grounds_map: list[tuple[str, str]] = [
            # Type Theory axioms → principles
            ("AX-TYPE-001", "P-API-CONTRACT"),  # type sig is contract → API as contract
            ("AX-TYPE-002", "P-ERR-FAIL-FAST"),  # null handling → fail fast
            ("AX-TYPE-003", "P-SEC-BOUNDARY"),  # type narrowing → validate at boundary
            # State axioms → principles
            ("AX-STATE-001", "P-CONC-ATOMIC"),  # shared mutable state → atomic updates
            ("AX-STATE-002", "P-CONC-ATOMIC"),  # atomic transitions → atomic updates
            ("AX-STATE-003", "P-CFG-CONSERVATIVE"),  # defaults ARE policy → conservative defaults
            # Security axioms → principles
            ("AX-SEC-001", "P-SEC-BOUNDARY"),  # enforce at boundary → validate at boundary
            ("AX-SEC-002", "P-SEC-DENY"),  # authn→authz→process → deny-by-default
            ("AX-SEC-003", "P-SEC-LEAST-PRIV"),  # least privilege → principle of least privilege
            ("AX-SEC-004", "P-SEC-DENY"),  # deny-by-default axiom → deny principle
            ("AX-SEC-004", "P-CFG-CONSERVATIVE"),  # deny-by-default → conservative defaults
            # Correctness axioms → principles
            ("AX-CORRECT-001", "P-TEST-PYRAMID"),  # untested=broken → testing pyramid
            ("AX-CORRECT-001", "P-TEST-DETERMINISTIC"),  # untested=broken → deterministic tests
            ("AX-CORRECT-002", "P-ERR-FAIL-FAST"),  # handle errors → fail fast
            ("AX-CORRECT-002", "P-ERR-ACTIONABLE"),  # handle errors → actionable errors
            ("AX-CORRECT-003", "P-ARCH-EXPLICIT"),  # side effects → explicit over implicit
            # Architecture axioms → principles
            ("AX-ARCH-001", "P-ARCH-SINGLE-RESP"),  # minimize coupling → single responsibility
            ("AX-ARCH-001", "P-ARCH-SEPARATION"),  # minimize coupling → separation of concerns
            ("AX-ARCH-002", "P-ARCH-DRY"),  # single source of truth → DRY
            ("AX-ARCH-003", "P-ARCH-SINGLE-RESP"),  # eliminate accidental complexity → SRP
            # Communication axioms → principles
            ("AX-COMM-001", "P-API-CONTRACT"),  # interfaces are contracts → API as contract
            ("AX-COMM-002", "P-API-IDEMPOTENT"),  # network fails → idempotent operations
            # Data axioms → principles
            ("AX-DATA-001", "P-API-CONTRACT"),  # data outlives code → API contract
            ("AX-DATA-002", "P-SEC-BOUNDARY"),  # validate at boundary → boundary validation
            # Performance → principles
            ("AX-PERF-001", "P-PERF-MEASURE"),  # measure before optimizing
            # DRY → principles
            ("AX-DRY-001", "P-ARCH-DRY"),  # single representation → DRY
            # Observability → principles
            ("AX-OBS-001", "P-OBS-STRUCTURED"),  # can't improve unmeasured → structured logging
            ("AX-OBS-001", "P-PERF-MEASURE"),  # can't improve unmeasured → measure first
            # Idempotency → principles
            ("AX-IDEMP-001", "P-API-IDEMPOTENT"),  # idempotent ops → idempotent operations
            # === Extended axioms (axioms_extended.yaml) → principles ===
            # Database axioms → principles
            ("AX-DB-001", "P-DB-NORMALIZE"),  # read/write scaling → normalize strategy
            ("AX-DB-001", "P-SCALE-CQRS"),  # read/write scaling → CQRS
            ("AX-DB-002", "P-DB-INDEX"),  # index tradeoff → index strategy
            # Testing axioms → principles
            ("AX-TEST-001", "P-TEST-PYRAMID"),  # falsifiable tests → testing pyramid
            ("AX-TEST-002", "P-TEST-PYRAMID"),  # bug cost distance → test early
            ("AX-TEST-002", "P-ERR-FAIL-FAST"),  # bug cost distance → fail fast
            # Distributed systems axioms → principles
            ("AX-DIST-001", "P-MSG-IDEMPOTENT"),  # exactly-once impossible → idempotent handlers
            ("AX-DIST-001", "P-API-IDEMPOTENT"),  # exactly-once impossible → idempotent ops
            ("AX-DIST-002", "P-DIST-EVENTUAL-CONSIST"),  # CAP theorem → eventual consistency
            ("AX-DIST-003", "P-DIST-SAGA"),  # clock sync → logical ordering via sagas
            # Reliability axioms → principles
            ("AX-REL-001", "P-REL-GRACEFUL-DEGRADE"),  # everything fails → graceful degradation
            ("AX-REL-001", "P-REL-REDUNDANCY"),  # everything fails → redundancy
            ("AX-REL-002", "P-REL-REDUNDANCY"),  # redundancy tradeoff → redundancy principle
            # Scalability axioms → principles
            ("AX-SCALE-001", "P-SCALE-HORIZONTAL"),  # vertical ceiling → horizontal scaling
            # Concurrency axioms → principles
            ("AX-CONC-001", "P-CONC-ATOMIC"),  # deadlock prevention → atomic updates
            ("AX-CONC-002", "P-CONC-ATOMIC"),  # lock-free tradeoff → atomic alternatives
            # UX axioms → principles
            ("AX-UX-001", "P-UX-FEEDBACK"),  # mental models → immediate feedback
            ("AX-UX-002", "P-UX-FEEDBACK"),  # cognitive load → immediate feedback
            # Cost axioms → principles
            ("AX-COST-001", "P-AI-COST"),  # resource cost → AI cost control
            ("AX-COST-001", "P-PERF-MEASURE"),  # resource cost → measure before optimize
            # Learning axioms → principles
            ("AX-LEARN-001", "P-OBS-STRUCTURED"),  # feedback loops → structured observability
            ("AX-LEARN-001", "P-ML-MONITORING"),  # feedback loops → model monitoring
            ("AX-LEARN-002", "P-REL-CHAOS"),  # failure is knowledge → chaos engineering
            # Abstraction axioms → principles
            ("AX-ABSTR-001", "P-ARCH-SEPARATION"),  # leaky abstractions → separation of concerns
            ("AX-ABSTR-002", "P-ARCH-EXPLICIT"),  # right abstraction level → explicit design
            # Feedback axioms → principles
            ("AX-FEEDBACK-001", "P-OBS-STRUCTURED"),  # feedback loops → structured observability
            ("AX-FEEDBACK-001", "P-ML-MONITORING"),  # feedback loops → model monitoring
            # Data axioms → new data principles
            ("AX-DATA-001", "P-DB-MIGRATION"),  # data outlives code → safe migrations
            ("AX-DATA-001", "P-DATA-SCHEMA-EVOLUTION"),  # data outlives code → schema evolution
        ]

        for axiom_id, principle_id in grounds_map:
            if self._graph.get_node(axiom_id) and self._graph.get_node(principle_id):
                add(axiom_id, principle_id, EdgeType.GROUNDS.value)
                count += 1

        # =====================================================================
        # INFORMS edges: Principle → Pattern
        # "This principle guides the design of this pattern"
        # NOTE: Some are already created via related_principles in patterns.yaml
        # These are additional connections not covered by related_principles
        # =====================================================================
        informs_map: list[tuple[str, str]] = [
            # Security principles → patterns
            ("P-SEC-DENY", "PAT-SEC-AUTH-DECO"),  # deny-by-default → auth decorator
            ("P-SEC-DENY", "PAT-CFG-ENV"),  # deny-by-default → env config (safe defaults)
            ("P-SEC-BOUNDARY", "PAT-SEC-INPUT-VALID"),  # boundary validation → input validation
            ("P-SEC-LEAST-PRIV", "PAT-SEC-AUTH-DECO"),  # least privilege → auth decorator
            # Error handling principles → patterns
            ("P-ERR-ACTIONABLE", "PAT-ERR-RESULT"),  # actionable errors → result type
            (
                "P-ERR-FAIL-FAST",
                "PAT-ERR-GRACEFUL",
            ),  # fail fast → graceful degradation (complement)
            # Architecture principles → patterns
            ("P-ARCH-SINGLE-RESP", "PAT-ARCH-REPOSITORY"),  # SRP → repository pattern
            ("P-ARCH-SEPARATION", "PAT-ARCH-FACTORY"),  # separation → factory pattern
            ("P-ARCH-DRY", "PAT-TEST-FIXTURE"),  # DRY → fixture composition
            ("P-ARCH-EXPLICIT", "PAT-ARCH-FACTORY"),  # explicit → factory (explicit construction)
            ("P-ARCH-EXPLICIT", "PAT-CFG-ENV"),  # explicit → env config
            # State principles → patterns
            ("P-CONC-ATOMIC", "PAT-STATE-ATOMIC"),  # atomic updates → atomic state pattern
            # API principles → patterns
            ("P-API-CONTRACT", "PAT-API-PAGINATION"),  # contract → pagination pattern
            ("P-API-IDEMPOTENT", "PAT-API-PAGINATION"),  # idempotent → cursor pagination
            # Observability → patterns
            ("P-OBS-STRUCTURED", "PAT-OBS-CONTEXT"),  # structured logging → request context
            # Testing → patterns
            ("P-TEST-PYRAMID", "PAT-TEST-FIXTURE"),  # pyramid → fixture composition
            ("P-TEST-DETERMINISTIC", "PAT-TEST-FIXTURE"),  # deterministic → fixture composition
            # UX → patterns
            ("P-UX-FEEDBACK", "PAT-STATE-ATOMIC"),  # immediate feedback → atomic UI updates
            # Config → patterns
            ("P-CFG-CONSERVATIVE", "PAT-CFG-ENV"),  # conservative defaults → env config
            # Reliability → patterns
            ("P-REL-CHAOS", "PAT-DIST-CIRCUIT-BREAKER"),  # chaos engineering → circuit breaker
            ("P-REL-CHAOS", "PAT-DIST-BULKHEAD"),  # chaos engineering → bulkhead isolation
        ]

        for principle_id, pattern_id in informs_map:
            if self._graph.get_node(principle_id) and self._graph.get_node(pattern_id):
                add(principle_id, pattern_id, EdgeType.INFORMS.value)
                count += 1

        # =====================================================================
        # INSTANTIATES edges: Pattern → Rule
        # "This pattern is concretely instantiated by this rule"
        # =====================================================================
        instantiates_map: list[tuple[str, str]] = [
            # Auth pattern → security rules
            ("PAT-SEC-AUTH-DECO", "CR-SEC-AUTH-001"),
            ("PAT-SEC-AUTH-DECO", "CR-SEC-AUTH-002"),
            # Input validation → validation rules
            ("PAT-SEC-INPUT-VALID", "CR-SEC-PATH-001"),  # Path traversal
            # CORS pattern (deny-by-default) → CORS rules
            ("PAT-CFG-ENV", "CR-SEC-CORS-001"),  # env config → CORS config from env
            # Error handling patterns → rules
            ("PAT-ERR-RESULT", "CR-ERR-STRUCT-001"),  # result type → structured errors
            ("PAT-ERR-RESULT", "CR-ERR-STRUCT-002"),  # result type → exception hierarchy
            ("PAT-ERR-GRACEFUL", "CR-ERR-DEGRADE-001"),  # graceful degradation → fallback values
            ("PAT-ERR-GRACEFUL", "CR-ERR-DEGRADE-002"),  # graceful degradation → health checks
            # Factory pattern → Flask rules
            ("PAT-ARCH-FACTORY", "CR-FLASK-001"),  # factory → Flask app factory
            # Repository pattern → architecture rules
            ("PAT-ARCH-REPOSITORY", "CR-FLASK-003"),  # repository → Flask JSON responses
            # Atomic state pattern → JS/CSS rules
            ("PAT-STATE-ATOMIC", "CR-JS-STATE-001"),  # atomic updates → JS state management
            ("PAT-STATE-ATOMIC", "CR-JS-STATE-002"),  # atomic updates → JS state consistency
            ("PAT-STATE-ATOMIC", "CR-CSS-STATE-001"),  # atomic updates → CSS state classes
            # Config pattern → Docker/DevOps rules
            ("PAT-CFG-ENV", "CR-COMPOSE-003"),  # env config → compose secrets
            ("PAT-CFG-ENV", "CR-ERR-TIMEOUT-002"),  # env config → configurable timeouts
            # Test fixture pattern → testing rules
            ("PAT-TEST-FIXTURE", "CR-TEST-001"),  # fixture → AAA pattern
            ("PAT-TEST-FIXTURE", "CR-TEST-003"),  # fixture → fixture usage
            # Pagination pattern → API rules
            ("PAT-API-PAGINATION", "CR-FLASK-002"),  # pagination → HTTP status codes
            # Observability pattern → logging rules
            ("PAT-OBS-CONTEXT", "CR-ERR-LOG-001"),  # request context → contextual logging
            ("PAT-OBS-CONTEXT", "CR-ERR-LOG-002"),  # request context → log levels
            # === Extended patterns → existing rules ===
            # Database patterns → database rules
            ("PAT-DB-CQRS", "CR-SYS-REPLICA-001"),  # CQRS → read replicas
            ("PAT-DB-CQRS", "CR-SYS-HSCALE-001"),  # CQRS → horizontal scaling
            ("PAT-DB-CDC-OUTBOX", "CR-DIST-OUTBOX-001"),  # CDC outbox → outbox rule
            ("PAT-DB-CDC-OUTBOX", "CR-KAFKA-001"),  # CDC outbox → Kafka durable writes
            ("PAT-DB-MIGRATION-SAFE", "CR-PG-IDX-001"),  # safe migration → index management
            ("PAT-DB-REPO", "CR-PG-CON-001"),  # repository → connection management
            ("PAT-DB-EVENT-SOURCING", "CR-KAFKA-004"),  # event sourcing → commit after processing
            # Caching patterns → caching/Redis rules
            ("PAT-CACHE-ASIDE", "CR-SYS-CACHE-001"),  # cache-aside → cache-aside rule
            ("PAT-CACHE-ASIDE", "CR-RED-DS-001"),  # cache-aside → Redis data structures
            (
                "PAT-CACHE-STAMPEDE-GUARD",
                "CR-SYS-STAMPEDE-001",
            ),  # stampede → thundering herd prevention
            # Distributed patterns → distributed/resilience rules
            (
                "PAT-DIST-CIRCUIT-BREAKER",
                "CR-DIST-CIRCUIT-001",
            ),  # circuit breaker → circuit breaker rule
            (
                "PAT-DIST-CIRCUIT-BREAKER",
                "CR-SRE-CASCADE-001",
            ),  # circuit breaker → cascade prevention
            ("PAT-DIST-SAGA", "CR-DIST-SAGA-001"),  # saga → saga rule
            ("PAT-DIST-SAGA", "CR-ARCH-SAG-001"),  # saga → saga architecture
            ("PAT-DIST-BULKHEAD", "CR-DIST-BULKHEAD-001"),  # bulkhead → bulkhead rule
            ("PAT-DIST-RETRY-BACKOFF", "CR-SRE-ERR-001"),  # retry backoff → retry with backoff
            ("PAT-DIST-SIDECAR", "CR-K8S-CORE-005"),  # sidecar → K8s sidecar pattern
            ("PAT-DIST-DLQ", "CR-SYS-DLQ-001"),  # DLQ → dead letter queue
            ("PAT-DIST-DLQ", "CR-KAFKA-002"),  # DLQ → idempotent producer
            ("PAT-DIST-EVENT-DRIVEN", "CR-KAFKA-007"),  # event-driven → partition key selection
            ("PAT-DIST-LEADER-ELECTION", "CR-DIST-RAFT-001"),  # leader election → Raft consensus
            # AI/LLM patterns → AI/LLM rules
            ("PAT-LLM-RAG", "CR-RAG-CHUNK-001"),  # RAG → semantic chunking
            ("PAT-LLM-RAG", "CR-RAG-HYBRID-001"),  # RAG → hybrid search
            ("PAT-LLM-RAG", "CR-RAG-RERANK-001"),  # RAG → reranking
            ("PAT-LLM-CHAIN-OF-THOUGHT", "CR-LLM-COT-001"),  # CoT → chain-of-thought rule
            ("PAT-LLM-TOOL-USE", "CR-LLM-REACT-001"),  # tool use → ReAct pattern
            ("PAT-LLM-TOOL-USE", "CR-LLM-STRUCTURED-001"),  # tool use → structured output
            ("PAT-LLM-GUARDRAIL", "CR-AISAFE-INJECT-001"),  # guardrail → prompt injection defense
            ("PAT-LLM-GUARDRAIL", "CR-AISAFE-OUTPUT-001"),  # guardrail → output filtering
            ("PAT-LLM-GUARDRAIL", "CR-AISAFE-PII-001"),  # guardrail → PII masking
            ("PAT-LLM-EVAL-HARNESS", "CR-LLM-SYSPROMPT-001"),  # eval harness → system prompt arch
            ("PAT-LLM-SEMANTIC-CACHE", "CR-RED-DS-001"),  # semantic cache → Redis structures
            ("PAT-AI-FALLBACK-CHAIN", "CR-DIST-CIRCUIT-001"),  # fallback chain → circuit breaker
            ("PAT-AI-HUMAN-IN-LOOP", "CR-AISAFE-AUDIT-001"),  # human-in-loop → audit logging
            ("PAT-AI-AB-TEST", "CR-AISAFE-BIAS-001"),  # A/B test → bias detection
        ]

        for pattern_id, rule_id in instantiates_map:
            if self._graph.get_node(pattern_id) and self._graph.get_node(rule_id):
                add(pattern_id, rule_id, EdgeType.INSTANTIATES.value)
                count += 1

        # Auto-create INFORMS edges from related_principles stored in L2 nodes.
        # This runs post-ingestion so all P-* nodes are guaranteed to exist
        # (fixes alphabetical load-order: patterns*.yaml < principles*.yaml).
        pattern_nodes = self._graph.query(label=NodeType.PATTERN.value, limit=5000)
        for data in pattern_nodes:
            nid = data.get("id", "")
            if not nid.startswith("PAT-"):
                continue
            related = data.get("related_principles") or []
            if isinstance(related, str):
                related = [related]
            for pr in related:
                if self._graph.get_node(pr):
                    add(pr, nid, EdgeType.INFORMS.value)
                    count += 1

        return count

    def _ingest_seed(self, seed: SeedFile) -> int:
        """Process a parsed seed file and add nodes to the graph."""
        count = 0
        layer = _normalize_layer(seed.layer)

        for entry in seed.knowledge:
            # Convert SeedEntry sources (list[dict]) to Source objects for model constructors
            _sources = _coerce_seed_sources(entry.sources)

            if layer == "L0":
                self.add_axiom(
                    statement=entry.statement or entry.text,
                    domain=seed.domain,
                    id=entry.id,
                    formal_notation=entry.formal_notation,
                    sources=_sources,
                )
            elif layer == "L1":
                self.add_principle(
                    name=entry.name or entry.text,
                    why=entry.why,
                    how=entry.how_to_apply or entry.how_to_do_right,
                    mental_model=entry.mental_model,
                    domains=entry.domains or ([seed.domain] if seed.domain else []),
                    id=entry.id,
                    violation_consequence=entry.violation_consequence,
                    teaching_example=entry.teaching_example,
                    when_applies=entry.when_applies,
                    when_not_applies=entry.when_not_applies,
                    sources=_sources,
                )
            elif layer == "L2":
                self.add_pattern(
                    name=entry.name or entry.text,
                    intent=entry.intent or entry.why,
                    when_to_use=entry.when_to_use,
                    when_not_to_use=entry.when_not_to_use,
                    languages=entry.languages or ([seed.technology] if seed.technology else []),
                    example_good=entry.example_good,
                    example_bad=entry.example_bad,
                    id=entry.id,
                    category=entry.category,
                    related_principles=entry.related_principles,
                    sources=_sources,
                )
            elif layer == "L3":
                extra: dict[str, Any] = {}
                if entry.prediction_if:
                    extra["prediction_if"] = entry.prediction_if
                if entry.prediction_then:
                    extra["prediction_then"] = entry.prediction_then
                if entry.when_applies:
                    extra["when_applies"] = entry.when_applies
                if entry.when_not_applies:
                    extra["when_not_applies"] = entry.when_not_applies
                self.add_rule(
                    text=entry.text or entry.name,
                    why=entry.why,
                    how=entry.how_to_do_right or entry.how_to_apply,
                    severity=entry.severity,
                    technologies=entry.technologies
                    or ([seed.technology] if seed.technology else []),
                    domains=entry.domains or ([seed.domain] if seed.domain else []),
                    example_good=entry.example_good,
                    example_bad=entry.example_bad,
                    id=entry.id,
                    sources=_sources,
                    **extra,
                )
            elif layer == "L4":
                # L4 evidence/findings — ingest as Finding nodes directly
                nid = entry.id or f"F-seed-{count}"
                props: dict[str, Any] = {
                    "id": nid,
                    "text": entry.text or entry.name,
                    "description": entry.text or entry.name,
                    "severity": entry.severity or "medium",
                    "technologies": entry.technologies
                    or ([seed.technology] if seed.technology else []),
                    "domains": entry.domains or ([seed.domain] if seed.domain else []),
                    "created_at": time.time(),
                }
                if entry.why:
                    props["why"] = entry.why
                self._graph.add_node(NodeType.FINDING.value, nid, props)
            else:
                logger.warning("Unsupported layer %s in seed entry %s", layer, entry.id)
                continue
            count += 1

        return count

    # =========================================================================
    # Epistemic API
    # =========================================================================

    def bootstrap_epistemic(self, cache_path: str | None = None) -> dict[str, int]:
        """Bootstrap epistemic opinions for all nodes using validation cache sources.

        Reads the validation cache (4,110+ real sources), computes
        OpinionTuples via CBF fusion of layer priors + sources, and
        writes ep_b/ep_d/ep_u/ep_a to each node.

        Returns:
            Stats: {bootstrapped, skipped, total_sources_used}
        """
        from engineering_brain.epistemic.bootstrap import bootstrap_all_nodes

        path = cache_path or self._config.validation_cache_dir
        return bootstrap_all_nodes(self._graph, path)

    def detect_contradictions(self) -> list[dict[str, Any]]:
        """Run contradiction detection across entire graph.

        Scans CONFLICTS_WITH edges and computes Dempster conflict K
        for each pair. Returns list of ContradictionReport dicts.
        """
        from engineering_brain.epistemic.contradiction import ContradictionDetector

        detector = ContradictionDetector(self._graph)
        reports = detector.detect_all()
        return [
            {
                "node_a_id": r.node_a_id,
                "node_b_id": r.node_b_id,
                "conflict_k": r.conflict_k,
                "severity": r.severity.value if hasattr(r.severity, "value") else str(r.severity),
                "resolution_method": r.resolution_method,
            }
            for r in reports
        ]

    def propagate_trust(self) -> dict[str, float]:
        """Run EigenTrust and store scores on nodes.

        Returns dict of {node_id: trust_score}.
        """
        from engineering_brain.epistemic.trust_propagation import EigenTrustEngine

        engine = EigenTrustEngine()
        scores = engine.compute(self._graph)

        # Store trust scores on nodes
        for node_id, score in scores.items():
            node = self._graph.get_node(node_id)
            if node is not None:
                label = _node_type_for_id(node_id)
                self._graph.add_node(
                    label,
                    node_id,
                    {**node, "eigentrust_score": score},
                )

        logger.info("EigenTrust propagated: %d nodes scored", len(scores))
        return scores

    def analyze_gaps(self) -> list[dict[str, Any]]:
        """Run gap analysis and return prioritized gaps."""
        from engineering_brain.epistemic.gap_analysis import GapAnalyzer

        analyzer = GapAnalyzer(self._graph)
        gaps = analyzer.analyze()
        return [
            {
                "gap_type": g.gap_type,
                "node_id": g.node_id,
                "description": g.description,
                "severity": g.severity,
                "suggested_action": g.suggested_action,
            }
            for g in gaps
        ]

    def apply_temporal_decay(self, now_unix: int | None = None) -> dict[str, int]:
        """Apply Hawkes decay to all nodes with epistemic opinions.

        Returns {decayed: N, unchanged: M}.
        """
        from datetime import datetime

        from engineering_brain.epistemic.opinion import OpinionTuple
        from engineering_brain.epistemic.temporal import get_decay_engine

        now = now_unix or int(datetime.now(UTC).timestamp())
        decayed = 0
        unchanged = 0

        for page in self._graph.get_nodes_paginated(page_size=500):
            for node in page:
                ep_b = node.get("ep_b")
                if ep_b is None:
                    unchanged += 1
                    continue

                node_id = node.get("id", "")
                layer = _node_layer_from_id(node_id)
                engine = get_decay_engine(layer)

                last_decay = int(node.get("last_decay_at", 0))
                events = node.get("event_timestamps", [])
                opinion = OpinionTuple(
                    b=float(ep_b),
                    d=float(node.get("ep_d", 0.0)),
                    u=float(node.get("ep_u", 0.5)),
                    a=float(node.get("ep_a", 0.5)),
                )

                result = engine.apply_decay(opinion, now, last_decay, events)

                if abs(result.b - opinion.b) > 1e-9 or abs(result.d - opinion.d) > 1e-9:
                    label = _node_type_for_id(node_id)
                    self._graph.add_node(
                        label,
                        node_id,
                        {
                            **node,
                            "ep_b": result.b,
                            "ep_d": result.d,
                            "ep_u": result.u,
                            "ep_a": result.a,
                            "confidence": result.projected_probability,
                            "last_decay_at": now,
                        },
                    )
                    decayed += 1
                else:
                    unchanged += 1

        logger.info("Temporal decay: %d decayed, %d unchanged", decayed, unchanged)
        return {"decayed": decayed, "unchanged": unchanged}

    def get_provenance(self, node_id: str) -> list[dict[str, Any]]:
        """Get provenance chain for a node."""
        node = self._graph.get_node(node_id)
        if node is None:
            return []
        chain_data = node.get("provenance", [])
        if isinstance(chain_data, list):
            return chain_data
        return []

    def get_learned_trust(self) -> dict[str, float]:
        """Get current learned trust per source type."""
        from engineering_brain.epistemic.learned_trust import LearnedSourceTrust

        # Check if we have persisted learned trust data
        # For now, return the static defaults (learned trust is stored per-session)
        learner = LearnedSourceTrust()
        return {st: learner.get_trust(st) for st in learner._priors}

    def epistemic_status(self, node_id: str) -> dict[str, Any] | None:
        """Get epistemic status for a single node.

        Returns dict with ep_b, ep_d, ep_u, ep_a, projected_probability,
        evidence_strength, sources_count, validation_status — or None if
        the node doesn't exist.
        """
        node = self._graph.get_node(node_id)
        if node is None:
            return None

        ep_b = node.get("ep_b")
        if ep_b is None:
            return {
                "node_id": node_id,
                "epistemic": False,
                "confidence": float(node.get("confidence", 0.5)),
                "validation_status": str(node.get("validation_status", "unvalidated")),
            }

        ep_b_f = float(ep_b)
        ep_d_f = float(node.get("ep_d", 0.0))
        ep_u_f = float(node.get("ep_u", 0.5))
        ep_a_f = float(node.get("ep_a", 0.5))

        return {
            "node_id": node_id,
            "epistemic": True,
            "ep_b": ep_b_f,
            "ep_d": ep_d_f,
            "ep_u": ep_u_f,
            "ep_a": ep_a_f,
            "projected_probability": ep_b_f + ep_a_f * ep_u_f,
            "evidence_strength": 1.0 - ep_u_f,
            "confidence": float(node.get("confidence", 0.5)),
            "validation_status": str(node.get("validation_status", "unvalidated")),
        }

    def query_with_provenance(
        self,
        task_description: str,
        technologies: list[str] | None = None,
        file_type: str = "",
        phase: str = "exec",
        domains: list[str] | None = None,
        budget_chars: int | None = None,
    ) -> tuple[KnowledgeResult, list[dict[str, Any]]]:
        """Query with provenance chains attached to each result node.

        Like query(), but each node in the scored_nodes list has a '_provenance'
        key containing its source chain (evidence → rule → pattern → principle).
        """
        request = KnowledgeQuery(
            task_description=task_description,
            technologies=technologies or [],
            file_type=file_type,
            phase=phase,
            domains=domains or [],
            budget_chars=budget_chars,
        )
        return self._query_router.query_with_provenance(request)

    def detect_communities(self, min_size: int = 3) -> list[dict[str, Any]]:
        """Detect knowledge communities in the graph.

        Uses Leiden (if available) → label propagation → connected components.
        Returns list of community dicts with summary, dominant domain/tech.
        """
        from engineering_brain.retrieval.communities import CommunityDetector

        detector = CommunityDetector(self._graph)
        communities = detector.detect(min_community_size=min_size)
        return [c.to_dict() for c in communities]

    # =========================================================================
    # Agent API (deep LLM reasoning over brain knowledge)
    # =========================================================================

    def agent(
        self,
        question: str,
        intent: str = "analysis",
        domain_hints: list[str] | None = None,
        technology_hints: list[str] | None = None,
        context: str = "",
        constraints: list[str] | None = None,
        max_depth: int = 2,
    ) -> Any:
        """Deep LLM reasoning over brain knowledge.

        Requires BRAIN_AGENT_ENABLED=true and BRAIN_AGENT_API_KEY set.
        For simple queries, uses fast path (zero LLM). For complex queries,
        decomposes into sub-questions, dispatches domain workers, synthesizes.

        Args:
            question: The question to reason about
            intent: Query intent (decision, analysis, investigation, explanation, synthesis)
            domain_hints: Domain hints (e.g. ['security', 'performance'])
            technology_hints: Technology hints (e.g. ['flask', 'kafka'])
            context: Additional context
            constraints: Answer constraints
            max_depth: Reasoning depth (1-5)

        Returns:
            ComposedKnowledge with claims, evidence, confidence, gaps
        """
        from engineering_brain.agent import run_agent
        from engineering_brain.agent.types import AgentQuery, QueryIntent

        try:
            query_intent = QueryIntent(intent)
        except ValueError:
            query_intent = QueryIntent.ANALYSIS

        query = AgentQuery(
            question=question,
            intent=query_intent,
            domain_hints=domain_hints or [],
            technology_hints=technology_hints or [],
            context=context,
            constraints=constraints or [],
            max_depth=max_depth,
        )
        return run_agent(self, query)

    def agent_status(self) -> dict[str, Any]:
        """Check agent system availability."""
        from engineering_brain.agent import agent_status

        return agent_status(self)

    # =========================================================================
    # Stats API
    # =========================================================================

    def stats(self) -> dict[str, Any]:
        """Get brain statistics."""
        graph_stats = self._graph.stats()
        cache_stats = self._cache.stats() if self._cache else {}

        # Count per layer
        layer_counts = {}
        for node_type in (
            NodeType.AXIOM,
            NodeType.PRINCIPLE,
            NodeType.PATTERN,
            NodeType.RULE,
            NodeType.FINDING,
        ):
            layer_counts[node_type.value] = self._graph.count(node_type.value)

        return {
            "layers": layer_counts,
            "total": sum(layer_counts.values()),
            "graph": graph_stats,
            "cache": cache_stats,
            "config": {
                "adapter": self._config.adapter,
                "sharding": self._config.sharding_enabled,
                "budget_chars": self._config.context_budget_chars,
            },
        }

    def is_healthy(self) -> bool:
        """Check if the brain's storage backends are reachable."""
        return self._graph.is_available()

    # =========================================================================
    # Persistence (O-04)
    # =========================================================================

    def save(self, path: str | Path) -> dict[str, Any]:
        """Save brain state to JSON file for persistence across runs.

        Serializes all nodes and edges from the graph adapter.
        Returns: {nodes: N, edges: M, version: V, path: str}
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        nodes: list[dict[str, Any]] = []
        for page in self._graph.get_nodes_paginated(page_size=500):
            nodes.extend(page)

        edges: list[dict[str, Any]] = []
        try:
            edges = self._graph.get_edges()
        except Exception as exc:
            logger.debug("Edge export failed, snapshot will have empty edges: %s", exc)

        data = {
            "version": self._write_counter,
            "loaded_seeds": self._loaded_seeds,
            "nodes": nodes,
            "edges": edges,
        }

        with open(path, "w") as f:
            json.dump(data, f, default=str)

        logger.info("Brain saved: %d nodes, %d edges → %s", len(nodes), len(edges), path)
        return {
            "nodes": len(nodes),
            "edges": len(edges),
            "version": self._write_counter,
            "path": str(path),
        }

    @classmethod
    def load(cls, path: str | Path, config: BrainConfig | None = None) -> Brain:
        """Load brain state from a previously saved JSON file.

        Creates a new Brain instance (memory adapter) and populates it
        with the serialized nodes and edges.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Brain save file not found: {path}")

        with open(path) as f:
            data = json.load(f)

        brain = cls(adapter="memory", config=config)
        brain._write_counter = data.get("version", 0)
        brain._loaded_seeds = data.get("loaded_seeds", {})

        # Restore nodes
        for node in data.get("nodes", []):
            node_id = node.get("id", "")
            if not node_id:
                continue
            label = _node_type_for_id(node_id)
            brain._graph.add_node(label, node_id, node)

        # Restore edges
        for edge in data.get("edges", []):
            from_id = edge.get("from_id", "")
            to_id = edge.get("to_id", "")
            edge_type = edge.get("edge_type", edge.get("type", EdgeType.REINFORCES.value))
            if from_id and to_id:
                brain._graph.add_edge(from_id, to_id, edge_type)

        logger.info(
            "Brain loaded: %d nodes, %d edges from %s",
            len(data.get("nodes", [])),
            len(data.get("edges", [])),
            path,
        )
        return brain

    # =========================================================================
    # Auto-Maintenance Scheduling (O-08)
    # =========================================================================

    def maybe_maintenance(self) -> dict[str, Any] | None:
        """Run maintenance if write threshold or time threshold is exceeded.

        Returns maintenance results if run, None if skipped.
        Thresholds: >50 writes since last maintenance OR >1 hour elapsed.
        """
        now = time.time()
        writes_since = self._write_counter - self._last_maintenance_version
        elapsed = now - self._last_maintenance_at

        if writes_since < 50 and elapsed < 3600:
            return None

        logger.info(
            "Auto-maintenance triggered: %d writes, %.0fs elapsed",
            writes_since,
            elapsed,
        )
        results = self.maintenance()
        self._last_maintenance_at = now
        self._last_maintenance_version = self._write_counter
        return results


_ID_PREFIX_TO_TYPE: list[tuple[str, str]] = [
    ("AX-", NodeType.AXIOM.value),
    ("PAT-", NodeType.PATTERN.value),  # before P- (prefix overlap)
    ("CPAT-", NodeType.PATTERN.value),  # cluster pattern
    ("P-", NodeType.PRINCIPLE.value),
    ("F-", NodeType.FINDING.value),
    ("CE-", NodeType.CODE_EXAMPLE.value),
    ("TR-", NodeType.TEST_RESULT.value),
    ("tech:", NodeType.TECHNOLOGY.value),
    ("domain:", NodeType.DOMAIN.value),
    ("filetype:", NodeType.FILE_TYPE.value),
    ("hl:", NodeType.HUMAN_LAYER.value),
    ("src:", NodeType.SOURCE.value),
    ("vr:", NodeType.VALIDATION_RUN.value),
    ("TASK-", NodeType.TASK.value),
]

_ID_PREFIX_TO_LAYER: list[tuple[str, str]] = [
    ("AX-", "L0"),
    ("P-", "L1"),
    ("PAT-", "L2"),
    ("CPAT-", "L2"),
    ("F-", "L4"),
    ("CE-", "L4"),
    ("TR-", "L4"),
    ("TASK-", "L5"),
    # taxonomy/source nodes don't belong to a cortical layer — default L3
]


def _node_type_for_id(node_id: str) -> str:
    """Infer NodeType from node ID prefix."""
    for prefix, ntype in _ID_PREFIX_TO_TYPE:
        if node_id.startswith(prefix):
            return ntype
    # CR- prefix = concrete rule
    if node_id.startswith("CR-"):
        return NodeType.RULE.value
    return NodeType.RULE.value


def _node_layer_from_id(node_id: str) -> str:
    """Infer cortical layer from node ID prefix."""
    for prefix, layer in _ID_PREFIX_TO_LAYER:
        if node_id.startswith(prefix):
            return layer
    return "L3"


def _coerce_seed_sources(raw_sources: list[dict[str, Any]]) -> list[Source]:
    """Convert SeedEntry source dicts to Source model instances.

    SeedEntry stores sources as list[dict] (already coerced from bare URLs by
    the _coerce_sources validator). This converts them to proper Source objects
    for the Axiom/Principle/Pattern/Rule constructors.
    """
    if not raw_sources:
        return []
    result: list[Source] = []
    for s in raw_sources:
        try:
            result.append(Source(**s))
        except Exception as exc:
            # Gracefully skip malformed source entries
            logger.debug("Skipping malformed source entry: %s", exc)
    return result


def _short_hash(text: str) -> str:
    """Generate a short hash for ID generation."""
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:8]


def _normalize_layer(layer_str: str) -> str:
    """Normalize layer string to L0/L1/L2/L3/L4/L5 format."""
    mapping = {
        "axioms": "L0",
        "axiom": "L0",
        "l0": "L0",
        "principles": "L1",
        "principle": "L1",
        "l1": "L1",
        "patterns": "L2",
        "pattern": "L2",
        "l2": "L2",
        "rules": "L3",
        "rule": "L3",
        "l3": "L3",
        "evidence": "L4",
        "findings": "L4",
        "l4": "L4",
        "context": "L5",
        "l5": "L5",
    }
    return mapping.get(layer_str.lower().strip(), layer_str.upper())
