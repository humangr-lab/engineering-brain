"""Append-only observation log for the Engineering Knowledge Brain.

Records brain interactions as JSONL lines. Each observation captures:
- What event occurred (query served, finding recorded, reinforcement)
- Which rules were involved
- The context (technologies, file_type, query text)
- The outcome (positive/negative/unknown)

This log is the sensory input for confidence calibration and self-assessment.
Never deletes or modifies previous entries — append-only by construction.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Event types
EVENT_QUERY_SERVED = "query_served"
EVENT_FINDING_RECORDED = "finding_recorded"
EVENT_REINFORCED = "reinforced"
EVENT_WEAKENED = "weakened"
EVENT_PREDICTION_TESTED = "prediction_tested"

EVENT_DEPRECATED = "deprecated"

_VALID_EVENTS = {
    EVENT_QUERY_SERVED,
    EVENT_FINDING_RECORDED,
    EVENT_REINFORCED,
    EVENT_WEAKENED,
    EVENT_PREDICTION_TESTED,
    EVENT_DEPRECATED,
}

_VALID_OUTCOMES = {"positive", "negative", "unknown"}


@dataclass(frozen=True)
class Observation:
    """Single brain interaction observation."""

    timestamp: str
    event_type: str
    rule_ids: tuple[str, ...] = ()
    query: str = ""
    technologies: tuple[str, ...] = ()
    file_type: str = ""
    outcome: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["rule_ids"] = list(self.rule_ids)
        d["technologies"] = list(self.technologies)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Observation:
        return cls(
            timestamp=d.get("timestamp", ""),
            event_type=d.get("event_type", ""),
            rule_ids=tuple(d.get("rule_ids", ())),
            query=d.get("query", ""),
            technologies=tuple(d.get("technologies", ())),
            file_type=d.get("file_type", ""),
            outcome=d.get("outcome", "unknown"),
            metadata=d.get("metadata", {}),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ObservationLog:
    """Append-only JSONL observation log.

    Thread-safe for single-writer append (typical MCP server usage).
    """

    def __init__(self, path: str | None = None) -> None:
        if path is None:
            path = os.path.join(
                os.path.expanduser("~"), ".engineering_brain", "observations.jsonl"
            )
        self._path = Path(path)

    @property
    def path(self) -> str:
        return str(self._path)

    def record(self, obs: Observation) -> None:
        """Append a single observation to the log.

        Uses fcntl.flock (LOCK_EX) for atomic writes in multi-process environments.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(obs.to_dict(), separators=(",", ":"), default=str)
        with open(self._path, "a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(line + "\n")
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def record_query(
        self,
        rule_ids: list[str],
        query: str = "",
        technologies: list[str] | None = None,
        file_type: str = "",
    ) -> None:
        """Convenience: record a query_served event."""
        self.record(Observation(
            timestamp=_now_iso(),
            event_type=EVENT_QUERY_SERVED,
            rule_ids=tuple(rule_ids),
            query=query,
            technologies=tuple(technologies or []),
            file_type=file_type,
        ))

    def record_finding(
        self,
        rule_ids: list[str] | None = None,
        description: str = "",
        severity: str = "medium",
    ) -> None:
        """Convenience: record a finding_recorded event."""
        self.record(Observation(
            timestamp=_now_iso(),
            event_type=EVENT_FINDING_RECORDED,
            rule_ids=tuple(rule_ids or []),
            query=description,
            metadata={"severity": severity},
        ))

    def record_reinforcement(
        self,
        rule_id: str,
        positive: bool = True,
        evidence_id: str = "",
    ) -> None:
        """Convenience: record reinforcement/weakening."""
        self.record(Observation(
            timestamp=_now_iso(),
            event_type=EVENT_REINFORCED if positive else EVENT_WEAKENED,
            rule_ids=(rule_id,),
            outcome="positive" if positive else "negative",
            metadata={"evidence_id": evidence_id},
        ))

    def record_prediction_test(
        self,
        rule_id: str,
        success: bool,
        confidence_at_time: float = 0.0,
    ) -> None:
        """Convenience: record a prediction outcome."""
        self.record(Observation(
            timestamp=_now_iso(),
            event_type=EVENT_PREDICTION_TESTED,
            rule_ids=(rule_id,),
            outcome="positive" if success else "negative",
            metadata={"confidence_at_time": confidence_at_time},
        ))

    def record_feedback(
        self,
        rule_id: str,
        reason: str = "",
        context: str = "",
    ) -> None:
        """Record negative feedback (rule was unhelpful/wrong for context)."""
        self.record(Observation(
            timestamp=_now_iso(),
            event_type=EVENT_WEAKENED,
            rule_ids=(rule_id,),
            outcome="negative",
            metadata={"reason": reason, "context": context, "source": "agent_feedback"},
        ))

    def record_deprecated(
        self,
        node_id: str,
        reason: str = "",
    ) -> None:
        """Convenience: record a node deprecation (soft-delete) event."""
        self.record(Observation(
            timestamp=_now_iso(),
            event_type=EVENT_DEPRECATED,
            rule_ids=(node_id,),
            metadata={"reason": reason},
        ))

    def get_prediction_stats(self, rule_id: str) -> dict[str, int]:
        """Get prediction test/success counts for a specific rule.

        Returns dict with 'tested' and 'correct' counts.
        Used by confidence calibrator.
        """
        tested = 0
        correct = 0
        for obs in self.read_all():
            if obs.event_type == EVENT_PREDICTION_TESTED and rule_id in obs.rule_ids:
                tested += 1
                if obs.outcome == "positive":
                    correct += 1
        return {"tested": tested, "correct": correct}

    def get_all_prediction_stats(self) -> dict[str, dict[str, int]]:
        """Get prediction stats for ALL rules in a single pass.

        Returns {rule_id: {"tested": N, "correct": M}}.
        Used by batch confidence calibration.
        """
        stats: dict[str, dict[str, int]] = {}
        for obs in self.read_all():
            if obs.event_type != EVENT_PREDICTION_TESTED:
                continue
            for rid in obs.rule_ids:
                if rid not in stats:
                    stats[rid] = {"tested": 0, "correct": 0}
                stats[rid]["tested"] += 1
                if obs.outcome == "positive":
                    stats[rid]["correct"] += 1
        return stats

    def read_all(self) -> list[Observation]:
        """Read all observations from the log."""
        if not self._path.exists():
            return []
        observations: list[Observation] = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    observations.append(Observation.from_dict(d))
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Skipping malformed observation line: %s", e)
        return observations

    def read_since(self, since: datetime) -> list[Observation]:
        """Read observations since a given timestamp."""
        since_iso = since.isoformat()
        return [obs for obs in self.read_all() if obs.timestamp >= since_iso]

    def rule_outcomes(self, rule_id: str) -> dict[str, int]:
        """Count outcomes for a specific rule."""
        counts: dict[str, int] = {"positive": 0, "negative": 0, "unknown": 0}
        for obs in self.read_all():
            if rule_id in obs.rule_ids and obs.outcome in counts:
                counts[obs.outcome] += 1
        return counts

    def stats(self) -> dict[str, int]:
        """Get observation counts by event type."""
        counts: dict[str, int] = {}
        for obs in self.read_all():
            counts[obs.event_type] = counts.get(obs.event_type, 0) + 1
        counts["total"] = sum(counts.values())
        return counts

    def count(self) -> int:
        """Get total number of observations."""
        if not self._path.exists():
            return 0
        count = 0
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
