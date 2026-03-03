"""Tests for the adaptive promotion policy (Gap 7).

Covers BetaPrior dataclass properties and AdaptivePromotionPolicy methods:
- Beta distribution math (mean, confidence, multiplier)
- Effective threshold computation with domain-specific priors
- Outcome recording and prior updates
- Stats reporting
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from typing import Any

import pytest

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from engineering_brain.core.config import BrainConfig
from engineering_brain.learning.adaptive_promotion import (
    AdaptivePromotionPolicy,
    BetaPrior,
)


# ---------------------------------------------------------------------------
# Mock observation log
# ---------------------------------------------------------------------------

@dataclass
class _MockObservation:
    """Lightweight stand-in for Observation namedtuple / dataclass."""
    event_type: str = "query_served"
    outcome: str = "unknown"
    rule_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


class MockObservationLog:
    """In-memory observation log for testing _compute_priors."""

    def __init__(self, events: list[_MockObservation] | None = None) -> None:
        self._events = events or []

    def read_all(self) -> list[_MockObservation]:
        return list(self._events)


def _config(**overrides: Any) -> BrainConfig:
    """Create a BrainConfig with custom overrides."""
    cfg = BrainConfig()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


# ===========================================================================
# 1. BetaPrior dataclass tests
# ===========================================================================


class TestBetaPrior:
    def test_beta_prior_defaults(self):
        """BetaPrior() has Jeffreys-like defaults: alpha=1, beta=1, mean=0.5."""
        p = BetaPrior()
        assert p.alpha == 1.0
        assert p.beta == 1.0
        assert p.n_observations == 0
        assert p.mean == pytest.approx(0.5, abs=1e-6)

    def test_beta_prior_mean(self):
        """mean = alpha / (alpha + beta) for various parameters."""
        p1 = BetaPrior(alpha=9.0, beta=1.0)
        assert p1.mean == pytest.approx(0.9, abs=1e-6)

        p2 = BetaPrior(alpha=1.0, beta=9.0)
        assert p2.mean == pytest.approx(0.1, abs=1e-6)

        p3 = BetaPrior(alpha=3.0, beta=7.0)
        assert p3.mean == pytest.approx(0.3, abs=1e-6)

    def test_beta_prior_confidence_low(self):
        """Few observations yield low confidence (< 1.0)."""
        p = BetaPrior(n_observations=5)
        assert p.confidence == pytest.approx(5 / 20.0, abs=1e-6)
        assert p.confidence < 1.0

        p_zero = BetaPrior(n_observations=0)
        assert p_zero.confidence == 0.0

    def test_beta_prior_confidence_capped(self):
        """20+ observations cap confidence at 1.0."""
        p20 = BetaPrior(n_observations=20)
        assert p20.confidence == 1.0

        p100 = BetaPrior(n_observations=100)
        assert p100.confidence == 1.0

    def test_beta_prior_multiplier_no_observations(self):
        """With 0 observations, confidence=0 so multiplier blends toward 1.0."""
        p = BetaPrior()  # alpha=1, beta=1, n_observations=0
        mult = p.multiplier()
        # confidence=0 => adjusted_mean = mean*0 + 0.5*(1-0) = 0.5
        # raw = 1.5 - 0.5*1.1 = 0.95
        assert mult == pytest.approx(0.95, abs=1e-6)

    def test_beta_prior_multiplier_high_success(self):
        """High alpha with many observations yields multiplier < 1.0."""
        p = BetaPrior(alpha=19.0, beta=1.0, n_observations=30)
        # mean = 19/20 = 0.95, confidence = 1.0
        # adjusted_mean = 0.95*1.0 + 0.5*0.0 = 0.95
        # raw = 1.5 - 0.95*1.1 = 1.5 - 1.045 = 0.455
        mult = p.multiplier()
        assert mult < 1.0
        assert mult == pytest.approx(0.455, abs=1e-3)

    def test_beta_prior_multiplier_bounds(self):
        """Multiplier is always clamped to [0.4, 1.5]."""
        # Extremely high success rate
        p_high = BetaPrior(alpha=100.0, beta=1.0, n_observations=100)
        assert p_high.multiplier() >= 0.4
        assert p_high.multiplier() <= 1.5

        # Extremely low success rate
        p_low = BetaPrior(alpha=1.0, beta=100.0, n_observations=100)
        assert p_low.multiplier() >= 0.4
        assert p_low.multiplier() <= 1.5

        # No observations
        p_none = BetaPrior()
        assert p_none.multiplier() >= 0.4
        assert p_none.multiplier() <= 1.5

    def test_beta_prior_multiplier_low_success_high_confidence(self):
        """Low success rate with high confidence yields multiplier > 1.0."""
        p = BetaPrior(alpha=1.0, beta=19.0, n_observations=30)
        # mean = 1/20 = 0.05, confidence = 1.0
        # adjusted_mean = 0.05*1.0 + 0.5*0.0 = 0.05
        # raw = 1.5 - 0.05*1.1 = 1.445
        mult = p.multiplier()
        assert mult > 1.0
        assert mult == pytest.approx(1.445, abs=1e-3)


# ===========================================================================
# 2. AdaptivePromotionPolicy tests
# ===========================================================================


class TestEffectiveThreshold:
    def test_effective_threshold_no_prior(self):
        """With no domain data and no observation log, returns near base threshold."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        # Force fresh computation
        policy._last_computed = 0.0
        result = policy.effective_threshold(10, "unknown_domain")
        # "general" domain exists in DEFAULT_DOMAINS with default BetaPrior
        # BetaPrior() → multiplier ~0.95, so effective = ceil(10 * 0.95) = 10
        min_t = max(1, int(10 * 0.4))  # 4
        max_t = int(math.ceil(10 * 1.5))  # 15
        assert min_t <= result <= max_t

    def test_effective_threshold_high_success_domain(self):
        """A domain with high success rate gets a lower effective threshold."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        # Manually inject a high-success prior for "security"
        policy._priors["security"] = BetaPrior(alpha=19.0, beta=1.0, n_observations=30)
        policy._last_computed = 1e18  # Prevent refresh

        base = 20
        result = policy.effective_threshold(base, "security")
        # multiplier ~0.455 => ceil(20 * 0.455) = ceil(9.1) = 10
        assert result < base
        assert result >= max(1, int(base * 0.4))

    def test_effective_threshold_low_success_domain(self):
        """A domain with low success rate gets a higher effective threshold."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        # Manually inject a low-success prior for "database"
        policy._priors["database"] = BetaPrior(alpha=1.0, beta=19.0, n_observations=30)
        policy._last_computed = 1e18  # Prevent refresh

        base = 20
        result = policy.effective_threshold(base, "database")
        # multiplier ~1.445 => ceil(20 * 1.445) = ceil(28.9) = 29
        assert result > base
        assert result <= int(math.ceil(base * 1.5))

    def test_effective_threshold_bounds(self):
        """Effective threshold never goes below max(1, base*0.4) or above base*1.5."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        policy._last_computed = 1e18

        for base in [1, 5, 10, 20, 50, 100]:
            min_threshold = max(1, int(base * 0.4))
            max_threshold = int(math.ceil(base * 1.5))

            # Test with extreme high-success prior
            policy._priors["test_hi"] = BetaPrior(alpha=100.0, beta=1.0, n_observations=100)
            result_hi = policy.effective_threshold(base, "test_hi")
            assert result_hi >= min_threshold, f"base={base}: {result_hi} < {min_threshold}"
            assert result_hi <= max_threshold, f"base={base}: {result_hi} > {max_threshold}"

            # Test with extreme low-success prior
            policy._priors["test_lo"] = BetaPrior(alpha=1.0, beta=100.0, n_observations=100)
            result_lo = policy.effective_threshold(base, "test_lo")
            assert result_lo >= min_threshold, f"base={base}: {result_lo} < {min_threshold}"
            assert result_lo <= max_threshold, f"base={base}: {result_lo} > {max_threshold}"

    def test_effective_threshold_falls_back_to_general(self):
        """Unknown domain falls back to 'general' prior if it exists."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        # Set a distinctive general prior
        policy._priors["general"] = BetaPrior(alpha=10.0, beta=10.0, n_observations=25)
        policy._last_computed = 1e18

        result = policy.effective_threshold(20, "totally_unknown")
        # general mean = 0.5, confidence = 1.0
        # adjusted_mean = 0.5*1.0 + 0.5*0.0 = 0.5
        # raw = 1.5 - 0.5*1.1 = 0.95
        # ceil(20 * 0.95) = 19
        assert result == 19


class TestRecordOutcome:
    def test_record_outcome_survived(self):
        """Recording a survived outcome increases alpha via _compute_priors rebuild."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())

        policy.record_outcome("security", promoted=True, survived=True)

        # _compute_priors rebuilds from Jeffreys prior (1,1) + 1 survived outcome
        assert policy._priors["security"].alpha == 2.0  # 1.0 base + 1.0 survived
        assert policy._priors["security"].beta == 1.0   # 1.0 base, no failure
        assert policy._priors["security"].n_observations == 1

    def test_record_outcome_not_survived(self):
        """Recording a non-survived outcome increases beta via _compute_priors rebuild."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())

        policy.record_outcome("security", promoted=True, survived=False)

        # _compute_priors rebuilds from Jeffreys prior (1,1) + 1 failed outcome
        assert policy._priors["security"].alpha == 1.0   # 1.0 base, no success
        assert policy._priors["security"].beta == 2.0    # 1.0 base + 1.0 failure
        assert policy._priors["security"].n_observations == 1

    def test_record_outcome_creates_prior(self):
        """Recording an outcome for an unknown domain creates a new BetaPrior."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        assert "brand_new_domain" not in policy._priors

        policy.record_outcome("brand_new_domain", promoted=True, survived=True)

        assert "brand_new_domain" in policy._priors
        prior = policy._priors["brand_new_domain"]
        # Starts from BetaPrior() defaults then +1 alpha
        assert prior.alpha == 2.0  # 1.0 default + 1.0 survived
        assert prior.beta == 1.0   # 1.0 default, no failure
        assert prior.n_observations == 1

    def test_record_outcome_case_insensitive(self):
        """Domain names are lowercased before recording."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        policy.record_outcome("Security", promoted=True, survived=True)
        policy.record_outcome("SECURITY", promoted=True, survived=True)

        assert "security" in policy._priors
        assert policy._priors["security"].alpha == 3.0  # 1 default + 2 survived
        assert policy._priors["security"].n_observations == 2

    def test_record_outcome_stored_in_outcomes_buffer(self):
        """Outcomes are stored in the internal _outcomes buffer."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        assert len(policy._outcomes) == 0

        policy.record_outcome("testing", promoted=True, survived=True)
        policy.record_outcome("testing", promoted=True, survived=False)

        assert len(policy._outcomes) == 2
        assert policy._outcomes[0]["domain"] == "testing"
        assert policy._outcomes[0]["survived"] is True
        assert policy._outcomes[1]["survived"] is False


class TestComputePriors:
    def test_compute_priors_from_observation_log(self):
        """_compute_priors incorporates observation log events."""
        events = [
            _MockObservation(
                event_type="reinforced",
                outcome="positive",
                rule_ids=("CR-001",),
                metadata={"domain": "security"},
            ),
            _MockObservation(
                event_type="reinforced",
                outcome="positive",
                rule_ids=("CR-002",),
                metadata={"domain": "security"},
            ),
            _MockObservation(
                event_type="deprecated",
                outcome="unknown",
                rule_ids=("CR-003",),
                metadata={"domain": "testing"},
            ),
        ]
        log = MockObservationLog(events)
        policy = AdaptivePromotionPolicy(observation_log=log, config=_config())
        policy._compute_priors()

        # Security: 2 reinforced events -> alpha += 0.1 each
        sec = policy._priors.get("security")
        assert sec is not None
        assert sec.alpha > 1.0  # Base 1.0 + 2 * 0.1

        # Testing: 1 deprecated -> beta += 0.5
        test = policy._priors.get("testing")
        assert test is not None
        assert test.beta > 1.0  # Base 1.0 + 0.5

    def test_compute_priors_default_domains_initialized(self):
        """All DEFAULT_DOMAINS get initialized even without observation data."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        policy._compute_priors()

        for domain in AdaptivePromotionPolicy.DEFAULT_DOMAINS:
            assert domain in policy._priors

    def test_compute_priors_incorporates_outcomes(self):
        """_compute_priors includes in-memory outcomes."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        policy._outcomes = [
            {"domain": "security", "survived": True, "promoted": True, "timestamp": 0},
            {"domain": "security", "survived": False, "promoted": True, "timestamp": 0},
        ]
        policy._compute_priors()

        sec = policy._priors["security"]
        # Base 1.0 + 1 survived, base 1.0 + 1 not-survived
        assert sec.alpha == 2.0
        assert sec.beta == 2.0


class TestStats:
    def test_stats_returns_dict(self):
        """stats() returns dict with expected top-level keys."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        result = policy.stats()

        assert isinstance(result, dict)
        assert "domains" in result
        assert "total_outcomes" in result
        assert isinstance(result["domains"], dict)
        assert isinstance(result["total_outcomes"], int)

    def test_stats_domain_fields(self):
        """Each domain in stats has the expected sub-keys."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        result = policy.stats()

        expected_keys = {
            "alpha", "beta", "mean", "confidence", "multiplier",
            "n_observations", "effective_l4_to_l3", "effective_l3_to_l2",
        }
        for domain, info in result["domains"].items():
            assert expected_keys.issubset(info.keys()), (
                f"Domain '{domain}' missing keys: {expected_keys - info.keys()}"
            )

    def test_stats_total_outcomes_reflects_recordings(self):
        """total_outcomes counts recorded outcomes."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        assert policy.stats()["total_outcomes"] == 0

        policy.record_outcome("security", promoted=True, survived=True)
        policy.record_outcome("testing", promoted=True, survived=False)

        assert policy.stats()["total_outcomes"] == 2


class TestGetPrior:
    def test_get_prior_existing_domain(self):
        """get_prior returns the BetaPrior for an existing domain."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        policy.record_outcome("security", promoted=True, survived=True)

        prior = policy.get_prior("security")
        assert isinstance(prior, BetaPrior)
        assert prior.alpha == 2.0  # 1.0 default + 1.0

    def test_get_prior_unknown_domain(self):
        """get_prior returns a fresh BetaPrior for unknown domains."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        prior = policy.get_prior("nonexistent_xyz")
        assert isinstance(prior, BetaPrior)
        assert prior.alpha == 1.0
        assert prior.beta == 1.0


class TestCacheBehavior:
    def test_cache_prevents_recomputation(self):
        """Priors are not recomputed if cache is fresh."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        # Force initial computation
        policy._compute_priors()
        policy._last_computed = 1e18  # Far future

        # Inject a custom prior
        policy._priors["custom"] = BetaPrior(alpha=99.0, beta=1.0, n_observations=50)

        # effective_threshold should use cached priors (not recompute)
        result = policy.effective_threshold(10, "custom")
        # If recomputed, "custom" would be gone. Since cached, it should use our prior.
        assert result < 10  # High success prior => lower threshold

    def test_stale_cache_triggers_recomputation(self):
        """Stale cache (last_computed = 0) triggers recomputation."""
        policy = AdaptivePromotionPolicy(observation_log=None, config=_config())
        # Inject a custom prior that won't survive recomputation
        policy._priors["ephemeral"] = BetaPrior(alpha=99.0, beta=1.0, n_observations=50)
        policy._last_computed = 0.0  # Stale

        # This triggers _maybe_refresh -> _compute_priors -> overwrites priors
        _ = policy.effective_threshold(10, "ephemeral")
        # "ephemeral" not in DEFAULT_DOMAINS, so after recomputation it's gone
        assert "ephemeral" not in policy._priors
