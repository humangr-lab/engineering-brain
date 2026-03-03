"""Tests for edge opinion computation."""

from __future__ import annotations

import pytest

from engineering_brain.epistemic.edge_opinion import (
    EDGE_TYPE_PRIORS,
    compute_edge_opinion,
    edge_prior,
)
from engineering_brain.epistemic.opinion import OpinionTuple


class TestEdgePrior:
    def test_grounds_near_dogmatic(self):
        p = edge_prior("GROUNDS")
        assert p.b >= 0.90
        assert p.u <= 0.10

    def test_conflicts_with_has_disbelief(self):
        p = edge_prior("CONFLICTS_WITH")
        assert p.d > 0.5
        assert p.b == 0.0

    def test_weakens_has_disbelief(self):
        p = edge_prior("WEAKENS")
        assert p.d > 0.0
        assert p.b == 0.0

    def test_reinforces_has_belief(self):
        p = edge_prior("REINFORCES")
        assert p.b > 0.5
        assert p.d == 0.0

    def test_unknown_edge_type_returns_default(self):
        p = edge_prior("TOTALLY_UNKNOWN_EDGE")
        assert p.b == pytest.approx(0.5, abs=1e-6)
        assert p.u == pytest.approx(0.5, abs=1e-6)

    def test_all_priors_mass_conservation(self):
        for edge_type, prior in EDGE_TYPE_PRIORS.items():
            total = prior.b + prior.d + prior.u
            assert total == pytest.approx(1.0, abs=1e-6), f"{edge_type}: {total}"

    def test_supersedes_has_some_disbelief(self):
        p = edge_prior("SUPERSEDES")
        assert p.d > 0.0  # superseding implies some negation


class TestComputeEdgeOpinion:
    def test_reliable_source_preserves_prior(self):
        """High-certainty source should preserve edge prior closely."""
        source = OpinionTuple(b=0.9, d=0.0, u=0.1, a=0.5)
        target = OpinionTuple(b=0.7, d=0.0, u=0.3, a=0.5)
        result = compute_edge_opinion("GROUNDS", source, target)
        prior = edge_prior("GROUNDS")
        # With source strength = 0.9, edge should be close to prior * 0.9
        assert result.b > 0.8

    def test_unreliable_source_injects_uncertainty(self):
        """Low-certainty source should inject uncertainty into edge."""
        source = OpinionTuple(b=0.1, d=0.0, u=0.9, a=0.5)
        target = OpinionTuple(b=0.7, d=0.0, u=0.3, a=0.5)
        result = compute_edge_opinion("GROUNDS", source, target)
        prior = edge_prior("GROUNDS")
        assert result.u > prior.u  # more uncertain than prior

    def test_mass_conservation(self):
        source = OpinionTuple(b=0.5, d=0.1, u=0.4, a=0.5)
        target = OpinionTuple(b=0.6, d=0.0, u=0.4, a=0.5)
        result = compute_edge_opinion("EVIDENCED_BY", source, target)
        total = result.b + result.d + result.u
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_conflicts_with_maintains_disbelief(self):
        source = OpinionTuple(b=0.8, d=0.0, u=0.2, a=0.5)
        target = OpinionTuple(b=0.8, d=0.0, u=0.2, a=0.5)
        result = compute_edge_opinion("CONFLICTS_WITH", source, target)
        # CONFLICTS_WITH prior has d=0.7, source is reliable
        assert result.d > 0.0

    def test_vacuous_source_makes_edge_uncertain(self):
        source = OpinionTuple.vacuous()
        target = OpinionTuple(b=0.8, d=0.0, u=0.2, a=0.5)
        result = compute_edge_opinion("REINFORCES", source, target)
        # Vacuous source (evidence_strength=0) → edge should be very uncertain
        assert result.u > 0.9
