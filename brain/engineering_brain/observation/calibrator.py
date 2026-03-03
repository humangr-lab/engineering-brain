"""Confidence calibrator for the Engineering Knowledge Brain.

Tracks predicted confidence vs actual accuracy using observation history.
Computes calibration curves and adjusts raw confidence scores to match
observed accuracy. A rule with confidence=0.8 should be correct ~80% of the time.

Uses simple bucketed calibration (no neural networks, no external deps).
Falls back to raw confidence when insufficient data (<30 observations).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from engineering_brain.observation.log import (
    EVENT_PREDICTION_TESTED,
    EVENT_REINFORCED,
    EVENT_WEAKENED,
    ObservationLog,
)

logger = logging.getLogger(__name__)

# Minimum observations needed for reliable calibration
MIN_OBSERVATIONS_FOR_CALIBRATION = 30

# Default confidence buckets
DEFAULT_BUCKETS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]


@dataclass
class CalibrationBucket:
    """A single bucket in the calibration curve."""

    lower: float
    upper: float
    total_observed: int
    positive_outcomes: int

    @property
    def accuracy(self) -> float:
        """Observed accuracy within this bucket."""
        if self.total_observed == 0:
            return (self.lower + self.upper) / 2  # Prior: midpoint
        return self.positive_outcomes / self.total_observed

    @property
    def midpoint(self) -> float:
        return (self.lower + self.upper) / 2


class ConfidenceCalibrator:
    """Calibrates confidence scores using observation history.

    Computes accuracy per confidence bucket from reinforcement/weakening
    and prediction test observations. Then adjusts raw confidence scores
    using the calibration curve.
    """

    def __init__(
        self,
        observation_log: ObservationLog,
        buckets: list[tuple[float, float]] | None = None,
    ) -> None:
        self._log = observation_log
        self._bucket_ranges = buckets or DEFAULT_BUCKETS
        self._calibration: list[CalibrationBucket] | None = None

    def compute_calibration(self) -> list[CalibrationBucket]:
        """Compute accuracy per confidence bucket from observation history."""
        observations = self._log.read_all()

        # Initialize buckets
        bucket_data: dict[int, dict[str, int]] = {
            i: {"total": 0, "positive": 0}
            for i in range(len(self._bucket_ranges))
        }

        for obs in observations:
            # Use prediction tests and reinforcements as outcome signals
            if obs.event_type not in (EVENT_PREDICTION_TESTED, EVENT_REINFORCED, EVENT_WEAKENED):
                continue

            confidence = obs.metadata.get("confidence_at_time")
            if confidence is None:
                continue

            confidence = float(confidence)
            is_positive = obs.outcome == "positive"

            # Find the right bucket
            for i, (lower, upper) in enumerate(self._bucket_ranges):
                if lower <= confidence < upper:
                    bucket_data[i]["total"] += 1
                    if is_positive:
                        bucket_data[i]["positive"] += 1
                    break

        self._calibration = [
            CalibrationBucket(
                lower=self._bucket_ranges[i][0],
                upper=self._bucket_ranges[i][1],
                total_observed=bucket_data[i]["total"],
                positive_outcomes=bucket_data[i]["positive"],
            )
            for i in range(len(self._bucket_ranges))
        ]

        return self._calibration

    def calibrated_confidence(self, raw_confidence: float) -> float:
        """Adjust a raw confidence score using the calibration curve.

        Falls back to raw_confidence if insufficient data.
        """
        if self._calibration is None:
            self.compute_calibration()

        assert self._calibration is not None

        # Check if we have enough data
        total_obs = sum(b.total_observed for b in self._calibration)
        if total_obs < MIN_OBSERVATIONS_FOR_CALIBRATION:
            return raw_confidence

        # Find the bucket for this confidence
        for bucket in self._calibration:
            if bucket.lower <= raw_confidence < bucket.upper:
                if bucket.total_observed >= 5:  # Need at least 5 per bucket
                    return bucket.accuracy
                return raw_confidence

        # Edge case: confidence exactly 1.0
        if self._calibration and raw_confidence >= self._calibration[-1].lower:
            last = self._calibration[-1]
            if last.total_observed >= 5:
                return last.accuracy

        return raw_confidence

    def calibration_report(self) -> str:
        """Human-readable calibration summary."""
        if self._calibration is None:
            self.compute_calibration()

        assert self._calibration is not None

        total_obs = sum(b.total_observed for b in self._calibration)
        lines = [f"Calibration Report ({total_obs} total observations)"]
        lines.append("-" * 50)

        if total_obs < MIN_OBSERVATIONS_FOR_CALIBRATION:
            lines.append(
                f"Insufficient data ({total_obs} < {MIN_OBSERVATIONS_FOR_CALIBRATION}). "
                "Using raw confidence scores."
            )
            return "\n".join(lines)

        for bucket in self._calibration:
            status = f"({bucket.total_observed} obs)"
            if bucket.total_observed >= 5:
                delta = bucket.accuracy - bucket.midpoint
                direction = "+" if delta >= 0 else ""
                lines.append(
                    f"  [{bucket.lower:.1f}-{bucket.upper:.1f}): "
                    f"predicted={bucket.midpoint:.2f} actual={bucket.accuracy:.2f} "
                    f"({direction}{delta:.2f}) {status}"
                )
            else:
                lines.append(
                    f"  [{bucket.lower:.1f}-{bucket.upper:.1f}): "
                    f"insufficient data {status}"
                )

        return "\n".join(lines)

    @property
    def has_sufficient_data(self) -> bool:
        """Whether the calibrator has enough observations for reliable calibration."""
        if self._calibration is None:
            self.compute_calibration()
        assert self._calibration is not None
        total = sum(b.total_observed for b in self._calibration)
        return total >= MIN_OBSERVATIONS_FOR_CALIBRATION
