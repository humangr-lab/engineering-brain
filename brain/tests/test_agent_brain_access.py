"""Tests for engineering_brain.agent.brain_access — read-only brain facade."""

from __future__ import annotations

from unittest import mock

from engineering_brain.agent.brain_access import BrainAccess
from engineering_brain.core.types import EnhancedKnowledgeResult, KnowledgeResult


def _mock_brain():
    """Create a mock Brain with standard returns."""
    brain = mock.MagicMock()

    # Mock think() return
    brain.think.return_value = EnhancedKnowledgeResult(
        enhanced_text="Always validate input at boundaries.",
        base_result=KnowledgeResult(
            formatted_text="validate input",
            principles=[],
            patterns=[],
            rules=[],
            evidence=[],
            total_nodes_queried=5,
            cache_hit=False,
            query_time_ms=10.0,
        ),
        overall_confidence="VALIDATED",
        contradictions=[
            {"node_a_id": "CR-SEC-001", "node_b_id": "CR-SEC-002", "severity": "medium"},
        ],
        gaps=[
            {"domain": "security", "technology": "websocket", "description": "No WS auth rules"},
        ],
    )

    # Mock query() return
    brain.query.return_value = KnowledgeResult(
        formatted_text="Use CORS headers",
        principles=[],
        patterns=[],
        rules=[],
        evidence=[],
        total_nodes_queried=3,
        cache_hit=False,
        query_time_ms=5.0,
    )

    # Mock detect_contradictions()
    brain.detect_contradictions.return_value = [
        {"node_a_id": "CR-SEC-001", "node_b_id": "CR-SEC-002", "domains": "security"},
    ]

    # Mock analyze_gaps()
    brain.analyze_gaps.return_value = [
        {"domain": "security", "technology": "websocket"},
        {"domain": "performance", "technology": "kafka"},
    ]

    # Mock stats()
    brain.stats.return_value = {"total": 100, "layers": {"rule": 80}}

    return brain


class TestBrainAccess:
    def test_think(self):
        brain = _mock_brain()
        access = BrainAccess(brain)
        result = access.think("How to validate input?")

        assert result["text"] == "Always validate input at boundaries."
        assert result["confidence"] == "VALIDATED"
        assert len(result["contradictions"]) == 1
        assert result["nodes_consulted"] == 5

    def test_think_with_filters(self):
        brain = _mock_brain()
        access = BrainAccess(brain)
        access.think("test", technologies=["flask"], domains=["security"])

        brain.think.assert_called_once_with(
            task_description="test",
            technologies=["flask"],
            domains=["security"],
        )

    def test_think_exception_fallback(self):
        brain = _mock_brain()
        brain.think.side_effect = RuntimeError("boom")
        access = BrainAccess(brain)
        result = access.think("test")

        assert result["text"] == ""
        assert result["nodes_consulted"] == 0

    def test_query(self):
        brain = _mock_brain()
        access = BrainAccess(brain)
        result = access.query("CORS headers?")

        assert "CORS" in result["text"]
        assert result["nodes_consulted"] == 3

    def test_query_exception_fallback(self):
        brain = _mock_brain()
        brain.query.side_effect = RuntimeError("boom")
        access = BrainAccess(brain)
        result = access.query("test")
        assert result["text"] == ""

    def test_get_contradictions_all(self):
        brain = _mock_brain()
        access = BrainAccess(brain)
        cs = access.get_contradictions()
        assert len(cs) == 1

    def test_get_contradictions_filtered(self):
        brain = _mock_brain()
        access = BrainAccess(brain)
        cs = access.get_contradictions(domain="security")
        assert len(cs) == 1

        cs_empty = access.get_contradictions(domain="nonexistent")
        assert len(cs_empty) == 0

    def test_get_gaps_all(self):
        brain = _mock_brain()
        access = BrainAccess(brain)
        gaps = access.get_gaps()
        assert len(gaps) == 2

    def test_get_gaps_filtered(self):
        brain = _mock_brain()
        access = BrainAccess(brain)
        gaps = access.get_gaps(domain="security")
        assert len(gaps) == 1

    def test_format_context(self):
        brain = _mock_brain()
        access = BrainAccess(brain)
        ctx = access.format_context("How to secure Flask?")

        assert "Brain Knowledge" in ctx
        assert "validate input" in ctx.lower() or "Validate" in ctx
        assert "Contradictions" in ctx
        assert "Knowledge Gaps" in ctx

    def test_format_context_truncation(self):
        brain = _mock_brain()
        access = BrainAccess(brain)
        ctx = access.format_context("test", max_chars=50)
        assert len(ctx) <= 80  # 50 + truncation message

    def test_stats(self):
        brain = _mock_brain()
        access = BrainAccess(brain)
        s = access.stats
        assert s["total"] == 100

    def test_stats_exception(self):
        brain = _mock_brain()
        brain.stats.side_effect = RuntimeError("boom")
        access = BrainAccess(brain)
        assert access.stats == {}
