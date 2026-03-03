"""Tests for adaptive scoring weight optimizer (Gap 4).

Covers the Thompson Sampling-based weight optimization:
1. SignalDistribution: Beta distribution math (mean, variance, sample)
2. AdaptiveWeightOptimizer: initialization, feedback, sampling, stats
"""

from __future__ import annotations

import os
import sys

import pytest

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from engineering_brain.core.config import BrainConfig
from engineering_brain.learning.adaptive_weights import (
    AdaptiveWeightOptimizer,
    DEFAULT_WEIGHTS,
    SIGNAL_NAMES,
    SignalDistribution,
)


# =============================================================================
# Mock observation log
# =============================================================================

class MockObservationLog:
    """Minimal mock for the observation log used by the optimizer."""

    def __init__(self, events=None):
        self._events = events or []

    def read_all(self):
        return self._events


# =============================================================================
# Helpers
# =============================================================================

def _make_optimizer(
    observation_log=None,
    config=None,
) -> AdaptiveWeightOptimizer:
    """Create an AdaptiveWeightOptimizer with defaults."""
    return AdaptiveWeightOptimizer(
        observation_log=observation_log,
        config=config or BrainConfig(),
    )


# =============================================================================
# 1. SignalDistribution tests
# =============================================================================


class TestSignalDistribution:
    def test_signal_distribution_defaults(self):
        """Mean equals alpha / (alpha + beta) for the Beta distribution."""
        dist = SignalDistribution(name="tech_match", alpha=5.6, beta=14.4)
        expected_mean = 5.6 / (5.6 + 14.4)
        assert dist.mean == pytest.approx(expected_mean, abs=1e-9)

    def test_signal_distribution_variance(self):
        """Variance follows the Beta distribution formula: ab / ((a+b)^2 * (a+b+1))."""
        dist = SignalDistribution(name="severity", alpha=3.6, beta=16.4)
        ab = dist.alpha + dist.beta
        expected_variance = (dist.alpha * dist.beta) / (ab * ab * (ab + 1))
        assert dist.variance == pytest.approx(expected_variance, abs=1e-12)

    def test_signal_distribution_sample_in_range(self):
        """sample() always returns a value in [0, 1]."""
        dist = SignalDistribution(name="recency", alpha=2.6, beta=17.4)
        for _ in range(200):
            s = dist.sample()
            assert 0.0 <= s <= 1.0


# =============================================================================
# 2. AdaptiveWeightOptimizer tests
# =============================================================================


class TestAdaptiveWeightOptimizer:
    def test_initial_weights_match_defaults(self):
        """Initial mean weights should approximate DEFAULT_WEIGHTS."""
        opt = _make_optimizer()
        mean_weights = opt.get_mean_weights()
        for name, default_w in zip(SIGNAL_NAMES, DEFAULT_WEIGHTS):
            assert mean_weights[name] == pytest.approx(default_w, abs=0.02)

    def test_weights_sum_to_one(self):
        """get_weights() must always sum to 1.0."""
        opt = _make_optimizer()
        weights = opt.get_weights()
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)

    def test_get_mean_weights_normalized(self):
        """get_mean_weights() must sum to 1.0."""
        opt = _make_optimizer()
        mean_weights = opt.get_mean_weights()
        assert sum(mean_weights.values()) == pytest.approx(1.0, abs=1e-9)

    def test_positive_feedback_increases_alpha(self):
        """record_feedback(helpful=True) increases alpha for high-scoring signals."""
        opt = _make_optimizer()
        alpha_before = opt._distributions["tech_match"].alpha

        opt.record_feedback(
            node_id="N-001",
            helpful=True,
            signal_scores={"tech_match": 0.9, "domain_match": 0.8},
        )

        alpha_after = opt._distributions["tech_match"].alpha
        assert alpha_after > alpha_before

    def test_negative_feedback_increases_beta(self):
        """record_feedback(helpful=False) increases beta for high-scoring signals."""
        opt = _make_optimizer()
        beta_before = opt._distributions["tech_match"].beta

        opt.record_feedback(
            node_id="N-002",
            helpful=False,
            signal_scores={"tech_match": 0.9, "domain_match": 0.8},
        )

        beta_after = opt._distributions["tech_match"].beta
        assert beta_after > beta_before

    def test_feedback_only_affects_high_scoring_signals(self):
        """Signals not present in signal_scores are unaffected by feedback."""
        opt = _make_optimizer()
        alpha_before = opt._distributions["confidence"].alpha
        beta_before = opt._distributions["confidence"].beta

        # Only provide tech_match in signal_scores; "confidence" is absent
        opt.record_feedback(
            node_id="N-003",
            helpful=True,
            signal_scores={"tech_match": 0.9},
        )

        alpha_after = opt._distributions["confidence"].alpha
        beta_after = opt._distributions["confidence"].beta
        assert alpha_after == alpha_before
        assert beta_after == beta_before

    def test_sample_and_normalize_sums_to_one(self):
        """_sample_and_normalize() always sums to 1.0."""
        opt = _make_optimizer()
        for _ in range(50):
            sampled = opt._sample_and_normalize()
            assert sum(sampled.values()) == pytest.approx(1.0, abs=1e-9)

    def test_sample_and_normalize_stochastic(self):
        """Different calls to _sample_and_normalize() may give different results."""
        opt = _make_optimizer()
        results = [tuple(opt._sample_and_normalize().values()) for _ in range(30)]
        # With 30 samples from Beta distributions it is overwhelmingly likely
        # that at least two distinct weight vectors appear.
        unique = set(results)
        assert len(unique) > 1

    def test_stats_returns_dict(self):
        """stats() returns a dict with expected top-level keys."""
        opt = _make_optimizer()
        s = opt.stats()
        assert "signals" in s
        assert "query_count" in s
        assert "current_weights" in s
        # Each signal must have alpha, beta, mean, variance
        for name in SIGNAL_NAMES:
            sig = s["signals"][name]
            assert "alpha" in sig
            assert "beta" in sig
            assert "mean" in sig
            assert "variance" in sig

    def test_signal_names_count(self):
        """There must be exactly 6 scoring signals."""
        assert len(SIGNAL_NAMES) == 6
        assert len(DEFAULT_WEIGHTS) == 6
        opt = _make_optimizer()
        assert len(opt._distributions) == 6
