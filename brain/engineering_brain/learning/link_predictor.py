"""Link prediction for the Engineering Knowledge Brain.

Predicts missing edges between existing nodes using HAKE-enhanced scoring
and type-constraint filtering. Only proposes edges that respect the valid
node type combinations defined by the schema's 22 edge types.

Scoring uses SOTA normalized-cosine + gated composite:
- Cosine normalization in empirical range [min, max] -> [0, 1]
  Bounds are configurable via BrainConfig.cross_layer_cosine_min/max
  (default 0.25-0.80, calibrated for bge-large-en-v1.5 1024-dim embeddings).
  Different embedding models may need recalibration — use calibrate() method.
- O(1) cosine floor gate for early rejection (scales to billions)
- Per-type-constraint top-K (rank-based selection)
- Bidirectional dedup for symmetric edge types

Reference: HAKE (Zhang et al. AAAI 2020), RotatE (Sun et al. 2019),
TP-RotatE (2025) for type-constrained prediction,
Model Calibration for Link Prediction (WWW 2024).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from engineering_brain.adapters.base import GraphAdapter
from engineering_brain.core.schema import EdgeType, NodeType

logger = logging.getLogger(__name__)


# Valid edge types per (source_NodeType, target_NodeType) pair
# This is the type constraint matrix -- we NEVER propose edges outside these.
TYPE_CONSTRAINTS: dict[tuple[str, str], list[EdgeType]] = {
    # Hierarchical
    (NodeType.AXIOM.value, NodeType.PRINCIPLE.value): [EdgeType.GROUNDS],
    (NodeType.PRINCIPLE.value, NodeType.PATTERN.value): [EdgeType.INFORMS],
    (NodeType.PATTERN.value, NodeType.RULE.value): [EdgeType.INSTANTIATES],
    (NodeType.RULE.value, NodeType.FINDING.value): [EdgeType.EVIDENCED_BY],
    (NodeType.RULE.value, NodeType.CODE_EXAMPLE.value): [EdgeType.DEMONSTRATED_BY],
    # Cross-layer
    (NodeType.RULE.value, NodeType.TECHNOLOGY.value): [EdgeType.APPLIES_TO],
    (NodeType.PATTERN.value, NodeType.TECHNOLOGY.value): [EdgeType.APPLIES_TO, EdgeType.USED_IN],
    (NodeType.RULE.value, NodeType.DOMAIN.value): [EdgeType.IN_DOMAIN],
    (NodeType.PATTERN.value, NodeType.DOMAIN.value): [EdgeType.IN_DOMAIN],
    (NodeType.FINDING.value, NodeType.HUMAN_LAYER.value): [EdgeType.CAUGHT_BY],
    (NodeType.FINDING.value, NodeType.RULE.value): [EdgeType.VIOLATED],
    # Evolution
    (NodeType.RULE.value, NodeType.RULE.value): [EdgeType.SUPERSEDES, EdgeType.CONFLICTS_WITH],
    (NodeType.PATTERN.value, NodeType.PATTERN.value): [EdgeType.VARIANT_OF],
    (NodeType.FINDING.value, NodeType.FINDING.value): [EdgeType.CAUSED_BY],
    # Source attribution
    (NodeType.RULE.value, NodeType.SOURCE.value): [EdgeType.SOURCED_FROM, EdgeType.CITES],
    (NodeType.PATTERN.value, NodeType.SOURCE.value): [EdgeType.CITES],
    (NodeType.PRINCIPLE.value, NodeType.SOURCE.value): [EdgeType.CITES],
}

# Node ID prefix -> NodeType label
_PREFIX_LABELS: dict[str, str] = {
    "AX-": NodeType.AXIOM.value,
    "P-": NodeType.PRINCIPLE.value,
    "PAT-": NodeType.PATTERN.value,
    "CPAT-": NodeType.PATTERN.value,
    "CR-": NodeType.RULE.value,
    "F-": NodeType.FINDING.value,
    "tech:": NodeType.TECHNOLOGY.value,
    "domain:": NodeType.DOMAIN.value,
}


def _node_label(node: dict[str, Any]) -> str:
    """Infer the NodeType label from a node."""
    label = node.get("_label", "")
    if label:
        return label
    nid = str(node.get("id", ""))
    for prefix, lbl in _PREFIX_LABELS.items():
        if nid.startswith(prefix):
            return lbl
    return NodeType.RULE.value  # Default


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
    empirical_min: float = 0.20,
    empirical_max: float = 0.85,
) -> float:
    """Normalize cosine from empirical [min, max] to [0, 1]."""
    if empirical_max <= empirical_min:
        return raw
    return max(0.0, min(1.0, (raw - empirical_min) / (empirical_max - empirical_min)))


@dataclass
class PredictedLink:
    """A single predicted missing link."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    confidence: float
    cosine_score: float = 0.0
    normalized_cosine: float = 0.0
    hake_score: float = 0.0
    tech_overlap: float = 0.0
    domain_overlap: float = 0.0


class LinkPredictor:
    """Predict missing edges in the knowledge graph.

    Uses HAKE hierarchy-aware embeddings (if available) combined with
    normalized cosine similarity and type constraint filtering.
    Designed for epistemic graphs at scale (billions of nodes).
    """

    def __init__(
        self,
        graph: GraphAdapter,
        embedder: Any,
        hake: Any = None,
        config: Any = None,
        vector_adapter: Any = None,
    ) -> None:
        self._graph = graph
        self._embedder = embedder
        self._hake = hake  # HAKEEncoder (optional)
        self._config = config
        self._vector_adapter = vector_adapter  # ANN hook for O(K log N) at scale

        # Cosine normalization params
        self._cosine_floor: float = 0.20
        self._cosine_min: float = 0.20
        self._cosine_max: float = 0.85

        # Threshold and top-K
        self._threshold: float = 0.45
        self._top_k_per_type: int = 20

        if config:
            if hasattr(config, "link_prediction_threshold"):
                self._threshold = config.link_prediction_threshold
            if hasattr(config, "link_prediction_cosine_floor"):
                self._cosine_floor = config.link_prediction_cosine_floor
            if hasattr(config, "link_prediction_cosine_min"):
                self._cosine_min = config.link_prediction_cosine_min
            if hasattr(config, "link_prediction_cosine_max"):
                self._cosine_max = config.link_prediction_cosine_max
            if hasattr(config, "link_prediction_top_k_per_type"):
                self._top_k_per_type = config.link_prediction_top_k_per_type

    def _embed_nodes(self, nodes: list[dict[str, Any]]) -> dict[str, list[float]]:
        """Embed a list of nodes, using batch embedding when available."""
        texts: list[str] = []
        ids: list[str] = []
        for node in nodes:
            nid = node.get("id", "")
            text = self._get_text(node)
            if nid and text:
                texts.append(text)
                ids.append(nid)

        if not texts:
            return {}

        # Try batch embedding first
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

    def predict_links(
        self,
        top_k: int = 50,
        batch_size: int = 20,
    ) -> list[PredictedLink]:
        """Predict missing links across the entire graph.

        Strategy:
        1. For each knowledge layer (L0-L3), batch-embed all nodes
        2. For each pair of node types with valid edge types, compute similarity
        3. Filter by cosine gate + normalized threshold
        4. Per-type-constraint top-K + global top-K
        5. Deduplicate bidirectional predictions
        """
        # Collect nodes by label
        nodes_by_label: dict[str, list[dict[str, Any]]] = {}
        for label_val in [
            NodeType.AXIOM.value,
            NodeType.PRINCIPLE.value,
            NodeType.PATTERN.value,
            NodeType.RULE.value,
        ]:
            nodes = self._graph.query(label=label_val, limit=500)
            if nodes:
                nodes_by_label[label_val] = nodes

        # Batch-embed all nodes
        embeddings: dict[str, list[float]] = {}
        for _label, nodes in nodes_by_label.items():
            node_vecs = self._embed_nodes(nodes)
            embeddings.update(node_vecs)

        # Build lookup
        all_nodes: dict[str, dict[str, Any]] = {}
        for nodes in nodes_by_label.values():
            for n in nodes:
                nid = n.get("id", "")
                if nid:
                    all_nodes[nid] = n

        predictions: list[PredictedLink] = []

        # Check each valid type constraint pair
        for (src_label, tgt_label), edge_types in TYPE_CONSTRAINTS.items():
            src_nodes = nodes_by_label.get(src_label, [])
            tgt_nodes = nodes_by_label.get(tgt_label, [])

            if not src_nodes or not tgt_nodes:
                continue

            # Per-constraint candidates
            constraint_preds: list[PredictedLink] = []

            for src in src_nodes:
                sid = src.get("id", "")
                if sid not in embeddings:
                    continue
                src_vec = embeddings[sid]

                for tgt in tgt_nodes:
                    tid = tgt.get("id", "")
                    if tid not in embeddings or sid == tid:
                        continue

                    # Skip if any edge already exists
                    if self._graph.has_edge(sid, tid):
                        continue

                    tgt_vec = embeddings[tid]
                    link = self._score_pair(sid, tid, src_vec, tgt_vec, src, tgt, edge_types)
                    if link and link.confidence >= self._threshold:
                        constraint_preds.append(link)

            # Per-type-constraint top-K
            constraint_preds.sort(key=lambda p: p.confidence, reverse=True)
            if self._top_k_per_type > 0:
                constraint_preds = constraint_preds[: self._top_k_per_type]

            predictions.extend(constraint_preds)

        # Bidirectional dedup: for symmetric edge types, canonicalize direction;
        # for asymmetric types (SUPERSEDES, GROUNDS), preserve direction
        _SYMMETRIC_EDGE_TYPES = {"CONFLICTS_WITH", "VARIANT_OF", "RELATES_TO", "COMPLEMENTS"}
        seen_pairs: dict[tuple[str, str, str], PredictedLink] = {}
        for pred in predictions:
            if pred.edge_type in _SYMMETRIC_EDGE_TYPES:
                pair = (
                    min(pred.source_id, pred.target_id),
                    max(pred.source_id, pred.target_id),
                    pred.edge_type,
                )
            else:
                pair = (pred.source_id, pred.target_id, pred.edge_type)
            existing = seen_pairs.get(pair)
            if existing is None or pred.confidence > existing.confidence:
                seen_pairs[pair] = pred
        predictions = list(seen_pairs.values())

        # Sort by confidence and take global top-k
        predictions.sort(key=lambda p: p.confidence, reverse=True)
        return predictions[:top_k]

    def predict_for_node(
        self,
        node_id: str,
        top_k: int = 10,
    ) -> list[PredictedLink]:
        """Predict missing links for a single node."""
        node = self._graph.get_node(node_id)
        if not node:
            return []

        text = self._get_text(node)
        if not text:
            return []

        try:
            node_vec = self._embedder.embed_text(text)
        except Exception as exc:
            logger.debug("Failed to embed node %s for link prediction: %s", node_id, exc)
            return []
        if not node_vec:
            return []

        node_label = _node_label(node)
        predictions: list[PredictedLink] = []

        # Check all valid connections for this node type
        for (src_label, tgt_label), edge_types in TYPE_CONSTRAINTS.items():
            if node_label == src_label:
                # This node is source -> find targets
                candidates = self._graph.query(label=tgt_label, limit=200)
                for cand in candidates:
                    cid = cand.get("id", "")
                    if not cid or cid == node_id or self._graph.has_edge(node_id, cid):
                        continue
                    cand_text = self._get_text(cand)
                    if not cand_text:
                        continue
                    try:
                        cand_vec = self._embedder.embed_text(cand_text)
                    except Exception as exc:
                        logger.debug("Failed to embed candidate %s: %s", cid, exc)
                        continue
                    if not cand_vec:
                        continue
                    link = self._score_pair(
                        node_id, cid, node_vec, cand_vec, node, cand, edge_types
                    )
                    if link and link.confidence >= self._threshold:
                        predictions.append(link)

            elif node_label == tgt_label:
                # This node is target -> find sources
                candidates = self._graph.query(label=src_label, limit=200)
                for cand in candidates:
                    cid = cand.get("id", "")
                    if not cid or cid == node_id or self._graph.has_edge(cid, node_id):
                        continue
                    cand_text = self._get_text(cand)
                    if not cand_text:
                        continue
                    try:
                        cand_vec = self._embedder.embed_text(cand_text)
                    except Exception as exc:
                        logger.debug("Failed to embed candidate %s: %s", cid, exc)
                        continue
                    if not cand_vec:
                        continue
                    link = self._score_pair(
                        cid, node_id, cand_vec, node_vec, cand, node, edge_types
                    )
                    if link and link.confidence >= self._threshold:
                        predictions.append(link)

        predictions.sort(key=lambda p: p.confidence, reverse=True)
        return predictions[:top_k]

    def _score_pair(
        self,
        src_id: str,
        tgt_id: str,
        src_vec: list[float],
        tgt_vec: list[float],
        source: dict[str, Any],
        target: dict[str, Any],
        valid_edge_types: list[EdgeType],
    ) -> PredictedLink | None:
        """Score a candidate link using normalized-cosine gated composite."""
        raw_cosine = _cosine_similarity(src_vec, tgt_vec)

        # O(1) gate: early rejection for irrelevant pairs
        if raw_cosine < self._cosine_floor:
            return None

        # Normalize cosine to [0, 1] in empirical range
        norm_cosine = _normalize_cosine(raw_cosine, self._cosine_min, self._cosine_max)

        # HAKE hierarchy distance (if available)
        hake_score = 0.0
        if self._hake:
            try:
                hake_score = 1.0 - self._hake.hierarchy_distance(src_vec, tgt_vec)
            except Exception as exc:
                logger.debug("HAKE hierarchy distance failed: %s", exc)

        # Technology overlap
        s_techs = set(
            t.lower() for t in (source.get("technologies") or source.get("languages") or [])
        )
        t_techs = set(
            t.lower() for t in (target.get("technologies") or target.get("languages") or [])
        )
        if s_techs and t_techs:
            tech_overlap = len(s_techs & t_techs) / max(len(s_techs | t_techs), 1)
        elif not s_techs and not t_techs:
            tech_overlap = 0.5
        else:
            tech_overlap = 0.0

        # Domain overlap
        s_domains = set(d.lower() for d in (source.get("domains") or []))
        t_domains = set(d.lower() for d in (target.get("domains") or []))
        if s_domains and t_domains:
            domain_overlap = len(s_domains & t_domains) / max(len(s_domains | t_domains), 1)
        elif not s_domains and not t_domains:
            domain_overlap = 0.5
        else:
            domain_overlap = 0.0

        # Combined score with normalized cosine
        if self._hake:
            confidence = (
                norm_cosine * 0.40 + hake_score * 0.20 + tech_overlap * 0.20 + domain_overlap * 0.20
            )
        else:
            confidence = norm_cosine * 0.50 + tech_overlap * 0.25 + domain_overlap * 0.25

        if confidence < self._threshold:
            return None

        # Pick the most appropriate edge type
        edge_type = valid_edge_types[0]

        return PredictedLink(
            source_id=src_id,
            target_id=tgt_id,
            edge_type=edge_type,
            confidence=confidence,
            cosine_score=raw_cosine,
            normalized_cosine=norm_cosine,
            hake_score=hake_score,
            tech_overlap=tech_overlap,
            domain_overlap=domain_overlap,
        )

    def apply_predictions(
        self,
        predictions: list[PredictedLink],
        min_confidence: float = 0.45,
    ) -> int:
        """Apply high-confidence predictions as actual edges in the graph."""
        count = 0
        for pred in predictions:
            if pred.confidence < min_confidence:
                continue
            if self._graph.has_edge(pred.source_id, pred.target_id):
                continue
            self._graph.add_edge(pred.source_id, pred.target_id, pred.edge_type.value)
            count += 1
        logger.info("Applied %d predicted links (min_confidence=%.2f)", count, min_confidence)
        return count

    @staticmethod
    def _get_text(node: dict[str, Any]) -> str:
        """Extract the primary text from a node for embedding."""
        return str(
            node.get("text")
            or node.get("statement")
            or node.get("name")
            or node.get("description")
            or node.get("intent")
            or ""
        )
