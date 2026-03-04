"""Query router for the Engineering Knowledge Brain.

Routes knowledge queries through the hybrid storage engine:
1. Extract context from task description
2. Route to relevant shards (graph + vector + cache)
3. Execute parallel queries
4. Merge, score, and budget-cap results
"""

from __future__ import annotations

import logging
import time
from datetime import UTC
from typing import Any

from engineering_brain.adapters.base import CacheAdapter, GraphAdapter, VectorAdapter
from engineering_brain.adapters.sharding import ShardRouter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import Layer, cache_key
from engineering_brain.core.types import KnowledgeQuery, KnowledgeResult
from engineering_brain.retrieval.budget import enforce_budget
from engineering_brain.retrieval.context_extractor import ExtractedContext, extract_context
from engineering_brain.retrieval.formatter import format_for_llm
from engineering_brain.retrieval.merger import (
    deduplicate_by_content,
    merge_results,
    merge_results_rrf,
)
from engineering_brain.retrieval.scorer import rank_results

logger = logging.getLogger(__name__)


class QueryRouter:
    """Routes queries through graph + vector + cache and returns formatted knowledge."""

    def __init__(
        self,
        graph: GraphAdapter,
        vector: VectorAdapter | None = None,
        cache: CacheAdapter | None = None,
        shard_router: ShardRouter | None = None,
        config: BrainConfig | None = None,
        weight_optimizer: Any = None,
    ) -> None:
        self._graph = graph
        self._vector = vector
        self._cache = cache
        self._shard_router = shard_router or ShardRouter(enabled=False)
        self._config = config or BrainConfig()
        self._weight_optimizer = weight_optimizer

    def query(self, request: KnowledgeQuery) -> KnowledgeResult:
        """Execute a knowledge query through the full retrieval pipeline."""
        start = time.time()

        # 1. Extract context
        ctx = extract_context(
            request.task_description,
            technologies=request.technologies,
            file_type=request.file_type,
            phase=request.phase,
            domains=request.domains,
        )

        # 2. Check cache
        ck = cache_key(
            domain=ctx.domains[0] if ctx.domains else "general",
            technology=ctx.technologies[0] if ctx.technologies else "",
            file_type=ctx.file_types[0] if ctx.file_types else "",
            phase=ctx.phase,
        )
        if self._cache:
            cached = self._cache.get(ck)
            if cached and isinstance(cached, dict):
                cached["cache_hit"] = True
                cached["query_time_ms"] = (time.time() - start) * 1000
                try:
                    return KnowledgeResult(**cached)
                except Exception as exc:
                    logger.debug("Failed to deserialize cached result: %s", exc)

        # 3. Route to shards
        layers_to_query = [
            Layer.L1_PRINCIPLES,
            Layer.L2_PATTERNS,
            Layer.L3_RULES,
            Layer.L4_EVIDENCE,
        ]

        # 4. Query graph
        graph_results = self._query_graph(ctx, layers_to_query)

        # 5. Query vector (if available)
        vector_results = self._query_vector(ctx, request.task_description) if self._vector else []

        # 6. Merge (use RRF when we have vector results)
        if vector_results:
            merged = merge_results_rrf(graph_results, vector_results)
        else:
            merged = merge_results(graph_results, vector_results)
        merged = deduplicate_by_content(merged)

        # 7. Score and rank
        scored = rank_results(
            merged,
            query_technologies=ctx.technologies,
            query_domains=ctx.domains,
            top_k=50,
            config=self._config,
            weight_optimizer=self._weight_optimizer,
        )

        # 7a. Cross-encoder reranking (optional, improves precision on top-K)
        if self._config.reranker_enabled and len(scored) > 5:
            try:
                from engineering_brain.retrieval.reranker import rerank_results

                scored = rerank_results(
                    scored,
                    request.task_description,
                    top_k=min(len(scored), 30),
                )
            except Exception as e:
                logger.debug("Reranking failed (non-blocking): %s", e)

        # 7b. Multi-hop graph expansion
        if self._config.graph_expansion_enabled:
            try:
                from engineering_brain.retrieval.graph_expander import expand_top_results

                expanded = expand_top_results(
                    self._graph,
                    scored,
                    max_expand=self._config.graph_expansion_max_expand,
                    max_hops=self._config.graph_expansion_max_hops,
                    discount=self._config.graph_expansion_discount,
                )
                if expanded:
                    expanded_scored = rank_results(
                        expanded,
                        query_technologies=ctx.technologies,
                        query_domains=ctx.domains,
                        top_k=20,
                        config=self._config,
                        weight_optimizer=self._weight_optimizer,
                    )
                    for n in expanded_scored:
                        disc = float(n.get("_expansion_discount", 0.4))
                        n["_relevance_score"] = n.get("_relevance_score", 0) * disc
                    scored.extend(expanded_scored)
                    scored.sort(key=lambda n: n.get("_relevance_score", 0), reverse=True)
            except Exception as e:
                logger.debug("Graph expansion failed (non-blocking): %s", e)

        # 7c. Record retrievals + track reuse metrics (non-blocking)
        try:
            from engineering_brain.observation.log import ObservationLog

            obs = ObservationLog()
            obs.record_query(rule_ids=[n.get("id", "") for n in scored if n.get("id")])
        except Exception as exc:
            logger.debug("Failed to record observation log: %s", exc)
        self._track_retrieval_metrics(scored)

        # 8-11. Assemble knowledge pack (replaces split + budget + format)
        try:
            from engineering_brain.retrieval.knowledge_assembler import KnowledgeAssembler

            assembler = KnowledgeAssembler(config=self._config)
            assembly = assembler.assemble(
                query=request.task_description,
                ctx=ctx,
                scored_nodes=scored,
                budget_chars=self._config.context_budget_chars,
            )
            formatted = assembly.formatted_text
            by_layer = assembly.by_layer
            guardrails = assembly.guardrails.model_dump() if assembly.guardrails else None
        except Exception as e:
            logger.debug("Assembly failed, using deterministic pipeline: %s", e)
            by_layer, formatted = self._deterministic_fallback(scored, request)
            guardrails = None

        # 12. Build result
        result = KnowledgeResult(
            principles=[_clean_node(n) for n in by_layer.get("L1", [])],
            patterns=[_clean_node(n) for n in by_layer.get("L2", [])],
            rules=[_clean_node(n) for n in by_layer.get("L3", [])],
            evidence=[_clean_node(n) for n in by_layer.get("L4", [])],
            formatted_text=formatted,
            total_nodes_queried=len(merged),
            cache_hit=False,
            shards_queried=[ctx.domains[0] if ctx.domains else "general"],
            query_time_ms=(time.time() - start) * 1000,
            guardrails=guardrails,
        )

        # 13. Cache result
        if self._cache:
            try:
                self._cache.set(
                    ck, result.model_dump(mode="json"), ttl_seconds=self._config.memory_cache_ttl
                )
            except Exception as e:
                logger.debug("Cache write failed: %s", e)

        return result

    def query_with_scored_nodes(
        self,
        request: KnowledgeQuery,
    ) -> tuple[KnowledgeResult, list[dict[str, Any]]]:
        """Like query(), but also returns scored nodes before budget trimming.

        Used by ThoughtEnhancer to access full epistemic metadata on all
        matched nodes, not just the budget-trimmed subset.
        """
        start = time.time()

        ctx = extract_context(
            request.task_description,
            technologies=request.technologies,
            file_type=request.file_type,
            phase=request.phase,
            domains=request.domains,
        )

        # Check cache (return empty scored_nodes on cache hit)
        ck = cache_key(
            domain=ctx.domains[0] if ctx.domains else "general",
            technology=ctx.technologies[0] if ctx.technologies else "",
            file_type=ctx.file_types[0] if ctx.file_types else "",
            phase=ctx.phase,
        )
        if self._cache:
            cached = self._cache.get(ck)
            if cached and isinstance(cached, dict):
                cached["cache_hit"] = True
                cached["query_time_ms"] = (time.time() - start) * 1000
                try:
                    return KnowledgeResult(**cached), []
                except Exception as exc:
                    logger.debug("Failed to deserialize cached result: %s", exc)

        # Steps 3-7: identical to query()
        layers_to_query = [
            Layer.L1_PRINCIPLES,
            Layer.L2_PATTERNS,
            Layer.L3_RULES,
            Layer.L4_EVIDENCE,
        ]
        graph_results = self._query_graph(ctx, layers_to_query)
        vector_results = self._query_vector(ctx, request.task_description) if self._vector else []
        if vector_results:
            merged = merge_results_rrf(graph_results, vector_results)
        else:
            merged = merge_results(graph_results, vector_results)
        merged = deduplicate_by_content(merged)
        scored = rank_results(
            merged,
            query_technologies=ctx.technologies,
            query_domains=ctx.domains,
            top_k=50,
            config=self._config,
            weight_optimizer=self._weight_optimizer,
        )

        # 7a. Cross-encoder reranking (optional)
        if self._config.reranker_enabled and len(scored) > 5:
            try:
                from engineering_brain.retrieval.reranker import rerank_results

                scored = rerank_results(
                    scored,
                    request.task_description,
                    top_k=min(len(scored), 30),
                )
            except Exception as e:
                logger.debug("Reranking failed (non-blocking): %s", e)

        # 7b. Multi-hop graph expansion
        if self._config.graph_expansion_enabled:
            try:
                from engineering_brain.retrieval.graph_expander import expand_top_results

                expanded = expand_top_results(
                    self._graph,
                    scored,
                    max_expand=self._config.graph_expansion_max_expand,
                    max_hops=self._config.graph_expansion_max_hops,
                    discount=self._config.graph_expansion_discount,
                )
                if expanded:
                    expanded_scored = rank_results(
                        expanded,
                        query_technologies=ctx.technologies,
                        query_domains=ctx.domains,
                        top_k=20,
                        config=self._config,
                        weight_optimizer=self._weight_optimizer,
                    )
                    for n in expanded_scored:
                        disc = float(n.get("_expansion_discount", 0.4))
                        n["_relevance_score"] = n.get("_relevance_score", 0) * disc
                    scored.extend(expanded_scored)
                    scored.sort(key=lambda n: n.get("_relevance_score", 0), reverse=True)
            except Exception as e:
                logger.debug("Graph expansion failed (non-blocking): %s", e)

        # 7c. Record retrievals (non-blocking)
        try:
            from engineering_brain.observation.log import ObservationLog

            obs = ObservationLog()
            obs.record_query(rule_ids=[n.get("id", "") for n in scored if n.get("id")])
        except Exception as exc:
            logger.debug("Failed to record observation log: %s", exc)
        self._track_retrieval_metrics(scored)

        # Capture all scored nodes BEFORE budget trimming
        all_scored = list(scored)

        # Steps 8-13: assemble knowledge pack (or deterministic fallback)
        try:
            from engineering_brain.retrieval.knowledge_assembler import KnowledgeAssembler

            assembler = KnowledgeAssembler(config=self._config)
            assembly = assembler.assemble(
                query=request.task_description,
                ctx=ctx,
                scored_nodes=scored,
                budget_chars=self._config.context_budget_chars,
            )
            formatted = assembly.formatted_text
            by_layer = assembly.by_layer
            guardrails = assembly.guardrails.model_dump() if assembly.guardrails else None
        except Exception as e:
            logger.debug("Assembly failed, using deterministic pipeline: %s", e)
            by_layer, formatted = self._deterministic_fallback(scored, request)
            guardrails = None

        result = KnowledgeResult(
            principles=[_clean_node(n) for n in by_layer.get("L1", [])],
            patterns=[_clean_node(n) for n in by_layer.get("L2", [])],
            rules=[_clean_node(n) for n in by_layer.get("L3", [])],
            evidence=[_clean_node(n) for n in by_layer.get("L4", [])],
            formatted_text=formatted,
            total_nodes_queried=len(merged),
            cache_hit=False,
            shards_queried=[ctx.domains[0] if ctx.domains else "general"],
            query_time_ms=(time.time() - start) * 1000,
            guardrails=guardrails,
        )

        if self._cache:
            try:
                self._cache.set(
                    ck, result.model_dump(mode="json"), ttl_seconds=self._config.memory_cache_ttl
                )
            except Exception as e:
                logger.debug("Cache write failed: %s", e)

        return result, all_scored

    def _track_retrieval_metrics(self, scored: list[dict[str, Any]]) -> None:
        """Track per-node retrieval metrics (non-blocking).

        Updates: retrieval_count, last_retrieved_at, avg_position.
        Used for active learning — unused nodes are pruning candidates.
        """
        now_iso = ""
        try:
            from datetime import datetime

            now_iso = datetime.now(UTC).isoformat()
        except Exception as exc:
            logger.debug("Failed to generate ISO timestamp: %s", exc)

        for rank, node in enumerate(scored[:30]):  # Only track top-30
            nid = node.get("id", "")
            if not nid:
                continue
            try:
                full_node = self._graph.get_node(nid)
                if full_node is None:
                    continue
                ret_count = int(full_node.get("retrieval_count", 0)) + 1
                old_avg = float(full_node.get("avg_result_position", rank))
                # Exponential moving average of position
                new_avg = old_avg * 0.8 + rank * 0.2
                label = full_node.get("_label", "Rule")
                self._graph.add_node(
                    label,
                    nid,
                    {
                        **full_node,
                        "retrieval_count": ret_count,
                        "last_retrieved_at": now_iso,
                        "avg_result_position": round(new_avg, 2),
                    },
                )
            except Exception as exc:
                logger.debug("Metrics tracking failed for node: %s", exc)

    def query_with_provenance(
        self,
        request: KnowledgeQuery,
    ) -> tuple[KnowledgeResult, list[dict[str, Any]]]:
        """Query with provenance chains attached to each node.

        Returns (result, nodes_with_provenance) where each node has a
        '_provenance' key containing its source chain (evidence → rule → pattern).
        """
        result, scored = self.query_with_scored_nodes(request)

        # Attach provenance chain to each scored node
        for node in scored:
            node_id = node.get("id", "")
            if not node_id:
                continue
            chain = self._trace_provenance(node_id)
            if chain:
                node["_provenance"] = chain

        return result, scored

    def _trace_provenance(self, node_id: str, max_depth: int = 3) -> list[dict[str, str]]:
        """Trace a node's provenance chain (source → evidence → rule → pattern).

        Follows EVIDENCED_BY, GROUNDS, INFORMS, INSTANTIATES edges backward.
        """
        chain: list[dict[str, str]] = []
        visited: set[str] = {node_id}
        current = node_id

        provenance_edges = {
            "EVIDENCED_BY",
            "GROUNDS",
            "INFORMS",
            "INSTANTIATES",
            "SOURCED_FROM",
            "CITES",
        }

        for _ in range(max_depth):
            try:
                edges = self._graph.get_edges(node_id=current)
            except Exception as exc:
                logger.debug("Provenance trace failed for node %s: %s", current, exc)
                break

            found_parent = False
            for edge in edges:
                if edge["edge_type"] not in provenance_edges:
                    continue
                # Follow edges where current is the target (incoming)
                parent_id = edge["from_id"]
                if parent_id == current:
                    parent_id = edge["to_id"]
                if parent_id in visited:
                    continue

                parent = self._graph.get_node(parent_id)
                if not parent:
                    continue

                visited.add(parent_id)
                chain.append(
                    {
                        "node_id": parent_id,
                        "edge_type": edge["edge_type"],
                        "text": str(
                            parent.get("text", parent.get("name", parent.get("statement", "")))
                        )[:100],
                    }
                )
                current = parent_id
                found_parent = True
                break

            if not found_parent:
                break

        return chain

    def _query_graph(
        self,
        ctx: ExtractedContext,
        layers: list[Layer],
    ) -> list[dict[str, Any]]:
        """Query graph adapter for knowledge nodes matching context."""
        results: list[dict[str, Any]] = []

        layer_labels = {
            Layer.L1_PRINCIPLES: "Principle",
            Layer.L2_PATTERNS: "Pattern",
            Layer.L3_RULES: "Rule",
            Layer.L4_EVIDENCE: "Finding",
        }

        for layer in layers:
            label = layer_labels.get(layer)
            if not label:
                continue

            # Query by technology match
            for tech in ctx.technologies:
                tech_nodes = self._graph.query(
                    label=label,
                    filters={"technologies": [tech]},
                    limit=20,
                )
                for n in tech_nodes:
                    n["_layer"] = layer.value
                results.extend(tech_nodes)

            # Query by domain match (expand domains if query expansion enabled)
            if self._config.query_expansion_enabled:
                try:
                    from engineering_brain.retrieval.context_extractor import expand_domains

                    query_domains = expand_domains(ctx.domains)
                except Exception as exc:
                    logger.debug("Domain expansion failed, using original domains: %s", exc)
                    query_domains = ctx.domains
            else:
                query_domains = ctx.domains
            for domain in query_domains:
                domain_nodes = self._graph.query(
                    label=label,
                    filters={"domains": [domain]},
                    limit=20,
                )
                for n in domain_nodes:
                    n["_layer"] = layer.value
                results.extend(domain_nodes)

            # If no tech/domain matches, get general knowledge for this layer
            if not ctx.technologies and not ctx.domains:
                general = self._graph.query(label=label, limit=20)
                for n in general:
                    n["_layer"] = layer.value
                results.extend(general)

        # Defense-in-depth: filter deprecated nodes before scoring
        results = [n for n in results if not n.get("deprecated")]
        return results

    def _query_vector(self, ctx: ExtractedContext, query_text: str = "") -> list[dict[str, Any]]:
        """Query vector adapter for semantically similar knowledge."""
        if not self._vector:
            return []
        try:
            from engineering_brain.retrieval.embedder import get_embedder

            embedder = get_embedder(self._vector, self._config)
            if not embedder:
                return []
            text = query_text or ctx.raw_text
            query_vec = embedder.embed_text(text)
            if not query_vec:
                return []

            from engineering_brain.core.schema import VECTOR_COLLECTIONS

            results: list[dict[str, Any]] = []
            seen_ids: set[str] = set()

            for layer_key, collection in VECTOR_COLLECTIONS.items():
                hits = self._vector.search(
                    collection=collection,
                    query_vector=query_vec,
                    top_k=10,
                    score_threshold=0.3,
                )
                for hit in hits:
                    hit_id = hit.get("id", "")
                    if hit_id in seen_ids:
                        continue
                    seen_ids.add(hit_id)
                    node = self._graph.get_node(hit_id)
                    if node and not node.get("deprecated"):
                        node["_layer"] = layer_key
                        node["_vector_score"] = hit.get("score", 0.0)
                        results.append(node)
            return results
        except Exception as e:
            logger.debug("Vector search failed (non-blocking): %s", e)
            return []

    def _deterministic_fallback(
        self,
        scored: list[dict[str, Any]],
        request: KnowledgeQuery,
    ) -> tuple[dict[str, list[dict[str, Any]]], str]:
        """Deterministic pipeline: split → top-K → budget → format. Single source of truth."""
        by_layer = self._split_by_layer(scored)
        cfg = self._config
        limits = request.max_results_per_layer or {
            "L1": cfg.top_k_principles,
            "L2": cfg.top_k_patterns,
            "L3": cfg.top_k_rules,
            "L4": cfg.top_k_evidence,
        }
        for layer_key, limit in limits.items():
            if layer_key in by_layer:
                by_layer[layer_key] = by_layer[layer_key][:limit]
        by_layer = enforce_budget(by_layer, config=cfg)
        formatted = format_for_llm(by_layer, config=cfg)
        return by_layer, formatted

    def _split_by_layer(self, nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Split scored nodes into per-layer buckets."""
        by_layer: dict[str, list[dict[str, Any]]] = {
            "L1": [],
            "L2": [],
            "L3": [],
            "L4": [],
        }
        for node in nodes:
            layer = node.get("_layer", "")
            label = node.get("_label", "")
            if layer in by_layer:
                by_layer[layer].append(node)
            elif label == "Principle":
                by_layer["L1"].append(node)
            elif label == "Pattern":
                by_layer["L2"].append(node)
            elif label in ("Rule",):
                by_layer["L3"].append(node)
            elif label in ("Finding", "CodeExample", "TestResult"):
                by_layer["L4"].append(node)
            else:
                by_layer["L3"].append(node)  # Default to rules
        return by_layer


def _clean_node(node: dict[str, Any]) -> dict[str, Any]:
    """Remove internal scoring/routing metadata from a node before returning."""
    return {k: v for k, v in node.items() if not k.startswith("_")}
