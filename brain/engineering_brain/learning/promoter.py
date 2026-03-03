"""Knowledge promoter for the Engineering Knowledge Brain.

Auto-promotes knowledge up the cortical hierarchy:
- L4 Evidence → L3 Rule (threshold: 5 reinforcements)
- L3 Rule → L2 Pattern (threshold: 20 reinforcements + high confidence)

This is the brain's learning mechanism — repeated observations
become crystallized rules, and well-established rules become patterns.
"""

from __future__ import annotations

import logging
from typing import Any

from engineering_brain.adapters.base import GraphAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import EdgeType, NodeType

logger = logging.getLogger(__name__)


class KnowledgePromoter:
    """Promotes knowledge nodes up the cortical hierarchy based on evidence strength."""

    def __init__(self, graph: GraphAdapter, config: BrainConfig | None = None) -> None:
        self._graph = graph
        self._config = config or BrainConfig()
        self._adaptive_policy: Any = None  # AdaptivePromotionPolicy (optional)

    def check_and_promote(self) -> list[str]:
        """Check all nodes for promotion eligibility and promote them.

        Returns list of promoted node IDs (L4→L3 + L3→L2 + cluster crystallization).
        """
        promoted: list[str] = []

        # L4 Evidence → L3 Rule promotion
        promoted.extend(self._promote_evidence_to_rules())

        # Single-rule L3 → L2 promotion
        promoted.extend(self._promote_rules_to_patterns())

        # Cluster crystallization (additive)
        promoted.extend(self._cluster_crystallize())

        return promoted

    def _promote_evidence_to_rules(self) -> list[str]:
        """Promote L4 findings to L3 rules when they reach the reinforcement threshold.

        When multiple findings describe the same pattern (same description/why text),
        and collectively reach `promote_l4_to_l3_threshold` reinforcements,
        auto-crystallize them into an L3 rule.

        Threshold is dynamically adapted per domain if adaptive policy is available.
        """
        base_threshold = self._config.promote_l4_to_l3_threshold
        findings = self._graph.query(label=NodeType.FINDING.value, limit=500)
        if not findings:
            return []

        # Group findings by a content key (description hash)
        import hashlib
        groups: dict[str, list[dict]] = {}
        for f in findings:
            desc = f.get("description", f.get("text", ""))
            key = hashlib.md5(desc.encode()).hexdigest()[:12]
            groups.setdefault(key, []).append(f)

        promoted: list[str] = []
        for key, group in groups.items():
            total_reinforcements = sum(int(f.get("reinforcement_count", 1)) for f in group)

            # Adaptive threshold per domain (if policy available)
            best = max(group, key=lambda f: float(f.get("confidence", 0)))
            domain = (best.get("domains") or ["general"])[0] if best.get("domains") else "general"
            if self._adaptive_policy:
                threshold = self._adaptive_policy.effective_threshold(base_threshold, domain, "L4")
            else:
                threshold = base_threshold

            if total_reinforcements < threshold:
                continue

            rule_id = f"CR-L4-{key}"

            # Idempotent check
            if self._graph.get_node(rule_id):
                continue

            rule = {
                "id": rule_id,
                "text": best.get("description", best.get("text", "")),
                "why": f"Auto-promoted from {len(group)} L4 findings with {total_reinforcements} reinforcements",
                "how_to_do_right": best.get("resolution", ""),
                "severity": best.get("severity", "medium"),
                "technologies": best.get("technologies", []),
                "domains": best.get("domains", []),
                "confidence": float(best.get("confidence", 0.5)),
                "reinforcement_count": total_reinforcements,
                "_promoted_from_l4": [f.get("id", "") for f in group],
            }

            if self._graph.add_node(NodeType.RULE.value, rule_id, rule):
                # Link to source findings
                for f in group:
                    fid = f.get("id", "")
                    if fid:
                        self._graph.add_edge(fid, rule_id, EdgeType.REINFORCES.value)
                promoted.append(rule_id)
                logger.info(
                    "Promoted %d L4 findings → rule %s (reinforcements=%d)",
                    len(group), rule_id, total_reinforcements,
                )

        return promoted

    def _cluster_crystallize(self) -> list[str]:
        """Run additive cluster crystallization."""
        if not self._config.crystallize_enabled:
            return []
        try:
            from engineering_brain.learning.cluster_promoter import ClusterPromoter
            cp = ClusterPromoter(self._graph, self._config)
            return cp.crystallize()
        except Exception as exc:
            logger.error("Cluster crystallization failed: %s", exc)
            return []

    def _promote_rules_to_patterns(self) -> list[str]:
        """Promote highly-reinforced rules to patterns.

        Threshold is dynamically adapted per domain if adaptive policy is available.
        """
        base_threshold = self._config.promote_l3_to_l2_threshold
        rules = self._graph.query(label=NodeType.RULE.value, limit=500)
        promoted: list[str] = []

        for rule in rules:
            reinforcement = int(rule.get("reinforcement_count", 0))
            confidence = float(rule.get("confidence", 0))

            # Adaptive threshold per domain
            domain = (rule.get("domains") or ["general"])[0] if rule.get("domains") else "general"
            if self._adaptive_policy:
                threshold = self._adaptive_policy.effective_threshold(base_threshold, domain, "L3")
            else:
                threshold = base_threshold

            # Epistemic-aware promotion: require low uncertainty if ep_* present
            ep_b = rule.get("ep_b")
            if ep_b is not None:
                ep_u = float(rule.get("ep_u", 1.0))
                ep_a = float(rule.get("ep_a", 0.5))
                projected = float(ep_b) + ep_a * ep_u
                eligible = reinforcement >= threshold and projected >= 0.8 and ep_u <= 0.3
            else:
                eligible = reinforcement >= threshold and confidence >= 0.8

            if eligible:
                pattern_id = self._create_pattern_from_rule(rule)
                if pattern_id:
                    promoted.append(pattern_id)
                    logger.info(
                        "Promoted rule %s → pattern %s (reinforcement=%d, confidence=%.2f)",
                        rule.get("id"), pattern_id, reinforcement, confidence,
                    )

        return promoted

    def _create_pattern_from_rule(self, rule: dict[str, Any]) -> str | None:
        """Create a pattern node from a well-established rule."""
        rule_id = rule.get("id", "")
        if not rule_id:
            return None

        pattern_id = f"PAT-{rule_id}"

        # Check if pattern already exists (idempotent)
        existing = self._graph.get_node(pattern_id)
        if existing:
            return pattern_id

        pattern = {
            "id": pattern_id,
            "name": str(rule.get("text", ""))[:100],
            "category": "learned",
            "intent": str(rule.get("why", "")),
            "when_to_use": str(rule.get("how_to_do_right", "")),
            "when_not_to_use": str(rule.get("example_bad", ""))[:200] if rule.get("example_bad") else "",
            "languages": rule.get("technologies", []),
            "example_good": str(rule.get("example_good", "")),
            "example_bad": str(rule.get("example_bad", "")),
            "related_principles": [],
            "_promoted_from": rule_id,
            "_promotion_confidence": float(rule.get("confidence", 0)),
            "_promotion_reinforcements": int(rule.get("reinforcement_count", 0)),
        }

        success = self._graph.add_node(NodeType.PATTERN.value, pattern_id, pattern)
        if success:
            # Link pattern to source rule
            self._graph.add_edge(pattern_id, rule_id, EdgeType.INSTANTIATES.value)

            # Copy technology edges
            for tech in (rule.get("technologies") or []):
                tech_id = f"tech:{tech.lower()}"
                self._graph.add_edge(pattern_id, tech_id, EdgeType.USED_IN.value)

            return pattern_id

        return None

    def promotion_candidates(self) -> dict[str, list[dict[str, Any]]]:
        """Get nodes that are close to promotion thresholds."""
        l3_threshold = self._config.promote_l3_to_l2_threshold

        rules = self._graph.query(label=NodeType.RULE.value, limit=500)
        near_promotion = [
            r for r in rules
            if int(r.get("reinforcement_count", 0)) >= l3_threshold * 0.7
            and float(r.get("confidence", 0)) >= 0.6
        ]

        return {"l3_to_l2": near_promotion}
