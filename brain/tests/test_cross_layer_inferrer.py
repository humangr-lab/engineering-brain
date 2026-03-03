"""Tests for the cross-layer edge inference system (Gap 1).

Covers:
- Layer transition definitions (L0->L1, L1->L2, L2->L3)
- Node-layer inference from ID prefix
- Edge type inference per layer pair
- Hierarchy constraint enforcement (no skip-layer edges)
- Threshold filtering
- Single-node edge inference
- Multi-signal edge scoring (embedding, tech, domain, facet)
- Merge with hardcoded edges (dedup vs keep)
- Batch processing parameter
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
from engineering_brain.learning.cross_layer_inferrer import (
    CrossLayerEdgeInferrer,
    InferredEdge,
    LAYER_TRANSITIONS,
    _node_layer,
)


# =============================================================================
# Mock embedder
# =============================================================================

class MockEmbedder:
    """Deterministic embedder that returns controllable vectors."""

    def __init__(self, vectors: dict[str, list[float]] | None = None) -> None:
        self._vectors = vectors or {}

    def embed_text(self, text: str) -> list[float]:
        if text in self._vectors:
            return self._vectors[text]
        # Return a deterministic vector based on hash
        h = hashlib.md5(text.encode()).hexdigest()
        return [int(c, 16) / 15.0 for c in h[:8]]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


# =============================================================================
# Helpers
# =============================================================================

def _make_graph() -> MemoryGraphAdapter:
    """Create a fresh in-memory graph adapter."""
    return MemoryGraphAdapter()


def _make_config(threshold: float = 0.1) -> BrainConfig:
    """Create a BrainConfig with a low similarity threshold for easy testing."""
    cfg = BrainConfig()
    cfg.cross_layer_similarity_threshold = threshold
    # Also set per-transition thresholds to match (tests expect uniform threshold)
    cfg.cross_layer_grounds_threshold = threshold
    cfg.cross_layer_informs_threshold = threshold
    cfg.cross_layer_instantiates_threshold = threshold
    return cfg


def _add_node(
    graph: MemoryGraphAdapter,
    node_type: str,
    node_id: str,
    text: str = "",
    **kwargs,
) -> dict:
    """Add a node to the graph and return its data dict."""
    data = {"id": node_id, "text": text, **kwargs}
    graph.add_node(node_type, node_id, data)
    return data


# =============================================================================
# Tests
# =============================================================================


class TestLayerTransitions:
    """Tests for LAYER_TRANSITIONS constant and _node_layer helper."""

    def test_layer_transitions_defined(self):
        """3 transitions exist: L0->L1, L1->L2, L2->L3."""
        assert len(LAYER_TRANSITIONS) == 3
        assert ("L0", "L1") in LAYER_TRANSITIONS
        assert ("L1", "L2") in LAYER_TRANSITIONS
        assert ("L2", "L3") in LAYER_TRANSITIONS

    def test_infer_layer_from_prefix(self):
        """AX- -> L0, P- -> L1, PAT- -> L2, CPAT- -> L2, CR- -> L3."""
        assert _node_layer("AX-001") == "L0"
        assert _node_layer("P-001") == "L1"
        assert _node_layer("PAT-001") == "L2"
        assert _node_layer("CPAT-001") == "L2"
        assert _node_layer("CR-001") == "L3"

    def test_infer_layer_unknown_prefix(self):
        """Unknown prefix returns empty string."""
        assert _node_layer("UNKNOWN-001") == ""
        assert _node_layer("") == ""


class TestEdgeTypeInference:
    """Tests for correct edge type per layer transition."""

    def test_infer_grounds_edge(self):
        """L0 -> L1 produces GROUNDS edge type."""
        graph = _make_graph()
        config = _make_config(threshold=0.1)

        # Add an L0 axiom and an L1 principle with identical text for high similarity
        shared_text = "separation of concerns in software design"
        embedder = MockEmbedder(vectors={shared_text: [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]})

        _add_node(graph, NodeType.AXIOM.value, "AX-001", text=shared_text)
        _add_node(graph, NodeType.PRINCIPLE.value, "P-001", text=shared_text)

        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)
        edges = inferrer.infer_edges()

        grounds_edges = [e for e in edges if e.edge_type == EdgeType.GROUNDS]
        assert len(grounds_edges) >= 1
        assert grounds_edges[0].source_id == "AX-001"
        assert grounds_edges[0].target_id == "P-001"
        assert grounds_edges[0].edge_type == EdgeType.GROUNDS

    def test_infer_informs_edge(self):
        """L1 -> L2 produces INFORMS edge type."""
        graph = _make_graph()
        config = _make_config(threshold=0.1)

        shared_text = "use dependency injection for testability"
        embedder = MockEmbedder(vectors={shared_text: [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]})

        _add_node(graph, NodeType.PRINCIPLE.value, "P-010", text=shared_text)
        _add_node(graph, NodeType.PATTERN.value, "PAT-010", text=shared_text)

        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)
        edges = inferrer.infer_edges()

        informs_edges = [e for e in edges if e.edge_type == EdgeType.INFORMS]
        assert len(informs_edges) >= 1
        assert informs_edges[0].source_id == "P-010"
        assert informs_edges[0].target_id == "PAT-010"
        assert informs_edges[0].edge_type == EdgeType.INFORMS

    def test_infer_instantiates_edge(self):
        """L2 -> L3 produces INSTANTIATES edge type."""
        graph = _make_graph()
        config = _make_config(threshold=0.1)

        shared_text = "always validate input at the boundary"
        embedder = MockEmbedder(vectors={shared_text: [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]})

        _add_node(graph, NodeType.PATTERN.value, "PAT-020", text=shared_text)
        _add_node(graph, NodeType.RULE.value, "CR-020", text=shared_text)

        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)
        edges = inferrer.infer_edges()

        inst_edges = [e for e in edges if e.edge_type == EdgeType.INSTANTIATES]
        assert len(inst_edges) >= 1
        assert inst_edges[0].source_id == "PAT-020"
        assert inst_edges[0].target_id == "CR-020"
        assert inst_edges[0].edge_type == EdgeType.INSTANTIATES


class TestHierarchyConstraints:
    """Tests for hierarchy enforcement: no skip-layer edges."""

    def test_no_direct_l0_to_l3(self):
        """L0 -> L3 is NOT a valid transition and should not be inferred."""
        graph = _make_graph()
        config = _make_config(threshold=0.01)  # Very low threshold

        shared_text = "fundamental truth about error handling"
        embedder = MockEmbedder(vectors={shared_text: [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]})

        _add_node(graph, NodeType.AXIOM.value, "AX-099", text=shared_text)
        _add_node(graph, NodeType.RULE.value, "CR-099", text=shared_text)

        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)
        edges = inferrer.infer_edges()

        # No direct L0->L3 edge should exist
        skip_edges = [
            e for e in edges
            if e.source_id == "AX-099" and e.target_id == "CR-099"
        ]
        assert len(skip_edges) == 0


class TestThresholdFiltering:
    """Tests for confidence threshold filtering."""

    def test_threshold_filtering(self):
        """Edges below the similarity threshold are filtered out."""
        graph = _make_graph()
        # Use a high threshold that blocks most hash-based embeddings
        config = _make_config(threshold=0.99)

        # Two different texts produce different hash-based vectors with low cosine
        _add_node(graph, NodeType.AXIOM.value, "AX-050", text="alpha concept xyz")
        _add_node(graph, NodeType.PRINCIPLE.value, "P-050", text="beta concept abc")

        embedder = MockEmbedder()  # Uses hash-based vectors (low similarity between different texts)
        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)
        edges = inferrer.infer_edges()

        # With high threshold and different texts, no edges should be inferred
        matching = [
            e for e in edges
            if e.source_id == "AX-050" and e.target_id == "P-050"
        ]
        assert len(matching) == 0

    def test_threshold_passes_high_similarity(self):
        """Edges above the threshold are included."""
        graph = _make_graph()
        config = _make_config(threshold=0.1)  # Low threshold

        shared_text = "identical text for high similarity"
        embedder = MockEmbedder(vectors={shared_text: [1.0, 0.5, 0.3, 0.2, 0.1, 0.8, 0.4, 0.6]})

        _add_node(graph, NodeType.AXIOM.value, "AX-051", text=shared_text)
        _add_node(graph, NodeType.PRINCIPLE.value, "P-051", text=shared_text)

        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)
        edges = inferrer.infer_edges()

        matching = [
            e for e in edges
            if e.source_id == "AX-051" and e.target_id == "P-051"
        ]
        assert len(matching) == 1
        assert matching[0].confidence >= 0.1


class TestInferForNode:
    """Tests for single-node edge inference."""

    def test_infer_for_node_single(self):
        """Infers edges for a specific node added to the graph."""
        graph = _make_graph()
        config = _make_config(threshold=0.1)

        shared_text = "consistent naming conventions"
        embedder = MockEmbedder(vectors={shared_text: [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]})

        # Pre-populate graph with an L1 principle
        _add_node(graph, NodeType.PRINCIPLE.value, "P-100", text=shared_text)
        # Add the L0 axiom we want to infer edges for
        _add_node(graph, NodeType.AXIOM.value, "AX-100", text=shared_text)

        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)
        edges = inferrer.infer_for_node("AX-100")

        # AX-100 is L0, so it should connect to L1 nodes with GROUNDS
        assert len(edges) >= 1
        assert edges[0].source_id == "AX-100"
        assert edges[0].target_id == "P-100"
        assert edges[0].edge_type == EdgeType.GROUNDS

    def test_infer_for_node_as_target(self):
        """When a target-layer node is added, source-layer edges are inferred."""
        graph = _make_graph()
        config = _make_config(threshold=0.1)

        shared_text = "abstraction layers for clean code"
        embedder = MockEmbedder(vectors={shared_text: [0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.9]})

        # Pre-populate graph with an L0 axiom
        _add_node(graph, NodeType.AXIOM.value, "AX-200", text=shared_text)
        # Add the L1 principle we want to infer edges for
        _add_node(graph, NodeType.PRINCIPLE.value, "P-200", text=shared_text)

        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)
        edges = inferrer.infer_for_node("P-200")

        # P-200 is L1 target in L0->L1, so AX-200 should be inferred as source
        assert len(edges) >= 1
        assert edges[0].source_id == "AX-200"
        assert edges[0].target_id == "P-200"
        assert edges[0].edge_type == EdgeType.GROUNDS

    def test_infer_for_node_unknown(self):
        """Inferring for a non-existent node returns empty list."""
        graph = _make_graph()
        config = _make_config()
        embedder = MockEmbedder()
        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)

        edges = inferrer.infer_for_node("NONEXISTENT-999")
        assert edges == []


class TestValidateEdgeScore:
    """Tests for multi-signal edge scoring."""

    def test_validate_edge_score_components(self):
        """Verify that validate_edge_score combines normalized cosine + metadata signals.

        SOTA weights: normalized_cosine (0.55), tech overlap (0.20),
                      domain overlap (0.15), facet overlap (0.10).
        Cosine is normalized from empirical [0.25, 0.80] to [0, 1].
        When facets are unavailable (facet_sim == 0.0), the 0.10 facet weight
        is redistributed proportionally: cos=0.611, tech=0.222, domain=0.167.
        """
        graph = _make_graph()
        config = _make_config()
        embedder = MockEmbedder()
        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)

        # Identical unit vectors => raw cosine = 1.0
        # Normalized: min(1.0, (1.0 - 0.25) / (0.80 - 0.25)) = min(1.0, 1.36) = 1.0
        src_vec = [1.0, 0.0, 0.0, 0.0]
        tgt_vec = [1.0, 0.0, 0.0, 0.0]

        # Both have no tech and no domains => tech_overlap = 0.5, domain_overlap = 0.5
        source = {"id": "AX-001"}
        target = {"id": "P-001"}

        score = inferrer.validate_edge_score(src_vec, tgt_vec, source, target)

        # No facets available => weight redistribution:
        # Expected: 1.0 * 0.611 + 0.5 * 0.222 + 0.5 * 0.167 = 0.611 + 0.111 + 0.0835 = 0.8055
        assert abs(score - 0.8055) < 0.02

    def test_validate_edge_score_zero_embedding(self):
        """Orthogonal vectors are gated out (cosine 0.0 < floor 0.25)."""
        graph = _make_graph()
        config = _make_config()
        embedder = MockEmbedder()
        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)

        # Orthogonal vectors => cosine = 0.0 < cosine_floor (0.25)
        src_vec = [1.0, 0.0, 0.0, 0.0]
        tgt_vec = [0.0, 1.0, 0.0, 0.0]

        source = {"id": "AX-001"}
        target = {"id": "P-001"}

        score = inferrer.validate_edge_score(src_vec, tgt_vec, source, target)

        # Gated: raw cosine 0.0 < floor 0.25 => returns 0.0
        assert score == 0.0

    def test_tech_overlap_boosts_score(self):
        """Shared technologies increase the overall score."""
        graph = _make_graph()
        config = _make_config()
        embedder = MockEmbedder()
        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)

        # Same vector => cosine = 1.0
        vec = [1.0, 0.5, 0.3, 0.2]

        # Shared technologies
        source = {"id": "AX-001", "technologies": ["Python", "FastAPI"]}
        target = {"id": "P-001", "technologies": ["Python", "FastAPI"]}

        score_with_tech = inferrer.validate_edge_score(vec, vec, source, target)

        # No tech overlap: different technologies
        source_no = {"id": "AX-001", "technologies": ["Java"]}
        target_no = {"id": "P-001", "technologies": ["Rust"]}

        score_without_tech = inferrer.validate_edge_score(vec, vec, source_no, target_no)

        # Full tech overlap (1.0 * 0.25) > zero tech overlap (0.0 * 0.25)
        assert score_with_tech > score_without_tech

    def test_domain_overlap_boosts_score(self):
        """Shared domains increase the overall score."""
        graph = _make_graph()
        config = _make_config()
        embedder = MockEmbedder()
        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)

        vec = [1.0, 0.5, 0.3, 0.2]

        # Shared domains
        source = {"id": "AX-001", "domains": ["security", "testing"]}
        target = {"id": "P-001", "domains": ["security", "testing"]}

        score_with_domain = inferrer.validate_edge_score(vec, vec, source, target)

        # No domain overlap: disjoint domains
        source_no = {"id": "AX-001", "domains": ["security"]}
        target_no = {"id": "P-001", "domains": ["database"]}

        score_without_domain = inferrer.validate_edge_score(vec, vec, source_no, target_no)

        # Full domain overlap (1.0 * 0.15) > zero domain overlap (0.0 * 0.15)
        assert score_with_domain > score_without_domain


class TestMergeWithHardcoded:
    """Tests for merge_with_hardcoded dedup behavior."""

    def test_merge_with_hardcoded_removes_duplicates(self):
        """Inferred edges that match hardcoded edges are removed."""
        graph = _make_graph()
        config = _make_config()
        embedder = MockEmbedder()
        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)

        hardcoded = {("AX-001", "P-001"), ("AX-002", "P-002")}

        inferred = [
            InferredEdge(source_id="AX-001", target_id="P-001", edge_type=EdgeType.GROUNDS, confidence=0.9),
            InferredEdge(source_id="AX-003", target_id="P-003", edge_type=EdgeType.GROUNDS, confidence=0.8),
        ]

        result = inferrer.merge_with_hardcoded(hardcoded, inferred)

        # AX-001 -> P-001 is hardcoded, so it should be removed
        assert len(result) == 1
        assert result[0].source_id == "AX-003"
        assert result[0].target_id == "P-003"

    def test_merge_with_hardcoded_keeps_non_overlapping(self):
        """Non-overlapping inferred edges are preserved."""
        graph = _make_graph()
        config = _make_config()
        embedder = MockEmbedder()
        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)

        hardcoded = {("AX-001", "P-001")}

        inferred = [
            InferredEdge(source_id="AX-010", target_id="P-010", edge_type=EdgeType.GROUNDS, confidence=0.85),
            InferredEdge(source_id="P-020", target_id="PAT-020", edge_type=EdgeType.INFORMS, confidence=0.75),
            InferredEdge(source_id="PAT-030", target_id="CR-030", edge_type=EdgeType.INSTANTIATES, confidence=0.65),
        ]

        result = inferrer.merge_with_hardcoded(hardcoded, inferred)

        # None of the inferred edges overlap with hardcoded, all should be kept
        assert len(result) == 3

    def test_merge_with_hardcoded_all_duplicates(self):
        """When all inferred edges are hardcoded, result is empty."""
        graph = _make_graph()
        config = _make_config()
        embedder = MockEmbedder()
        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)

        hardcoded = {("AX-001", "P-001"), ("AX-002", "P-002")}

        inferred = [
            InferredEdge(source_id="AX-001", target_id="P-001", edge_type=EdgeType.GROUNDS, confidence=0.9),
            InferredEdge(source_id="AX-002", target_id="P-002", edge_type=EdgeType.GROUNDS, confidence=0.8),
        ]

        result = inferrer.merge_with_hardcoded(hardcoded, inferred)
        assert len(result) == 0


class TestBatchProcessing:
    """Tests for the batch_size parameter in infer_edges."""

    def test_batch_processing(self):
        """batch_size parameter controls embedding batching without affecting results."""
        graph = _make_graph()
        config = _make_config(threshold=0.1)

        shared_text = "batch processing validation text"
        embedder = MockEmbedder(vectors={shared_text: [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]})

        # Create multiple nodes to exceed a small batch size
        for i in range(5):
            _add_node(graph, NodeType.AXIOM.value, f"AX-B{i:02d}", text=shared_text)
        for i in range(5):
            _add_node(graph, NodeType.PRINCIPLE.value, f"P-B{i:02d}", text=shared_text)

        inferrer = CrossLayerEdgeInferrer(graph, embedder, config)

        # Run with small batch size
        edges_small = inferrer.infer_edges(batch_size=2)

        # Run with large batch size
        edges_large = inferrer.infer_edges(batch_size=100)

        # Results should be identical regardless of batch size
        assert len(edges_small) == len(edges_large)

        # All should be GROUNDS edges (L0 -> L1)
        for edge in edges_small:
            assert edge.edge_type == EdgeType.GROUNDS

        # Should produce 5 * 5 = 25 edges (all pairs, identical text = max similarity)
        assert len(edges_small) == 25


class TestInferredEdgeDataclass:
    """Tests for the InferredEdge dataclass defaults."""

    def test_inferred_edge_defaults(self):
        """InferredEdge has correct default method field."""
        edge = InferredEdge(
            source_id="AX-001",
            target_id="P-001",
            edge_type=EdgeType.GROUNDS,
            confidence=0.85,
        )
        assert edge.method == "embedding_similarity"
        assert edge.source_id == "AX-001"
        assert edge.target_id == "P-001"
        assert edge.edge_type == EdgeType.GROUNDS
        assert edge.confidence == 0.85

    def test_inferred_edge_custom_method(self):
        """InferredEdge method can be overridden."""
        edge = InferredEdge(
            source_id="P-001",
            target_id="PAT-001",
            edge_type=EdgeType.INFORMS,
            confidence=0.90,
            method="manual",
        )
        assert edge.method == "manual"
