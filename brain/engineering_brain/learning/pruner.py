"""Knowledge pruner for the Engineering Knowledge Brain.

Removes obsolete, contradicted, or stale knowledge to prevent bloating.
Runs periodically to keep the graph lean and relevant.

Pruning rules:
1. Remove rules with 0 reinforcements after PRUNE_DAYS days
2. Resolve conflicting rules (keep higher-confidence version)
3. Remove L5 context nodes past their TTL
4. Archive superseded rules (soft delete)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from engineering_brain.adapters.base import GraphAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import NodeType

logger = logging.getLogger(__name__)


class KnowledgePruner:
    """Deprecates stale and contradicted knowledge in the brain (zero-loss soft-delete)."""

    def __init__(self, graph: GraphAdapter, config: BrainConfig | None = None) -> None:
        self._graph = graph
        self._config = config or BrainConfig()

    def _soft_delete(self, node_id: str, reason: str = "") -> bool:
        """Soft-delete a node: mark deprecated but preserve in graph (zero loss)."""
        node = self._graph.get_node(node_id)
        if node is None:
            return False
        label = node.get("_label", NodeType.RULE.value)
        self._graph.add_node(label, node_id, {
            **node,
            "deprecated": True,
            "deprecated_at": datetime.now(timezone.utc).isoformat(),
            "deprecation_reason": reason,
        })
        logger.debug("Soft-deleted %s (reason=%s)", node_id, reason)
        # Record in observation log (non-blocking)
        try:
            from engineering_brain.observation.log import ObservationLog
            obs = ObservationLog()
            obs.record_deprecated(node_id, reason=reason)
        except Exception:
            pass
        return True

    def prune(self) -> dict[str, int]:
        """Run all pruning operations. Returns counts per category."""
        results = {
            "stale_rules": self._prune_stale_rules(),
            "expired_context": self._prune_expired_context(),
            "low_confidence": self._prune_low_confidence(),
        }
        total = sum(results.values())
        if total > 0:
            logger.info("Pruned %d total nodes: %s", total, results)
        return results

    def _prune_stale_rules(self) -> int:
        """Remove rules with 0 reinforcements past the prune deadline."""
        now = datetime.now(timezone.utc)
        prune_days = self._config.prune_after_days
        min_reinforcements = self._config.prune_min_reinforcements
        pruned = 0

        rules = self._graph.query(label=NodeType.RULE.value, limit=1000)
        for rule in rules:
            if rule.get("deprecated"):
                continue
            reinforcement = int(rule.get("reinforcement_count", 0))
            if reinforcement > min_reinforcements:
                continue

            created = rule.get("created_at", "")
            try:
                if isinstance(created, str) and created:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    age_days = (now - created_dt).days
                    if age_days >= prune_days:
                        rule_id = rule.get("id", "")
                        if rule_id and self._soft_delete(rule_id, reason="stale"):
                            pruned += 1
                            logger.debug("Deprecated stale rule %s (age=%dd, reinforce=%d)", rule_id, age_days, reinforcement)
            except (ValueError, TypeError):
                continue

        return pruned

    def _prune_expired_context(self) -> int:
        """Remove L5 context nodes past their TTL."""
        now = datetime.now(timezone.utc)
        pruned = 0

        tasks = self._graph.query(label=NodeType.TASK.value, limit=500)
        for task in tasks:
            ttl_minutes = int(task.get("ttl_minutes", 60))
            created = task.get("created_at", "")
            try:
                if isinstance(created, str) and created:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    age_minutes = (now - created_dt).total_seconds() / 60
                    if age_minutes > ttl_minutes:
                        task_id = task.get("id", "")
                        if task_id and self._graph.delete_node(task_id):
                            pruned += 1
            except (ValueError, TypeError):
                continue

        return pruned

    def _prune_low_confidence(self) -> int:
        """Remove rules with very low confidence (contradicted or unreliable)."""
        from engineering_brain.epistemic.temporal import get_decay_engine
        from engineering_brain.epistemic.opinion import OpinionTuple

        pruned = 0
        rules = self._graph.query(label=NodeType.RULE.value, limit=1000)
        now = int(datetime.now(timezone.utc).timestamp())

        for rule in rules:
            if rule.get("deprecated"):
                continue
            confidence = float(rule.get("confidence", 0.5))
            reinforcement = int(rule.get("reinforcement_count", 0))

            # Epistemic-aware pruning with temporal decay
            ep_b = rule.get("ep_b")
            if ep_b is not None:
                ep_d = float(rule.get("ep_d", 0.0))
                ep_u = float(rule.get("ep_u", 0.5))
                ep_a = float(rule.get("ep_a", 0.5))

                # Apply temporal decay before prune decision
                node_id = rule.get("id", "")
                layer = "L3"  # Rules are L3
                if node_id.startswith("AX-"):
                    layer = "L0"
                elif node_id.startswith("P-"):
                    layer = "L1"
                elif node_id.startswith("PAT-"):
                    layer = "L2"

                engine = get_decay_engine(layer)
                last_decay = int(rule.get("last_decay_at", 0))
                if last_decay == 0:
                    # H16: Avoid 54+ years of accumulated decay for nodes never decayed.
                    # Use created_at timestamp if available, else 30 days ago as default.
                    created = rule.get("created_at")
                    if created:
                        try:
                            if isinstance(created, str):
                                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                                last_decay = int(dt.timestamp())
                            elif isinstance(created, (int, float)):
                                last_decay = int(created)
                        except (ValueError, TypeError):
                            pass
                    if last_decay == 0:
                        import time as _time
                        last_decay = int(_time.time()) - 30 * 86400  # 30 days ago
                events = rule.get("event_timestamps", [])
                opinion = OpinionTuple(b=float(ep_b), d=ep_d, u=ep_u, a=ep_a)
                decayed = engine.apply_decay(opinion, now, last_decay, events)

                projected = decayed.b + decayed.a * decayed.u
                should_prune = projected < 0.05 or decayed.d > 0.8 or decayed.u > 0.95
            else:
                should_prune = confidence < 0.05 and reinforcement > 0

            if should_prune:
                rule_id = rule.get("id", "")
                if rule_id and self._soft_delete(rule_id, reason="low_confidence"):
                    pruned += 1
                    logger.debug("Deprecated low-confidence rule %s (confidence=%.3f)", rule_id, confidence)
        return pruned

    def dry_run(self) -> dict[str, list[str]]:
        """Preview what would be deprecated without actually modifying."""
        now = datetime.now(timezone.utc)
        prune_days = self._config.prune_after_days
        candidates: dict[str, list[str]] = {"stale_rules": [], "expired_context": [], "low_confidence": []}

        rules = self._graph.query(label=NodeType.RULE.value, limit=1000)
        for rule in rules:
            if rule.get("deprecated"):
                continue
            rid = rule.get("id", "")
            reinforcement = int(rule.get("reinforcement_count", 0))
            confidence = float(rule.get("confidence", 0.5))
            created = rule.get("created_at", "")

            if reinforcement <= self._config.prune_min_reinforcements:
                try:
                    if isinstance(created, str) and created:
                        age = (now - datetime.fromisoformat(created.replace("Z", "+00:00"))).days
                        if age >= prune_days:
                            candidates["stale_rules"].append(rid)
                except (ValueError, TypeError):
                    pass

            if confidence < 0.05 and reinforcement > 0:
                candidates["low_confidence"].append(rid)

        return candidates
