"""Tests for the observation log module."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest

from engineering_brain.observation.log import (
    EVENT_FINDING_RECORDED,
    EVENT_PREDICTION_TESTED,
    EVENT_QUERY_SERVED,
    EVENT_REINFORCED,
    EVENT_WEAKENED,
    Observation,
    ObservationLog,
)


@pytest.fixture
def tmp_log(tmp_path):
    """Create an ObservationLog with a temp file."""
    return ObservationLog(str(tmp_path / "test_obs.jsonl"))


class TestObservation:
    def test_to_dict_roundtrip(self):
        obs = Observation(
            timestamp="2026-02-18T12:00:00+00:00",
            event_type=EVENT_QUERY_SERVED,
            rule_ids=("CR-001", "CR-002"),
            query="Flask CORS",
            technologies=("flask", "cors"),
            file_type=".py",
            outcome="unknown",
            metadata={"phase": "exec"},
        )
        d = obs.to_dict()
        assert isinstance(d["rule_ids"], list)
        assert isinstance(d["technologies"], list)
        restored = Observation.from_dict(d)
        assert restored.timestamp == obs.timestamp
        assert restored.event_type == obs.event_type
        assert restored.rule_ids == obs.rule_ids
        assert restored.query == obs.query
        assert restored.technologies == obs.technologies
        assert restored.outcome == obs.outcome

    def test_from_dict_missing_fields(self):
        obs = Observation.from_dict({"timestamp": "t", "event_type": "query_served"})
        assert obs.rule_ids == ()
        assert obs.query == ""
        assert obs.outcome == "unknown"

    def test_frozen(self):
        obs = Observation(timestamp="t", event_type="query_served")
        with pytest.raises(AttributeError):
            obs.timestamp = "new"  # type: ignore


class TestObservationLog:
    def test_record_and_read(self, tmp_log: ObservationLog):
        obs = Observation(
            timestamp="2026-02-18T12:00:00+00:00",
            event_type=EVENT_QUERY_SERVED,
            rule_ids=("CR-001",),
            query="test",
        )
        tmp_log.record(obs)
        all_obs = tmp_log.read_all()
        assert len(all_obs) == 1
        assert all_obs[0].event_type == EVENT_QUERY_SERVED
        assert all_obs[0].rule_ids == ("CR-001",)

    def test_append_only(self, tmp_log: ObservationLog):
        for i in range(3):
            tmp_log.record(Observation(
                timestamp=f"2026-02-18T12:0{i}:00+00:00",
                event_type=EVENT_QUERY_SERVED,
                rule_ids=(f"CR-{i:03d}",),
            ))
        assert len(tmp_log.read_all()) == 3
        assert tmp_log.count() == 3

    def test_record_query_convenience(self, tmp_log: ObservationLog):
        tmp_log.record_query(
            rule_ids=["CR-001", "CR-002"],
            query="Flask CORS security",
            technologies=["flask"],
            file_type=".py",
        )
        obs = tmp_log.read_all()
        assert len(obs) == 1
        assert obs[0].event_type == EVENT_QUERY_SERVED
        assert obs[0].rule_ids == ("CR-001", "CR-002")
        assert obs[0].technologies == ("flask",)

    def test_record_finding_convenience(self, tmp_log: ObservationLog):
        tmp_log.record_finding(
            rule_ids=["F-abc123"],
            description="CORS wildcard found",
            severity="high",
        )
        obs = tmp_log.read_all()
        assert len(obs) == 1
        assert obs[0].event_type == EVENT_FINDING_RECORDED
        assert obs[0].metadata["severity"] == "high"

    def test_record_reinforcement_positive(self, tmp_log: ObservationLog):
        tmp_log.record_reinforcement("CR-001", positive=True, evidence_id="F-001")
        obs = tmp_log.read_all()
        assert len(obs) == 1
        assert obs[0].event_type == EVENT_REINFORCED
        assert obs[0].outcome == "positive"

    def test_record_reinforcement_negative(self, tmp_log: ObservationLog):
        tmp_log.record_reinforcement("CR-001", positive=False, evidence_id="F-002")
        obs = tmp_log.read_all()
        assert len(obs) == 1
        assert obs[0].event_type == EVENT_WEAKENED
        assert obs[0].outcome == "negative"

    def test_record_prediction_test(self, tmp_log: ObservationLog):
        tmp_log.record_prediction_test("CR-001", success=True, confidence_at_time=0.8)
        obs = tmp_log.read_all()
        assert len(obs) == 1
        assert obs[0].event_type == EVENT_PREDICTION_TESTED
        assert obs[0].outcome == "positive"
        assert obs[0].metadata["confidence_at_time"] == 0.8

    def test_rule_outcomes(self, tmp_log: ObservationLog):
        tmp_log.record_reinforcement("CR-001", positive=True)
        tmp_log.record_reinforcement("CR-001", positive=True)
        tmp_log.record_reinforcement("CR-001", positive=False)
        tmp_log.record_reinforcement("CR-002", positive=True)

        outcomes = tmp_log.rule_outcomes("CR-001")
        assert outcomes["positive"] == 2
        assert outcomes["negative"] == 1
        assert outcomes["unknown"] == 0

    def test_stats(self, tmp_log: ObservationLog):
        tmp_log.record_query(rule_ids=["CR-001"], query="test")
        tmp_log.record_query(rule_ids=["CR-002"], query="test2")
        tmp_log.record_finding(description="bug")
        tmp_log.record_reinforcement("CR-001", positive=True)

        s = tmp_log.stats()
        assert s[EVENT_QUERY_SERVED] == 2
        assert s[EVENT_FINDING_RECORDED] == 1
        assert s[EVENT_REINFORCED] == 1
        assert s["total"] == 4

    def test_read_empty_file(self, tmp_log: ObservationLog):
        assert tmp_log.read_all() == []
        assert tmp_log.count() == 0

    def test_read_since(self, tmp_log: ObservationLog):
        tmp_log.record(Observation(
            timestamp="2026-02-17T12:00:00+00:00",
            event_type=EVENT_QUERY_SERVED,
            rule_ids=("CR-old",),
        ))
        tmp_log.record(Observation(
            timestamp="2026-02-19T12:00:00+00:00",
            event_type=EVENT_QUERY_SERVED,
            rule_ids=("CR-new",),
        ))

        since = datetime(2026, 2, 18, tzinfo=timezone.utc)
        recent = tmp_log.read_since(since)
        assert len(recent) == 1
        assert recent[0].rule_ids == ("CR-new",)

    def test_malformed_line_skipped(self, tmp_log: ObservationLog):
        tmp_log._path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_log._path, "w") as f:
            f.write("not json\n")
            f.write(json.dumps({"timestamp": "t", "event_type": "query_served"}) + "\n")
        obs = tmp_log.read_all()
        assert len(obs) == 1

    def test_creates_parent_directories(self, tmp_path):
        log = ObservationLog(str(tmp_path / "deep" / "nested" / "obs.jsonl"))
        log.record(Observation(timestamp="t", event_type="query_served"))
        assert log.count() == 1

    def test_record_deprecated(self, tmp_log: ObservationLog):
        tmp_log.record_deprecated("CR-OLD-001", reason="stale")
        obs = tmp_log.read_all()
        assert len(obs) == 1
        assert obs[0].event_type == "deprecated"
        assert obs[0].rule_ids == ("CR-OLD-001",)
        assert obs[0].metadata["reason"] == "stale"

    def test_get_prediction_stats_empty(self, tmp_log: ObservationLog):
        stats = tmp_log.get_prediction_stats("CR-001")
        assert stats == {"tested": 0, "correct": 0}

    def test_get_prediction_stats_counts(self, tmp_log: ObservationLog):
        tmp_log.record_prediction_test("CR-001", success=True)
        tmp_log.record_prediction_test("CR-001", success=True)
        tmp_log.record_prediction_test("CR-001", success=False)
        tmp_log.record_prediction_test("CR-002", success=True)  # Different rule
        stats = tmp_log.get_prediction_stats("CR-001")
        assert stats == {"tested": 3, "correct": 2}

    def test_get_all_prediction_stats(self, tmp_log: ObservationLog):
        tmp_log.record_prediction_test("CR-001", success=True)
        tmp_log.record_prediction_test("CR-001", success=False)
        tmp_log.record_prediction_test("CR-002", success=True)
        tmp_log.record_query(rule_ids=["CR-001"])  # Non-prediction event
        stats = tmp_log.get_all_prediction_stats()
        assert len(stats) == 2
        assert stats["CR-001"] == {"tested": 2, "correct": 1}
        assert stats["CR-002"] == {"tested": 1, "correct": 1}
