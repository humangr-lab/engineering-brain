"""Tests for epistemic reinforcement via CBF fusion."""

from __future__ import annotations

import pytest

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.learning.reinforcer import EvidenceReinforcer


def _make_rule(graph, rule_id, ep_b=None, ep_d=None, ep_u=None, ep_a=None, confidence=0.5):
    """Helper: create a rule node in the graph."""
    data = {
        "id": rule_id,
        "text": "test rule",
        "confidence": confidence,
        "reinforcement_count": 0,
    }
    if ep_b is not None:
        data.update({"ep_b": ep_b, "ep_d": ep_d or 0.0, "ep_u": ep_u or 0.5, "ep_a": ep_a or 0.5})
    graph.add_node("Rule", rule_id, data)
    return data


class TestEpistemicReinforcement:
    def test_positive_reinforcement_increases_belief(self):
        graph = MemoryGraphAdapter()
        _make_rule(graph, "CR-001", ep_b=0.6, ep_d=0.0, ep_u=0.4, ep_a=0.5)
        reinforcer = EvidenceReinforcer(graph)

        result = reinforcer.reinforce("CR-001", "EV-001", positive=True)
        assert result is True

        node = graph.get_node("CR-001")
        assert node["ep_b"] > 0.6  # belief increased
        assert node["ep_u"] < 0.4  # uncertainty decreased

    def test_negative_reinforcement_increases_disbelief(self):
        graph = MemoryGraphAdapter()
        _make_rule(graph, "CR-002", ep_b=0.6, ep_d=0.0, ep_u=0.4, ep_a=0.5)
        reinforcer = EvidenceReinforcer(graph)

        result = reinforcer.reinforce("CR-002", "EV-002", positive=False)
        assert result is True

        node = graph.get_node("CR-002")
        assert node["ep_d"] > 0.0  # disbelief appeared
        assert node["ep_u"] < 0.4  # uncertainty decreased

    def test_repeated_reinforcement_converges(self):
        """Many positive reinforcements → belief approaches 1, uncertainty approaches 0."""
        graph = MemoryGraphAdapter()
        _make_rule(graph, "CR-003", ep_b=0.5, ep_d=0.0, ep_u=0.5, ep_a=0.5)
        reinforcer = EvidenceReinforcer(graph)

        for i in range(20):
            reinforcer.reinforce("CR-003", f"EV-{i}", positive=True)

        node = graph.get_node("CR-003")
        assert node["ep_b"] > 0.9
        assert node["ep_u"] < 0.1

    def test_backward_compat_confidence_updated(self):
        """confidence field should be updated to projected_probability."""
        graph = MemoryGraphAdapter()
        _make_rule(graph, "CR-004", ep_b=0.6, ep_d=0.0, ep_u=0.4, ep_a=0.5)
        reinforcer = EvidenceReinforcer(graph)

        reinforcer.reinforce("CR-004", "EV-004", positive=True)

        node = graph.get_node("CR-004")
        expected_pp = node["ep_b"] + node["ep_a"] * node["ep_u"]
        assert node["confidence"] == pytest.approx(expected_pp, abs=1e-6)

    def test_mass_conservation_after_reinforce(self):
        """b + d + u = 1 invariant must hold."""
        graph = MemoryGraphAdapter()
        _make_rule(graph, "CR-005", ep_b=0.5, ep_d=0.1, ep_u=0.4, ep_a=0.5)
        reinforcer = EvidenceReinforcer(graph)

        reinforcer.reinforce("CR-005", "EV-005", positive=True)

        node = graph.get_node("CR-005")
        total = node["ep_b"] + node["ep_d"] + node["ep_u"]
        assert abs(total - 1.0) < 1e-9

    def test_fallback_without_ep_fields(self):
        """Without ep_* fields, uses legacy heuristic."""
        graph = MemoryGraphAdapter()
        _make_rule(graph, "CR-006", confidence=0.5)
        reinforcer = EvidenceReinforcer(graph)

        reinforcer.reinforce("CR-006", "EV-006", positive=True)

        node = graph.get_node("CR-006")
        assert node["confidence"] > 0.5  # increased
        assert node.get("ep_b") is None  # no epistemic fields added

    def test_missing_rule_returns_false(self):
        graph = MemoryGraphAdapter()
        reinforcer = EvidenceReinforcer(graph)
        assert reinforcer.reinforce("NONEXISTENT", "EV-X") is False
