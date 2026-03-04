"""Tests for soft-delete (zero-loss deprecation) in the pruner.

Verifies:
- Pruned nodes are deprecated, not deleted
- Deprecated nodes are invisible in query results
- Deprecated nodes still exist in the graph
- Scorer returns 0.0 for deprecated nodes
- Pruner skips already-deprecated nodes
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import NodeType
from engineering_brain.learning.pruner import KnowledgePruner
from engineering_brain.retrieval.scorer import score_knowledge


def _make_stale_rule(
    graph: MemoryGraphAdapter,
    rule_id: str,
    age_days: int = 90,
    reinforcement_count: int = 0,
    confidence: float = 0.5,
    **extra,
) -> None:
    created_at = (datetime.now(UTC) - timedelta(days=age_days)).isoformat()
    graph.add_node(
        NodeType.RULE.value,
        rule_id,
        {
            "id": rule_id,
            "text": f"Stale rule {rule_id}",
            "why": "Testing",
            "how_to_do_right": "Do it",
            "severity": "medium",
            "technologies": ["python"],
            "domains": ["testing"],
            "reinforcement_count": reinforcement_count,
            "confidence": confidence,
            "created_at": created_at,
            **extra,
        },
    )


class TestSoftDelete:
    def test_stale_rules_deprecated_not_deleted(self):
        """Pruned stale rules get deprecated=True, still exist in graph."""
        graph = MemoryGraphAdapter()
        config = BrainConfig()
        config.prune_after_days = 60
        config.prune_min_reinforcements = 0

        _make_stale_rule(graph, "CR-STALE-001", age_days=90, reinforcement_count=0)

        pruner = KnowledgePruner(graph, config)
        results = pruner.prune()
        assert results["stale_rules"] >= 1

        # Node still exists
        node = graph.get_node("CR-STALE-001")
        assert node is not None
        assert node["deprecated"] is True
        assert node["deprecation_reason"] == "stale"
        assert "deprecated_at" in node

    def test_deprecated_nodes_invisible_in_scorer(self):
        """Scorer returns 0.0 for deprecated nodes."""
        node = {
            "technologies": ["flask"],
            "domains": ["security"],
            "severity": "high",
            "reinforcement_count": 10,
            "confidence": 0.9,
            "deprecated": True,
        }
        score = score_knowledge(node, ["flask"], ["security"])
        assert score == 0.0

    def test_non_deprecated_scored_normally(self):
        """Non-deprecated nodes get normal scores."""
        node = {
            "technologies": ["flask"],
            "domains": ["security"],
            "severity": "high",
            "reinforcement_count": 10,
            "confidence": 0.9,
        }
        score = score_knowledge(node, ["flask"], ["security"])
        assert score > 0.0

    def test_pruner_skips_already_deprecated(self):
        """Already-deprecated nodes are not re-processed."""
        graph = MemoryGraphAdapter()
        config = BrainConfig()
        config.prune_after_days = 60
        config.prune_min_reinforcements = 0

        _make_stale_rule(
            graph,
            "CR-ALREADY-001",
            age_days=90,
            deprecated=True,
            deprecated_at="2026-01-01T00:00:00+00:00",
            deprecation_reason="previous_prune",
        )

        pruner = KnowledgePruner(graph, config)
        results = pruner.prune()
        assert results["stale_rules"] == 0

        # Still has original deprecation reason
        node = graph.get_node("CR-ALREADY-001")
        assert node["deprecation_reason"] == "previous_prune"

    def test_l5_context_hard_deleted(self):
        """L5 context nodes are still hard-deleted (ephemeral by design)."""
        graph = MemoryGraphAdapter()
        config = BrainConfig()

        created = (datetime.now(UTC) - timedelta(minutes=120)).isoformat()
        graph.add_node(
            NodeType.TASK.value,
            "TASK-001",
            {
                "id": "TASK-001",
                "ttl_minutes": 60,
                "created_at": created,
            },
        )

        pruner = KnowledgePruner(graph, config)
        results = pruner.prune()
        assert results["expired_context"] >= 1

        # Task node actually deleted (not soft-deleted)
        assert graph.get_node("TASK-001") is None

    def test_dry_run_does_not_modify(self):
        """dry_run() previews without modifying the graph."""
        graph = MemoryGraphAdapter()
        config = BrainConfig()
        config.prune_after_days = 60
        config.prune_min_reinforcements = 0

        _make_stale_rule(graph, "CR-DRY-001", age_days=90)

        pruner = KnowledgePruner(graph, config)
        candidates = pruner.dry_run()
        assert "CR-DRY-001" in candidates["stale_rules"]

        # Node NOT deprecated
        node = graph.get_node("CR-DRY-001")
        assert not node.get("deprecated")

    def test_total_node_count_preserved(self):
        """After pruning, total node count stays the same (soft-delete)."""
        graph = MemoryGraphAdapter()
        config = BrainConfig()
        config.prune_after_days = 60
        config.prune_min_reinforcements = 0

        for i in range(5):
            _make_stale_rule(graph, f"CR-COUNT-{i:03d}", age_days=90)

        count_before = graph.count(NodeType.RULE.value)
        pruner = KnowledgePruner(graph, config)
        pruner.prune()
        count_after = graph.count(NodeType.RULE.value)

        # Same count — nodes deprecated, not deleted
        assert count_after == count_before
