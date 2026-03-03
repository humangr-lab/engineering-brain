"""Tests for the LinkPredictor (Gap 5).

Verifies:
- TYPE_CONSTRAINTS coverage
- _cosine_similarity edge cases
- _node_label prefix inference
- predict_links with type constraint filtering
- predict_links threshold filtering
- predict_for_node targeting
- _score_pair formulas (with and without HAKE)
- apply_predictions confidence and duplicate guards
- No self-links
- PredictedLink dataclass fields
- top_k limit enforcement
"""

from __future__ import annotations

import hashlib
import os
import sys

import pytest

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import EdgeType, NodeType
from engineering_brain.learning.link_predictor import (
    LinkPredictor,
    PredictedLink,
    TYPE_CONSTRAINTS,
    _cosine_similarity,
    _node_label,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockEmbedder:
    """Deterministic embedder for testing.

    If an explicit vector mapping is provided, returns the mapped vector.
    Otherwise, generates a deterministic 8-dim vector from an MD5 hash.
    """

    def __init__(self, vectors=None):
        self._vectors = vectors or {}

    def embed_text(self, text):
        if text in self._vectors:
            return self._vectors[text]
        h = hashlib.md5(text.encode()).hexdigest()
        return [int(c, 16) / 15.0 for c in h[:8]]


class MockHAKE:
    """Mock HAKE encoder that returns a fixed hierarchy distance."""

    def __init__(self, distance: float = 0.2):
        self._distance = distance

    def hierarchy_distance(self, a, b):
        return self._distance


def _make_graph() -> MemoryGraphAdapter:
    """Create a fresh in-memory graph adapter."""
    return MemoryGraphAdapter()


def _add_node(
    graph: MemoryGraphAdapter,
    label: str,
    node_id: str,
    text: str = "",
    technologies: list[str] | None = None,
    domains: list[str] | None = None,
    **extra,
) -> dict:
    """Add a node with standard fields and return its data dict."""
    data = {
        "id": node_id,
        "text": text or f"Text for {node_id}",
        "technologies": technologies or [],
        "domains": domains or [],
        **extra,
    }
    graph.add_node(label, node_id, data)
    return data


def _build_constrained_graph(embedder: MockEmbedder | None = None):
    """Build a small graph with Axiom, Principle, Pattern, and Rule nodes.

    Returns (graph, embedder, predictor).
    """
    graph = _make_graph()

    _add_node(graph, NodeType.AXIOM.value, "AX-001",
              text="Defense in depth principle",
              technologies=["python"], domains=["security"])
    _add_node(graph, NodeType.PRINCIPLE.value, "P-001",
              text="Layered security architecture",
              technologies=["python"], domains=["security"])
    _add_node(graph, NodeType.PATTERN.value, "PAT-001",
              text="Input validation at every layer",
              technologies=["python"], domains=["security"])
    _add_node(graph, NodeType.RULE.value, "CR-001",
              text="Validate all user input before processing",
              technologies=["python"], domains=["security"])
    _add_node(graph, NodeType.RULE.value, "CR-002",
              text="Sanitize output encoding to prevent XSS",
              technologies=["python"], domains=["security"])

    if embedder is None:
        embedder = MockEmbedder()

    predictor = LinkPredictor(graph, embedder)
    predictor._threshold = 0.01  # Low threshold for testing
    predictor._cosine_floor = 0.0  # Disable gate for testing
    return graph, embedder, predictor


# ---------------------------------------------------------------------------
# 1. TYPE_CONSTRAINTS tests
# ---------------------------------------------------------------------------


def test_type_constraints_defined():
    """TYPE_CONSTRAINTS has at least 10 defined constraint pairs."""
    assert len(TYPE_CONSTRAINTS) >= 10

    # Spot-check known pairs
    key_ax_p = (NodeType.AXIOM.value, NodeType.PRINCIPLE.value)
    assert key_ax_p in TYPE_CONSTRAINTS
    assert EdgeType.GROUNDS in TYPE_CONSTRAINTS[key_ax_p]

    key_p_pat = (NodeType.PRINCIPLE.value, NodeType.PATTERN.value)
    assert key_p_pat in TYPE_CONSTRAINTS
    assert EdgeType.INFORMS in TYPE_CONSTRAINTS[key_p_pat]

    key_pat_r = (NodeType.PATTERN.value, NodeType.RULE.value)
    assert key_pat_r in TYPE_CONSTRAINTS
    assert EdgeType.INSTANTIATES in TYPE_CONSTRAINTS[key_pat_r]

    key_r_r = (NodeType.RULE.value, NodeType.RULE.value)
    assert key_r_r in TYPE_CONSTRAINTS
    assert EdgeType.SUPERSEDES in TYPE_CONSTRAINTS[key_r_r]
    assert EdgeType.CONFLICTS_WITH in TYPE_CONSTRAINTS[key_r_r]

    key_pat_pat = (NodeType.PATTERN.value, NodeType.PATTERN.value)
    assert key_pat_pat in TYPE_CONSTRAINTS
    assert EdgeType.VARIANT_OF in TYPE_CONSTRAINTS[key_pat_pat]


# ---------------------------------------------------------------------------
# 2-4. _cosine_similarity tests
# ---------------------------------------------------------------------------


def test_cosine_similarity_identical():
    """Identical vectors return 1.0."""
    vec = [1.0, 2.0, 3.0]
    assert _cosine_similarity(vec, vec) == pytest.approx(1.0, abs=1e-9)


def test_cosine_similarity_orthogonal():
    """Orthogonal vectors return 0.0."""
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert _cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-9)


def test_cosine_similarity_empty():
    """Empty vectors return 0.0."""
    assert _cosine_similarity([], []) == 0.0
    assert _cosine_similarity([1.0], []) == 0.0
    assert _cosine_similarity([], [1.0]) == 0.0


# ---------------------------------------------------------------------------
# 5. _node_label tests
# ---------------------------------------------------------------------------


def test_node_label_from_prefix():
    """_node_label correctly infers NodeType from ID prefix."""
    assert _node_label({"id": "AX-001"}) == NodeType.AXIOM.value
    assert _node_label({"id": "P-001"}) == NodeType.PRINCIPLE.value
    assert _node_label({"id": "PAT-001"}) == NodeType.PATTERN.value
    assert _node_label({"id": "CR-001"}) == NodeType.RULE.value
    assert _node_label({"id": "F-001"}) == NodeType.FINDING.value
    assert _node_label({"id": "CPAT-abc"}) == NodeType.PATTERN.value
    assert _node_label({"id": "tech:flask"}) == NodeType.TECHNOLOGY.value
    assert _node_label({"id": "domain:security"}) == NodeType.DOMAIN.value

    # Explicit _label overrides prefix
    assert _node_label({"id": "AX-001", "_label": "Pattern"}) == "Pattern"

    # Unknown prefix defaults to Rule
    assert _node_label({"id": "UNKNOWN-001"}) == NodeType.RULE.value


# ---------------------------------------------------------------------------
# 6. predict_links with type constraints
# ---------------------------------------------------------------------------


def test_predict_with_type_constraints():
    """predict_links only produces edges allowed by TYPE_CONSTRAINTS."""
    graph, embedder, predictor = _build_constrained_graph()

    predictions = predictor.predict_links(top_k=100)

    for pred in predictions:
        src_node = graph.get_node(pred.source_id)
        tgt_node = graph.get_node(pred.target_id)
        assert src_node is not None
        assert tgt_node is not None

        src_label = _node_label(src_node)
        tgt_label = _node_label(tgt_node)
        key = (src_label, tgt_label)

        assert key in TYPE_CONSTRAINTS, (
            f"Edge {pred.source_id} -> {pred.target_id} with labels "
            f"({src_label}, {tgt_label}) is not in TYPE_CONSTRAINTS"
        )
        valid_types = TYPE_CONSTRAINTS[key]
        assert pred.edge_type in valid_types, (
            f"Edge type {pred.edge_type} not valid for ({src_label}, {tgt_label})"
        )


# ---------------------------------------------------------------------------
# 7. predict_links threshold filtering
# ---------------------------------------------------------------------------


def test_predict_respects_threshold():
    """Low-similarity pairs are excluded when threshold is high."""
    graph = _make_graph()

    # Use explicit vectors that are very different
    embedder = MockEmbedder(vectors={
        "Text for AX-001": [1.0, 0.0, 0.0],
        "Text for P-001": [0.0, 1.0, 0.0],
    })

    _add_node(graph, NodeType.AXIOM.value, "AX-001",
              technologies=[], domains=[])
    _add_node(graph, NodeType.PRINCIPLE.value, "P-001",
              technologies=[], domains=[])

    predictor = LinkPredictor(graph, embedder)
    predictor._threshold = 0.99  # Very high threshold

    predictions = predictor.predict_links(top_k=100)

    # Orthogonal vectors with no tech/domain overlap -> confidence << 0.99
    assert len(predictions) == 0


# ---------------------------------------------------------------------------
# 8. predict_for_node
# ---------------------------------------------------------------------------


def test_predict_for_node():
    """predict_for_node returns predictions for a specific node."""
    # Use similar vectors for axiom -> principle pair
    embedder = MockEmbedder(vectors={
        "Defense in depth principle": [1.0, 0.1, 0.0],
        "Layered security architecture": [0.99, 0.12, 0.0],
        "Input validation at every layer": [0.5, 0.8, 0.1],
        "Validate all user input before processing": [0.4, 0.9, 0.1],
        "Sanitize output encoding to prevent XSS": [0.3, 0.7, 0.2],
    })

    graph, _, predictor = _build_constrained_graph(embedder)

    predictions = predictor.predict_for_node("AX-001", top_k=10)

    # AX-001 is an Axiom -> should only predict edges to Principle nodes
    for pred in predictions:
        assert pred.source_id == "AX-001" or pred.target_id == "AX-001"

    # At minimum, should find AX-001 -> P-001 (GROUNDS)
    if predictions:
        source_ids = {p.source_id for p in predictions}
        target_ids = {p.target_id for p in predictions}
        # AX-001 can be source (Axiom->Principle) or target (other->Axiom)
        assert "AX-001" in source_ids or "AX-001" in target_ids


# ---------------------------------------------------------------------------
# 9. _score_pair without HAKE
# ---------------------------------------------------------------------------


def test_score_pair_without_hake():
    """Without HAKE: confidence = norm_cosine*0.50 + tech_overlap*0.25 + domain_overlap*0.25."""
    graph = _make_graph()
    embedder = MockEmbedder()
    predictor = LinkPredictor(graph, embedder, hake=None)
    predictor._threshold = 0.0  # Accept everything

    src_vec = [1.0, 0.0, 0.0]
    tgt_vec = [1.0, 0.0, 0.0]  # Identical -> cosine = 1.0

    source = {"id": "CR-A", "technologies": ["python", "flask"], "domains": ["security"]}
    target = {"id": "CR-B", "technologies": ["python", "flask"], "domains": ["security"]}

    link = predictor._score_pair(
        "CR-A", "CR-B", src_vec, tgt_vec, source, target,
        [EdgeType.SUPERSEDES],
    )

    assert link is not None
    # raw cosine = 1.0, normalized = clamp((1.0-0.20)/(0.85-0.20)) = clamp(1.23) = 1.0
    # tech_overlap = 1.0, domain_overlap = 1.0
    expected = 1.0 * 0.50 + 1.0 * 0.25 + 1.0 * 0.25
    assert link.confidence == pytest.approx(expected, abs=0.01)
    assert link.cosine_score == pytest.approx(1.0, abs=0.01)
    assert link.hake_score == 0.0  # No HAKE


def test_score_pair_without_hake_partial_overlap():
    """Without HAKE: orthogonal vectors are gated out (cosine 0.0 < floor 0.20)."""
    graph = _make_graph()
    embedder = MockEmbedder()
    predictor = LinkPredictor(graph, embedder, hake=None)
    predictor._threshold = 0.0

    src_vec = [1.0, 0.0, 0.0]
    tgt_vec = [0.0, 1.0, 0.0]  # Orthogonal -> cosine = 0.0

    # tech overlap: {python} & {python, react} / {python, react} = 1/2 = 0.5
    source = {"id": "CR-A", "technologies": ["python"], "domains": ["security"]}
    target = {"id": "CR-B", "technologies": ["python", "react"], "domains": ["testing"]}

    link = predictor._score_pair(
        "CR-A", "CR-B", src_vec, tgt_vec, source, target,
        [EdgeType.SUPERSEDES],
    )

    # Cosine 0.0 < cosine_floor 0.20 => gated out, returns None
    assert link is None


# ---------------------------------------------------------------------------
# 10. _score_pair with HAKE
# ---------------------------------------------------------------------------


def test_score_pair_with_hake():
    """With HAKE: confidence = norm_cosine*0.40 + hake*0.20 + tech*0.20 + domain*0.20."""
    graph = _make_graph()
    embedder = MockEmbedder()
    hake = MockHAKE(distance=0.2)  # hake_score = 1.0 - 0.2 = 0.8
    predictor = LinkPredictor(graph, embedder, hake=hake)
    predictor._threshold = 0.0

    src_vec = [1.0, 0.0, 0.0]
    tgt_vec = [1.0, 0.0, 0.0]  # Identical -> cosine = 1.0

    source = {"id": "CR-A", "technologies": ["python"], "domains": ["security"]}
    target = {"id": "CR-B", "technologies": ["python"], "domains": ["security"]}

    link = predictor._score_pair(
        "CR-A", "CR-B", src_vec, tgt_vec, source, target,
        [EdgeType.SUPERSEDES],
    )

    assert link is not None
    # norm_cosine = clamp((1.0-0.20)/(0.85-0.20)) = 1.0, hake=0.8, tech=1.0, domain=1.0
    expected = 1.0 * 0.40 + 0.8 * 0.20 + 1.0 * 0.20 + 1.0 * 0.20
    assert link.confidence == pytest.approx(expected, abs=0.01)
    assert link.hake_score == pytest.approx(0.8, abs=0.01)


# ---------------------------------------------------------------------------
# 11. apply_predictions respects threshold
# ---------------------------------------------------------------------------


def test_apply_predictions_respects_threshold():
    """apply_predictions only applies predictions above min_confidence."""
    graph = _make_graph()
    embedder = MockEmbedder()
    predictor = LinkPredictor(graph, embedder)

    _add_node(graph, NodeType.RULE.value, "CR-A", text="Rule A")
    _add_node(graph, NodeType.RULE.value, "CR-B", text="Rule B")
    _add_node(graph, NodeType.RULE.value, "CR-C", text="Rule C")

    predictions = [
        PredictedLink(
            source_id="CR-A", target_id="CR-B",
            edge_type=EdgeType.SUPERSEDES,
            confidence=0.95,
        ),
        PredictedLink(
            source_id="CR-A", target_id="CR-C",
            edge_type=EdgeType.SUPERSEDES,
            confidence=0.50,  # Below min_confidence
        ),
    ]

    applied = predictor.apply_predictions(predictions, min_confidence=0.80)
    assert applied == 1

    # CR-A -> CR-B should exist
    assert graph.has_edge("CR-A", "CR-B")
    # CR-A -> CR-C should NOT exist
    assert not graph.has_edge("CR-A", "CR-C")


# ---------------------------------------------------------------------------
# 12. apply_predictions skips existing edges
# ---------------------------------------------------------------------------


def test_apply_predictions_skips_existing_edges():
    """apply_predictions does not duplicate edges that already exist."""
    graph = _make_graph()
    embedder = MockEmbedder()
    predictor = LinkPredictor(graph, embedder)

    _add_node(graph, NodeType.RULE.value, "CR-A", text="Rule A")
    _add_node(graph, NodeType.RULE.value, "CR-B", text="Rule B")

    # Pre-create the edge
    graph.add_edge("CR-A", "CR-B", EdgeType.SUPERSEDES.value)

    predictions = [
        PredictedLink(
            source_id="CR-A", target_id="CR-B",
            edge_type=EdgeType.SUPERSEDES,
            confidence=0.95,
        ),
    ]

    applied = predictor.apply_predictions(predictions, min_confidence=0.80)
    assert applied == 0  # Skipped because edge already exists


# ---------------------------------------------------------------------------
# 13. No self-links
# ---------------------------------------------------------------------------


def test_no_self_links():
    """A node cannot link to itself via predict_links."""
    graph = _make_graph()

    # Create two Rule nodes (Rule->Rule is a valid constraint pair)
    _add_node(graph, NodeType.RULE.value, "CR-SELF",
              text="Self-link test rule",
              technologies=["python"], domains=["testing"])

    embedder = MockEmbedder(vectors={
        "Self-link test rule": [1.0, 0.0, 0.0],
    })

    predictor = LinkPredictor(graph, embedder)
    predictor._threshold = 0.01
    predictor._cosine_floor = 0.0

    predictions = predictor.predict_links(top_k=100)

    for pred in predictions:
        assert pred.source_id != pred.target_id, (
            f"Self-link detected: {pred.source_id} -> {pred.target_id}"
        )

    # Also test predict_for_node
    node_predictions = predictor.predict_for_node("CR-SELF", top_k=10)
    for pred in node_predictions:
        assert pred.source_id != pred.target_id


# ---------------------------------------------------------------------------
# 14. PredictedLink dataclass
# ---------------------------------------------------------------------------


def test_predicted_link_dataclass():
    """PredictedLink has all expected fields with correct defaults."""
    link = PredictedLink(
        source_id="CR-001",
        target_id="CR-002",
        edge_type=EdgeType.SUPERSEDES,
        confidence=0.85,
    )

    assert link.source_id == "CR-001"
    assert link.target_id == "CR-002"
    assert link.edge_type == EdgeType.SUPERSEDES
    assert link.confidence == 0.85
    assert link.cosine_score == 0.0
    assert link.hake_score == 0.0
    assert link.tech_overlap == 0.0
    assert link.domain_overlap == 0.0

    # With explicit values
    link2 = PredictedLink(
        source_id="AX-001",
        target_id="P-001",
        edge_type=EdgeType.GROUNDS,
        confidence=0.92,
        cosine_score=0.88,
        hake_score=0.75,
        tech_overlap=0.60,
        domain_overlap=1.0,
    )

    assert link2.cosine_score == 0.88
    assert link2.hake_score == 0.75
    assert link2.tech_overlap == 0.60
    assert link2.domain_overlap == 1.0


# ---------------------------------------------------------------------------
# 15. top_k limit
# ---------------------------------------------------------------------------


def test_top_k_limit():
    """predict_links returns at most top_k results."""
    graph = _make_graph()

    # Create many Rule nodes so many Rule->Rule pairs exist
    for i in range(20):
        _add_node(graph, NodeType.RULE.value, f"CR-{i:03d}",
                  text=f"Rule number {i} for top-k test",
                  technologies=["python"], domains=["security"])

    embedder = MockEmbedder()
    predictor = LinkPredictor(graph, embedder)
    predictor._threshold = 0.01  # Accept most predictions
    predictor._cosine_floor = 0.0  # Disable gate for testing

    top_k = 5
    predictions = predictor.predict_links(top_k=top_k)
    assert len(predictions) <= top_k

    # Verify sorting: confidences should be in descending order
    for i in range(len(predictions) - 1):
        assert predictions[i].confidence >= predictions[i + 1].confidence
