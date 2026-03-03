"""Adaptive scoring weight optimizer for the Engineering Knowledge Brain.

Optimizes the 6 scoring signal weights using Thompson Sampling. Each signal
(tech_match, domain_match, severity, reinforcement, recency, confidence) has
a Beta(alpha, beta) distribution. Feedback from the observation log updates
the distributions: positive feedback on high-scoring signals increases alpha,
negative feedback increases beta.

Weights are sampled from the posteriors, then normalized to sum to 1.0.

Reference: Thompson (1933), Russo et al. "A Tutorial on Thompson Sampling" (2018).
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


SIGNAL_NAMES = [
    "tech_match", "domain_match", "severity",
    "reinforcement", "recency", "confidence",
]
DEFAULT_WEIGHTS = [0.28, 0.18, 0.18, 0.13, 0.13, 0.10]


@dataclass
class SignalDistribution:
    """Beta distribution for a single scoring signal."""

    name: str
    alpha: float = 1.0
    beta: float = 1.0

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        ab = self.alpha + self.beta
        return (self.alpha * self.beta) / (ab * ab * (ab + 1))

    def sample(self) -> float:
        """Sample from Beta distribution. Uses random.betavariate."""
        try:
            return random.betavariate(max(self.alpha, 0.01), max(self.beta, 0.01))
        except (ValueError, ZeroDivisionError):
            return self.mean


class AdaptiveWeightOptimizer:
    """Optimize scoring weights using Thompson Sampling.

    Reads feedback from observation log (positive/negative outcomes)
    and adjusts signal weights accordingly. Signals that consistently
    correlate with positive outcomes get higher weights.
    """

    def __init__(
        self,
        observation_log: Any = None,
        config: Any = None,
    ) -> None:
        self._log = observation_log
        self._config = config

        # Initialize distributions from default weights
        self._distributions: dict[str, SignalDistribution] = {}
        for name, w in zip(SIGNAL_NAMES, DEFAULT_WEIGHTS):
            # Use default weight to set initial alpha/beta ratio
            # alpha = w * 20, beta = (1-w) * 20 → mean = w
            self._distributions[name] = SignalDistribution(
                name=name,
                alpha=max(w * 20, 0.5),
                beta=max((1 - w) * 20, 0.5),
            )

        self._current_weights: dict[str, float] | None = None
        self._update_interval = 50  # Re-sample every 50 queries
        self._query_count = 0
        self._last_log_read: float = 0.0
        self._log_read_interval = 300.0  # Re-read log every 5 min
        self._log_watermark: int = 0  # H13: track already-processed log entries

    def get_weights(self) -> dict[str, float]:
        """Get current optimized weights. May re-sample from posteriors."""
        self._query_count += 1

        # Periodically refresh from log
        now = time.time()
        if now - self._last_log_read > self._log_read_interval:
            self._update_from_log()
            self._last_log_read = now

        # Re-sample periodically
        if self._current_weights is None or self._query_count % self._update_interval == 0:
            self._current_weights = self._sample_and_normalize()

        return dict(self._current_weights)

    def record_feedback(
        self,
        node_id: str,
        helpful: bool,
        signal_scores: dict[str, float] | None = None,
    ) -> None:
        """Update signal distributions based on user feedback.

        If helpful=True: signals with high scores get alpha += contribution
        If helpful=False: signals with high scores get beta += contribution

        signal_scores: {signal_name: score_value} for the node that received feedback.
        If not provided, updates all signals equally.
        """
        if signal_scores:
            for name, score in signal_scores.items():
                dist = self._distributions.get(name)
                if dist is None:
                    continue
                # Uniform contribution — all signals get equal credit to avoid rich-get-richer bias
                contribution = 0.25
                if helpful:
                    dist.alpha = min(dist.alpha + contribution, 1000.0)
                else:
                    dist.beta = min(dist.beta + contribution, 1000.0)
        else:
            # Equal update to all signals
            contribution = 0.2
            for dist in self._distributions.values():
                if helpful:
                    dist.alpha = min(dist.alpha + contribution, 1000.0)
                else:
                    dist.beta = min(dist.beta + contribution, 1000.0)

        # Invalidate cached weights
        self._current_weights = None

    def _sample_and_normalize(self) -> dict[str, float]:
        """Sample from Beta posteriors and normalize to sum=1.0."""
        samples: dict[str, float] = {}
        for name, dist in self._distributions.items():
            samples[name] = dist.sample()

        # Normalize
        total = sum(samples.values())
        if total <= 0:
            # Fallback to defaults
            return dict(zip(SIGNAL_NAMES, DEFAULT_WEIGHTS))

        return {name: val / total for name, val in samples.items()}

    def _update_from_log(self) -> None:
        """Batch-update distributions from recent observation log entries.

        Reads reinforcement/weakening events and adjusts distributions.
        Positive reinforcements → all signals get small alpha boost.
        Negative feedback → all signals get small beta boost.

        H13 fix: Uses a watermark to only process new entries since
        last read, preventing N-fold inflation from re-reading all entries.
        """
        if self._log is None:
            return

        try:
            observations = self._log.read_all()
        except Exception:
            return

        # H13: Only process entries past the watermark
        new_observations = observations[self._log_watermark:]
        self._log_watermark = len(observations)

        positive_count = 0
        negative_count = 0
        for obs in new_observations:
            if obs.event_type == "reinforced" and obs.outcome == "positive":
                positive_count += 1
            elif obs.event_type == "weakened" or obs.outcome == "negative":
                negative_count += 1

        # Apply as weak updates (log evidence is noisy)
        if positive_count > 0:
            boost = min(positive_count * 0.05, 2.0)
            for dist in self._distributions.values():
                dist.alpha += boost

        if negative_count > 0:
            penalty = min(negative_count * 0.05, 2.0)
            for dist in self._distributions.values():
                dist.beta += penalty

    def get_mean_weights(self) -> dict[str, float]:
        """Get deterministic weights based on distribution means (no sampling)."""
        means = {name: dist.mean for name, dist in self._distributions.items()}
        total = sum(means.values())
        if total <= 0:
            return dict(zip(SIGNAL_NAMES, DEFAULT_WEIGHTS))
        return {name: val / total for name, val in means.items()}

    def stats(self) -> dict[str, Any]:
        """Current distributions and effective weights."""
        result: dict[str, Any] = {
            "signals": {},
            "query_count": self._query_count,
            "current_weights": self.get_mean_weights(),
        }
        for name, dist in self._distributions.items():
            result["signals"][name] = {
                "alpha": round(dist.alpha, 2),
                "beta": round(dist.beta, 2),
                "mean": round(dist.mean, 4),
                "variance": round(dist.variance, 6),
            }
        return result
