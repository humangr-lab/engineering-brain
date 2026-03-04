"""Temporal dynamics for epistemic opinions using Hawkes Process.

Models knowledge decay and reinforcement:
    lambda*(t) = mu + sum alpha * beta * exp(-beta * (t - ti))

Key insight: belief that decays becomes uncertainty, NOT disbelief.
Forgotten != wrong — it's epistemically unknown again.

Each cortical layer has a calibrated decay profile:
    L0 Axioms:    never decay (permanent truths)
    L1 Principles: very slow (decades of wisdom)
    L2 Patterns:   slow (years of practice)
    L3 Rules:      moderate (months to years)
    L4 Evidence:   faster (months)
    L5 Context:    fast (hours to days)

Reference: Hawkes, A.G. (1971). Spectra of some self-exciting and
           mutually exciting point processes.
"""

from __future__ import annotations

import math

from engineering_brain.epistemic.opinion import OpinionTuple


class HawkesDecayEngine:
    """Temporal dynamics engine based on Hawkes process.

    Parameters:
        mu:    baseline decay rate (larger = faster natural decay)
        alpha: excitation magnitude per reinforcement event
        beta:  excitation decay speed (how fast boost fades)
    """

    def __init__(
        self,
        mu: float = 0.001,
        alpha: float = 0.05,
        beta: float = 0.01,
    ) -> None:
        self.mu = mu
        self.alpha = alpha
        self.beta = beta

    def compute_intensity(self, now_days: float, event_timestamps_days: list[float]) -> float:
        """Compute Hawkes conditional intensity at time `now`.

        Args:
            now_days: Current time in days.
            event_timestamps_days: Past event times in days.

        Returns:
            Intensity lambda*(now).
        """
        excitation = 0.0
        for t_i in event_timestamps_days:
            dt = now_days - t_i
            if dt > 0:
                excitation += self.alpha * self.beta * math.exp(-self.beta * dt)
        return self.mu + excitation

    def compute_temporal_factor(self, now_unix: int, event_timestamps_unix: list[int]) -> float:
        """Compute temporal modulation factor tau in [0, 1].

        tau = 1: fully maintained (active reinforcement)
        tau -> 0: fully decayed (no recent events)
        """
        seconds_per_day = 86400.0
        now_days = now_unix / seconds_per_day
        events_days = [ts / seconds_per_day for ts in event_timestamps_unix]

        intensity = self.compute_intensity(now_days, events_days)
        n_events = max(len(events_days), 1)
        max_intensity = self.mu + n_events * self.alpha * self.beta

        if max_intensity < 1e-15:
            return 0.0

        tau = intensity / max_intensity
        return max(0.0, min(1.0, tau))

    def apply_decay(
        self,
        opinion: OpinionTuple,
        now_unix: int,
        last_decay_unix: int,
        event_timestamps_unix: list[int],
    ) -> OpinionTuple:
        """Apply temporal decay to an opinion.

        Belief/disbelief that decay become uncertainty (not the opposite).
        Mass conservation: b + d + u = 1 always holds.
        """
        if now_unix <= last_decay_unix:
            return opinion

        # Zero decay rate → no change (L0 axioms)
        if self.mu < 1e-15:
            return opinion

        tau = self.compute_temporal_factor(now_unix, event_timestamps_unix)

        elapsed_days = (now_unix - last_decay_unix) / 86400.0

        # Decay factor: exponential in elapsed time, modulated by tau
        decay = math.exp(-self.mu * elapsed_days * (1.0 - tau))

        new_b = opinion.b * decay
        new_d = opinion.d * decay

        # Lost mass returns to uncertainty
        lost_mass = (opinion.b - new_b) + (opinion.d - new_d)
        new_u = opinion.u + lost_mass

        # Renormalize for float precision
        total = new_b + new_d + new_u
        if total > 1e-15 and abs(total - 1.0) > 1e-9:
            new_b /= total
            new_d /= total
            new_u /= total

        return OpinionTuple(b=new_b, d=new_d, u=new_u, a=opinion.a)


# Layer-specific decay profiles
LAYER_DECAY_PROFILES: dict[str, HawkesDecayEngine] = {
    "L0": HawkesDecayEngine(mu=0.0, alpha=0.0, beta=0.0),  # axioms: permanent
    "L1": HawkesDecayEngine(mu=0.0002, alpha=0.01, beta=0.003),  # principles: very slow
    "L2": HawkesDecayEngine(mu=0.0005, alpha=0.03, beta=0.005),  # patterns: slow
    "L3": HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01),  # rules: moderate
    "L4": HawkesDecayEngine(mu=0.003, alpha=0.05, beta=0.02),  # evidence: faster
    "L5": HawkesDecayEngine(mu=0.01, alpha=0.1, beta=0.05),  # context: fast
}


def get_decay_engine(layer: str) -> HawkesDecayEngine:
    """Get layer-appropriate decay engine."""
    return LAYER_DECAY_PROFILES.get(layer, LAYER_DECAY_PROFILES["L3"])
