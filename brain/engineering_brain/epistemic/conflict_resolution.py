"""Conflict detection and resolution for Dempster-Shafer evidence fusion.

Dempster's conflict factor K measures disagreement between opinions.
When K is high, standard CBF produces unreliable results — Murphy's
weighted averaging provides robust fusion under high conflict.

Reference: Murphy, C.K. (2000). Combining belief functions when evidence conflicts.
Reference: Josang, A. (2016). Subjective Logic, Ch. 12.
"""

from __future__ import annotations

from enum import StrEnum

from engineering_brain.epistemic.fusion import cbf
from engineering_brain.epistemic.opinion import OpinionTuple


class ConflictSeverity(StrEnum):
    """Severity classification based on Dempster conflict factor K."""

    NONE = "none"  # K < 0.3 — sources agree
    LOW = "low"  # 0.3 <= K < 0.5 — mild disagreement
    MODERATE = "moderate"  # 0.5 <= K < 0.7 — notable disagreement
    HIGH = "high"  # 0.7 <= K < 0.9 — strong contradiction
    EXTREME = "extreme"  # K >= 0.9 — total contradiction


def dempster_conflict(omega_a: OpinionTuple, omega_b: OpinionTuple) -> float:
    """Compute Dempster's conflict factor K between two opinions.

    K = b_A * d_B + d_A * b_B

    K in [0, 1]:
        K = 0:    no conflict (complete agreement)
        K > 0.5:  moderate conflict
        K > 0.8:  high conflict (Murphy's recommended)
        K = 1:    complete conflict (Dempster's rule undefined)
    """
    return omega_a.b * omega_b.d + omega_a.d * omega_b.b


def classify_conflict(k: float) -> ConflictSeverity:
    """Classify conflict severity from K value."""
    if k >= 0.9:
        return ConflictSeverity.EXTREME
    if k >= 0.7:
        return ConflictSeverity.HIGH
    if k >= 0.5:
        return ConflictSeverity.MODERATE
    if k >= 0.3:
        return ConflictSeverity.LOW
    return ConflictSeverity.NONE


def murphy_weighted_average(
    opinions: list[OpinionTuple],
    weights: list[float] | None = None,
) -> OpinionTuple:
    """Murphy's weighted averaging for high-conflict evidence fusion.

    Algorithm:
        1. Compute weighted average of all opinions
        2. Apply CBF n-1 times on the averaged opinion

    More robust than direct CBF under high conflict (K > 0.5).
    """
    if not opinions:
        return OpinionTuple.vacuous()
    if len(opinions) == 1:
        return opinions[0]

    n = len(opinions)
    if weights is None:
        w = [1.0 / n] * n
    else:
        total = sum(weights)
        w = [x / total for x in weights] if total > 1e-15 else [1.0 / n] * n

    # Step 1: weighted average
    avg_b = sum(wi * op.b for wi, op in zip(w, opinions, strict=False))
    avg_d = sum(wi * op.d for wi, op in zip(w, opinions, strict=False))
    avg_u = sum(wi * op.u for wi, op in zip(w, opinions, strict=False))
    avg_a = sum(wi * op.a for wi, op in zip(w, opinions, strict=False))

    # Normalize b+d+u=1
    total = avg_b + avg_d + avg_u
    if total > 1e-15:
        avg_b /= total
        avg_d /= total
        avg_u /= total

    averaged = OpinionTuple(b=avg_b, d=avg_d, u=avg_u, a=avg_a)

    # Step 2: apply CBF n-1 times
    result = averaged
    for _ in range(n - 1):
        result = cbf(result, averaged)

    return result
