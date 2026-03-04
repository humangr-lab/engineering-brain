"""Tests for EigenTrust trust propagation."""

from __future__ import annotations

import pytest

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.epistemic.trust_propagation import TRUST_WEIGHTS, EigenTrustEngine


class TestEigenTrustBasic:
    def test_empty_graph_returns_empty(self):
        g = MemoryGraphAdapter()
        engine = EigenTrustEngine()
        scores = engine.compute(g)
        assert scores == {}

    def test_single_node_no_edges(self):
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX-001", {"id": "AX-001"})
        engine = EigenTrustEngine()
        scores = engine.compute(g)
        assert "AX-001" in scores
        # Single seed node gets all trust
        assert scores["AX-001"] == pytest.approx(1.0, abs=1e-3)

    def test_two_nodes_trust_flows_along_edge(self):
        """AX-001 → P-001: trust flows from seed to target."""
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX-001", {"id": "AX-001"})
        g.add_node("Principle", "P-001", {"id": "P-001"})
        g.add_edge("AX-001", "P-001", "GROUNDS")

        engine = EigenTrustEngine()
        scores = engine.compute(g)

        # Both nodes should have trust scores
        assert "AX-001" in scores
        assert "P-001" in scores
        # Trust should be > 0 for both
        assert scores["AX-001"] > 0.0
        assert scores["P-001"] > 0.0


class TestEigenTrustSeeds:
    def test_seeds_get_teleport_trust(self):
        """Seeds get trust via teleport even without incoming edges."""
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX-001", {"id": "AX-001"})
        g.add_node("Axiom", "AX-002", {"id": "AX-002"})
        g.add_node("Rule", "CR-001", {"id": "CR-001"})
        g.add_edge("AX-001", "CR-001", "GROUNDS")
        g.add_edge("AX-002", "CR-001", "GROUNDS")

        engine = EigenTrustEngine()
        scores = engine.compute(g)

        # All 3 nodes should have scores
        assert len(scores) == 3
        for s in scores.values():
            assert s > 0.0

    def test_more_incoming_edges_higher_trust(self):
        """Node receiving from multiple trusted sources gets higher trust."""
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX-001", {"id": "AX-001"})
        g.add_node("Axiom", "AX-002", {"id": "AX-002"})
        g.add_node("Rule", "CR-MULTI", {"id": "CR-MULTI"})
        g.add_node("Rule", "CR-SINGLE", {"id": "CR-SINGLE"})
        g.add_edge("AX-001", "CR-MULTI", "GROUNDS")
        g.add_edge("AX-002", "CR-MULTI", "GROUNDS")
        g.add_edge("AX-001", "CR-SINGLE", "GROUNDS")

        engine = EigenTrustEngine()
        scores = engine.compute(g)

        # CR-MULTI receives from 2 axioms, CR-SINGLE from 1
        assert scores["CR-MULTI"] > scores["CR-SINGLE"]


class TestEigenTrustEdgeTypes:
    def test_negative_edges_excluded(self):
        """CONFLICTS_WITH and WEAKENS have negative weights and are excluded from adjacency."""
        assert TRUST_WEIGHTS["CONFLICTS_WITH"] < 0
        assert TRUST_WEIGHTS["WEAKENS"] < 0

    def test_hierarchical_edges_highest_weight(self):
        assert TRUST_WEIGHTS["GROUNDS"] >= TRUST_WEIGHTS["INFORMS"]
        assert TRUST_WEIGHTS["INFORMS"] >= TRUST_WEIGHTS["INSTANTIATES"]

    def test_stronger_edge_more_trust(self):
        """Higher-weighted edges should transfer more trust."""
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX-001", {"id": "AX-001"})
        g.add_node("Rule", "CR-STRONG", {"id": "CR-STRONG"})
        g.add_node("Rule", "CR-WEAK", {"id": "CR-WEAK"})
        g.add_edge("AX-001", "CR-STRONG", "GROUNDS")  # weight 1.0
        g.add_edge("AX-001", "CR-WEAK", "APPLIES_TO")  # weight 0.3

        engine = EigenTrustEngine()
        scores = engine.compute(g)
        assert scores["CR-STRONG"] > scores["CR-WEAK"]


class TestEigenTrustConvergence:
    def test_converges_medium_graph(self):
        """Medium-sized graph should converge within 30 iterations."""
        g = MemoryGraphAdapter()
        for i in range(5):
            g.add_node("Axiom", f"AX-{i:03d}", {"id": f"AX-{i:03d}"})
        for i in range(10):
            g.add_node("Principle", f"P-{i:03d}", {"id": f"P-{i:03d}"})
            g.add_edge(f"AX-{i % 5:03d}", f"P-{i:03d}", "GROUNDS")
        for i in range(20):
            g.add_node("Rule", f"CR-{i:03d}", {"id": f"CR-{i:03d}"})
            g.add_edge(f"P-{i % 10:03d}", f"CR-{i:03d}", "INFORMS")

        engine = EigenTrustEngine(max_iterations=30, tolerance=1e-6)
        scores = engine.compute(g)

        assert len(scores) == 35

        for score in scores.values():
            assert 0.0 <= score <= 1.0 + 1e-9

    def test_scores_normalized_to_0_1(self):
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX-001", {"id": "AX-001"})
        g.add_node("Rule", "CR-001", {"id": "CR-001"})
        g.add_edge("AX-001", "CR-001", "GROUNDS")

        engine = EigenTrustEngine()
        scores = engine.compute(g)

        max_score = max(scores.values())
        assert max_score == pytest.approx(1.0, abs=1e-3)

    def test_no_negative_scores(self):
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001"})
        g.add_node("Rule", "CR-002", {"id": "CR-002"})
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")  # negative weight, excluded

        engine = EigenTrustEngine()
        scores = engine.compute(g)
        for s in scores.values():
            assert s >= 0.0
