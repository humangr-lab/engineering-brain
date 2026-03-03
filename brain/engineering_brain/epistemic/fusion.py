"""Belief fusion operators — Cumulative Belief Fusion (CBF).

CBF fuses opinions from independent sources. Key property:
uncertainty monotonically decreases with more evidence.

Reference: Josang, A. (2016). Subjective Logic, Ch. 12.
"""

from __future__ import annotations

from engineering_brain.epistemic.opinion import OpinionTuple


def cbf(omega_a: OpinionTuple, omega_b: OpinionTuple) -> OpinionTuple:
    """Cumulative Belief Fusion for two independent sources.

    u_fused = u_A * u_B / (u_A + u_B - u_A * u_B)
    Invariant: u_fused < min(u_A, u_B) when both have partial uncertainty.
    """
    u_a, u_b = omega_a.u, omega_b.u

    # Handle dogmatic cases (u=0)
    if u_a < 1e-15 and u_b < 1e-15:
        # Both dogmatic — check for conflict (H14)
        conflict = omega_a.b * omega_b.d + omega_a.d * omega_b.b
        if conflict > 0.5:
            # High conflict between dogmatic opinions → return maximum uncertainty
            a = (omega_a.a + omega_b.a) / 2
            return OpinionTuple(b=0.0, d=0.0, u=1.0, a=a)
        # Low conflict — safe to average
        b = (omega_a.b + omega_b.b) / 2
        d = (omega_a.d + omega_b.d) / 2
        u = 0.0
    elif u_a < 1e-15:
        return omega_a
    elif u_b < 1e-15:
        return omega_b
    else:
        denom = u_a + u_b - u_a * u_b
        b = (omega_a.b * u_b + omega_b.b * u_a) / denom
        d = (omega_a.d * u_b + omega_b.d * u_a) / denom
        u = (u_a * u_b) / denom

    # Renormalize for float precision
    total = b + d + u
    if total > 1e-15:
        b /= total
        d /= total
        u /= total

    # Uncertainty-weighted base rate (Josang 2016, Ch. 12)
    u_sum = omega_a.u + omega_b.u
    if u_sum > 1e-15:
        a = (omega_a.a * omega_b.u + omega_b.a * omega_a.u) / u_sum
    else:
        a = (omega_a.a + omega_b.a) / 2
    return OpinionTuple(b=b, d=d, u=u, a=a)


def multi_source_cbf(opinions: list[OpinionTuple]) -> OpinionTuple:
    """Sequential CBF across N independent sources.

    Known limitation: the base rate 'a' is order-dependent because CBF
    base rate fusion is not strictly associative. b/d/u values are
    mathematically associative and unaffected by ordering.
    """
    if not opinions:
        return OpinionTuple.vacuous()
    result = opinions[0]
    for op in opinions[1:]:
        result = cbf(result, op)
    return result
