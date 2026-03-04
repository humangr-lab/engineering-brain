"""Tests for ProactivePush — LLM adjacent domain inference.

Covers:
1. _llm_infer_adjacent_domains: flag OFF, success, failure, filtering
2. Domain proximity basics
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from unittest import mock

from engineering_brain.retrieval.proactive_push import ProactivePush

# =============================================================================
# Helpers
# =============================================================================


def _make_pp() -> ProactivePush:
    """Create a ProactivePush with a mock brain (avoids slow seed)."""
    mock_brain = mock.MagicMock()
    mock_brain.graph = mock.MagicMock()
    return ProactivePush(mock_brain)


# =============================================================================
# LLM adjacent domain inference
# =============================================================================


class TestLLMAdjacentDomains:
    """Tests for _llm_infer_adjacent_domains."""

    def test_flag_off_returns_none(self) -> None:
        """LLM inference skipped when flag is off."""
        pp = _make_pp()
        with mock.patch.dict(os.environ, {}, clear=True):
            result = pp._llm_infer_adjacent_domains("Flask API", ["api"])
            assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_success_returns_domains(
        self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock
    ) -> None:
        """Returns adjacent domains when LLM succeeds."""
        mock_llm.return_value = {"domains": ["security", "testing"]}
        pp = _make_pp()
        result = pp._llm_infer_adjacent_domains("Flask API", ["api"])
        assert result == ["security", "testing"]

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_failure_returns_none(
        self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock
    ) -> None:
        """Returns None when LLM call fails."""
        mock_llm.return_value = None
        pp = _make_pp()
        result = pp._llm_infer_adjacent_domains("Flask API", ["api"])
        assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_malformed_response(
        self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock
    ) -> None:
        """Returns None when LLM returns malformed data."""
        mock_llm.return_value = {"wrong_key": "value"}
        pp = _make_pp()
        result = pp._llm_infer_adjacent_domains("Flask API", ["api"])
        assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_filters_non_strings(
        self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock
    ) -> None:
        """Filters out non-string items from LLM response."""
        mock_llm.return_value = {"domains": ["security", 42, None, "testing"]}
        pp = _make_pp()
        result = pp._llm_infer_adjacent_domains("Flask API", ["api"])
        assert result == ["security", "testing"]

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_empty_domains(self, mock_flag: mock.MagicMock, mock_llm: mock.MagicMock) -> None:
        """Returns empty list when LLM returns no domains."""
        mock_llm.return_value = {"domains": []}
        pp = _make_pp()
        result = pp._llm_infer_adjacent_domains("test", ["api"])
        assert result == []
