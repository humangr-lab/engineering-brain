"""Bayesian source trust learning via Beta distribution.

The static SOURCE_TRUST_MAP provides initial trust weights. As the
system observes which sources produce correct vs incorrect predictions,
it updates trust using Bayesian conjugate analysis:

    Prior: Beta(alpha, beta)
    Observation: correct (Bernoulli success) or incorrect (failure)
    Posterior: Beta(alpha + 1, beta) or Beta(alpha, beta + 1)

After many observations, the posterior mean converges to the
empirical accuracy rate — no MCMC required (closed form).

Reference: Josang, A. (2016). Subjective Logic, Ch. 10.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engineering_brain.epistemic.source_trust import SOURCE_TRUST_MAP


@dataclass
class BetaPrior:
    """Beta(alpha, beta) prior for a source type's trustworthiness.

    alpha = pseudo-count of successes (correct predictions)
    beta = pseudo-count of failures (incorrect predictions)
    """

    alpha: float = 1.0
    beta: float = 1.0

    @property
    def mean(self) -> float:
        """Posterior mean = alpha / (alpha + beta)."""
        total = self.alpha + self.beta
        if total < 1e-15:
            return 0.5
        return self.alpha / total

    @property
    def variance(self) -> float:
        """Posterior variance = alpha*beta / ((alpha+beta)^2 * (alpha+beta+1))."""
        total = self.alpha + self.beta
        if total < 1e-15:
            return 0.25
        return (self.alpha * self.beta) / (total * total * (total + 1))

    @property
    def confidence(self) -> float:
        """How confident we are in our estimate (higher = more observations)."""
        # Confidence grows with observations: 1 - 1/(alpha+beta)
        total = self.alpha + self.beta
        if total <= 1.0:
            return 0.0
        return 1.0 - 1.0 / total

    @property
    def observations(self) -> int:
        """Total number of observations (approximate, non-negative)."""
        return max(0, int(self.alpha + self.beta - 2))  # subtract initial pseudocounts

    def to_dict(self) -> dict[str, float]:
        return {"alpha": round(self.alpha, 4), "beta": round(self.beta, 4)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BetaPrior:
        return cls(alpha=float(d.get("alpha", 1.0)), beta=float(d.get("beta", 1.0)))


class LearnedSourceTrust:
    """Bayesian learner for source type trustworthiness."""

    def __init__(self, priors: dict[str, BetaPrior] | None = None) -> None:
        if priors is not None:
            self._priors = dict(priors)
        else:
            # Initialize from static SOURCE_TRUST_MAP
            # alpha = trust * 10, beta = (1-trust) * 10 → weak prior centered on static trust
            self._priors = {}
            for source_type, trust in SOURCE_TRUST_MAP.items():
                self._priors[source_type] = BetaPrior(
                    alpha=trust * 10.0,
                    beta=(1.0 - trust) * 10.0,
                )

    def observe(self, source_type: str, correct: bool) -> float:
        """Record an observation and return updated posterior mean.

        correct=True: source prediction was accurate → alpha += 1
        correct=False: source prediction was wrong → beta += 1
        """
        if source_type not in self._priors:
            # Unknown source type: start with uninformative prior
            self._priors[source_type] = BetaPrior(alpha=1.0, beta=1.0)

        prior = self._priors[source_type]
        if correct:
            self._priors[source_type] = BetaPrior(
                alpha=prior.alpha + 1.0, beta=prior.beta
            )
        else:
            self._priors[source_type] = BetaPrior(
                alpha=prior.alpha, beta=prior.beta + 1.0
            )
        return self._priors[source_type].mean

    def get_trust(self, source_type: str) -> float:
        """Get current trust estimate for a source type.

        Returns posterior mean if observed, otherwise falls back to SOURCE_TRUST_MAP.
        """
        if source_type in self._priors:
            return self._priors[source_type].mean
        return SOURCE_TRUST_MAP.get(source_type, 0.5)

    def get_prior(self, source_type: str) -> BetaPrior:
        """Get the BetaPrior for a source type."""
        if source_type not in self._priors:
            trust = SOURCE_TRUST_MAP.get(source_type, 0.5)
            self._priors[source_type] = BetaPrior(
                alpha=trust * 10.0, beta=(1.0 - trust) * 10.0
            )
        return self._priors[source_type]

    def divergence_from_static(self) -> dict[str, float]:
        """How much learned trust differs from static SOURCE_TRUST_MAP.

        Positive = learned trust is higher than static.
        Negative = learned trust is lower.
        """
        result = {}
        for source_type, prior in self._priors.items():
            static = SOURCE_TRUST_MAP.get(source_type, 0.5)
            result[source_type] = prior.mean - static
        return result

    def to_dict(self) -> dict[str, dict[str, float]]:
        """Serialize for persistence."""
        return {st: p.to_dict() for st, p in self._priors.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearnedSourceTrust:
        """Deserialize from persistence."""
        priors = {}
        for st, p_dict in data.items():
            priors[st] = BetaPrior.from_dict(p_dict)
        return cls(priors=priors)
