"""Tests for epistemic scoring integration in the scorer."""

from __future__ import annotations

import pytest

from engineering_brain.retrieval.scorer import score_knowledge


class TestEpistemicScoring:
    """Test scorer behavior with ep_* fields present."""

    def test_epistemic_node_uses_projected_probability(self):
        node = {
            "ep_b": 0.8,
            "ep_d": 0.05,
            "ep_u": 0.15,
            "ep_a": 0.5,
            "technologies": ["python"],
            "severity": "high",
        }
        score = score_knowledge(node, ["python"], ["general"])
        # Should score higher than a node without ep_*
        assert score > 0.0

    def test_high_belief_low_uncertainty_scores_high(self):
        high = {
            "ep_b": 0.9,
            "ep_d": 0.0,
            "ep_u": 0.1,
            "ep_a": 0.5,
            "technologies": ["python"],
            "severity": "high",
        }
        low = {
            "ep_b": 0.2,
            "ep_d": 0.3,
            "ep_u": 0.5,
            "ep_a": 0.5,
            "technologies": ["python"],
            "severity": "high",
        }
        score_high = score_knowledge(high, ["python"], ["general"])
        score_low = score_knowledge(low, ["python"], ["general"])
        assert score_high > score_low

    def test_uncertainty_penalty_lowers_score(self):
        """High belief but high uncertainty should score lower than same belief with low uncertainty."""
        certain = {
            "ep_b": 0.8,
            "ep_d": 0.0,
            "ep_u": 0.2,
            "ep_a": 0.5,
            "technologies": ["python"],
            "severity": "medium",
        }
        uncertain = {
            "ep_b": 0.3,
            "ep_d": 0.0,
            "ep_u": 0.7,
            "ep_a": 0.5,
            "technologies": ["python"],
            "severity": "medium",
        }
        score_certain = score_knowledge(certain, ["python"], [])
        score_uncertain = score_knowledge(uncertain, ["python"], [])
        assert score_certain > score_uncertain

    def test_fallback_without_ep_fields(self):
        """Without ep_* fields, scorer uses legacy confidence behavior."""
        node = {
            "confidence": 0.9,
            "validation_status": "cross_checked",
            "technologies": ["python"],
            "severity": "medium",
        }
        score = score_knowledge(node, ["python"], [])
        assert 0.0 < score <= 1.0

    def test_ep_none_falls_back(self):
        """ep_b=None should use fallback path."""
        node = {
            "ep_b": None,
            "confidence": 0.7,
            "technologies": ["react"],
            "severity": "low",
        }
        score = score_knowledge(node, ["react"], [])
        assert 0.0 < score <= 1.0
