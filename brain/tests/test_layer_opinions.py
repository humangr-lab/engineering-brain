"""Tests for layer_opinions — cortical layer priors and bootstrap."""

from __future__ import annotations

import pytest

from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.layer_opinions import (
    initial_opinion_for_layer,
    bootstrap_opinion,
)


# --- initial_opinion_for_layer ---


class TestInitialOpinionForLayer:
    def test_l0_near_dogmatic(self):
        o = initial_opinion_for_layer("L0")
        assert o.b == pytest.approx(0.95)
        assert o.u == pytest.approx(0.05)
        assert o.a == pytest.approx(0.9)

    def test_l1_high_confidence(self):
        o = initial_opinion_for_layer("L1")
        assert o.b == pytest.approx(0.80)
        assert o.u == pytest.approx(0.20)

    def test_l2_moderate(self):
        o = initial_opinion_for_layer("L2")
        assert o.b == pytest.approx(0.55)
        assert o.u == pytest.approx(0.45)

    def test_l3_uncertain(self):
        o = initial_opinion_for_layer("L3")
        assert o.b == pytest.approx(0.30)
        assert o.u == pytest.approx(0.70)

    def test_l4_low(self):
        o = initial_opinion_for_layer("L4")
        assert o.b == pytest.approx(0.15)
        assert o.u == pytest.approx(0.85)

    def test_l5_ephemeral(self):
        o = initial_opinion_for_layer("L5")
        assert o.b == pytest.approx(0.05)
        assert o.u == pytest.approx(0.95)

    def test_unknown_layer_defaults_to_l3(self):
        o = initial_opinion_for_layer("LX")
        l3 = initial_opinion_for_layer("L3")
        assert o.b == l3.b
        assert o.u == l3.u

    def test_monotonic_belief_decrease(self):
        """Deeper layers have higher belief: L0 > L1 > ... > L5."""
        layers = ["L0", "L1", "L2", "L3", "L4", "L5"]
        beliefs = [initial_opinion_for_layer(l).b for l in layers]
        for i in range(len(beliefs) - 1):
            assert beliefs[i] > beliefs[i + 1]

    def test_monotonic_uncertainty_increase(self):
        """Surface layers have higher uncertainty: L5 > L4 > ... > L0."""
        layers = ["L0", "L1", "L2", "L3", "L4", "L5"]
        uncertainties = [initial_opinion_for_layer(l).u for l in layers]
        for i in range(len(uncertainties) - 1):
            assert uncertainties[i] < uncertainties[i + 1]

    def test_all_layers_valid_opinions(self):
        for layer in ["L0", "L1", "L2", "L3", "L4", "L5"]:
            o = initial_opinion_for_layer(layer)
            assert abs(o.b + o.d + o.u - 1.0) < 1e-9
            assert o.d == 0.0  # priors have no disbelief

    def test_accepts_layer_enum(self):
        """Should handle Layer enum values (via .value)."""

        class FakeLayer:
            value = "L0"

        o = initial_opinion_for_layer(FakeLayer())
        assert o.b == pytest.approx(0.95)


# --- bootstrap_opinion ---


class TestBootstrapOpinion:
    def test_no_sources_returns_prior(self):
        prior = initial_opinion_for_layer("L3")
        result = bootstrap_opinion("L3", [])
        assert result.b == pytest.approx(prior.b)
        assert result.u == pytest.approx(prior.u)

    def test_sources_reduce_uncertainty(self):
        prior = initial_opinion_for_layer("L3")
        sources = [
            {"source_type": "official_docs", "verified": True},
        ]
        result = bootstrap_opinion("L3", sources)
        assert result.u < prior.u

    def test_more_sources_less_uncertainty(self):
        one_source = bootstrap_opinion("L3", [
            {"source_type": "official_docs"},
        ])
        two_sources = bootstrap_opinion("L3", [
            {"source_type": "official_docs"},
            {"source_type": "package_registry"},
        ])
        assert two_sources.u < one_source.u

    def test_high_trust_source_boosts_belief(self):
        prior = initial_opinion_for_layer("L3")
        result = bootstrap_opinion("L3", [
            {"source_type": "rfc_standard", "verified": True},
        ])
        assert result.b > prior.b

    def test_result_is_valid_opinion(self):
        sources = [
            {"source_type": "official_docs"},
            {"source_type": "stackoverflow", "vote_count": 50},
            {"source_type": "security_cve", "cvss_score": 8.0},
        ]
        result = bootstrap_opinion("L2", sources)
        assert abs(result.b + result.d + result.u - 1.0) < 1e-9

    def test_l0_with_sources_stays_high(self):
        """L0 axioms with good sources should remain near-dogmatic."""
        result = bootstrap_opinion("L0", [
            {"source_type": "official_docs", "verified": True},
            {"source_type": "rfc_standard", "verified": True},
        ])
        assert result.b > 0.90
        assert result.u < 0.05

    def test_l5_with_weak_source_still_moderate(self):
        """L5 ephemeral with one weak source stays moderate (not high confidence)."""
        result = bootstrap_opinion("L5", [
            {"source_type": "stackoverflow", "vote_count": 5},
        ])
        # SO base trust=0.60, CBF with L5 prior (b=0.05, u=0.95) → ~0.61
        # Not high confidence, but source evidence carries real weight
        assert result.b < 0.65
