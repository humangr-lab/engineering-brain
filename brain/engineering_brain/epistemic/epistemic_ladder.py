"""Epistemic Ladder — classify and promote knowledge by maturity level.

The E0-E5 ladder assigns a discrete epistemic status to every knowledge
node based on its evidence quality, source count, and confidence:

    E0 Rumor:       Single unverified source
    E1 Hypothesis:  Some evidence, plausible
    E2 Observation: Empirically observed, multiple sources
    E3 Tested:      Validated through automated checks
    E4 Proven:      Formally verified, exhaustive evidence
    E5 Axiom:       Foundational truth, immutable

A mathematical axiom and a StackOverflow rumor can no longer have the
same confidence — the ladder makes this distinction explicit.

Feature flag: BRAIN_EPISTEMIC_LADDER (default OFF)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from engineering_brain.core.types import EpistemicStatus

logger = logging.getLogger(__name__)


class EpistemicLadder:
    """Classify, promote, and demote nodes on the E0-E5 ladder."""

    def classify(self, node: dict[str, Any]) -> EpistemicStatus:
        """Classify a node's epistemic status based on its properties.

        Classification rules:
        1. L0 Axioms are always E5 (immutable truths).
        2. Nodes with validation_status=human_verified: at least E3.
        3. Nodes with validation_status=cross_checked: at least E2.
        4. Otherwise, classify by ep_b (belief mass) and source count.
        """
        nid = str(node.get("id", ""))

        # L0 Axioms are always E5
        if nid.startswith("AX-") or node.get("immutable"):
            return EpistemicStatus.E5_AXIOM

        # Extract key signals
        ep_b = float(node.get("ep_b", 0.0) or 0.0)
        ep_u = float(node.get("ep_u", 1.0) or 1.0)
        sources = node.get("sources", [])
        source_count = len(sources) if isinstance(sources, list) else 0
        validation = str(node.get("validation_status", "unvalidated")).lower()
        reinforcement = int(node.get("reinforcement_count", 0))

        # Formal verification (E4): high belief, low uncertainty, 3+ sources, human verified
        if ep_b >= 0.8 and ep_u <= 0.2 and source_count >= 3 and validation == "human_verified":
            return EpistemicStatus.E4_PROVEN

        # Tested (E3): validated + moderate belief
        if ep_b >= 0.6 and ep_u <= 0.4 and validation in ("human_verified", "cross_checked"):
            return EpistemicStatus.E3_TESTED

        # Observation (E2): multiple sources or high reinforcement
        if (ep_b >= 0.4 and ep_u <= 0.6 and source_count >= 2) or reinforcement >= 10:
            return EpistemicStatus.E2_OBSERVATION

        # Hypothesis (E1): some evidence
        if ep_b >= 0.2 and ep_u <= 0.8 and (source_count >= 1 or reinforcement >= 3):
            return EpistemicStatus.E1_HYPOTHESIS

        # Default: rumor
        return EpistemicStatus.E0_RUMOR

    def can_promote(
        self, node: dict[str, Any], target: EpistemicStatus
    ) -> tuple[bool, str]:
        """Check if a node meets the requirements for promotion to target level.

        Returns:
            (can_promote, reason): True if requirements met, False with explanation.
        """
        current = self.classify(node)
        if target.level <= current.level:
            return False, f"Already at {current.value}, target {target.value} is not higher"

        # Check one-step promotion (no skipping)
        if target.level > current.level + 1:
            return False, f"Cannot skip from {current.value} to {target.value} (one step at a time)"

        # Check target requirements
        ep_b = float(node.get("ep_b", 0.0) or 0.0)
        ep_u = float(node.get("ep_u", 1.0) or 1.0)
        sources = node.get("sources", [])
        source_count = len(sources) if isinstance(sources, list) else 0
        validation = str(node.get("validation_status", "unvalidated")).lower()

        if ep_b < target.min_belief:
            return False, f"Belief {ep_b:.2f} < required {target.min_belief:.2f}"

        if ep_u > target.max_uncertainty:
            return False, f"Uncertainty {ep_u:.2f} > max allowed {target.max_uncertainty:.2f}"

        if source_count < target.min_sources:
            return False, f"Sources {source_count} < required {target.min_sources}"

        # H15: validation_status checks to match classify() requirements
        if target == EpistemicStatus.E4_PROVEN and validation != "human_verified":
            return False, f"E4 requires validation_status=human_verified, got {validation}"

        if target == EpistemicStatus.E3_TESTED and validation not in ("human_verified", "cross_checked"):
            return False, f"E3 requires validation_status in (human_verified, cross_checked), got {validation}"

        return True, "Requirements met"

    def promote(
        self, node: dict[str, Any], target: EpistemicStatus
    ) -> dict[str, Any]:
        """Promote a node to the target epistemic status.

        Updates the node dict in place and returns it.
        """
        can, reason = self.can_promote(node, target)
        if not can:
            raise ValueError(f"Cannot promote {node.get('id')}: {reason}")

        node["epistemic_status"] = target.value
        node["epistemic_promoted_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("Promoted %s to %s", node.get("id"), target.value)
        return node

    def demote(
        self, node: dict[str, Any], reason: str = "", to_e0: bool = False,
    ) -> dict[str, Any]:
        """Demote a node by one epistemic level on contradiction or invalidation.

        By default, demotion goes down exactly one level (E4 -> E3, E3 -> E2, etc.).
        Pass to_e0=True to force demotion to E0 (for severe contradictions).
        """
        _LEVEL_ORDER = [
            EpistemicStatus.E0_RUMOR, EpistemicStatus.E1_HYPOTHESIS,
            EpistemicStatus.E2_OBSERVATION, EpistemicStatus.E3_TESTED,
            EpistemicStatus.E4_PROVEN, EpistemicStatus.E5_AXIOM,
        ]
        old_status = node.get("epistemic_status", "E0")
        if to_e0:
            new_status = EpistemicStatus.E0_RUMOR
        else:
            current_level = int(old_status[1]) if len(old_status) == 2 and old_status[1].isdigit() else 0
            target_level = max(0, current_level - 1)
            new_status = _LEVEL_ORDER[target_level]
        node["epistemic_status"] = new_status.value
        node["epistemic_demoted_at"] = datetime.now(timezone.utc).isoformat()
        node["epistemic_demotion_reason"] = reason
        logger.info(
            "Demoted %s from %s to %s: %s",
            node.get("id"), old_status, new_status.value, reason,
        )
        return node

    def batch_classify(self, nodes: list[dict[str, Any]]) -> dict[str, EpistemicStatus]:
        """Classify all nodes and return a mapping of node_id -> status."""
        result: dict[str, EpistemicStatus] = {}
        for node in nodes:
            nid = node.get("id", "")
            if nid:
                result[nid] = self.classify(node)
        return result
