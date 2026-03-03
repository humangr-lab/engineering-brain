"""Scalable Pack Manager v2 — O(log N) at 10M nodes.

Vector-first ANN retrieval with multi-query decomposition and RRF fusion.
Replaces O(N) full-scan approach in PackManager v1 with a pipeline that
stays sub-second at any graph size:

    Description → context_extractor → Multi-Query Decomposition (max 5)
        → Per sub-query: Vector ANN (4 collections) + Graph filtered query
        → RRF merge → 7-signal scoring on O(K) candidates
        → Graph expansion (1-hop) → Vertical completeness (filtered)
        → Reasoning edges → Pack

Feature-flagged via BRAIN_PACK_V2_ENABLED (default OFF).
Falls back gracefully to graph-only retrieval when vector adapter is None.
Delegates batch/explicit operations to PackManager v1 (already O(K)).
"""

from __future__ import annotations

import logging
from typing import Any

from engineering_brain.adapters.base import GraphAdapter, VectorAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.types import Pack
from engineering_brain.retrieval.context_extractor import ExtractedContext, extract_context
from engineering_brain.retrieval.merger import merge_results_rrf
from engineering_brain.retrieval.scorer import rank_results

logger = logging.getLogger(__name__)

# Layer prefix → Qdrant collection mapping
_LAYER_COLLECTIONS: dict[str, str] = {
    "L1": "brain_principles",
    "L2": "brain_patterns",
    "L3": "brain_rules",
    "L4": "brain_evidence",
}

# Layer prefix → graph label for filtered queries
_LAYER_LABELS: dict[str, str] = {
    "L1": "Principle",
    "L2": "Pattern",
    "L3": "Rule",
    "L4": "Finding",
}


def _infer_layer(node_id: str) -> str:
    """Infer cortical layer from node ID prefix."""
    if node_id.startswith("AX-"):
        return "L0"
    if node_id.startswith("P-"):
        return "L1"
    if node_id.startswith(("PAT-", "CPAT-")):
        return "L2"
    if node_id.startswith("F-"):
        return "L4"
    return "L3"


class ScalablePackManager:
    """O(log N) pack creation via vector-first retrieval + RRF fusion.

    Uses the same scoring, merging, and expansion infrastructure as the
    rest of the Brain — zero reimplementation.
    """

    def __init__(
        self,
        graph: GraphAdapter,
        vector: VectorAdapter | None,
        config: BrainConfig,
        query_router: Any = None,
        embedder: Any = None,
    ) -> None:
        self._graph = graph
        self._vector = vector
        self._config = config
        self._query_router = query_router
        self._embedder = embedder

    # ------------------------------------------------------------------
    # Public: create_pack (from natural language)
    # ------------------------------------------------------------------

    def create_pack(
        self,
        description: str,
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
        min_score: float = 0.3,
        max_nodes: int = 80,
    ) -> Pack:
        """Create a pack using O(log N) vector-first retrieval.

        Pipeline:
        1. Extract context → technologies, domains
        2. Decompose into 3-5 sub-queries
        3. Per sub-query: vector ANN + graph filtered search
        4. RRF merge across all sub-queries
        5. Score O(K) candidates with 7-signal scorer
        6. Graph expansion (1-hop)
        7. Vertical completeness (filtered, not full scan)
        8. Generate reasoning edges + build Pack
        """
        ctx = extract_context(
            description,
            technologies=technologies,
            domains=domains,
        )

        # Step 2: Decompose into sub-queries
        sub_queries = self._decompose_queries(ctx)
        logger.debug("Pack v2: %d sub-queries from description", len(sub_queries))

        # Step 3-4: Retrieve + merge via RRF
        all_vector_results: list[dict[str, Any]] = []
        all_graph_results: list[dict[str, Any]] = []

        for sq in sub_queries:
            vector_hits, graph_hits = self._retrieve_candidates(sq, ctx)
            all_vector_results.extend(vector_hits)
            all_graph_results.extend(graph_hits)

        merged = merge_results_rrf(all_graph_results, all_vector_results)
        logger.debug("Pack v2: %d candidates after RRF merge", len(merged))

        # Step 5: Score O(K) candidates
        scored = rank_results(
            merged,
            query_technologies=ctx.technologies,
            query_domains=ctx.domains,
            top_k=max_nodes * 2,
            config=self._config,
        )

        # Filter by min_score
        candidates = [n for n in scored if n.get("_relevance_score", 0) >= min_score]
        candidates = candidates[:max_nodes]

        # Step 6: Graph expansion (1-hop)
        if self._config.graph_expansion_enabled and candidates:
            try:
                from engineering_brain.retrieval.graph_expander import expand_top_results

                expanded = expand_top_results(
                    self._graph,
                    candidates,
                    max_expand=self._config.graph_expansion_max_expand,
                    max_hops=self._config.graph_expansion_max_hops,
                    discount=self._config.graph_expansion_discount,
                )
                if expanded:
                    # Score expanded nodes and add qualifying ones
                    scored_expanded = rank_results(
                        expanded,
                        query_technologies=ctx.technologies,
                        query_domains=ctx.domains,
                        top_k=10,
                        config=self._config,
                    )
                    for node in scored_expanded:
                        discount = node.get("_expansion_discount", 0.4)
                        node["_relevance_score"] = node.get("_relevance_score", 0) * (1 - discount)
                        if node.get("_relevance_score", 0) >= min_score:
                            candidates.append(node)
            except Exception as e:
                logger.debug("Pack v2 expansion failed (non-blocking): %s", e)

        # Step 7: Vertical completeness (filtered, not O(N))
        candidates = self._ensure_vertical_completeness_v2(candidates, ctx)

        # Enforce max_nodes after completeness
        candidates = candidates[:max_nodes]

        # Step 8: Reasoning edges + build Pack
        from engineering_brain.retrieval.pack_manager import PackManager

        v1 = PackManager(self._graph, self._vector, self._config, self._query_router)
        reasoning_edges = v1._generate_reasoning_edges(candidates)

        pack_id = v1._generate_pack_id(ctx)
        pack = v1._build_pack(pack_id, description, candidates, reasoning_edges, ctx)
        pack.quality_score = v1._compute_quality_score(pack)

        logger.info(
            "Pack v2 created: %s (nodes=%d, quality=%.3f, layers=%s)",
            pack.id, pack.node_count, pack.quality_score, pack.layers_present,
        )
        return pack

    # ------------------------------------------------------------------
    # Delegated methods (already O(K) in v1)
    # ------------------------------------------------------------------

    def auto_generate_packs(self) -> list[Pack]:
        """Delegate to v1 — batch offline operation, O(N) is acceptable."""
        from engineering_brain.retrieval.pack_manager import PackManager
        v1 = PackManager(self._graph, self._vector, self._config, self._query_router)
        return v1.auto_generate_packs()

    def create_pack_from_nodes(
        self,
        pack_id: str,
        node_ids: list[str],
        description: str = "",
    ) -> Pack:
        """Delegate to v1 — explicit IDs, already O(K)."""
        from engineering_brain.retrieval.pack_manager import PackManager
        v1 = PackManager(self._graph, self._vector, self._config, self._query_router)
        return v1.create_pack_from_nodes(pack_id, node_ids, description)

    def select_packs(
        self,
        ctx: ExtractedContext,
        packs: list[Pack],
        profile: Any = None,
        top_n: int = 3,
    ) -> list[Pack]:
        """Delegate to v1 — operates on pack list, already O(K)."""
        from engineering_brain.retrieval.pack_manager import PackManager
        v1 = PackManager(self._graph, self._vector, self._config, self._query_router)
        return v1.select_packs(ctx, packs, profile=profile, top_n=top_n)

    # ------------------------------------------------------------------
    # Internal: Multi-query decomposition
    # ------------------------------------------------------------------

    def _decompose_queries(self, ctx: ExtractedContext) -> list[str]:
        """Decompose ExtractedContext into 3-5 sub-queries.

        No LLM calls — pure string composition from extracted context:
        - 1 sub-query per technology (max 3)
        - 1 sub-query per unique domain (max 2)
        Deduplicates and caps at config.pack_v2_max_sub_queries.
        """
        max_queries = self._config.pack_v2_max_sub_queries
        sub_queries: list[str] = []
        seen: set[str] = set()

        # 1 per technology (max 3)
        domain_str = " ".join(ctx.domains[:2]) if ctx.domains else ""
        for tech in ctx.technologies[:3]:
            q = f"{tech} {domain_str} best practices".strip()
            q_key = q.lower()
            if q_key not in seen:
                seen.add(q_key)
                sub_queries.append(q)

        # 1 per unique domain (max 2)
        tech_str = " ".join(ctx.technologies[:2]) if ctx.technologies else ""
        for domain in ctx.domains[:2]:
            if domain == "general":
                continue
            q = f"{domain} {tech_str} knowledge".strip()
            q_key = q.lower()
            if q_key not in seen:
                seen.add(q_key)
                sub_queries.append(q)

        # If nothing detected, use raw text
        if not sub_queries:
            sub_queries.append(ctx.raw_text[:200] if ctx.raw_text else "engineering knowledge")

        return sub_queries[:max_queries]

    # ------------------------------------------------------------------
    # Internal: Per-query retrieval (vector + graph)
    # ------------------------------------------------------------------

    def _retrieve_candidates(
        self,
        query_text: str,
        ctx: ExtractedContext,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Retrieve candidates for a single sub-query.

        Returns (vector_results, graph_results).
        Vector: ANN search across 4 Qdrant collections.
        Graph: Filtered query per layer with technology/domain filters.
        """
        vector_results: list[dict[str, Any]] = []
        graph_results: list[dict[str, Any]] = []
        top_k = self._config.pack_v2_vector_top_k
        graph_limit = self._config.pack_v2_graph_filter_limit

        # --- Vector ANN search ---
        if self._vector and self._embedder:
            query_vector = self._embedder.embed_text(query_text)
            if query_vector:
                for layer_key, collection in _LAYER_COLLECTIONS.items():
                    try:
                        hits = self._vector.search(
                            collection=collection,
                            query_vector=query_vector,
                            top_k=top_k,
                        )
                        for hit in hits:
                            # Hydrate from graph if we only have metadata
                            node_id = hit.get("id", "")
                            if not node_id:
                                node_id = (hit.get("metadata") or {}).get("id", "")
                            if not node_id:
                                continue
                            # Try to hydrate full node from graph
                            full_node = self._graph.get_node(node_id)
                            if full_node:
                                full_node["_vector_score"] = hit.get("score", 0.0)
                                vector_results.append(full_node)
                            else:
                                # Use hit directly with vector score
                                hit["_vector_score"] = hit.get("score", 0.0)
                                vector_results.append(hit)
                    except Exception as e:
                        logger.debug(
                            "Pack v2 vector search failed for %s (non-blocking): %s",
                            collection, e,
                        )

        # --- Graph filtered queries ---
        for layer_key, label in _LAYER_LABELS.items():
            filters: dict[str, Any] = {}
            if ctx.technologies:
                filters["technologies"] = ctx.technologies
            if ctx.domains and ctx.domains != ["general"]:
                filters["domains"] = ctx.domains

            try:
                hits = self._graph.query(
                    label=label,
                    filters=filters if filters else None,
                    limit=graph_limit,
                )
                graph_results.extend(hits)
            except Exception as e:
                logger.debug(
                    "Pack v2 graph query failed for %s (non-blocking): %s",
                    label, e,
                )

        return vector_results, graph_results

    # ------------------------------------------------------------------
    # Internal: Vertical completeness (O(filtered), not O(N))
    # ------------------------------------------------------------------

    def _ensure_vertical_completeness_v2(
        self,
        candidates: list[dict[str, Any]],
        ctx: ExtractedContext,
    ) -> list[dict[str, Any]]:
        """Ensure pack has nodes from L1+L2+L3 using filtered queries.

        Unlike v1 which scans get_all_nodes(), this uses filtered graph
        queries with technology/domain constraints — O(filtered) not O(N).
        """
        layers_present: set[str] = set()
        candidate_ids: set[str] = set()
        for n in candidates:
            nid = str(n.get("id", ""))
            layers_present.add(_infer_layer(nid))
            candidate_ids.add(nid)

        needed_layers = {"L1", "L2", "L3"} - layers_present
        if not needed_layers:
            return candidates

        graph_limit = self._config.pack_v2_graph_filter_limit

        for layer in needed_layers:
            label = _LAYER_LABELS.get(layer)
            if not label:
                continue

            # Build filters from context
            filters: dict[str, Any] = {}
            if ctx.technologies:
                filters["technologies"] = ctx.technologies
            if ctx.domains and ctx.domains != ["general"]:
                filters["domains"] = ctx.domains

            try:
                pool = self._graph.query(
                    label=label,
                    filters=filters if filters else None,
                    limit=graph_limit,
                )
            except Exception:
                pool = []

            # Filter out already-included and deprecated nodes
            pool = [
                n for n in pool
                if str(n.get("id", "")) not in candidate_ids
                and not n.get("deprecated")
            ]

            if not pool:
                continue

            # Score and take top 2 for the missing layer
            ranked = rank_results(
                pool,
                query_technologies=ctx.technologies,
                query_domains=ctx.domains,
                top_k=2,
                config=self._config,
            )
            candidates.extend(ranked[:2])
            for n in ranked[:2]:
                candidate_ids.add(str(n.get("id", "")))

        return candidates
