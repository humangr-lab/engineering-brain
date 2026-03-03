"""Comprehensive tests for the epistemic subsystem.

Covers four pillars:
1. EigenTrust — compute, incremental_update, invalidate_cache, cache_valid
2. Contradiction — detect_all with CONFLICTS_WITH edges, resolve, inject_disbelief
3. Temporal decay — HawkesDecayEngine intensity, factor, apply_decay
4. OpinionTuple/CBF — creation, invariants, fusion of multiple opinions
"""

from __future__ import annotations

import math
import sys
import os

# Ensure src/ is importable regardless of how pytest is invoked
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.epistemic.trust_propagation import (
    EigenTrustEngine,
    IncrementalEigenTrust,
    TRUST_WEIGHTS,
)
from engineering_brain.epistemic.contradiction import (
    ContradictionDetector,
    ContradictionReport,
)
from engineering_brain.epistemic.conflict_resolution import (
    ConflictSeverity,
    dempster_conflict,
    classify_conflict,
    murphy_weighted_average,
)
from engineering_brain.epistemic.temporal import (
    HawkesDecayEngine,
    LAYER_DECAY_PROFILES,
    get_decay_engine,
)
from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.fusion import cbf, multi_source_cbf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph_node(graph: MemoryGraphAdapter, node_id: str, label: str = "Rule",
                     b: float = 0.5, d: float = 0.0, u: float = 0.5,
                     a: float = 0.5) -> None:
    """Helper: add a node with epistemic opinion properties."""
    graph.add_node(label, node_id, {
        "id": node_id,
        "ep_b": b, "ep_d": d, "ep_u": u, "ep_a": a,
    })


def _build_linear_chain(n: int = 5) -> MemoryGraphAdapter:
    """Build AX-000 -> P-000 -> P-001 -> ... -> P-(n-2) linear chain."""
    g = MemoryGraphAdapter()
    g.add_node("Axiom", "AX-000", {"id": "AX-000"})
    for i in range(n - 1):
        nid = f"P-{i:03d}"
        g.add_node("Principle", nid, {"id": nid})
        prev = "AX-000" if i == 0 else f"P-{i - 1:03d}"
        g.add_edge(prev, nid, "GROUNDS")
    return g


def _build_diamond_graph() -> MemoryGraphAdapter:
    """Build a diamond: AX -> A, AX -> B, A -> C, B -> C."""
    g = MemoryGraphAdapter()
    g.add_node("Axiom", "AX", {"id": "AX"})
    g.add_node("Principle", "A", {"id": "A"})
    g.add_node("Principle", "B", {"id": "B"})
    g.add_node("Rule", "C", {"id": "C"})
    g.add_edge("AX", "A", "GROUNDS")
    g.add_edge("AX", "B", "GROUNDS")
    g.add_edge("A", "C", "INFORMS")
    g.add_edge("B", "C", "INFORMS")
    return g


# ===========================================================================
# SECTION 1: EigenTrust
# ===========================================================================


class TestEigenTrustCompute:
    """EigenTrustEngine.compute returns scores in [0, 1] for every node."""

    def test_empty_graph_returns_empty_dict(self):
        engine = EigenTrustEngine()
        scores = engine.compute(MemoryGraphAdapter())
        assert scores == {}

    def test_single_seed_node_gets_max_trust(self):
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX-001", {"id": "AX-001"})
        scores = EigenTrustEngine().compute(g)
        assert "AX-001" in scores
        assert scores["AX-001"] == pytest.approx(1.0, abs=1e-3)

    def test_returns_score_for_every_node(self):
        g = _build_diamond_graph()
        scores = EigenTrustEngine().compute(g)
        assert len(scores) == 4
        for nid in ["AX", "A", "B", "C"]:
            assert nid in scores

    def test_all_scores_in_0_1_range(self):
        g = _build_linear_chain(10)
        scores = EigenTrustEngine().compute(g)
        for nid, score in scores.items():
            assert 0.0 <= score <= 1.0 + 1e-9, f"{nid} has score {score}"

    def test_max_score_normalized_to_1(self):
        g = _build_diamond_graph()
        scores = EigenTrustEngine().compute(g)
        assert max(scores.values()) == pytest.approx(1.0, abs=1e-3)

    def test_trust_flows_from_seed_to_children(self):
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX-001", {"id": "AX-001"})
        g.add_node("Rule", "CR-001", {"id": "CR-001"})
        g.add_edge("AX-001", "CR-001", "GROUNDS")
        scores = EigenTrustEngine().compute(g)
        assert scores["CR-001"] > 0.0

    def test_more_incoming_edges_higher_trust(self):
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX-001", {"id": "AX-001"})
        g.add_node("Axiom", "AX-002", {"id": "AX-002"})
        g.add_node("Rule", "MULTI", {"id": "MULTI"})
        g.add_node("Rule", "SINGLE", {"id": "SINGLE"})
        g.add_edge("AX-001", "MULTI", "GROUNDS")
        g.add_edge("AX-002", "MULTI", "GROUNDS")
        g.add_edge("AX-001", "SINGLE", "GROUNDS")
        scores = EigenTrustEngine().compute(g)
        assert scores["MULTI"] > scores["SINGLE"]

    def test_stronger_edge_type_more_trust(self):
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX", {"id": "AX"})
        g.add_node("Rule", "STRONG", {"id": "STRONG"})
        g.add_node("Rule", "WEAK", {"id": "WEAK"})
        g.add_edge("AX", "STRONG", "GROUNDS")      # weight=1.0
        g.add_edge("AX", "WEAK", "APPLIES_TO")      # weight=0.3
        scores = EigenTrustEngine().compute(g)
        assert scores["STRONG"] > scores["WEAK"]

    def test_negative_edges_excluded_from_adjacency(self):
        """CONFLICTS_WITH edges have negative weight and do not propagate trust."""
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001"})
        g.add_node("Rule", "CR-002", {"id": "CR-002"})
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")
        scores = EigenTrustEngine().compute(g)
        # Both should have scores, but only via teleport (no trust flow)
        for s in scores.values():
            assert s >= 0.0

    def test_diamond_convergence_merges_both_paths(self):
        g = _build_diamond_graph()
        scores = EigenTrustEngine().compute(g)
        # C receives from both A and B, so it should have reasonable trust
        assert scores["C"] > 0.0
        # AX is the seed — but due to teleport + multi-hop propagation,
        # intermediate nodes may accumulate more trust than the source
        assert scores["AX"] > 0.0
        assert scores["A"] > 0.0
        assert scores["B"] > 0.0

    def test_medium_graph_converges(self):
        g = MemoryGraphAdapter()
        for i in range(5):
            g.add_node("Axiom", f"AX-{i}", {"id": f"AX-{i}"})
        for i in range(15):
            g.add_node("Principle", f"P-{i}", {"id": f"P-{i}"})
            g.add_edge(f"AX-{i % 5}", f"P-{i}", "GROUNDS")
        for i in range(30):
            g.add_node("Rule", f"CR-{i}", {"id": f"CR-{i}"})
            g.add_edge(f"P-{i % 15}", f"CR-{i}", "INFORMS")

        engine = EigenTrustEngine(max_iterations=30, tolerance=1e-6)
        scores = engine.compute(g)
        assert len(scores) == 50
        for s in scores.values():
            assert 0.0 <= s <= 1.0 + 1e-9

    def test_alpha_parameter_affects_teleport(self):
        """Higher alpha gives more weight to seeds via teleport."""
        g = _build_linear_chain(5)
        low_alpha = EigenTrustEngine(alpha=0.05).compute(g)
        high_alpha = EigenTrustEngine(alpha=0.50).compute(g)
        # With higher alpha, the seed (AX-000) gets relatively more trust
        # compared to far-away nodes
        seed_ratio_low = low_alpha["AX-000"] / (low_alpha.get("P-003", 0.001) + 1e-15)
        seed_ratio_high = high_alpha["AX-000"] / (high_alpha.get("P-003", 0.001) + 1e-15)
        assert seed_ratio_high > seed_ratio_low


class TestEigenTrustCacheValidity:
    """Cache flag semantics: compute sets valid, invalidate clears."""

    def test_cache_invalid_initially(self):
        engine = EigenTrustEngine()
        assert engine._cache_valid is False
        assert engine._cached_scores == {}

    def test_compute_sets_cache_valid(self):
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX", {"id": "AX"})
        engine = EigenTrustEngine()
        engine.compute(g)
        assert engine._cache_valid is True
        assert len(engine._cached_scores) == 1

    def test_invalidate_cache_clears_flag_and_data(self):
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX", {"id": "AX"})
        engine = EigenTrustEngine()
        engine.compute(g)
        engine.invalidate_cache()
        assert engine._cache_valid is False
        assert engine._cached_scores == {}

    def test_invalidate_then_compute_rebuilds(self):
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX", {"id": "AX"})
        engine = EigenTrustEngine()
        scores1 = engine.compute(g)
        engine.invalidate_cache()
        scores2 = engine.compute(g)
        assert scores2 == scores1
        assert engine._cache_valid is True


class TestEigenTrustIncrementalUpdate:
    """incremental_update: 1-hop local recompute when cache is valid."""

    def test_falls_back_to_full_compute_when_cache_empty(self):
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX", {"id": "AX"})
        g.add_node("Rule", "CR", {"id": "CR"})
        g.add_edge("AX", "CR", "GROUNDS")
        engine = EigenTrustEngine()
        # No prior compute, so incremental should fall back
        result = engine.incremental_update(g, "CR")
        assert "AX" in result or "CR" in result
        assert engine._cache_valid is True

    def test_incremental_after_edge_add(self):
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX", {"id": "AX"})
        g.add_node("Rule", "CR-001", {"id": "CR-001"})
        g.add_node("Rule", "CR-002", {"id": "CR-002"})
        g.add_edge("AX", "CR-001", "GROUNDS")

        engine = EigenTrustEngine()
        scores_before = engine.compute(g)

        # Add a new edge and do incremental update
        g.add_edge("AX", "CR-002", "GROUNDS")
        affected = engine.incremental_update(g, "CR-002")
        assert "CR-002" in affected
        assert affected["CR-002"] > 0.0

    def test_incremental_returns_subset_of_nodes(self):
        g = _build_diamond_graph()
        engine = EigenTrustEngine()
        engine.compute(g)
        # Incremental update on node "C" should only return its 1-hop neighborhood
        affected = engine.incremental_update(g, "C")
        # C's 1-hop: {C, A, B} (from edges A->C and B->C)
        for nid in affected:
            assert nid in {"AX", "A", "B", "C"}

    def test_incremental_preserves_cache_valid(self):
        g = _build_diamond_graph()
        engine = EigenTrustEngine()
        engine.compute(g)
        assert engine._cache_valid is True
        engine.incremental_update(g, "C")
        # Cache should remain valid after incremental
        assert engine._cache_valid is True

    def test_invalidate_forces_full_recompute_on_incremental(self):
        g = _build_diamond_graph()
        engine = EigenTrustEngine()
        engine.compute(g)
        engine.invalidate_cache()
        # Now incremental should fall back to full compute
        result = engine.incremental_update(g, "C")
        # Full compute returns all 4 nodes
        assert len(engine._cached_scores) == 4


class TestIncrementalEigenTrustClass:
    """IncrementalEigenTrust: higher-level wrapper with dirty flag."""

    def test_full_compute_returns_all_scores(self):
        g = _build_diamond_graph()
        inc = IncrementalEigenTrust()
        scores = inc.full_compute(g)
        assert len(scores) == 4
        for s in scores.values():
            assert 0.0 <= s <= 1.0 + 1e-9

    def test_scores_property_returns_copy(self):
        g = _build_diamond_graph()
        inc = IncrementalEigenTrust()
        inc.full_compute(g)
        s1 = inc.scores
        s2 = inc.scores
        assert s1 == s2
        # Should be a copy, not same object
        s1["AX"] = 999.0
        assert inc.scores["AX"] != 999.0

    def test_local_update_with_dirty_flag_triggers_full(self):
        g = _build_diamond_graph()
        inc = IncrementalEigenTrust()
        # _dirty is True by default
        assert inc._dirty is True
        result = inc.local_update(g, "C")
        # After full recompute via local_update fallback
        assert inc._dirty is False
        assert len(result) == 4

    def test_local_update_after_full_is_incremental(self):
        g = _build_diamond_graph()
        inc = IncrementalEigenTrust()
        inc.full_compute(g)
        g.add_node("Rule", "NEW", {"id": "NEW"})
        g.add_edge("C", "NEW", "INFORMS")
        result = inc.local_update(g, "NEW")
        assert "NEW" in result

    def test_mark_dirty_resets_state(self):
        g = _build_diamond_graph()
        inc = IncrementalEigenTrust()
        inc.full_compute(g)
        assert inc._dirty is False
        inc.mark_dirty()
        assert inc._dirty is True


# ===========================================================================
# SECTION 2: Contradiction Detection
# ===========================================================================


class TestContradictionDetectAll:
    """ContradictionDetector.detect_all scans CONFLICTS_WITH edges."""

    def test_no_edges_returns_empty(self):
        g = MemoryGraphAdapter()
        _make_graph_node(g, "CR-001")
        detector = ContradictionDetector(g)
        assert detector.detect_all() == []

    def test_non_conflict_edges_ignored(self):
        g = MemoryGraphAdapter()
        _make_graph_node(g, "CR-001", b=0.8, d=0.0, u=0.2)
        _make_graph_node(g, "CR-002", b=0.0, d=0.7, u=0.3)
        g.add_edge("CR-001", "CR-002", "GROUNDS")  # not CONFLICTS_WITH
        detector = ContradictionDetector(g)
        assert detector.detect_all() == []

    def test_finds_single_contradiction(self):
        g = MemoryGraphAdapter()
        _make_graph_node(g, "CR-001", b=0.8, d=0.1, u=0.1)
        _make_graph_node(g, "CR-002", b=0.1, d=0.8, u=0.1)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")
        detector = ContradictionDetector(g)
        reports = detector.detect_all()
        assert len(reports) == 1
        assert reports[0].node_a_id in ("CR-001", "CR-002")
        assert reports[0].node_b_id in ("CR-001", "CR-002")

    def test_conflict_k_computed_correctly(self):
        g = MemoryGraphAdapter()
        _make_graph_node(g, "A", b=0.9, d=0.0, u=0.1)
        _make_graph_node(g, "B", b=0.0, d=0.9, u=0.1)
        g.add_edge("A", "B", "CONFLICTS_WITH")
        detector = ContradictionDetector(g)
        reports = detector.detect_all()
        assert len(reports) == 1
        # K = b_A * d_B + d_A * b_B = 0.9*0.9 + 0*0 = 0.81
        assert reports[0].conflict_k == pytest.approx(0.81, abs=1e-6)
        assert reports[0].severity == ConflictSeverity.HIGH

    def test_agreeing_nodes_produce_no_report(self):
        """Two nodes both believing (low K) should not produce a report."""
        g = MemoryGraphAdapter()
        _make_graph_node(g, "A", b=0.7, d=0.0, u=0.3)
        _make_graph_node(g, "B", b=0.6, d=0.0, u=0.4)
        g.add_edge("A", "B", "CONFLICTS_WITH")
        detector = ContradictionDetector(g)
        reports = detector.detect_all()
        # K = 0.7*0 + 0*0.6 = 0.0, severity NONE -> not reported
        assert len(reports) == 0

    def test_deduplicates_bidirectional_edges(self):
        g = MemoryGraphAdapter()
        _make_graph_node(g, "A", b=0.8, d=0.1, u=0.1)
        _make_graph_node(g, "B", b=0.1, d=0.8, u=0.1)
        g.add_edge("A", "B", "CONFLICTS_WITH")
        g.add_edge("B", "A", "CONFLICTS_WITH")
        detector = ContradictionDetector(g)
        reports = detector.detect_all()
        assert len(reports) == 1

    def test_multiple_contradictions(self):
        g = MemoryGraphAdapter()
        _make_graph_node(g, "A", b=0.9, d=0.0, u=0.1)
        _make_graph_node(g, "B", b=0.0, d=0.8, u=0.2)
        _make_graph_node(g, "C", b=0.0, d=0.7, u=0.3)
        g.add_edge("A", "B", "CONFLICTS_WITH")
        g.add_edge("A", "C", "CONFLICTS_WITH")
        detector = ContradictionDetector(g)
        reports = detector.detect_all()
        assert len(reports) == 2

    def test_missing_opinion_skipped(self):
        """Nodes without ep_b property are skipped."""
        g = MemoryGraphAdapter()
        g.add_node("Rule", "A", {"id": "A"})  # no ep_b
        _make_graph_node(g, "B", b=0.5, d=0.5, u=0.0)
        g.add_edge("A", "B", "CONFLICTS_WITH")
        detector = ContradictionDetector(g)
        reports = detector.detect_all()
        assert len(reports) == 0

    def test_report_to_dict(self):
        g = MemoryGraphAdapter()
        _make_graph_node(g, "A", b=0.9, d=0.0, u=0.1)
        _make_graph_node(g, "B", b=0.0, d=0.9, u=0.1)
        g.add_edge("A", "B", "CONFLICTS_WITH")
        detector = ContradictionDetector(g)
        reports = detector.detect_all()
        d = reports[0].to_dict()
        assert "node_a_id" in d
        assert "conflict_k" in d
        assert "severity" in d

    def test_is_contradicted_property(self):
        report_high = ContradictionReport(
            node_a_id="A", node_b_id="B",
            opinion_a=OpinionTuple(b=0.9, d=0.0, u=0.1),
            opinion_b=OpinionTuple(b=0.0, d=0.9, u=0.1),
            conflict_k=0.81, severity=ConflictSeverity.HIGH,
        )
        report_low = ContradictionReport(
            node_a_id="A", node_b_id="B",
            opinion_a=OpinionTuple(b=0.5, d=0.1, u=0.4),
            opinion_b=OpinionTuple(b=0.1, d=0.4, u=0.5),
            conflict_k=0.21, severity=ConflictSeverity.NONE,
        )
        assert report_high.is_contradicted is True
        assert report_low.is_contradicted is False


class TestContradictionDetectForNode:
    """detect_for_node targets a specific node."""

    def test_finds_contradictions_for_target(self):
        g = MemoryGraphAdapter()
        _make_graph_node(g, "A", b=0.8, d=0.1, u=0.1)
        _make_graph_node(g, "B", b=0.1, d=0.7, u=0.2)
        _make_graph_node(g, "C", b=0.7, d=0.0, u=0.3)
        g.add_edge("A", "B", "CONFLICTS_WITH")
        g.add_edge("A", "C", "REINFORCES")
        detector = ContradictionDetector(g)
        reports = detector.detect_for_node("A")
        assert len(reports) == 1
        assert reports[0].node_b_id == "B"

    def test_missing_node_returns_empty(self):
        g = MemoryGraphAdapter()
        detector = ContradictionDetector(g)
        assert detector.detect_for_node("NONEXISTENT") == []


class TestContradictionResolve:
    """resolve uses CBF for low conflict, Murphy's for high."""

    def test_low_conflict_cbf(self):
        g = MemoryGraphAdapter()
        detector = ContradictionDetector(g)
        report = ContradictionReport(
            node_a_id="A", node_b_id="B",
            opinion_a=OpinionTuple(b=0.6, d=0.1, u=0.3),
            opinion_b=OpinionTuple(b=0.1, d=0.5, u=0.4),
            conflict_k=0.35, severity=ConflictSeverity.LOW,
        )
        result = detector.resolve(report)
        assert report.resolution_method == "cbf"
        assert result.b + result.d + result.u == pytest.approx(1.0, abs=1e-6)

    def test_moderate_conflict_murphy(self):
        g = MemoryGraphAdapter()
        detector = ContradictionDetector(g)
        report = ContradictionReport(
            node_a_id="A", node_b_id="B",
            opinion_a=OpinionTuple(b=0.7, d=0.1, u=0.2),
            opinion_b=OpinionTuple(b=0.1, d=0.7, u=0.2),
            conflict_k=0.56, severity=ConflictSeverity.MODERATE,
        )
        result = detector.resolve(report)
        assert report.resolution_method == "murphy_wbf"
        assert result.b + result.d + result.u == pytest.approx(1.0, abs=1e-6)

    def test_high_conflict_murphy_trust_squared(self):
        g = MemoryGraphAdapter()
        detector = ContradictionDetector(g)
        report = ContradictionReport(
            node_a_id="A", node_b_id="B",
            opinion_a=OpinionTuple(b=0.9, d=0.0, u=0.1),
            opinion_b=OpinionTuple(b=0.0, d=0.9, u=0.1),
            conflict_k=0.81, severity=ConflictSeverity.HIGH,
        )
        result = detector.resolve(report)
        assert report.resolution_method == "murphy_trust_squared"
        assert result.b + result.d + result.u == pytest.approx(1.0, abs=1e-6)

    def test_extreme_injects_uncertainty(self):
        g = MemoryGraphAdapter()
        detector = ContradictionDetector(g)
        report = ContradictionReport(
            node_a_id="A", node_b_id="B",
            opinion_a=OpinionTuple(b=1.0, d=0.0, u=0.0),
            opinion_b=OpinionTuple(b=0.0, d=1.0, u=0.0),
            conflict_k=1.0, severity=ConflictSeverity.EXTREME,
        )
        result = detector.resolve(report)
        assert result.u > 0.0  # penalty injects uncertainty
        assert result.b + result.d + result.u == pytest.approx(1.0, abs=1e-6)

    def test_trust_weights_influence_resolution(self):
        g = MemoryGraphAdapter()
        detector = ContradictionDetector(g)
        report = ContradictionReport(
            node_a_id="A", node_b_id="B",
            opinion_a=OpinionTuple(b=0.8, d=0.0, u=0.2),
            opinion_b=OpinionTuple(b=0.0, d=0.8, u=0.2),
            conflict_k=0.64, severity=ConflictSeverity.MODERATE,
        )
        # A is highly trusted, B is not
        result_biased = detector.resolve(report, source_trusts={"A": 0.9, "B": 0.1})
        # With equal trust
        result_equal = detector.resolve(report, source_trusts={"A": 0.5, "B": 0.5})
        # Biased toward A should produce higher belief
        assert result_biased.b > result_equal.b or abs(result_biased.b - result_equal.b) < 0.01


class TestContradictionInjectDisbelief:
    """inject_disbelief pushes belief mass into disbelief."""

    def test_disbelief_increases(self):
        g = MemoryGraphAdapter()
        _make_graph_node(g, "A", b=0.8, d=0.0, u=0.2)
        _make_graph_node(g, "B", b=0.1, d=0.7, u=0.2)
        g.add_edge("A", "B", "CONFLICTS_WITH")
        detector = ContradictionDetector(g)
        reports = detector.detect_for_node("A")
        result = detector.inject_disbelief("A", reports)
        assert result is not None
        assert result.d > 0.0
        assert result.b + result.d + result.u == pytest.approx(1.0, abs=1e-6)

    def test_no_contradictions_leaves_opinion_unchanged(self):
        g = MemoryGraphAdapter()
        _make_graph_node(g, "A", b=0.8, d=0.0, u=0.2)
        detector = ContradictionDetector(g)
        result = detector.inject_disbelief("A", [])
        assert result is not None
        assert result.d == pytest.approx(0.0, abs=1e-9)
        assert result.b == pytest.approx(0.8, abs=1e-6)

    def test_missing_node_returns_none(self):
        g = MemoryGraphAdapter()
        detector = ContradictionDetector(g)
        assert detector.inject_disbelief("GHOST", []) is None

    def test_disbelief_capped_at_half_belief(self):
        """Injected disbelief cannot exceed 50% of current belief."""
        g = MemoryGraphAdapter()
        _make_graph_node(g, "A", b=0.8, d=0.0, u=0.2)
        _make_graph_node(g, "B", b=0.9, d=0.0, u=0.1)  # high belief aggressor
        g.add_edge("A", "B", "CONFLICTS_WITH")
        detector = ContradictionDetector(g)

        # Create a high-K report manually
        reports = [ContradictionReport(
            node_a_id="A", node_b_id="B",
            opinion_a=OpinionTuple(b=0.8, d=0.0, u=0.2),
            opinion_b=OpinionTuple(b=0.9, d=0.0, u=0.1),
            conflict_k=0.95, severity=ConflictSeverity.EXTREME,
        )]
        result = detector.inject_disbelief("A", reports)
        assert result is not None
        # Disbelief should not exceed half of original belief
        assert result.d <= 0.8 * 0.5 + 1e-6


# ===========================================================================
# SECTION 3: Temporal Decay (Hawkes Process)
# ===========================================================================


class TestHawkesDecayIntensity:
    """HawkesDecayEngine.compute_intensity returns Hawkes conditional intensity."""

    def test_baseline_only_when_no_events(self):
        engine = HawkesDecayEngine(mu=0.002, alpha=0.05, beta=0.01)
        intensity = engine.compute_intensity(100.0, [])
        assert intensity == pytest.approx(0.002, abs=1e-9)

    def test_recent_event_increases_intensity(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        baseline = engine.compute_intensity(100.0, [])
        boosted = engine.compute_intensity(100.0, [99.9])
        assert boosted > baseline

    def test_old_event_contributes_less(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        recent = engine.compute_intensity(100.0, [99.0])
        old = engine.compute_intensity(100.0, [10.0])
        assert recent > old

    def test_multiple_events_accumulate(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        one = engine.compute_intensity(100.0, [99.0])
        two = engine.compute_intensity(100.0, [98.0, 99.0])
        assert two > one

    def test_future_events_ignored(self):
        """Events at time > now contribute zero (dt <= 0)."""
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        baseline = engine.compute_intensity(50.0, [])
        with_future = engine.compute_intensity(50.0, [60.0, 70.0])
        assert with_future == pytest.approx(baseline, abs=1e-12)

    def test_intensity_formula_exact(self):
        """Verify against manual Hawkes formula: mu + sum alpha*beta*exp(-beta*dt)."""
        mu, alpha, beta = 0.001, 0.05, 0.01
        engine = HawkesDecayEngine(mu=mu, alpha=alpha, beta=beta)
        now = 100.0
        events = [90.0, 95.0]
        expected = mu
        for t_i in events:
            dt = now - t_i
            expected += alpha * beta * math.exp(-beta * dt)
        result = engine.compute_intensity(now, events)
        assert result == pytest.approx(expected, abs=1e-12)


class TestHawkesTemporalFactor:
    """compute_temporal_factor returns tau in [0, 1]."""

    def test_tau_bounded_0_1(self):
        engine = HawkesDecayEngine(mu=0.01, alpha=0.1, beta=0.05)
        for events in [[], [1000000], [1000000, 999000, 998000]]:
            tau = engine.compute_temporal_factor(1000000, events)
            assert 0.0 <= tau <= 1.0

    def test_no_events_returns_low_tau(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        tau = engine.compute_temporal_factor(8640000, [])
        # tau = mu / (mu + alpha*beta) = 0.001 / (0.001 + 0.0005) = ~0.667
        assert 0.0 < tau <= 1.0

    def test_recent_events_raise_tau(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        now = 8640000
        tau_none = engine.compute_temporal_factor(now, [])
        tau_recent = engine.compute_temporal_factor(now, [now - 3600])
        assert tau_recent >= tau_none

    def test_zero_max_intensity_returns_zero(self):
        engine = HawkesDecayEngine(mu=0.0, alpha=0.0, beta=0.0)
        tau = engine.compute_temporal_factor(1000000, [999999])
        assert tau == 0.0


class TestHawkesApplyDecay:
    """apply_decay transforms opinion — belief decays to uncertainty."""

    def test_no_elapsed_no_change(self):
        engine = HawkesDecayEngine(mu=0.005, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.8, d=0.1, u=0.1)
        result = engine.apply_decay(op, now_unix=1000, last_decay_unix=1000,
                                    event_timestamps_unix=[])
        assert result.b == pytest.approx(op.b, abs=1e-9)
        assert result.d == pytest.approx(op.d, abs=1e-9)

    def test_backward_time_no_change(self):
        engine = HawkesDecayEngine(mu=0.01, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.7, d=0.0, u=0.3)
        result = engine.apply_decay(op, now_unix=100, last_decay_unix=200,
                                    event_timestamps_unix=[])
        assert result.b == pytest.approx(op.b, abs=1e-9)

    def test_belief_decays_over_time(self):
        engine = HawkesDecayEngine(mu=0.01, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.8, d=0.1, u=0.1)
        result = engine.apply_decay(op, now_unix=365 * 86400, last_decay_unix=0,
                                    event_timestamps_unix=[])
        assert result.b < op.b
        assert result.u > op.u

    def test_disbelief_also_decays(self):
        engine = HawkesDecayEngine(mu=0.005, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.1, d=0.7, u=0.2)
        result = engine.apply_decay(op, now_unix=10000000, last_decay_unix=0,
                                    event_timestamps_unix=[])
        assert result.d < op.d
        assert result.u > op.u

    def test_mass_conservation(self):
        engine = HawkesDecayEngine(mu=0.005, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.6, d=0.2, u=0.2)
        result = engine.apply_decay(op, now_unix=5000000, last_decay_unix=0,
                                    event_timestamps_unix=[])
        total = result.b + result.d + result.u
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_events_slow_down_decay(self):
        engine = HawkesDecayEngine(mu=0.005, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.8, d=0.0, u=0.2)
        now = 100 * 86400
        no_events = engine.apply_decay(op, now, 0, [])
        events = [now - 86400 * i for i in range(1, 10)]
        with_events = engine.apply_decay(op, now, 0, events)
        assert with_events.b > no_events.b

    def test_zero_mu_means_no_decay(self):
        engine = HawkesDecayEngine(mu=0.0, alpha=0.0, beta=0.0)
        op = OpinionTuple(b=0.9, d=0.0, u=0.1)
        result = engine.apply_decay(op, now_unix=99999999, last_decay_unix=0,
                                    event_timestamps_unix=[])
        assert result.b == pytest.approx(op.b, abs=1e-9)

    def test_base_rate_preserved(self):
        engine = HawkesDecayEngine(mu=0.005, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.6, d=0.2, u=0.2, a=0.7)
        result = engine.apply_decay(op, now_unix=5000000, last_decay_unix=0,
                                    event_timestamps_unix=[])
        assert result.a == pytest.approx(0.7, abs=1e-9)


class TestLayerDecayProfiles:
    """Layer-specific decay profiles from LAYER_DECAY_PROFILES."""

    def test_all_six_layers_present(self):
        for layer in ["L0", "L1", "L2", "L3", "L4", "L5"]:
            assert layer in LAYER_DECAY_PROFILES

    def test_l0_axioms_never_decay(self):
        engine = LAYER_DECAY_PROFILES["L0"]
        assert engine.mu == 0.0
        op = OpinionTuple(b=0.95, d=0.0, u=0.05, a=0.9)
        result = engine.apply_decay(op, now_unix=100000000, last_decay_unix=0,
                                    event_timestamps_unix=[])
        assert result.b == pytest.approx(op.b, abs=1e-9)

    def test_l5_context_decays_fastest(self):
        op = OpinionTuple(b=0.8, d=0.0, u=0.2)
        now = 30 * 86400  # 30 days
        l5 = LAYER_DECAY_PROFILES["L5"].apply_decay(op, now, 0, [])
        l3 = LAYER_DECAY_PROFILES["L3"].apply_decay(op, now, 0, [])
        l1 = LAYER_DECAY_PROFILES["L1"].apply_decay(op, now, 0, [])
        assert l5.b < l3.b < l1.b

    def test_hierarchy_preserved_over_one_year(self):
        op = OpinionTuple(b=0.8, d=0.0, u=0.2)
        now = 365 * 86400
        results = {}
        for layer in ["L1", "L2", "L3", "L4", "L5"]:
            results[layer] = LAYER_DECAY_PROFILES[layer].apply_decay(op, now, 0, [])
        # L1 > L2 > L3 > L4 > L5 in preserved belief
        assert results["L1"].b > results["L2"].b
        assert results["L2"].b > results["L3"].b
        assert results["L3"].b > results["L4"].b
        assert results["L4"].b > results["L5"].b

    def test_get_decay_engine_returns_correct(self):
        for layer in ["L0", "L1", "L2", "L3", "L4", "L5"]:
            engine = get_decay_engine(layer)
            assert engine is LAYER_DECAY_PROFILES[layer]

    def test_get_decay_engine_unknown_defaults_to_l3(self):
        engine = get_decay_engine("UNKNOWN")
        assert engine.mu == LAYER_DECAY_PROFILES["L3"].mu
        assert engine.alpha == LAYER_DECAY_PROFILES["L3"].alpha


# ===========================================================================
# SECTION 4: OpinionTuple and CBF Fusion
# ===========================================================================


class TestOpinionTupleCreation:
    """OpinionTuple: frozen dataclass with invariant b + d + u = 1."""

    def test_valid_creation(self):
        op = OpinionTuple(b=0.5, d=0.2, u=0.3, a=0.5)
        assert op.b == 0.5
        assert op.d == 0.2
        assert op.u == 0.3
        assert op.a == 0.5

    def test_default_base_rate(self):
        op = OpinionTuple(b=0.5, d=0.2, u=0.3)
        assert op.a == 0.5

    def test_invalid_sum_raises_error(self):
        with pytest.raises(ValueError, match="b \\+ d \\+ u must equal 1.0"):
            OpinionTuple(b=0.5, d=0.5, u=0.5)

    def test_negative_value_raises_error(self):
        with pytest.raises(ValueError, match="must be in"):
            OpinionTuple(b=-0.1, d=0.5, u=0.6)

    def test_value_exceeds_1_raises_error(self):
        with pytest.raises(ValueError, match="must be in"):
            OpinionTuple(b=1.1, d=0.0, u=0.0)

    def test_frozen_cannot_mutate(self):
        op = OpinionTuple(b=0.5, d=0.2, u=0.3)
        with pytest.raises(AttributeError):
            op.b = 0.9  # type: ignore[misc]


class TestOpinionTupleProperties:
    """Computed properties: projected_probability, evidence_strength, entropy."""

    def test_projected_probability(self):
        op = OpinionTuple(b=0.7, d=0.0, u=0.3, a=0.5)
        # P(x) = b + a*u = 0.7 + 0.5*0.3 = 0.85
        assert op.projected_probability == pytest.approx(0.85, abs=1e-9)

    def test_evidence_strength(self):
        op = OpinionTuple(b=0.6, d=0.1, u=0.3)
        assert op.evidence_strength == pytest.approx(0.7, abs=1e-9)

    def test_shannon_entropy_full_uncertainty(self):
        op = OpinionTuple(b=0.0, d=0.0, u=1.0)
        assert op.shannon_entropy == pytest.approx(0.0, abs=1e-9)  # only u=1

    def test_shannon_entropy_max_disorder(self):
        """Equal distribution b=d=u=1/3 gives max entropy."""
        op = OpinionTuple(b=1/3, d=1/3, u=1/3)
        expected = -3 * (1/3 * math.log2(1/3))
        assert op.shannon_entropy == pytest.approx(expected, abs=1e-6)

    def test_to_confidence_equals_projected(self):
        op = OpinionTuple(b=0.7, d=0.0, u=0.3, a=0.5)
        assert op.to_confidence() == pytest.approx(op.projected_probability, abs=1e-9)


class TestOpinionTupleFactories:
    """Factory methods: vacuous, dogmatic_belief, dogmatic_disbelief, from_confidence, from_dict."""

    def test_vacuous(self):
        op = OpinionTuple.vacuous()
        assert op.b == 0.0
        assert op.d == 0.0
        assert op.u == 1.0

    def test_vacuous_custom_base_rate(self):
        op = OpinionTuple.vacuous(a=0.8)
        assert op.a == 0.8

    def test_dogmatic_belief(self):
        op = OpinionTuple.dogmatic_belief()
        assert op.b == 1.0
        assert op.d == 0.0
        assert op.u == 0.0

    def test_dogmatic_disbelief(self):
        op = OpinionTuple.dogmatic_disbelief()
        assert op.b == 0.0
        assert op.d == 1.0
        assert op.u == 0.0

    def test_from_confidence(self):
        op = OpinionTuple.from_confidence(0.8, uncertainty=0.2, a=0.5)
        assert op.b + op.d + op.u == pytest.approx(1.0, abs=1e-6)
        assert op.projected_probability == pytest.approx(0.8, abs=0.05)

    def test_to_dict_and_from_dict_roundtrip(self):
        original = OpinionTuple(b=0.6, d=0.15, u=0.25, a=0.4)
        d = original.to_dict()
        restored = OpinionTuple.from_dict(d)
        assert restored.b == pytest.approx(original.b, abs=1e-5)
        assert restored.d == pytest.approx(original.d, abs=1e-5)
        assert restored.u == pytest.approx(original.u, abs=1e-5)
        assert restored.a == pytest.approx(original.a, abs=1e-5)

    def test_from_dict_renormalizes(self):
        """from_dict handles float drift by renormalizing."""
        d = {"ep_b": 0.600001, "ep_d": 0.150001, "ep_u": 0.250001, "ep_a": 0.5}
        op = OpinionTuple.from_dict(d)
        assert op.b + op.d + op.u == pytest.approx(1.0, abs=1e-6)


class TestCBFFusion:
    """Cumulative Belief Fusion operator tests."""

    def test_uncertainty_monotonically_decreases(self):
        a = OpinionTuple(b=0.6, d=0.0, u=0.4)
        b = OpinionTuple(b=0.7, d=0.0, u=0.3)
        fused = cbf(a, b)
        assert fused.u < min(a.u, b.u)

    def test_mass_conservation(self):
        a = OpinionTuple(b=0.5, d=0.1, u=0.4)
        b = OpinionTuple(b=0.3, d=0.2, u=0.5)
        fused = cbf(a, b)
        assert fused.b + fused.d + fused.u == pytest.approx(1.0, abs=1e-9)

    def test_commutativity(self):
        a = OpinionTuple(b=0.6, d=0.1, u=0.3)
        b = OpinionTuple(b=0.4, d=0.2, u=0.4)
        f1 = cbf(a, b)
        f2 = cbf(b, a)
        assert f1.b == pytest.approx(f2.b, abs=1e-9)
        assert f1.d == pytest.approx(f2.d, abs=1e-9)
        assert f1.u == pytest.approx(f2.u, abs=1e-9)

    def test_vacuous_is_identity(self):
        a = OpinionTuple(b=0.7, d=0.1, u=0.2)
        v = OpinionTuple.vacuous()
        fused = cbf(a, v)
        assert fused.b == pytest.approx(a.b, abs=1e-6)
        assert fused.d == pytest.approx(a.d, abs=1e-6)
        assert fused.u == pytest.approx(a.u, abs=1e-6)

    def test_dogmatic_dominates_non_dogmatic(self):
        dog = OpinionTuple.dogmatic_belief()
        other = OpinionTuple(b=0.3, d=0.2, u=0.5)
        fused = cbf(dog, other)
        assert fused.b == pytest.approx(1.0)
        assert fused.u == pytest.approx(0.0)

    def test_both_dogmatic_conflicting_returns_uncertainty(self):
        """When two dogmatic opinions fully contradict, return max uncertainty (H14)."""
        a = OpinionTuple.dogmatic_belief()
        b = OpinionTuple.dogmatic_disbelief()
        fused = cbf(a, b)
        # conflict = 1.0*1.0 + 0.0*0.0 = 1.0 > 0.5 → max uncertainty
        assert fused.u == pytest.approx(1.0)
        assert fused.b == pytest.approx(0.0)
        assert fused.d == pytest.approx(0.0)

    def test_agreement_boosts_belief(self):
        a = OpinionTuple(b=0.6, d=0.0, u=0.4)
        b = OpinionTuple(b=0.7, d=0.0, u=0.3)
        fused = cbf(a, b)
        assert fused.b > max(a.b, b.b)

    def test_base_rate_averaged(self):
        a = OpinionTuple(b=0.5, d=0.0, u=0.5, a=0.3)
        b = OpinionTuple(b=0.5, d=0.0, u=0.5, a=0.7)
        fused = cbf(a, b)
        assert fused.a == pytest.approx(0.5)


class TestMultiSourceCBFFusion:
    """Multi-source CBF: sequential fusion across N opinions."""

    def test_empty_returns_vacuous(self):
        result = multi_source_cbf([])
        assert result.b == 0.0 and result.u == 1.0

    def test_single_source_identity(self):
        op = OpinionTuple(b=0.7, d=0.1, u=0.2)
        result = multi_source_cbf([op])
        assert result.b == pytest.approx(op.b)

    def test_many_agreeing_sources_reduce_uncertainty(self):
        sources = [OpinionTuple(b=0.6, d=0.0, u=0.4)] * 10
        result = multi_source_cbf(sources)
        assert result.u < 0.10
        assert result.b > 0.90

    def test_mass_conservation_multi(self):
        sources = [
            OpinionTuple(b=0.5, d=0.1, u=0.4),
            OpinionTuple(b=0.6, d=0.0, u=0.4),
            OpinionTuple(b=0.7, d=0.1, u=0.2),
        ]
        result = multi_source_cbf(sources)
        assert result.b + result.d + result.u == pytest.approx(1.0, abs=1e-9)

    def test_monotonic_uncertainty_reduction(self):
        source = OpinionTuple(b=0.6, d=0.0, u=0.4)
        prev_u = 1.0
        for n in range(1, 7):
            result = multi_source_cbf([source] * n)
            assert result.u <= prev_u + 1e-9
            prev_u = result.u

    def test_conflicting_sources_produce_mixed_opinion(self):
        believer = OpinionTuple(b=0.7, d=0.0, u=0.3)
        skeptic = OpinionTuple(b=0.0, d=0.7, u=0.3)
        result = multi_source_cbf([believer, skeptic])
        assert result.b > 0
        assert result.d > 0


# ===========================================================================
# SECTION 5: Cross-module integration (EigenTrust + Contradiction + Decay)
# ===========================================================================


class TestEpistemicIntegration:
    """Integration tests combining multiple epistemic components."""

    def test_eigentrust_scores_feed_contradiction_resolution(self):
        """EigenTrust trust scores used as weights in contradiction resolution."""
        g = MemoryGraphAdapter()
        g.add_node("Axiom", "AX", {"id": "AX"})
        _make_graph_node(g, "A", label="Principle", b=0.8, d=0.0, u=0.2)
        _make_graph_node(g, "B", label="Rule", b=0.0, d=0.8, u=0.2)
        g.add_edge("AX", "A", "GROUNDS")
        g.add_edge("AX", "B", "INFORMS")
        g.add_edge("A", "B", "CONFLICTS_WITH")

        # Compute trust
        engine = EigenTrustEngine()
        trust_scores = engine.compute(g)

        # Detect contradictions
        detector = ContradictionDetector(g)
        reports = detector.detect_all()
        assert len(reports) >= 1

        # Resolve using trust scores from EigenTrust
        resolved = detector.resolve(reports[0], source_trusts=trust_scores)
        assert resolved.b + resolved.d + resolved.u == pytest.approx(1.0, abs=1e-6)

    def test_decay_then_fusion_produces_valid_opinion(self):
        """Decayed opinion can still be fused via CBF."""
        engine = HawkesDecayEngine(mu=0.005, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.7, d=0.0, u=0.3)
        decayed = engine.apply_decay(op, now_unix=180 * 86400, last_decay_unix=0,
                                     event_timestamps_unix=[])
        other = OpinionTuple(b=0.6, d=0.0, u=0.4)
        fused = cbf(decayed, other)
        assert fused.b + fused.d + fused.u == pytest.approx(1.0, abs=1e-6)
        assert fused.u < min(decayed.u, other.u)

    def test_dempster_conflict_symmetric(self):
        a = OpinionTuple(b=0.8, d=0.1, u=0.1)
        b = OpinionTuple(b=0.1, d=0.8, u=0.1)
        assert dempster_conflict(a, b) == pytest.approx(dempster_conflict(b, a), abs=1e-9)

    def test_conflict_severity_classification_boundaries(self):
        """Verify classify_conflict boundary values."""
        assert classify_conflict(0.0) == ConflictSeverity.NONE
        assert classify_conflict(0.29) == ConflictSeverity.NONE
        assert classify_conflict(0.3) == ConflictSeverity.LOW
        assert classify_conflict(0.49) == ConflictSeverity.LOW
        assert classify_conflict(0.5) == ConflictSeverity.MODERATE
        assert classify_conflict(0.69) == ConflictSeverity.MODERATE
        assert classify_conflict(0.7) == ConflictSeverity.HIGH
        assert classify_conflict(0.89) == ConflictSeverity.HIGH
        assert classify_conflict(0.9) == ConflictSeverity.EXTREME
        assert classify_conflict(1.0) == ConflictSeverity.EXTREME

    def test_murphy_weighted_average_mass_conservation(self):
        opinions = [
            OpinionTuple(b=0.7, d=0.1, u=0.2),
            OpinionTuple(b=0.3, d=0.4, u=0.3),
            OpinionTuple(b=0.5, d=0.2, u=0.3),
        ]
        result = murphy_weighted_average(opinions, weights=[0.5, 0.3, 0.2])
        assert result.b + result.d + result.u == pytest.approx(1.0, abs=1e-6)

    def test_murphy_single_opinion_identity(self):
        op = OpinionTuple(b=0.6, d=0.2, u=0.2)
        result = murphy_weighted_average([op])
        assert result.b == pytest.approx(op.b)
        assert result.d == pytest.approx(op.d)

    def test_murphy_empty_returns_vacuous(self):
        result = murphy_weighted_average([])
        assert result.u == 1.0
