"""Tests for Bayesian learned source trust."""

from __future__ import annotations

import pytest

from engineering_brain.epistemic.learned_trust import BetaPrior, LearnedSourceTrust
from engineering_brain.epistemic.source_trust import SOURCE_TRUST_MAP


class TestBetaPrior:
    def test_uniform_prior(self):
        p = BetaPrior(alpha=1.0, beta=1.0)
        assert p.mean == pytest.approx(0.5, abs=1e-6)

    def test_strong_belief(self):
        p = BetaPrior(alpha=9.0, beta=1.0)
        assert p.mean == pytest.approx(0.9, abs=1e-6)

    def test_strong_disbelief(self):
        p = BetaPrior(alpha=1.0, beta=9.0)
        assert p.mean == pytest.approx(0.1, abs=1e-6)

    def test_variance_decreases_with_observations(self):
        few = BetaPrior(alpha=2.0, beta=2.0)
        many = BetaPrior(alpha=20.0, beta=20.0)
        assert many.variance < few.variance

    def test_confidence_increases_with_observations(self):
        few = BetaPrior(alpha=2.0, beta=2.0)
        many = BetaPrior(alpha=50.0, beta=50.0)
        assert many.confidence > few.confidence

    def test_serialization_roundtrip(self):
        p = BetaPrior(alpha=5.0, beta=3.0)
        d = p.to_dict()
        restored = BetaPrior.from_dict(d)
        assert restored.alpha == pytest.approx(p.alpha, abs=1e-3)
        assert restored.beta == pytest.approx(p.beta, abs=1e-3)


class TestLearnedSourceTrust:
    def test_initialized_from_static_map(self):
        learner = LearnedSourceTrust()
        for source_type, static_trust in SOURCE_TRUST_MAP.items():
            learned = learner.get_trust(source_type)
            assert learned == pytest.approx(static_trust, abs=1e-2)

    def test_observe_correct_increases_trust(self):
        learner = LearnedSourceTrust()
        before = learner.get_trust("official_docs")
        learner.observe("official_docs", correct=True)
        after = learner.get_trust("official_docs")
        assert after > before

    def test_observe_incorrect_decreases_trust(self):
        learner = LearnedSourceTrust()
        before = learner.get_trust("stackoverflow")
        learner.observe("stackoverflow", correct=False)
        after = learner.get_trust("stackoverflow")
        assert after < before

    def test_many_correct_converges_high(self):
        learner = LearnedSourceTrust()
        for _ in range(100):
            learner.observe("mdn", correct=True)
        trust = learner.get_trust("mdn")
        assert trust > 0.95

    def test_many_incorrect_converges_low(self):
        learner = LearnedSourceTrust()
        for _ in range(100):
            learner.observe("stackoverflow", correct=False)
        trust = learner.get_trust("stackoverflow")
        assert trust < 0.15

    def test_mixed_observations_converge_to_rate(self):
        """80% correct → trust ~0.8."""
        learner = LearnedSourceTrust()
        for i in range(200):
            learner.observe("package_registry", correct=(i % 5 != 0))  # 80% correct
        trust = learner.get_trust("package_registry")
        assert 0.70 < trust < 0.90

    def test_unknown_source_type(self):
        learner = LearnedSourceTrust()
        # Unknown source starts at 0.5
        learner.observe("totally_new_source", correct=True)
        assert learner.get_trust("totally_new_source") > 0.5

    def test_serialization_roundtrip(self):
        learner = LearnedSourceTrust()
        learner.observe("official_docs", correct=True)
        learner.observe("stackoverflow", correct=False)

        data = learner.to_dict()
        restored = LearnedSourceTrust.from_dict(data)

        for st in SOURCE_TRUST_MAP:
            assert restored.get_trust(st) == pytest.approx(learner.get_trust(st), abs=1e-4)

    def test_divergence_from_static(self):
        learner = LearnedSourceTrust()
        # After initialization, divergence should be ~0
        div = learner.divergence_from_static()
        for source_type, delta in div.items():
            assert abs(delta) < 0.01

    def test_divergence_after_observations(self):
        learner = LearnedSourceTrust()
        for _ in range(50):
            learner.observe("stackoverflow", correct=True)
        div = learner.divergence_from_static()
        # SO should have diverged positively (learned trust > static 0.60)
        assert div["stackoverflow"] > 0.1

    def test_get_prior(self):
        learner = LearnedSourceTrust()
        prior = learner.get_prior("official_docs")
        assert isinstance(prior, BetaPrior)
        assert prior.alpha > 1.0
