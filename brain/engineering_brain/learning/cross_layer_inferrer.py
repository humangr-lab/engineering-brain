"""Cross-layer edge inference for the Engineering Knowledge Brain.

Replaces/augments the hardcoded 71-tuple maps in brain._build_cross_layer_edges()
with embedding-based edge inference that respects layer hierarchy constraints.

Only infers edges that follow the valid layer transitions:
- L0 -> L1: GROUNDS (Axiom -> Principle)
- L1 -> L2: INFORMS (Principle -> Pattern)
- L2 -> L3: INSTANTIATES (Pattern -> Rule)

Scoring uses SOTA normalized-cosine + gated composite (HAKE/BAKE calibration lit.):
- Cosine normalization in empirical range [min, max] -> [0, 1]
- O(1) cosine floor gate for early rejection (scales to billions)
- Per-layer-transition thresholds (different distributions per edge type)
- Top-K per transition (rank-based, not threshold-only)

Reference: HAKE (Zhang et al. AAAI 2020), BAKE (WWW 2026),
Model Calibration for Link Prediction (WWW 2024).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from engineering_brain.adapters.base import GraphAdapter
from engineering_brain.core.schema import EdgeType, NodeType

logger = logging.getLogger(__name__)


# Valid cross-layer transitions (source_layer, target_layer) -> EdgeType
LAYER_TRANSITIONS: dict[tuple[str, str], EdgeType] = {
    ("L0", "L1"): EdgeType.GROUNDS,
    ("L1", "L2"): EdgeType.INFORMS,
    ("L2", "L3"): EdgeType.INSTANTIATES,
}

# Map NodeType ID prefixes to layers
_PREFIX_TO_LAYER: dict[str, str] = {
    "AX-": "L0",
    "P-": "L1",
    "PAT-": "L2",
    "CPAT-": "L2",
    "CR-": "L3",
}

# Map layers to NodeType labels for querying
_LAYER_TO_LABEL: dict[str, str] = {
    "L0": NodeType.AXIOM.value,
    "L1": NodeType.PRINCIPLE.value,
    "L2": NodeType.PATTERN.value,
    "L3": NodeType.RULE.value,
}


@dataclass
class InferredEdge:
    """A single inferred cross-layer edge."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    confidence: float
    raw_cosine: float = 0.0
    method: str = "embedding_similarity"


def _node_layer(node_id: str) -> str:
    """Infer the layer of a node from its ID prefix."""
    nid = str(node_id).upper()
    for prefix, layer in _PREFIX_TO_LAYER.items():
        if nid.startswith(prefix):
            return layer
    return ""


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _normalize_cosine(
    raw: float,
    empirical_min: float = 0.25,
    empirical_max: float = 0.80,
) -> float:
    """Normalize cosine from empirical [min, max] to [0, 1].

    Essential because bge embeddings on this domain produce cosines
    in a narrow range (e.g. [0.25, 0.85]), not the theoretical [0, 1].
    Without normalization, thresholds are meaningless.
    """
    if empirical_max <= empirical_min:
        return raw
    return max(0.0, min(1.0, (raw - empirical_min) / (empirical_max - empirical_min)))


def _tech_overlap(source: dict[str, Any], target: dict[str, Any]) -> float:
    """Compute technology overlap between two nodes (0.0-1.0)."""
    s_techs = set(t.lower() for t in (source.get("technologies") or source.get("languages") or []))
    t_techs = set(t.lower() for t in (target.get("technologies") or target.get("languages") or []))
    if not s_techs and not t_techs:
        return 0.5  # Both tech-agnostic -> partial credit
    if not s_techs or not t_techs:
        return 0.3
    return len(s_techs & t_techs) / max(len(s_techs | t_techs), 1)


def _domain_overlap(source: dict[str, Any], target: dict[str, Any]) -> float:
    """Compute domain overlap between two nodes (0.0-1.0)."""
    s_domains = set(d.lower() for d in (source.get("domains") or []))
    t_domains = set(d.lower() for d in (target.get("domains") or []))
    if not s_domains and not t_domains:
        return 0.5
    if not s_domains or not t_domains:
        return 0.3
    return len(s_domains & t_domains) / max(len(s_domains | t_domains), 1)


class CrossLayerEdgeInferrer:
    """Infer cross-layer edges using normalized embedding similarity + type constraints.

    Uses SOTA scoring: cosine normalization, O(1) gate, per-transition thresholds,
    and top-K rank-based selection. Designed for epistemic graphs at scale.

    Augments the hardcoded tuple maps with dynamically inferred edges.
    Hardcoded edges always take precedence on conflict (merge_with_hardcoded).
    """

    def __init__(
        self,
        graph: GraphAdapter,
        embedder: Any,
        config: Any = None,
        vector_adapter: Any = None,
    ) -> None:
        self._graph = graph
        self._embedder = embedder
        self._config = config
        self._vector_adapter = vector_adapter  # ANN hook for O(K log N) at scale

        # Cosine normalization params
        self._cosine_floor: float = 0.25
        self._cosine_min: float = 0.25
        self._cosine_max: float = 0.80

        # Per-transition thresholds (SOTA: each edge type has different distribution)
        self._transition_thresholds: dict[EdgeType, float] = {
            EdgeType.GROUNDS: 0.35,
            EdgeType.INFORMS: 0.35,
            EdgeType.INSTANTIATES: 0.40,
        }

        # Top-K per transition (rank-based selection)
        self._top_k_per_transition: int = 50

        # Fallback single threshold (backward compat)
        self._similarity_threshold: float = 0.40

        if config:
            if hasattr(config, "cross_layer_cosine_floor"):
                self._cosine_floor = config.cross_layer_cosine_floor
            if hasattr(config, "cross_layer_cosine_min"):
                self._cosine_min = config.cross_layer_cosine_min
            if hasattr(config, "cross_layer_cosine_max"):
                self._cosine_max = config.cross_layer_cosine_max
            if hasattr(config, "cross_layer_top_k_per_transition"):
                self._top_k_per_transition = config.cross_layer_top_k_per_transition
            if hasattr(config, "cross_layer_similarity_threshold"):
                self._similarity_threshold = config.cross_layer_similarity_threshold
            # Per-transition overrides from config
            if hasattr(config, "cross_layer_grounds_threshold"):
                self._transition_thresholds[EdgeType.GROUNDS] = config.cross_layer_grounds_threshold
            if hasattr(config, "cross_layer_informs_threshold"):
                self._transition_thresholds[EdgeType.INFORMS] = config.cross_layer_informs_threshold
            if hasattr(config, "cross_layer_instantiates_threshold"):
                self._transition_thresholds[EdgeType.INSTANTIATES] = (
                    config.cross_layer_instantiates_threshold
                )

            # Backward compat: if user explicitly set BRAIN_CROSS_LAYER_SIM env var,
            # use that single threshold for all transitions
            if os.environ.get("BRAIN_CROSS_LAYER_SIM"):
                for et in self._transition_thresholds:
                    self._transition_thresholds[et] = self._similarity_threshold

    def _get_threshold(self, edge_type: EdgeType) -> float:
        """Get the threshold for a specific edge type."""
        return self._transition_thresholds.get(edge_type, self._similarity_threshold)

    def _embed_nodes(self, nodes: list[dict[str, Any]]) -> dict[str, list[float]]:
        """Embed a list of nodes, using batch embedding when available."""
        texts: list[str] = []
        ids: list[str] = []
        for node in nodes:
            nid = node.get("id", "")
            text = self._get_node_text(node)
            if nid and text:
                texts.append(text)
                ids.append(nid)

        if not texts:
            return {}

        # Try batch embedding first (much faster)
        vectors: list[list[float]] = []
        if hasattr(self._embedder, "embed_batch") and len(texts) > 1:
            try:
                vectors = self._embedder.embed_batch(texts)
            except Exception as exc:
                logger.debug("Batch embedding failed, falling back to one-by-one: %s", exc)
                vectors = []

        # Fallback to one-by-one
        if not vectors or len(vectors) != len(texts):
            vectors = []
            for text in texts:
                try:
                    vec = self._embedder.embed_text(text)
                    vectors.append(vec if vec else [])
                except Exception as exc:
                    logger.debug("Single text embedding failed: %s", exc)
                    vectors.append([])

        return {nid: vec for nid, vec in zip(ids, vectors, strict=False) if vec}

    def infer_edges(self, batch_size: int = 20) -> list[InferredEdge]:
        """Scan all valid cross-layer node pairs and infer missing edges.

        For each valid layer transition (L0->L1, L1->L2, L2->L3):
        1. Get all nodes in source and target layers
        2. Batch-embed all nodes
        3. Pairwise scoring with cosine gate + normalized composite
        4. Per-transition threshold + top-K selection
        """
        inferred: list[InferredEdge] = []

        for (src_layer, tgt_layer), edge_type in LAYER_TRANSITIONS.items():
            src_label = _LAYER_TO_LABEL.get(src_layer)
            tgt_label = _LAYER_TO_LABEL.get(tgt_layer)
            if not src_label or not tgt_label:
                continue

            src_nodes = self._graph.query(label=src_label, limit=500)
            tgt_nodes = self._graph.query(label=tgt_label, limit=500)

            if not src_nodes or not tgt_nodes:
                continue

            # Batch-embed all nodes
            src_vecs = self._embed_nodes(src_nodes)
            tgt_vecs = self._embed_nodes(tgt_nodes)

            # Build node lookup for metadata scoring
            src_lookup = {n.get("id", ""): n for n in src_nodes if n.get("id")}
            tgt_lookup = {n.get("id", ""): n for n in tgt_nodes if n.get("id")}

            # Per-transition threshold
            threshold = self._get_threshold(edge_type)

            # Compare pairs (brute-force; ANN candidate gen deferred until >10K nodes)
            transition_edges: list[InferredEdge] = []
            for src_id, src_vec in src_vecs.items():
                for tgt_id, tgt_vec in tgt_vecs.items():
                    # Skip if edge already exists
                    if self._graph.has_edge(src_id, tgt_id):
                        continue

                    confidence = self.validate_edge_score(
                        src_vec,
                        tgt_vec,
                        src_lookup.get(src_id, {}),
                        tgt_lookup.get(tgt_id, {}),
                    )
                    if confidence >= threshold:
                        transition_edges.append(
                            InferredEdge(
                                source_id=src_id,
                                target_id=tgt_id,
                                edge_type=edge_type,
                                confidence=confidence,
                                raw_cosine=_cosine_similarity(src_vec, tgt_vec),
                            )
                        )

            # Top-K per transition (rank-based selection)
            transition_edges.sort(key=lambda e: e.confidence, reverse=True)
            if self._top_k_per_transition > 0:
                transition_edges = transition_edges[: self._top_k_per_transition]

            inferred.extend(transition_edges)

        # Sort by confidence descending
        inferred.sort(key=lambda e: e.confidence, reverse=True)
        logger.info(
            "Inferred %d cross-layer edges (per-transition thresholds, top-K=%d)",
            len(inferred),
            self._top_k_per_transition,
        )
        return inferred

    def infer_for_node(self, node_id: str) -> list[InferredEdge]:
        """Infer edges for a single newly added node."""
        node = self._graph.get_node(node_id)
        if not node:
            return []

        layer = _node_layer(node_id)
        if not layer:
            return []

        text = self._get_node_text(node)
        if not text:
            return []

        try:
            node_vec = self._embedder.embed_text(text)
        except Exception as exc:
            logger.debug("Failed to embed node %s for inference: %s", node_id, exc)
            return []
        if not node_vec:
            return []

        inferred: list[InferredEdge] = []

        # Check where this node can connect (as source or target)
        for (src_layer, tgt_layer), edge_type in LAYER_TRANSITIONS.items():
            threshold = self._get_threshold(edge_type)

            if layer == src_layer:
                # This node is a source -> find targets
                tgt_label = _LAYER_TO_LABEL.get(tgt_layer)
                if not tgt_label:
                    continue
                candidates = self._graph.query(label=tgt_label, limit=200)
                for cand in candidates:
                    cid = cand.get("id", "")
                    if not cid or self._graph.has_edge(node_id, cid):
                        continue
                    cand_text = self._get_node_text(cand)
                    if not cand_text:
                        continue
                    try:
                        cand_vec = self._embedder.embed_text(cand_text)
                    except Exception as exc:
                        logger.debug("Failed to embed candidate %s: %s", cid, exc)
                        continue
                    if not cand_vec:
                        continue
                    confidence = self.validate_edge_score(node_vec, cand_vec, node, cand)
                    if confidence >= threshold:
                        inferred.append(
                            InferredEdge(
                                source_id=node_id,
                                target_id=cid,
                                edge_type=edge_type,
                                confidence=confidence,
                                raw_cosine=_cosine_similarity(node_vec, cand_vec),
                            )
                        )

            elif layer == tgt_layer:
                # This node is a target -> find sources
                src_label = _LAYER_TO_LABEL.get(src_layer)
                if not src_label:
                    continue
                candidates = self._graph.query(label=src_label, limit=200)
                for cand in candidates:
                    cid = cand.get("id", "")
                    if not cid or self._graph.has_edge(cid, node_id):
                        continue
                    cand_text = self._get_node_text(cand)
                    if not cand_text:
                        continue
                    try:
                        cand_vec = self._embedder.embed_text(cand_text)
                    except Exception as exc:
                        logger.debug("Failed to embed candidate %s: %s", cid, exc)
                        continue
                    if not cand_vec:
                        continue
                    confidence = self.validate_edge_score(cand_vec, node_vec, cand, node)
                    if confidence >= threshold:
                        inferred.append(
                            InferredEdge(
                                source_id=cid,
                                target_id=node_id,
                                edge_type=edge_type,
                                confidence=confidence,
                                raw_cosine=_cosine_similarity(cand_vec, node_vec),
                            )
                        )

        inferred.sort(key=lambda e: e.confidence, reverse=True)
        return inferred

    def validate_edge_score(
        self,
        src_vec: list[float],
        tgt_vec: list[float],
        source: dict[str, Any],
        target: dict[str, Any],
    ) -> float:
        """Score a proposed edge using normalized-cosine gated composite.

        SOTA scoring formula:
        1. Raw cosine similarity
        2. O(1) gate: reject if raw cosine < floor (crucial for scale)
        3. Normalize cosine to [0,1] in empirical range
        4. Weighted composite: norm_cos*0.55 + tech*0.20 + domain*0.15 + facet*0.10
        """
        raw_cosine = _cosine_similarity(src_vec, tgt_vec)

        # O(1) gate: early rejection for irrelevant pairs (scales to billions)
        if raw_cosine < self._cosine_floor:
            return 0.0

        # Normalize cosine to [0, 1] in empirical range
        norm_cosine = _normalize_cosine(raw_cosine, self._cosine_min, self._cosine_max)

        tech_sim = _tech_overlap(source, target)
        domain_sim = _domain_overlap(source, target)

        # Taxonomy facet overlap (optional, uses TagRegistry if available)
        facet_sim = 0.0
        try:
            from engineering_brain.core.taxonomy import get_registry

            registry = get_registry()
            if registry.size > 0:
                s_tags = list(
                    set((source.get("technologies") or []) + (source.get("domains") or []))
                )
                t_tags = list(
                    set((target.get("technologies") or []) + (target.get("domains") or []))
                )
                if s_tags and t_tags:
                    facet_sim = min(
                        registry.overlap_count(s_tags, t_tags) / max(len(s_tags), 1), 1.0
                    )
        except Exception as exc:
            logger.debug("Facet similarity computation failed: %s", exc)

        if facet_sim == 0.0:
            # Redistribute facet weight proportionally when facets unavailable
            return norm_cosine * 0.611 + tech_sim * 0.222 + domain_sim * 0.167
        return norm_cosine * 0.55 + tech_sim * 0.20 + domain_sim * 0.15 + facet_sim * 0.10

    def calibrate(
        self,
        ground_truth: list[tuple[str, str, str]],
    ) -> dict[str, Any]:
        """Calibrate thresholds against known-good edges (e.g. 72 hardcoded).

        For each ground-truth (src_id, tgt_id, edge_type_str), computes the
        score and reports per-transition recall and score distribution.

        Does NOT modify thresholds -- returns data for human decision.
        """
        results: dict[str, dict[str, Any]] = {}
        scores_by_type: dict[str, list[float]] = {}

        for src_id, tgt_id, edge_type_str in ground_truth:
            src = self._graph.get_node(src_id)
            tgt = self._graph.get_node(tgt_id)
            if not src or not tgt:
                continue

            src_text = self._get_node_text(src)
            tgt_text = self._get_node_text(tgt)
            if not src_text or not tgt_text:
                continue

            try:
                src_vec = self._embedder.embed_text(src_text)
                tgt_vec = self._embedder.embed_text(tgt_text)
            except Exception as exc:
                logger.debug("Failed to embed calibration pair (%s, %s): %s", src_id, tgt_id, exc)
                continue
            if not src_vec or not tgt_vec:
                continue

            score = self.validate_edge_score(src_vec, tgt_vec, src, tgt)
            scores_by_type.setdefault(edge_type_str, []).append(score)

        for edge_type_str, scores in scores_by_type.items():
            scores.sort()
            n = len(scores)
            threshold = self._transition_thresholds.get(
                EdgeType(edge_type_str),
                self._similarity_threshold,
            )
            recall = sum(1 for s in scores if s >= threshold) / max(n, 1)
            results[edge_type_str] = {
                "count": n,
                "recall_at_threshold": round(recall, 3),
                "threshold": threshold,
                "min": round(scores[0], 4) if scores else 0,
                "p25": round(scores[n // 4], 4) if n >= 4 else round(scores[0], 4) if scores else 0,
                "p50": round(scores[n // 2], 4) if n >= 2 else round(scores[0], 4) if scores else 0,
                "p75": round(scores[3 * n // 4], 4)
                if n >= 4
                else round(scores[-1], 4)
                if scores
                else 0,
                "max": round(scores[-1], 4) if scores else 0,
                "mean": round(sum(scores) / max(n, 1), 4),
            }

        return results

    def merge_with_hardcoded(
        self,
        hardcoded_edges: set[tuple[str, str]],
        inferred: list[InferredEdge],
    ) -> list[InferredEdge]:
        """Return only inferred edges that don't conflict with hardcoded ones."""
        return [
            edge for edge in inferred if (edge.source_id, edge.target_id) not in hardcoded_edges
        ]

    @staticmethod
    def _get_node_text(node: dict[str, Any]) -> str:
        """Extract the primary text from a node for embedding."""
        return str(
            node.get("text")
            or node.get("statement")
            or node.get("name")
            or node.get("description")
            or node.get("intent")
            or ""
        )
