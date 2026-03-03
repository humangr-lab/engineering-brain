"""Subjective Logic OpinionTuple — lightweight frozen dataclass.

An opinion omega = (b, d, u, a) represents belief about a proposition:
    b (belief):      evidence-based support
    d (disbelief):   evidence-based opposition
    u (uncertainty): lack of evidence
    a (base_rate):   prior probability absent evidence

Invariant: b + d + u = 1.0
Projected probability: P(x) = b + a * u

Reference: Josang, A. (2016). Subjective Logic. Springer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpinionTuple:
    """Subjective Logic opinion (b, d, u, a).

    Frozen dataclass for performance — no Pydantic overhead.
    """

    b: float
    d: float
    u: float
    a: float = 0.5

    def __post_init__(self) -> None:
        for name, val in [("b", self.b), ("d", self.d), ("u", self.u), ("a", self.a)]:
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{name} must be in [0, 1], got {val}")
        total = self.b + self.d + self.u
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"b + d + u must equal 1.0, got {total:.9f}")

    @property
    def projected_probability(self) -> float:
        """P(x) = b + a * u — expected probability incorporating prior."""
        return self.b + self.a * self.u

    @property
    def evidence_strength(self) -> float:
        """1 - u: total evidence-based mass."""
        return 1.0 - self.u

    @property
    def shannon_entropy(self) -> float:
        """H(omega) = -sum m*log2(m) for m in {b, d, u} where m > 0."""
        h = 0.0
        for m in (self.b, self.d, self.u):
            if m > 1e-15:
                h -= m * math.log2(m)
        return h

    def to_confidence(self) -> float:
        """Backward-compatible scalar confidence = projected_probability."""
        return self.projected_probability

    def to_dict(self) -> dict[str, float]:
        """Flat dict for graph storage."""
        return {
            "ep_b": round(self.b, 6),
            "ep_d": round(self.d, 6),
            "ep_u": round(self.u, 6),
            "ep_a": round(self.a, 6),
        }

    @classmethod
    def from_dict(cls, d: dict) -> OpinionTuple:
        """Reconstruct from graph properties, renormalizing for float drift."""
        b = float(d.get("ep_b", 0.0))
        dd = float(d.get("ep_d", 0.0))
        u = float(d.get("ep_u", 1.0))
        a = float(d.get("ep_a", 0.5))
        total = b + dd + u
        if total > 1e-15 and abs(total - 1.0) > 1e-9:
            b /= total
            dd /= total
            u /= total
        return cls(b=b, d=dd, u=u, a=a)

    @classmethod
    def vacuous(cls, a: float = 0.5) -> OpinionTuple:
        """Complete ignorance: no evidence at all."""
        return cls(b=0.0, d=0.0, u=1.0, a=a)

    @classmethod
    def dogmatic_belief(cls, a: float = 0.5) -> OpinionTuple:
        """Absolute certainty in truth."""
        return cls(b=1.0, d=0.0, u=0.0, a=a)

    @classmethod
    def dogmatic_disbelief(cls, a: float = 0.5) -> OpinionTuple:
        """Absolute certainty in falsehood."""
        return cls(b=0.0, d=1.0, u=0.0, a=a)

    @classmethod
    def from_confidence(
        cls, confidence: float, uncertainty: float = 0.3, a: float = 0.5
    ) -> OpinionTuple:
        """Create from legacy scalar confidence for migration.

        Solves: P(x) = b + a*u = confidence  =>  b = confidence - a*u
        """
        u = max(0.0, min(1.0, uncertainty))
        b = max(0.0, min(1.0 - u, confidence - a * u))
        d = 1.0 - u - b
        return cls(b=b, d=d, u=u, a=a)
