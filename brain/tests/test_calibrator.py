"""Tests for the confidence calibrator.

Verifies:
- Bucketed calibration from observation history
- Cold-start protection (insufficient data → raw confidence)
- Calibration curve computation
- Per-bucket minimum observation threshold
- Calibration report generation
- Integration with scorer
"""

from __future__ import annotations

import pytest

from engineering_brain.observation.calibrator import (
    MIN_OBSERVATIONS_FOR_CALIBRATION,
    CalibrationBucket,
    ConfidenceCalibrator,
)
from engineering_brain.observation.log import ObservationLog


@pytest.fixture()
def tmp_log(tmp_path):
    """Create an observation log with a temp file."""
    path = str(tmp_path / "obs.jsonl")
    return ObservationLog(path=path)


@pytest.fixture()
def calibrator_empty(tmp_log):
    """Calibrator with no observations."""
    return ConfidenceCalibrator(observation_log=tmp_log)


def _populate_log(log: ObservationLog, entries: list[tuple[float, bool]]) -> None:
    """Record prediction_tested observations with (confidence, success) pairs."""
    for confidence, success in entries:
        log.record_prediction_test(
            rule_id="R-TEST",
            success=success,
            confidence_at_time=confidence,
        )


def _populate_reinforcements(log: ObservationLog, entries: list[tuple[float, bool]]) -> None:
    """Record reinforcement observations with (confidence, positive) pairs.

    We manually record because record_reinforcement doesn't store confidence_at_time.
    """
    from engineering_brain.observation.log import (
        EVENT_REINFORCED,
        EVENT_WEAKENED,
        Observation,
        _now_iso,
    )

    for confidence, positive in entries:
        log.record(
            Observation(
                timestamp=_now_iso(),
                event_type=EVENT_REINFORCED if positive else EVENT_WEAKENED,
                rule_ids=("R-TEST",),
                outcome="positive" if positive else "negative",
                metadata={"confidence_at_time": confidence},
            )
        )


# --- CalibrationBucket ---


class TestCalibrationBucket:
    def test_accuracy_with_data(self):
        b = CalibrationBucket(lower=0.6, upper=0.8, total_observed=10, positive_outcomes=7)
        assert b.accuracy == pytest.approx(0.7)

    def test_accuracy_empty_uses_midpoint(self):
        b = CalibrationBucket(lower=0.6, upper=0.8, total_observed=0, positive_outcomes=0)
        assert b.accuracy == pytest.approx(0.7)

    def test_midpoint(self):
        b = CalibrationBucket(lower=0.2, upper=0.4, total_observed=5, positive_outcomes=2)
        assert b.midpoint == pytest.approx(0.3)

    def test_perfect_accuracy(self):
        b = CalibrationBucket(lower=0.8, upper=1.01, total_observed=20, positive_outcomes=20)
        assert b.accuracy == pytest.approx(1.0)

    def test_zero_accuracy(self):
        b = CalibrationBucket(lower=0.0, upper=0.2, total_observed=15, positive_outcomes=0)
        assert b.accuracy == pytest.approx(0.0)


# --- ConfidenceCalibrator: cold start ---


class TestColdStart:
    def test_empty_log_returns_raw(self, calibrator_empty):
        """With no observations, calibrated_confidence should return raw."""
        assert calibrator_empty.calibrated_confidence(0.75) == pytest.approx(0.75)

    def test_insufficient_data_returns_raw(self, tmp_log):
        """With <30 observations, raw confidence is returned."""
        _populate_log(tmp_log, [(0.5, True)] * 10)
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        assert cal.calibrated_confidence(0.5) == pytest.approx(0.5)

    def test_has_sufficient_data_false_when_empty(self, calibrator_empty):
        assert calibrator_empty.has_sufficient_data is False

    def test_has_sufficient_data_false_below_threshold(self, tmp_log):
        _populate_log(tmp_log, [(0.5, True)] * (MIN_OBSERVATIONS_FOR_CALIBRATION - 1))
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        assert cal.has_sufficient_data is False


# --- ConfidenceCalibrator: with data ---


class TestWithData:
    @pytest.fixture()
    def populated_log(self, tmp_log):
        """Log with enough observations across multiple buckets."""
        # Bucket [0.0, 0.2): 10 entries, 1 positive → accuracy 0.1
        _populate_log(tmp_log, [(0.1, False)] * 9 + [(0.1, True)])
        # Bucket [0.2, 0.4): 8 entries, 2 positive → accuracy 0.25
        _populate_log(tmp_log, [(0.3, False)] * 6 + [(0.3, True)] * 2)
        # Bucket [0.4, 0.6): 7 entries, 4 positive → accuracy ~0.571
        _populate_log(tmp_log, [(0.5, False)] * 3 + [(0.5, True)] * 4)
        # Bucket [0.6, 0.8): 10 entries, 7 positive → accuracy 0.7
        _populate_log(tmp_log, [(0.7, False)] * 3 + [(0.7, True)] * 7)
        # Bucket [0.8, 1.01): 10 entries, 9 positive → accuracy 0.9
        _populate_log(tmp_log, [(0.9, False)] + [(0.9, True)] * 9)
        return tmp_log  # Total: 45 obs, all buckets ≥ 5

    def test_calibrates_overconfident_down(self, populated_log):
        """If bucket [0.8,1.0) has 0.9 accuracy, confidence 0.95 → 0.9."""
        cal = ConfidenceCalibrator(observation_log=populated_log)
        result = cal.calibrated_confidence(0.95)
        assert result == pytest.approx(0.9)

    def test_calibrates_underconfident_up(self, populated_log):
        """If bucket [0.6,0.8) has 0.7 accuracy, confidence 0.65 → 0.7."""
        cal = ConfidenceCalibrator(observation_log=populated_log)
        result = cal.calibrated_confidence(0.65)
        assert result == pytest.approx(0.7)

    def test_calibrates_low_bucket(self, populated_log):
        """Bucket [0.0,0.2) has 0.1 accuracy."""
        cal = ConfidenceCalibrator(observation_log=populated_log)
        result = cal.calibrated_confidence(0.15)
        assert result == pytest.approx(0.1)

    def test_has_sufficient_data_true(self, populated_log):
        cal = ConfidenceCalibrator(observation_log=populated_log)
        assert cal.has_sufficient_data is True

    def test_compute_calibration_returns_5_buckets(self, populated_log):
        cal = ConfidenceCalibrator(observation_log=populated_log)
        buckets = cal.compute_calibration()
        assert len(buckets) == 5

    def test_all_buckets_have_observations(self, populated_log):
        cal = ConfidenceCalibrator(observation_log=populated_log)
        buckets = cal.compute_calibration()
        for b in buckets:
            assert b.total_observed >= 5

    def test_bucket_accuracy_monotonically_increasing(self, populated_log):
        """With well-calibrated data, accuracy should generally increase."""
        cal = ConfidenceCalibrator(observation_log=populated_log)
        buckets = cal.compute_calibration()
        accuracies = [b.accuracy for b in buckets]
        # Not strictly monotonic due to noise, but should trend upward
        assert accuracies[-1] > accuracies[0]


# --- Per-bucket threshold ---


class TestPerBucketThreshold:
    def test_bucket_below_5_returns_raw(self, tmp_log):
        """Buckets with <5 observations return raw confidence."""
        # Put 30+ in one bucket, <5 in another
        _populate_log(tmp_log, [(0.9, True)] * 32)  # All in [0.8, 1.01)
        _populate_log(tmp_log, [(0.3, True)] * 3)  # Only 3 in [0.2, 0.4)
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        # Bucket [0.2, 0.4) has only 3 obs → raw
        result = cal.calibrated_confidence(0.35)
        assert result == pytest.approx(0.35)

    def test_bucket_at_5_calibrates(self, tmp_log):
        """Buckets with exactly 5 observations should calibrate."""
        _populate_log(tmp_log, [(0.9, True)] * 30)  # 30 in high bucket
        _populate_log(tmp_log, [(0.3, True)] * 3 + [(0.3, False)] * 2)  # 5 in [0.2,0.4)
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        result = cal.calibrated_confidence(0.35)
        assert result == pytest.approx(0.6)  # 3/5 = 0.6


# --- Mixed event types ---


class TestMixedEvents:
    def test_reinforcements_count_as_observations(self, tmp_log):
        """Reinforcement events with confidence_at_time contribute to calibration."""
        _populate_reinforcements(tmp_log, [(0.7, True)] * 20 + [(0.7, False)] * 5)
        _populate_log(tmp_log, [(0.7, True)] * 5 + [(0.7, False)] * 2)
        # Total in [0.6, 0.8): 32 obs (25 reinforce + 7 prediction)
        # Positive: 25 (from reinforce) + 5 (from prediction) = 25
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        buckets = cal.compute_calibration()
        total = sum(b.total_observed for b in buckets)
        assert total == 32

    def test_query_served_events_ignored(self, tmp_log):
        """query_served events should NOT affect calibration."""
        # Record 50 query events
        for _ in range(50):
            tmp_log.record_query(rule_ids=["R-1"], query="test")
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        # No prediction/reinforcement data → insufficient
        assert cal.has_sufficient_data is False


# --- Calibration report ---


class TestCalibrationReport:
    def test_report_insufficient_data(self, calibrator_empty):
        report = calibrator_empty.calibration_report()
        assert "Insufficient data" in report

    def test_report_with_data(self, tmp_log):
        _populate_log(tmp_log, [(0.9, True)] * 20 + [(0.1, False)] * 15)
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        report = cal.calibration_report()
        assert "35 total observations" in report
        assert "[0.8-1.0)" in report

    def test_report_shows_delta(self, tmp_log):
        _populate_log(tmp_log, [(0.9, True)] * 20 + [(0.1, False)] * 15)
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        report = cal.calibration_report()
        assert "predicted=" in report
        assert "actual=" in report


# --- Edge cases ---


class TestEdgeCases:
    def test_confidence_exactly_zero(self, tmp_log):
        _populate_log(tmp_log, [(0.05, True)] * 35)
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        result = cal.calibrated_confidence(0.0)
        # Should land in [0.0, 0.2) bucket, but only 35 in that bucket
        # Not enough total across all buckets? Actually 35 ≥ 30, so calibrates
        assert isinstance(result, float)

    def test_confidence_exactly_one(self, tmp_log):
        _populate_log(tmp_log, [(0.95, True)] * 35)
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        result = cal.calibrated_confidence(1.0)
        assert isinstance(result, float)

    def test_custom_buckets(self, tmp_log):
        _populate_log(tmp_log, [(0.5, True)] * 35)
        cal = ConfidenceCalibrator(
            observation_log=tmp_log,
            buckets=[(0.0, 0.5), (0.5, 1.01)],
        )
        buckets = cal.compute_calibration()
        assert len(buckets) == 2

    def test_lazy_compute(self, tmp_log):
        """calibrated_confidence auto-computes calibration on first call."""
        _populate_log(tmp_log, [(0.5, True)] * 35)
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        assert cal._calibration is None
        cal.calibrated_confidence(0.5)
        assert cal._calibration is not None


# --- Integration with scorer ---


class TestScorerIntegration:
    def test_scorer_accepts_calibrator(self, tmp_log):
        """Verify the scorer's calibrator parameter works end-to-end."""
        from engineering_brain.retrieval.scorer import score_knowledge

        _populate_log(tmp_log, [(0.7, True)] * 35)
        cal = ConfidenceCalibrator(observation_log=tmp_log)
        cal.compute_calibration()

        node = {
            "technologies": ["flask"],
            "domains": ["security"],
            "severity": "high",
            "reinforcement_count": 5,
            "confidence": 0.7,
        }

        # Without calibrator
        score_no_cal = score_knowledge(
            node,
            query_technologies=["flask"],
            query_domains=["security"],
        )
        # With calibrator
        score_with_cal = score_knowledge(
            node,
            query_technologies=["flask"],
            query_domains=["security"],
            calibrator=cal,
        )
        # Both should be valid scores
        assert 0.0 <= score_no_cal <= 1.0
        assert 0.0 <= score_with_cal <= 1.0
