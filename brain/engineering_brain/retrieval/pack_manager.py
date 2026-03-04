"""Pack Manager — creates and selects knowledge packs for ERG reasoning.

A Pack is a "frozen query": a materialized subgraph of nodes plus reasoning
edges that capture the causal structure (PREREQUISITE, DEEPENS, ALTERNATIVE,
TRIGGERS, COMPLEMENTS, VALIDATES) between them.

Three creation paths:
1. auto_generate_packs()  — zero input, groups by (technology, domain)
2. create_pack()          — one natural-language description
3. create_pack_from_nodes — explicit node IDs (power user)

The existing scorer.py determines pack boundaries — no manual taxonomy needed.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from typing import Any

from engineering_brain.adapters.base import GraphAdapter, VectorAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.types import Pack
from engineering_brain.retrieval.context_extractor import ExtractedContext, extract_context
from engineering_brain.retrieval.scorer import rank_results

logger = logging.getLogger(__name__)

# Edge type mapping: existing graph edges → reasoning edges
_EDGE_TYPE_MAP: dict[str, str] = {
    "GROUNDS": "TRIGGERS",
    "INFORMS": "TRIGGERS",
    "INSTANTIATES": "DEEPENS",
    "EVIDENCED_BY": "DEEPENS",
    "REINFORCES": "DEEPENS",
    "CONFLICTS_WITH": "ALTERNATIVE",
    "WEAKENS": "ALTERNATIVE",
    "SUPERSEDES": "ALTERNATIVE",
    "VARIANT_OF": "ALTERNATIVE",
    "PREVENTS": "COMPLEMENTS",
    "REQUIRES": "PREREQUISITE",
    "APPLIES_TO": "COMPLEMENTS",
    "CITES": "VALIDATES",
    "VALIDATED_BY": "VALIDATES",
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


def _jaccard(a: list[str], b: list[str]) -> float:
    """Hierarchy-aware similarity between two tag lists.

    Uses the TagRegistry for ancestor/descendant matching when available,
    falling back to exact Jaccard similarity.
    """
    if not a and not b:
        return 0.0
    try:
        from engineering_brain.core.taxonomy import get_registry

        registry = get_registry()
        if registry.size > 0:
            # Count how many items in 'a' match any item in 'b'
            matches = registry.overlap_count(a, b)
            total = max(len(set(x.lower() for x in a) | set(x.lower() for x in b)), 1)
            return matches / total
    except Exception as exc:
        logger.debug("TagRegistry overlap_count failed in hierarchy Jaccard: %s", exc)
    # Fallback: exact Jaccard
    sa = {x.lower() for x in a}
    sb = {x.lower() for x in b}
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


def _hierarchy_match(a: list[str], b: list[str]) -> bool:
    """Check if any tag in 'a' hierarchy-matches any tag in 'b'.

    Uses the TagRegistry for ancestor/descendant matching when available,
    falling back to exact set intersection.
    """
    if not a or not b:
        return False
    try:
        from engineering_brain.core.taxonomy import get_registry

        registry = get_registry()
        if registry.size > 0:
            return registry.match_flat(a, b)
    except Exception as exc:
        logger.debug("TagRegistry match_flat failed in hierarchy match: %s", exc)
    return bool({x.lower() for x in a} & {x.lower() for x in b})


class PackManager:
    """Creates, validates, and selects knowledge packs."""

    def __init__(
        self,
        graph: GraphAdapter,
        vector: VectorAdapter | None,
        config: BrainConfig,
        query_router: Any = None,
    ) -> None:
        self._graph = graph
        self._vector = vector
        self._config = config
        self._query_router = query_router

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
        """Create a pack from a natural-language description.

        Runs the retrieval+scoring pipeline internally — the score threshold
        IS the pack boundary.
        """
        ctx = extract_context(
            description,
            technologies=technologies,
            domains=domains,
        )

        # Retrieve candidate nodes
        all_nodes = self._graph.get_all_nodes()
        scored = rank_results(
            all_nodes,
            query_technologies=ctx.technologies,
            query_domains=ctx.domains,
            top_k=max_nodes * 2,
            config=self._config,
        )

        # Filter by min_score
        candidates = [n for n in scored if n.get("_relevance_score", 0) >= min_score]
        candidates = candidates[:max_nodes]

        # Ensure vertical completeness (L1+L2+L3)
        candidates = self._ensure_vertical_completeness(candidates, all_nodes, ctx)

        # Generate reasoning edges
        reasoning_edges = self._generate_reasoning_edges(candidates)

        # Build pack
        pack_id = self._generate_pack_id(ctx)
        pack = self._build_pack(pack_id, description, candidates, reasoning_edges, ctx)

        # Validate quality
        pack.quality_score = self._compute_quality_score(pack)

        return pack

    # ------------------------------------------------------------------
    # Public: create_pack_from_nodes (explicit IDs)
    # ------------------------------------------------------------------

    def create_pack_from_nodes(
        self,
        pack_id: str,
        node_ids: list[str],
        description: str = "",
    ) -> Pack:
        """Create a pack from an explicit list of node IDs."""
        nodes: list[dict[str, Any]] = []
        for nid in node_ids:
            node = self._graph.get_node(nid)
            if node:
                nodes.append(node)

        reasoning_edges = self._generate_reasoning_edges(nodes)

        techs: set[str] = set()
        doms: set[str] = set()
        layers: set[str] = set()
        for n in nodes:
            for t in n.get("technologies") or n.get("languages") or []:
                techs.add(t)
            for d in n.get("domains") or []:
                doms.add(d)
            layers.add(_infer_layer(str(n.get("id", ""))))

        pack = Pack(
            id=pack_id,
            description=description,
            node_ids=[str(n.get("id", "")) for n in nodes],
            reasoning_edges=reasoning_edges,
            technologies=sorted(techs),
            domains=sorted(doms),
            layers_present=sorted(layers),
            node_count=len(nodes),
        )
        pack.quality_score = self._compute_quality_score(pack)
        return pack

    # ------------------------------------------------------------------
    # Public: auto_generate_packs
    # ------------------------------------------------------------------

    def auto_generate_packs(self) -> list[Pack]:
        """Auto-generate packs by grouping nodes by (technology, domain).

        Zero input required — discovers structure from the graph.
        """
        all_nodes = self._graph.get_all_nodes()
        if not all_nodes:
            return []

        # Group nodes by dominant (technology, domain) pair
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for node in all_nodes:
            if node.get("deprecated"):
                continue
            techs = node.get("technologies") or node.get("languages") or []
            doms = node.get("domains") or []
            tech = techs[0] if techs else "General"
            domain = doms[0] if doms else "general"
            key = (tech, domain)
            groups.setdefault(key, []).append(node)

        packs: list[Pack] = []
        for (tech, domain), nodes in groups.items():
            if len(nodes) < 3:
                continue

            pack_id = f"auto-{tech.lower().replace(' ', '_')}-{domain.lower()}"
            description = f"{tech} {domain} knowledge"
            reasoning_edges = self._generate_reasoning_edges(nodes)

            layers: set[str] = set()
            for n in nodes:
                layers.add(_infer_layer(str(n.get("id", ""))))

            pack = Pack(
                id=pack_id,
                description=description,
                node_ids=[str(n.get("id", "")) for n in nodes],
                reasoning_edges=reasoning_edges,
                technologies=[tech] if tech != "General" else [],
                domains=[domain] if domain != "general" else [],
                layers_present=sorted(layers),
                node_count=len(nodes),
            )
            pack.quality_score = self._compute_quality_score(pack)
            packs.append(pack)

        packs.sort(key=lambda p: p.quality_score, reverse=True)
        return packs

    # ------------------------------------------------------------------
    # Public: select_packs
    # ------------------------------------------------------------------

    def select_packs(
        self,
        ctx: ExtractedContext,
        packs: list[Pack],
        profile: Any = None,
        top_n: int = 3,
    ) -> list[Pack]:
        """Select the top-N most relevant packs for a query context.

        Relevance = Jaccard(technologies) * 0.5 + Jaccard(domains) * 0.5,
        multiplied by profile boost/suppress if provided.
        """
        if not packs:
            return []

        scored: list[tuple[float, Pack]] = []
        for pack in packs:
            tech_sim = _jaccard(pack.technologies, ctx.technologies)
            domain_sim = _jaccard(pack.domains, ctx.domains)
            relevance = tech_sim * 0.5 + domain_sim * 0.5

            # Apply profile boost/suppress
            if profile is not None:
                boost = self._get_profile_multiplier(pack.id, profile)
                relevance *= boost

            # Quality bonus (small weight so relevance dominates)
            relevance += pack.quality_score * 0.1

            scored.append((relevance, pack))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [pack for _, pack in scored[:top_n]]

    # ------------------------------------------------------------------
    # Internal: vertical completeness
    # ------------------------------------------------------------------

    def _ensure_vertical_completeness(
        self,
        candidates: list[dict[str, Any]],
        all_nodes: list[dict[str, Any]],
        ctx: ExtractedContext,
    ) -> list[dict[str, Any]]:
        """Ensure the pack has nodes from L1+L2+L3 (vertical coverage).

        If a layer is missing, pull the top-scoring node for that layer
        from the full node set.
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

        # Find best nodes for missing layers
        layer_nodes: dict[str, list[dict[str, Any]]] = {"L1": [], "L2": [], "L3": []}
        for n in all_nodes:
            nid = str(n.get("id", ""))
            if nid in candidate_ids or n.get("deprecated"):
                continue
            layer = _infer_layer(nid)
            if layer in needed_layers:
                layer_nodes.setdefault(layer, []).append(n)

        for layer in needed_layers:
            pool = layer_nodes.get(layer, [])
            if not pool:
                continue
            ranked = rank_results(
                pool,
                query_technologies=ctx.technologies,
                query_domains=ctx.domains,
                top_k=2,
                config=self._config,
            )
            candidates.extend(ranked[:2])

        return candidates

    # ------------------------------------------------------------------
    # Internal: reasoning edge generation (3 rules)
    # ------------------------------------------------------------------

    def _generate_reasoning_edges(
        self,
        nodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Generate reasoning edges using 3 rules:

        1. L1→L3 TRIGGERS: principles trigger rules in the same domain
        2. Existing edge mapping: reuse graph edges as reasoning edges
        3. Sequential IDs PREREQUISITE: nodes with sequential IDs in same prefix
        """
        node_ids = {str(n.get("id", "")) for n in nodes}
        edges: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        def _add(from_id: str, to_id: str, edge_type: str) -> None:
            key = (from_id, to_id, edge_type)
            if key not in seen and from_id != to_id:
                seen.add(key)
                edges.append(
                    {
                        "from_id": from_id,
                        "to_id": to_id,
                        "edge_type": edge_type,
                    }
                )

        # --- Rule 1: L1→L3 TRIGGERS (principles trigger rules in shared domain) ---
        l1_nodes = [n for n in nodes if _infer_layer(str(n.get("id", ""))) == "L1"]
        l3_nodes = [n for n in nodes if _infer_layer(str(n.get("id", ""))) == "L3"]

        for p in l1_nodes:
            p_domains = list(d.lower() for d in (p.get("domains") or []))
            p_id = str(p.get("id", ""))
            for r in l3_nodes:
                r_domains = list(d.lower() for d in (r.get("domains") or []))
                if _hierarchy_match(p_domains, r_domains):
                    _add(p_id, str(r.get("id", "")), "TRIGGERS")

        # --- Rule 2: Map existing graph edges to reasoning edges ---
        for nid in node_ids:
            try:
                graph_edges = self._graph.get_edges(node_id=nid)
            except Exception as exc:
                logger.debug("Failed to get edges for node %s: %s", nid, exc)
                continue
            for edge in graph_edges:
                from_id = edge.get("from_id", "")
                to_id = edge.get("to_id", "")
                etype = edge.get("edge_type", "")
                if from_id in node_ids and to_id in node_ids and etype in _EDGE_TYPE_MAP:
                    _add(from_id, to_id, _EDGE_TYPE_MAP[etype])

        # --- Rule 3: Sequential IDs → PREREQUISITE ---
        # Group by prefix (e.g., CR-SEC-CORS-001 → prefix "CR-SEC-CORS-")
        prefix_groups: dict[str, list[tuple[int, str]]] = {}
        for nid in sorted(node_ids):
            match = re.match(r"^(.+?)(\d{3,})$", nid)
            if match:
                prefix, num_str = match.groups()
                prefix_groups.setdefault(prefix, []).append((int(num_str), nid))

        for prefix, items in prefix_groups.items():
            items.sort()
            for i in range(len(items) - 1):
                curr_num, curr_id = items[i]
                next_num, next_id = items[i + 1]
                if next_num - curr_num <= 2:  # Allow small gaps
                    _add(curr_id, next_id, "PREREQUISITE")

        return edges

    # ------------------------------------------------------------------
    # Internal: quality score
    # ------------------------------------------------------------------

    def _compute_quality_score(self, pack: Pack) -> float:
        """Quality score 0.0–1.0 based on 5 signals:

        1. Node count (≥5 = full credit)
        2. Layer diversity (has L1+L2+L3 = full credit)
        3. Edge density (≥3 reasoning edges = full credit)
        4. Average epistemic P (from ep_b if available)
        5. Technology/domain specificity (non-empty = credit)
        """
        score = 0.0

        # 1. Node count: 0→0.0, 3→0.6, 5+→1.0
        node_score = min(pack.node_count / 5.0, 1.0) if pack.node_count > 0 else 0.0
        score += node_score * 0.25

        # 2. Layer diversity: count of {L1, L2, L3} present
        target_layers = {"L1", "L2", "L3"}
        present = target_layers & set(pack.layers_present)
        layer_score = len(present) / 3.0
        score += layer_score * 0.25

        # 3. Edge density
        edge_count = len(pack.reasoning_edges)
        edge_score = min(edge_count / 3.0, 1.0) if edge_count > 0 else 0.0
        score += edge_score * 0.25

        # 4. Specificity (has at least 1 tech and 1 domain)
        specificity = 0.0
        if pack.technologies:
            specificity += 0.5
        if pack.domains:
            specificity += 0.5
        score += specificity * 0.25

        return round(min(score, 1.0), 3)

    # ------------------------------------------------------------------
    # Internal: helpers
    # ------------------------------------------------------------------

    def _build_pack(
        self,
        pack_id: str,
        description: str,
        nodes: list[dict[str, Any]],
        reasoning_edges: list[dict[str, Any]],
        ctx: ExtractedContext,
    ) -> Pack:
        """Build a Pack object from scored nodes."""
        layers: set[str] = set()
        techs: set[str] = set()
        doms: set[str] = set()

        for n in nodes:
            nid = str(n.get("id", ""))
            layers.add(_infer_layer(nid))
            for t in n.get("technologies") or n.get("languages") or []:
                techs.add(t)
            for d in n.get("domains") or []:
                doms.add(d)

        return Pack(
            id=pack_id,
            description=description,
            node_ids=[str(n.get("id", "")) for n in nodes],
            reasoning_edges=reasoning_edges,
            technologies=sorted(techs) or ctx.technologies,
            domains=sorted(doms) or ctx.domains,
            layers_present=sorted(layers),
            node_count=len(nodes),
        )

    def _generate_pack_id(self, ctx: ExtractedContext) -> str:
        """Generate a pack ID from context."""
        parts = ["pack"]
        if ctx.technologies:
            parts.append(ctx.technologies[0].lower().replace(" ", "_"))
        if ctx.domains and ctx.domains[0] != "general":
            parts.append(ctx.domains[0].lower())
        return "-".join(parts) or "pack-general"

    def _get_profile_multiplier(self, pack_id: str, profile: Any) -> float:
        """Get boost/suppress multiplier from a BrainProfile for a pack."""
        multiplier = 1.0

        boost_dict = getattr(profile, "pack_boost", {}) or {}
        for pattern, factor in boost_dict.items():
            if fnmatch.fnmatch(pack_id, pattern):
                multiplier *= factor

        suppress_dict = getattr(profile, "pack_suppress", {}) or {}
        for pattern, factor in suppress_dict.items():
            if fnmatch.fnmatch(pack_id, pattern):
                multiplier *= factor

        return multiplier
