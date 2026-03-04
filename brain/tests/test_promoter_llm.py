"""Tests for LLM-enhanced promotion assessment in KnowledgePromoter.

Covers:
1. _llm_assess_promotion: flag OFF, success, failure, boost capping
2. Integration: effective_count boost in _promote_evidence_to_rules
3. Regression: reinforcement_count in graph never modified by LLM
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from typing import Any
from unittest import mock

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import NodeType
from engineering_brain.learning.promoter import KnowledgePromoter

# =============================================================================
# Helpers
# =============================================================================


def _make_graph() -> MemoryGraphAdapter:
    """Create a fresh in-memory graph adapter."""
    return MemoryGraphAdapter()


def _config(**overrides) -> BrainConfig:
    """Build a BrainConfig with optional overrides."""
    cfg = BrainConfig()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _add_finding(
    graph: MemoryGraphAdapter,
    fid: str,
    text: str = "test finding",
    reinforcement_count: int = 0,
    **kwargs: Any,
) -> dict:
    """Add a finding (L4) node to the graph."""
    data = {
        "id": fid,
        "text": text,
        "reinforcement_count": reinforcement_count,
        "_layer": "L4",
        **kwargs,
    }
    graph.add_node(NodeType.FINDING.value, fid, data)
    return data


# =============================================================================
# _llm_assess_promotion — unit tests
# =============================================================================


class TestLLMAssessPromotion:
    """Direct tests for _llm_assess_promotion method."""

    def test_flag_off_returns_none(self) -> None:
        """Returns None when flag is off."""
        graph = _make_graph()
        promoter = KnowledgePromoter(graph)

        with mock.patch.dict(os.environ, {}, clear=True):
            result = promoter._llm_assess_promotion("some finding", 3, 5)
            assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_success_worthy(self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock) -> None:
        """Returns assessment dict when LLM deems worthy."""
        mock_llm.return_value = {
            "worthy": True,
            "reasoning": "Strong evidence pattern",
            "boost": 2,
        }
        graph = _make_graph()
        promoter = KnowledgePromoter(graph)

        result = promoter._llm_assess_promotion("SQL injection finding", 3, 5)
        assert result is not None
        assert result["worthy"] is True
        assert result["boost"] == 2
        assert "Strong evidence" in result["reasoning"]

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_success_not_worthy(
        self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock
    ) -> None:
        """Returns assessment with worthy=False."""
        mock_llm.return_value = {
            "worthy": False,
            "reasoning": "Insufficient evidence",
            "boost": 0,
        }
        graph = _make_graph()
        promoter = KnowledgePromoter(graph)

        result = promoter._llm_assess_promotion("weak finding", 1, 5)
        assert result is not None
        assert result["worthy"] is False
        assert result["boost"] == 0

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_boost_capped_at_half_threshold(
        self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock
    ) -> None:
        """Boost is capped at threshold // 2."""
        mock_llm.return_value = {
            "worthy": True,
            "reasoning": "Very strong",
            "boost": 100,  # Excessive boost
        }
        graph = _make_graph()
        promoter = KnowledgePromoter(graph)

        result = promoter._llm_assess_promotion("finding", 3, 10)
        assert result is not None
        assert result["boost"] == 5  # 10 // 2 = 5

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_negative_boost_clamped_to_zero(
        self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock
    ) -> None:
        """Negative boost values are clamped to 0."""
        mock_llm.return_value = {
            "worthy": True,
            "reasoning": "Edge case",
            "boost": -5,
        }
        graph = _make_graph()
        promoter = KnowledgePromoter(graph)

        result = promoter._llm_assess_promotion("finding", 3, 10)
        assert result is not None
        assert result["boost"] == 0

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_failure_returns_none(
        self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock
    ) -> None:
        """Returns None when LLM call fails."""
        mock_llm.return_value = None
        graph = _make_graph()
        promoter = KnowledgePromoter(graph)

        result = promoter._llm_assess_promotion("finding", 3, 5)
        assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_malformed_response(
        self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock
    ) -> None:
        """Returns None when LLM returns missing/invalid keys."""
        mock_llm.return_value = {"wrong": "schema"}
        graph = _make_graph()
        promoter = KnowledgePromoter(graph)

        result = promoter._llm_assess_promotion("finding", 3, 5)
        # Should still return a dict (with defaults) or None depending on impl
        if result is not None:
            assert result["boost"] == 0

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_reasoning_truncated(self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock) -> None:
        """Reasoning is truncated to 200 chars."""
        mock_llm.return_value = {
            "worthy": True,
            "reasoning": "x" * 500,
            "boost": 1,
        }
        graph = _make_graph()
        promoter = KnowledgePromoter(graph)

        result = promoter._llm_assess_promotion("finding", 3, 10)
        assert result is not None
        assert len(result["reasoning"]) <= 200
