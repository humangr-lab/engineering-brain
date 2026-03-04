"""Adaptive promotion policy for the Engineering Knowledge Brain.

Uses Bayesian Beta priors per domain to dynamically adjust promotion thresholds.
Domains with higher historical promotion success rates get lower thresholds
(faster promotion), while domains with lower success rates get higher thresholds
(more cautious promotion).

Reference: Thompson Sampling (Thompson 1933, Russo et al. 2018 "A Tutorial on
Thompson Sampling"). Adapted for knowledge promotion in a cortical hierarchy.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BetaPrior:
    """Beta distribution prior for a single domain's promotion success rate.

    Uses Jeffreys prior (alpha=1, beta=1) as starting point — uninformative.
    Updated via Bayesian conjugate update: success → alpha += 1, failure → beta += 1.
    """

    alpha: float = 1.0  # Successes + prior
    beta: float = 1.0  # Failures + prior
    n_observations: int = 0

    @property
    def mean(self) -> float:
        """Expected success rate (0.0-1.0)."""
        ab = self.alpha + self.beta
        return self.alpha / ab if ab > 0 else 0.5

    @property
    def variance(self) -> float:
        """Variance of the Beta distribution."""
        ab = self.alpha + self.beta
        if ab <= 0:
            return 0.0
        return (self.alpha * self.beta) / (ab * ab * (ab + 1))

    @property
    def confidence(self) -> float:
        """How confident we are in the estimate (0.0-1.0).

        Reaches 0.5 at 10 observations, 1.0 at 20+.
        Low confidence → multiplier stays near 1.0 (no adjustment).
        """
        return min(1.0, self.n_observations / 20.0)

    def multiplier(self) -> float:
        """Threshold multiplier based on success rate and confidence.

        Range: [0.4, 1.5]
        - High success rate + high confidence → ~0.4 (lower threshold, faster promotion)
        - Low success rate + high confidence → ~1.5 (higher threshold, cautious promotion)
        - Low confidence → ~1.0 (no adjustment, use base threshold)
        """
        # Blend toward 1.0 when confidence is low
        adjusted_mean = self.mean * self.confidence + 0.5 * (1.0 - self.confidence)
        # Map [0.0, 1.0] mean → [1.5, 0.4] multiplier (inverted: high success → low multiplier)
        raw = 1.5 - adjusted_mean * 1.1
        return max(0.4, min(1.5, raw))

    def sample(self) -> float:
        """Sample from the Beta distribution for Thompson Sampling exploration."""
        import random

        return random.betavariate(self.alpha, self.beta)


class AdaptivePromotionPolicy:
    """Bayesian adaptive thresholds for knowledge promotion.

    Tracks promotion outcomes per domain and adjusts thresholds accordingly.
    Domains where promoted rules have high survival rates (not deprecated
    within 30 days) get lower effective thresholds, enabling faster promotion.
    """

    # Default domains to track
    DEFAULT_DOMAINS = [
        "security",
        "testing",
        "architecture",
        "api",
        "database",
        "performance",
        "devops",
        "ui",
        "general",
    ]

    def __init__(
        self,
        observation_log: Any = None,
        config: Any = None,
    ) -> None:
        self._log = observation_log
        self._config = config
        self._priors: dict[str, BetaPrior] = {}
        self._outcomes: list[dict[str, Any]] = []  # In-memory outcome buffer
        self._cache_ttl = 300.0  # 5 min cache
        self._last_computed: float = 0.0

    def effective_threshold(
        self,
        base_threshold: int,
        domain: str,
        layer_from: str = "L4",
    ) -> int:
        """Compute adapted threshold for a given domain and layer transition.

        Returns threshold in range [base * 0.4, base * 1.5].
        High-confidence domains get lower thresholds (faster promotion).
        Low-confidence domains get higher thresholds (cautious promotion).
        """
        self._maybe_refresh()
        prior = self._priors.get(domain.lower())
        if prior is None:
            prior = self._priors.get("general", BetaPrior())

        mult = prior.multiplier()
        adapted = int(math.ceil(base_threshold * mult))

        # Clamp to reasonable bounds
        min_threshold = max(1, int(base_threshold * 0.4))
        max_threshold = int(math.ceil(base_threshold * 1.5))
        return max(min_threshold, min(max_threshold, adapted))

    def record_outcome(
        self,
        domain: str,
        promoted: bool,
        survived: bool,
    ) -> None:
        """Record a promotion outcome.

        Args:
            domain: The domain of the promoted knowledge.
            promoted: Whether the node was promoted (always True for outcomes).
            survived: Whether the promoted node survived (not deprecated within 30 days).
        """
        domain_lower = domain.lower()
        self._outcomes.append(
            {
                "domain": domain_lower,
                "promoted": promoted,
                "survived": survived,
                "timestamp": time.time(),
            }
        )

        # Invalidate cache so _maybe_refresh() triggers a full rebuild.
        # _compute_priors() is the sole writer to self._priors, which
        # eliminates inconsistency between direct updates and full rebuilds.
        self._last_computed = 0.0
        self._maybe_refresh()

    def _maybe_refresh(self) -> None:
        """Refresh priors from observation log if cache is stale."""
        now = time.time()
        if now - self._last_computed < self._cache_ttl and self._priors:
            return
        self._compute_priors()
        self._last_computed = now

    def _compute_priors(self) -> None:
        """Build Beta priors from observation log + in-memory outcomes."""
        # Start fresh from Jeffreys priors
        priors: dict[str, BetaPrior] = {}
        for domain in self.DEFAULT_DOMAINS:
            priors[domain] = BetaPrior()

        # Incorporate observation log data if available
        if self._log is not None:
            try:
                for obs in self._log.read_all():
                    if obs.event_type == "reinforced" and obs.outcome == "positive":
                        for _rid in obs.rule_ids:
                            domain = obs.metadata.get("domain", "general")
                            p = priors.setdefault(domain, BetaPrior())
                            p.alpha += 0.1  # Weak positive signal from reinforcement
                            p.n_observations += 1
                    elif obs.event_type == "deprecated":
                        domain = obs.metadata.get("domain", "general")
                        p = priors.setdefault(domain, BetaPrior())
                        p.beta += 0.5  # Moderate negative signal from deprecation
                        p.n_observations += 1
            except Exception as exc:
                logger.debug("Failed to read observation log for adaptive promotion: %s", exc)

        # Incorporate in-memory outcomes (stronger signal)
        for outcome in self._outcomes:
            domain = outcome["domain"]
            p = priors.setdefault(domain, BetaPrior())
            if outcome["survived"]:
                p.alpha += 1.0
            else:
                p.beta += 1.0
            p.n_observations += 1

        self._priors = priors

    def get_prior(self, domain: str) -> BetaPrior:
        """Get the Beta prior for a specific domain."""
        self._maybe_refresh()
        return self._priors.get(domain.lower(), BetaPrior())

    def stats(self) -> dict[str, Any]:
        """Return current priors and effective thresholds per domain."""
        self._maybe_refresh()
        result: dict[str, Any] = {
            "domains": {},
            "total_outcomes": len(self._outcomes),
        }
        for domain, prior in sorted(self._priors.items()):
            result["domains"][domain] = {
                "alpha": prior.alpha,
                "beta": prior.beta,
                "mean": round(prior.mean, 3),
                "confidence": round(prior.confidence, 3),
                "multiplier": round(prior.multiplier(), 3),
                "n_observations": prior.n_observations,
                "effective_l4_to_l3": self.effective_threshold(5, domain, "L4"),
                "effective_l3_to_l2": self.effective_threshold(20, domain, "L3"),
            }
        return result
