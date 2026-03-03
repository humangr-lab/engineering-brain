"""Evidence reinforcer for the Engineering Knowledge Brain.

Tracks how evidence strengthens or weakens existing rules.
When a finding confirms a rule, the rule's confidence and reinforcement
count increase. When a finding contradicts a rule, confidence decreases.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from engineering_brain.adapters.base import GraphAdapter
from engineering_brain.core.schema import EdgeType, NodeType

logger = logging.getLogger(__name__)


class EvidenceReinforcer:
    """Manages evidence-based rule confidence adjustments."""

    def __init__(self, graph: GraphAdapter, observation_log: Any = None) -> None:
        self._graph = graph
        self._observation_log = observation_log

    def reinforce(self, rule_id: str, evidence_id: str, positive: bool = True) -> bool:
        """Reinforce (or weaken) a rule based on new evidence.

        positive=True: Evidence confirms the rule → increase confidence
        positive=False: Evidence contradicts the rule → decrease confidence

        When epistemic opinions are present, uses Subjective Logic CBF fusion
        with proper polarity (negative evidence produces disbelief, not just
        reduced belief). Also records provenance and event timestamps for
        Hawkes temporal decay.
        """
        rule = self._graph.get_node(rule_id)
        if rule is None:
            logger.warning("Rule %s not found for reinforcement", rule_id)
            return False

        count = int(rule.get("reinforcement_count", 0))
        confidence = float(rule.get("confidence", 0.5))
        now = datetime.now(timezone.utc)
        now_unix = int(now.timestamp())

        # Check if epistemic opinion exists
        ep_b = rule.get("ep_b")
        use_epistemic = ep_b is not None

        if use_epistemic:
            from engineering_brain.epistemic.opinion import OpinionTuple
            from engineering_brain.epistemic.fusion import cbf

            current = OpinionTuple(
                b=float(rule["ep_b"]),
                d=float(rule.get("ep_d", 0.0)),
                u=float(rule.get("ep_u", 0.5)),
                a=float(rule.get("ep_a", 0.5)),
            )
            if positive:
                evidence = OpinionTuple(b=0.6, d=0.0, u=0.4, a=0.5)
                new_count = count + 1
                edge_type = EdgeType.REINFORCES.value
            else:
                # Negative evidence: disbelief axis active
                evidence = OpinionTuple(b=0.0, d=0.5, u=0.5, a=0.5)
                new_count = count
                edge_type = EdgeType.WEAKENS.value

            fused = cbf(current, evidence)
            new_confidence = fused.projected_probability
            ep_update = {
                "ep_b": fused.b,
                "ep_d": fused.d,
                "ep_u": fused.u,
                "ep_a": fused.a,
            }
        else:
            ep_update = {}
            if positive:
                new_confidence = min(confidence + (1.0 - confidence) * 0.1, 0.99)
                new_count = count + 1
                edge_type = EdgeType.REINFORCES.value
            else:
                new_confidence = max(confidence * 0.9, 0.01)
                new_count = count
                edge_type = EdgeType.WEAKENS.value

        # Update event timestamps for Hawkes temporal decay
        event_timestamps = list(rule.get("event_timestamps", []))
        event_timestamps.append(now_unix)

        # Build provenance record
        provenance_update = {}
        if use_epistemic:
            from engineering_brain.epistemic.provenance import ProvenanceChain, ProvenanceRecord

            prov_record = ProvenanceRecord(
                operation="cbf_reinforce" if positive else "cbf_weaken",
                timestamp=now.isoformat(),
                inputs=(
                    {"source": "current_opinion", "b": current.b, "d": current.d, "u": current.u},
                    {"source": "evidence", "id": evidence_id, "positive": positive},
                ),
                output={"b": fused.b, "d": fused.d, "u": fused.u, "a": fused.a},
                reason=f"{'reinforced' if positive else 'weakened'} by {evidence_id}",
            )
            existing_prov = rule.get("provenance", [])
            if not isinstance(existing_prov, list):
                existing_prov = []
            chain = ProvenanceChain.from_list(existing_prov)
            chain.add(prov_record)
            provenance_update = {"provenance": chain.to_list()}

        # Increment observation count (tracks total observations, not just positive)
        observation_count = int(rule.get("observation_count", 0)) + 1

        self._graph.add_node(
            NodeType.RULE.value,
            rule_id,
            {
                **rule,
                "reinforcement_count": new_count,
                "confidence": new_confidence,
                "observation_count": observation_count,
                "last_violation": now.isoformat(),
                "event_timestamps": event_timestamps,
                **ep_update,
                **provenance_update,
            },
        )

        self._graph.add_edge(evidence_id, rule_id, edge_type)

        # Record observation (non-blocking)
        if self._observation_log is not None:
            try:
                self._observation_log.record_reinforcement(
                    rule_id=rule_id,
                    positive=positive,
                    evidence_id=evidence_id,
                )
            except Exception:
                pass

        logger.debug(
            "Rule %s %s (count=%d, confidence=%.2f)",
            rule_id,
            "reinforced" if positive else "weakened",
            new_count,
            new_confidence,
        )
        return True

    def get_weak_rules(
        self,
        min_age_days: int = 30,
        max_confidence: float = 0.3,
        max_observations: int = 3,
    ) -> list[dict[str, Any]]:
        """Find rules with low confidence that may need review or removal.

        A rule is weak if: low confidence AND (few observations OR old enough).
        Rules with < max_observations observations that are > min_age_days old
        are candidates for active learning or pruning.
        """
        rules = self._graph.query(label=NodeType.RULE.value, limit=500)
        weak: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for rule in rules:
            confidence = float(rule.get("confidence", 0.5))
            observations = int(rule.get("observation_count", 0))

            # Low confidence rules are weak
            if confidence > max_confidence:
                continue

            # Check age criterion
            created = rule.get("created_at", "")
            is_old = True  # default: treat missing timestamps as old
            try:
                if isinstance(created, str) and created:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    is_old = (now - created_dt).days >= min_age_days
            except (ValueError, TypeError):
                pass

            # Weak if: old enough OR too few observations
            if is_old or observations < max_observations:
                weak.append(rule)

        return weak

    def get_strong_rules(self, min_confidence: float = 0.8, min_reinforcements: int = 10) -> list[dict[str, Any]]:
        """Find highly-reinforced, high-confidence rules (promotion candidates)."""
        rules = self._graph.query(label=NodeType.RULE.value, limit=500)
        return [
            r for r in rules
            if float(r.get("confidence", 0)) >= min_confidence
            and int(r.get("reinforcement_count", 0)) >= min_reinforcements
        ]
