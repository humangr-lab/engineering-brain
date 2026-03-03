"""Tests for contradiction detection and resolution."""

from __future__ import annotations

import pytest

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.epistemic.conflict_resolution import ConflictSeverity
from engineering_brain.epistemic.contradiction import (
    ContradictionDetector,
    ContradictionReport,
)
from engineering_brain.epistemic.opinion import OpinionTuple


def _make_node(graph, node_id, b, d, u, a=0.5):
    graph.add_node("Rule", node_id, {
        "id": node_id,
        "ep_b": b, "ep_d": d, "ep_u": u, "ep_a": a,
    })


class TestDetectAll:
    def test_finds_conflicts_with_edges(self):
        g = MemoryGraphAdapter()
        _make_node(g, "CR-001", b=0.8, d=0.0, u=0.2)
        _make_node(g, "CR-002", b=0.0, d=0.7, u=0.3)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")

        detector = ContradictionDetector(g)
        reports = detector.detect_all()
        assert len(reports) == 1
        assert reports[0].conflict_k > 0.3

    def test_no_contradictions_for_agreeing_nodes(self):
        g = MemoryGraphAdapter()
        _make_node(g, "CR-001", b=0.8, d=0.0, u=0.2)
        _make_node(g, "CR-002", b=0.7, d=0.0, u=0.3)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")

        detector = ContradictionDetector(g)
        reports = detector.detect_all()
        # K = 0.8*0 + 0*0.7 = 0, severity NONE → not reported
        assert len(reports) == 0

    def test_no_edges_returns_empty(self):
        g = MemoryGraphAdapter()
        _make_node(g, "CR-001", b=0.8, d=0.0, u=0.2)
        detector = ContradictionDetector(g)
        assert detector.detect_all() == []

    def test_deduplicates_bidirectional_edges(self):
        g = MemoryGraphAdapter()
        _make_node(g, "CR-001", b=0.8, d=0.1, u=0.1)
        _make_node(g, "CR-002", b=0.1, d=0.8, u=0.1)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")
        g.add_edge("CR-002", "CR-001", "CONFLICTS_WITH")

        detector = ContradictionDetector(g)
        reports = detector.detect_all()
        assert len(reports) == 1  # deduplicated


class TestDetectForNode:
    def test_finds_contradictions_for_specific_node(self):
        g = MemoryGraphAdapter()
        _make_node(g, "CR-001", b=0.8, d=0.1, u=0.1)
        _make_node(g, "CR-002", b=0.1, d=0.7, u=0.2)
        _make_node(g, "CR-003", b=0.7, d=0.0, u=0.3)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")
        g.add_edge("CR-001", "CR-003", "REINFORCES")  # not a conflict edge

        detector = ContradictionDetector(g)
        reports = detector.detect_for_node("CR-001")
        assert len(reports) == 1
        assert reports[0].node_b_id == "CR-002"


class TestResolve:
    def test_low_conflict_uses_cbf(self):
        g = MemoryGraphAdapter()
        detector = ContradictionDetector(g)
        report = ContradictionReport(
            node_a_id="CR-001", node_b_id="CR-002",
            opinion_a=OpinionTuple(b=0.6, d=0.1, u=0.3, a=0.5),
            opinion_b=OpinionTuple(b=0.1, d=0.5, u=0.4, a=0.5),
            conflict_k=0.35, severity=ConflictSeverity.LOW,
        )
        result = detector.resolve(report)
        assert report.resolution_method == "cbf"
        total = result.b + result.d + result.u
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_high_conflict_uses_murphy(self):
        g = MemoryGraphAdapter()
        detector = ContradictionDetector(g)
        report = ContradictionReport(
            node_a_id="CR-001", node_b_id="CR-002",
            opinion_a=OpinionTuple(b=0.9, d=0.0, u=0.1, a=0.5),
            opinion_b=OpinionTuple(b=0.0, d=0.9, u=0.1, a=0.5),
            conflict_k=0.81, severity=ConflictSeverity.HIGH,
        )
        result = detector.resolve(report)
        assert report.resolution_method == "murphy_trust_squared"
        total = result.b + result.d + result.u
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_extreme_injects_uncertainty_penalty(self):
        g = MemoryGraphAdapter()
        detector = ContradictionDetector(g)
        report = ContradictionReport(
            node_a_id="CR-001", node_b_id="CR-002",
            opinion_a=OpinionTuple(b=1.0, d=0.0, u=0.0, a=0.5),
            opinion_b=OpinionTuple(b=0.0, d=1.0, u=0.0, a=0.5),
            conflict_k=1.0, severity=ConflictSeverity.EXTREME,
        )
        result = detector.resolve(report)
        assert result.u > 0.0  # uncertainty injected


class TestInjectDisbelief:
    def test_injects_disbelief_from_contradictions(self):
        g = MemoryGraphAdapter()
        _make_node(g, "CR-001", b=0.8, d=0.0, u=0.2)
        _make_node(g, "CR-002", b=0.1, d=0.7, u=0.2)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")

        detector = ContradictionDetector(g)
        reports = detector.detect_for_node("CR-001")

        result = detector.inject_disbelief("CR-001", reports)
        assert result is not None
        assert result.d > 0.0  # disbelief injected
        total = result.b + result.d + result.u
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_no_contradictions_no_change(self):
        g = MemoryGraphAdapter()
        _make_node(g, "CR-001", b=0.8, d=0.0, u=0.2)

        detector = ContradictionDetector(g)
        result = detector.inject_disbelief("CR-001", [])
        assert result is not None
        assert result.d == pytest.approx(0.0, abs=1e-9)

    def test_missing_node_returns_none(self):
        g = MemoryGraphAdapter()
        detector = ContradictionDetector(g)
        assert detector.inject_disbelief("NONEXISTENT", []) is None
