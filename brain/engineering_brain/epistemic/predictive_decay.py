"""Predictive Decay Engine — forecast when knowledge will become stale.

Extends the existing Hawkes decay (reactive) with predictive capabilities:
- Per-knowledge-type half-life profiles (framework versions decay fast, axioms never)
- Staleness prediction: "this node will become stale in ~45 days"
- At-risk detection: find nodes likely to expire within a horizon
- Freshness scoring: continuous 0-1 freshness based on age + type

Feature flag: BRAIN_PREDICTIVE_DECAY (default OFF)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# Per-knowledge-type half-life profiles
DECAY_PROFILES: dict[str, dict[str, float]] = {
    "framework_version": {"half_life_days": 180, "volatility": 0.3},
    "security_vuln": {"half_life_days": 90, "volatility": 0.5},
    "api_endpoint": {"half_life_days": 120, "volatility": 0.4},
    "design_pattern": {"half_life_days": 730, "volatility": 0.1},
    "language_feature": {"half_life_days": 365, "volatility": 0.2},
    "best_practice": {"half_life_days": 548, "volatility": 0.15},
    "axiom": {"half_life_days": float("inf"), "volatility": 0.0},
    "principle": {"half_life_days": 1825, "volatility": 0.05},
    "code_pattern": {"half_life_days": 365, "volatility": 0.2},
    "test_result": {"half_life_days": 90, "volatility": 0.4},
    "task_context": {"half_life_days": 1, "volatility": 1.0},
}

# Map layer prefix to knowledge type
_PREFIX_TO_TYPE: dict[str, str] = {
    "AX-": "axiom",
    "P-": "principle",
    "PAT-": "design_pattern",
    "CPAT-": "code_pattern",
    "CR-": "best_practice",
    "F-": "test_result",
    "CE-": "code_pattern",
    "TR-": "test_result",
    "TC-": "task_context",
}

# Default freshness threshold below which a node is "stale"
STALE_THRESHOLD = 0.3


@dataclass
class DecayPrediction:
    """Prediction of when a node will become stale."""

    node_id: str
    knowledge_type: str
    current_freshness: float
    estimated_stale_date: datetime | None
    days_until_stale: float
    half_life_days: float
    volatility: float
    confidence: float  # How confident we are in this prediction

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "knowledge_type": self.knowledge_type,
            "current_freshness": round(self.current_freshness, 4),
            "estimated_stale_date": self.estimated_stale_date.isoformat()
            if self.estimated_stale_date
            else None,
            "days_until_stale": round(self.days_until_stale, 1),
            "half_life_days": self.half_life_days,
            "volatility": self.volatility,
            "confidence": round(self.confidence, 4),
        }


class PredictiveDecayEngine:
    """Predicts when knowledge nodes will become stale."""

    def __init__(self, stale_threshold: float = STALE_THRESHOLD) -> None:
        self.stale_threshold = stale_threshold

    def classify_knowledge_type(self, node: dict[str, Any]) -> str:
        """Infer knowledge type from node properties."""
        nid = str(node.get("id", ""))

        # Check severity + domain for security hints FIRST (overrides prefix)
        if node.get("severity") in ("critical", "high"):
            domains = node.get("domains", [])
            if isinstance(domains, list) and "security" in [d.lower() for d in domains]:
                return "security_vuln"

        # Check technologies for framework hints
        techs = node.get("technologies") or node.get("languages") or []
        if isinstance(techs, list) and techs:
            text = str(node.get("text", "")) + str(node.get("name", ""))
            if any(c.isdigit() for c in text) and any(
                t in text.lower() for t in ("version", "v2", "v3", "update")
            ):
                return "framework_version"

        # Check ID prefix
        for prefix, ktype in _PREFIX_TO_TYPE.items():
            if nid.startswith(prefix):
                return ktype

        return "best_practice"

    def get_profile(self, knowledge_type: str) -> dict[str, float]:
        """Get decay profile for a knowledge type."""
        return DECAY_PROFILES.get(knowledge_type, DECAY_PROFILES["best_practice"])

    def compute_freshness(self, node: dict[str, Any], now: datetime | None = None) -> float:
        """Compute current freshness of a node (0.0 = stale, 1.0 = fresh).

        Uses exponential decay based on the knowledge type's half-life.
        """
        if now is None:
            now = datetime.now(UTC)

        ktype = self.classify_knowledge_type(node)
        profile = self.get_profile(ktype)
        half_life = profile["half_life_days"]

        if half_life == float("inf"):
            return 1.0  # Never decays (axioms)

        # Get the most recent timestamp
        created_at = self._get_timestamp(node)
        if created_at is None:
            return 0.5  # Unknown age = moderate freshness

        age_days = max((now - created_at).total_seconds() / 86400.0, 0.0)

        # Exponential decay: freshness = exp(-age * ln(2) / half_life)
        decay_rate = math.log(2) / half_life
        freshness = math.exp(-decay_rate * age_days)

        # Reinforcement bonus: each reinforcement adds ~10% of a half-life worth of freshness
        reinforcement = int(node.get("reinforcement_count", 0))
        if reinforcement > 0:
            bonus = min(reinforcement * 0.05, 0.3)  # Cap at 30% bonus
            freshness = min(
                freshness + bonus * freshness, 1.0
            )  # multiplicative: bonus decays WITH freshness

        return max(0.0, min(freshness, 1.0))

    def predict_staleness(
        self, node: dict[str, Any], now: datetime | None = None
    ) -> DecayPrediction:
        """Predict when a node will become stale."""
        if now is None:
            now = datetime.now(UTC)

        nid = str(node.get("id", ""))
        ktype = self.classify_knowledge_type(node)
        profile = self.get_profile(ktype)
        half_life = profile["half_life_days"]
        volatility = profile["volatility"]

        freshness = self.compute_freshness(node, now)

        if half_life == float("inf"):
            return DecayPrediction(
                node_id=nid,
                knowledge_type=ktype,
                current_freshness=1.0,
                estimated_stale_date=None,
                days_until_stale=float("inf"),
                half_life_days=half_life,
                volatility=volatility,
                confidence=1.0,
            )

        # Compute days until freshness drops below threshold
        if freshness <= self.stale_threshold:
            days_until = 0.0
        else:
            # freshness * exp(-rate * days) = threshold
            # days = -ln(threshold/freshness) / rate
            decay_rate = math.log(2) / half_life
            if decay_rate > 0 and freshness > 0:
                days_until = -math.log(self.stale_threshold / freshness) / decay_rate
            else:
                days_until = float("inf")

        estimated_stale = None
        if days_until < float("inf"):
            from datetime import timedelta

            estimated_stale = now + timedelta(days=days_until)

        # Confidence in prediction: lower for high-volatility types
        # and when we have less data about the node
        confidence = 1.0 - volatility * 0.5
        if not self._get_timestamp(node):
            confidence *= 0.5  # Unknown creation date = less confident

        return DecayPrediction(
            node_id=nid,
            knowledge_type=ktype,
            current_freshness=freshness,
            estimated_stale_date=estimated_stale,
            days_until_stale=days_until,
            half_life_days=half_life,
            volatility=volatility,
            confidence=confidence,
        )

    def get_at_risk_nodes(
        self,
        nodes: list[dict[str, Any]],
        horizon_days: int = 30,
        now: datetime | None = None,
    ) -> list[DecayPrediction]:
        """Find nodes likely to become stale within the horizon.

        Returns predictions sorted by urgency (soonest stale first).
        """
        if now is None:
            now = datetime.now(UTC)

        at_risk: list[DecayPrediction] = []
        for node in nodes:
            pred = self.predict_staleness(node, now)
            if 0 < pred.days_until_stale <= horizon_days:
                at_risk.append(pred)

        at_risk.sort(key=lambda p: p.days_until_stale)
        return at_risk

    def refresh_node(self, node: dict[str, Any]) -> dict[str, Any]:
        """Reset the decay clock with new evidence (updates timestamps)."""
        now = datetime.now(UTC)
        node["updated_at"] = now.isoformat()
        # Increment reinforcement to reflect the refresh
        node["reinforcement_count"] = int(node.get("reinforcement_count", 0)) + 1
        return node

    @staticmethod
    def _get_timestamp(node: dict[str, Any]) -> datetime | None:
        """Extract the most relevant timestamp from a node."""
        for field in ("updated_at", "created_at", "timestamp", "last_violation"):
            val = node.get(field)
            if val is None:
                continue
            try:
                if isinstance(val, datetime):
                    if val.tzinfo is None:
                        return val.replace(tzinfo=UTC)
                    return val
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
        return None
