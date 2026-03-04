"""Tests for the Epistemic Ladder (E0-E5 classification and promotion)."""

from __future__ import annotations

import pytest

from engineering_brain.core.types import EpistemicStatus
from engineering_brain.epistemic.epistemic_ladder import EpistemicLadder


@pytest.fixture
def ladder():
    return EpistemicLadder()


# ---------------------------------------------------------------------------
# EpistemicStatus enum
# ---------------------------------------------------------------------------


class TestEpistemicStatus:
    def test_values(self):
        assert EpistemicStatus.E0_RUMOR.value == "E0"
        assert EpistemicStatus.E5_AXIOM.value == "E5"

    def test_min_sources(self):
        assert EpistemicStatus.E0_RUMOR.min_sources == 0
        assert EpistemicStatus.E2_OBSERVATION.min_sources == 2
        assert EpistemicStatus.E4_PROVEN.min_sources == 3

    def test_min_belief(self):
        assert EpistemicStatus.E0_RUMOR.min_belief == 0.0
        assert EpistemicStatus.E3_TESTED.min_belief == 0.6
        assert EpistemicStatus.E5_AXIOM.min_belief == 0.95

    def test_max_uncertainty(self):
        assert EpistemicStatus.E0_RUMOR.max_uncertainty == 1.0
        assert EpistemicStatus.E3_TESTED.max_uncertainty == 0.4
        assert EpistemicStatus.E5_AXIOM.max_uncertainty == 0.05

    def test_level(self):
        assert EpistemicStatus.E0_RUMOR.level == 0
        assert EpistemicStatus.E5_AXIOM.level == 5

    def test_ordering(self):
        assert EpistemicStatus.E0_RUMOR.level < EpistemicStatus.E5_AXIOM.level


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class TestClassification:
    def test_axiom_always_e5(self, ladder):
        node = {"id": "AX-001", "immutable": True, "ep_b": 0.1, "ep_u": 0.9}
        assert ladder.classify(node) == EpistemicStatus.E5_AXIOM

    def test_e0_default(self, ladder):
        node = {"id": "CR-999", "ep_b": 0.0, "ep_u": 1.0}
        assert ladder.classify(node) == EpistemicStatus.E0_RUMOR

    def test_e1_hypothesis(self, ladder):
        node = {
            "id": "CR-100",
            "ep_b": 0.3,
            "ep_u": 0.7,
            "sources": [{"url": "https://example.com"}],
        }
        assert ladder.classify(node) == EpistemicStatus.E1_HYPOTHESIS

    def test_e2_observation(self, ladder):
        node = {
            "id": "CR-200",
            "ep_b": 0.5,
            "ep_u": 0.4,
            "sources": [{"url": "a"}, {"url": "b"}],
        }
        assert ladder.classify(node) == EpistemicStatus.E2_OBSERVATION

    def test_e2_by_reinforcement(self, ladder):
        node = {"id": "CR-201", "ep_b": 0.5, "ep_u": 0.4, "reinforcement_count": 15}
        assert ladder.classify(node) == EpistemicStatus.E2_OBSERVATION

    def test_e3_tested(self, ladder):
        node = {
            "id": "CR-300",
            "ep_b": 0.7,
            "ep_u": 0.2,
            "validation_status": "cross_checked",
            "sources": [{"url": "a"}, {"url": "b"}],
        }
        assert ladder.classify(node) == EpistemicStatus.E3_TESTED

    def test_e4_proven(self, ladder):
        node = {
            "id": "CR-400",
            "ep_b": 0.9,
            "ep_u": 0.05,
            "validation_status": "human_verified",
            "sources": [{"url": "a"}, {"url": "b"}, {"url": "c"}],
        }
        assert ladder.classify(node) == EpistemicStatus.E4_PROVEN

    def test_no_ep_fields_defaults_e0(self, ladder):
        node = {"id": "CR-000"}
        assert ladder.classify(node) == EpistemicStatus.E0_RUMOR

    def test_batch_classify(self, ladder):
        nodes = [
            {"id": "AX-001", "immutable": True},
            {"id": "CR-001", "ep_b": 0.0, "ep_u": 1.0},
        ]
        result = ladder.batch_classify(nodes)
        assert result["AX-001"] == EpistemicStatus.E5_AXIOM
        assert result["CR-001"] == EpistemicStatus.E0_RUMOR


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


class TestPromotion:
    def test_cannot_promote_insufficient_belief(self, ladder):
        """E0 node with low belief cannot promote to E1."""
        node = {"id": "CR-050", "ep_b": 0.1, "ep_u": 0.9}
        assert ladder.classify(node) == EpistemicStatus.E0_RUMOR
        can, reason = ladder.can_promote(node, EpistemicStatus.E1_HYPOTHESIS)
        assert not can
        assert "belief" in reason.lower()

    def test_cannot_promote_insufficient_sources(self, ladder):
        """E1 node with 1 source cannot promote to E2 (needs 2)."""
        node = {
            "id": "CR-051",
            "ep_b": 0.45,
            "ep_u": 0.5,
            "sources": [{"url": "a"}],
            "reinforcement_count": 3,
        }
        assert ladder.classify(node) == EpistemicStatus.E1_HYPOTHESIS
        can, reason = ladder.can_promote(node, EpistemicStatus.E2_OBSERVATION)
        assert not can
        assert "sources" in reason.lower()

    def test_cannot_skip_levels(self, ladder):
        """E1 node cannot skip directly to E4."""
        node = {
            "id": "CR-053",
            "ep_b": 0.3,
            "ep_u": 0.6,
            "sources": [{"url": "a"}],
            "reinforcement_count": 3,
        }
        assert ladder.classify(node) == EpistemicStatus.E1_HYPOTHESIS
        can, reason = ladder.can_promote(node, EpistemicStatus.E4_PROVEN)
        assert not can
        assert "skip" in reason.lower() or "one step" in reason.lower()

    def test_cannot_promote_already_at_level(self, ladder):
        """Cannot promote to E2 when already classified as E2."""
        node = {
            "id": "CR-054",
            "ep_b": 0.5,
            "ep_u": 0.4,
            "sources": [{"url": "a"}, {"url": "b"}],
            "reinforcement_count": 10,
        }
        assert ladder.classify(node) == EpistemicStatus.E2_OBSERVATION
        can, reason = ladder.can_promote(node, EpistemicStatus.E2_OBSERVATION)
        assert not can
        assert "not higher" in reason.lower()

    def test_promote_raises_on_unmet(self, ladder):
        """Promote raises ValueError when requirements not met."""
        node = {"id": "CR-055", "ep_b": 0.05, "ep_u": 0.95}
        with pytest.raises(ValueError, match="Cannot promote"):
            ladder.promote(node, EpistemicStatus.E1_HYPOTHESIS)

    def test_promote_updates_field(self, ladder):
        """Verify classification changes as data improves."""
        # Start with E0 node
        node = {
            "id": "CR-056",
            "ep_b": 0.1,
            "ep_u": 0.9,
            "epistemic_status": "E0",
        }
        assert ladder.classify(node) == EpistemicStatus.E0_RUMOR
        # Upgrade data to meet E1 requirements
        node["ep_b"] = 0.3
        node["ep_u"] = 0.6
        node["sources"] = [{"url": "a"}]
        node["reinforcement_count"] = 3
        assert ladder.classify(node) == EpistemicStatus.E1_HYPOTHESIS
        # Upgrade data to meet E2 requirements
        node["sources"].append({"url": "b"})
        node["ep_b"] = 0.45
        node["ep_u"] = 0.5
        assert ladder.classify(node) == EpistemicStatus.E2_OBSERVATION


# ---------------------------------------------------------------------------
# Demotion
# ---------------------------------------------------------------------------


class TestDemotion:
    def test_demote_goes_down_one_level(self, ladder):
        node = {"id": "CR-060", "epistemic_status": "E3"}
        updated = ladder.demote(node, reason="Contradicted by new evidence")
        assert updated["epistemic_status"] == "E2"
        assert updated["epistemic_demotion_reason"] == "Contradicted by new evidence"

    def test_demote_to_e0_flag(self, ladder):
        node = {"id": "CR-060b", "epistemic_status": "E3"}
        updated = ladder.demote(node, reason="Severe contradiction", to_e0=True)
        assert updated["epistemic_status"] == "E0"

    def test_demote_already_e0(self, ladder):
        node = {"id": "CR-061", "epistemic_status": "E0"}
        updated = ladder.demote(node)
        assert updated["epistemic_status"] == "E0"


# ---------------------------------------------------------------------------
# LLM Epistemic Suggestion
# ---------------------------------------------------------------------------

import os
from unittest import mock


class TestLLMEpistemicSuggestion:
    """Tests for _llm_suggest_classification (advisory only)."""

    def test_flag_off_returns_none(self, ladder) -> None:
        """LLM suggestion skipped when flag is off."""
        node = {"id": "CR-070", "text": "Always use parameterized queries"}
        with mock.patch.dict(os.environ, {}, clear=True):
            result = ladder._llm_suggest_classification(node)
            assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_success_returns_status(self, mock_flag, mock_llm, ladder) -> None:
        """Returns EpistemicStatus when LLM suggests valid classification."""
        mock_llm.return_value = {"status": "E3", "reasoning": "Well-tested pattern"}
        node = {
            "id": "CR-071",
            "text": "Always use parameterized queries",
            "reinforcement_count": 5,
            "validation_status": "validated",
        }

        result = ladder._llm_suggest_classification(node)
        assert result is not None
        assert result.value == "E3"

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_stores_advisory_metadata(self, mock_flag, mock_llm, ladder) -> None:
        """Stores suggestion as metadata on node, never overrides classify()."""
        mock_llm.return_value = {"status": "E4", "reasoning": "Proven across projects"}
        node = {
            "id": "CR-072",
            "text": "Use type hints",
            "reinforcement_count": 10,
            "validation_status": "cross_checked",
        }

        ladder._llm_suggest_classification(node)
        assert node["_llm_suggested_status"] == "E4"
        assert "Proven" in node["_llm_suggested_reasoning"]

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_invalid_status_returns_none(self, mock_flag, mock_llm, ladder) -> None:
        """Returns None when LLM suggests invalid status."""
        mock_llm.return_value = {"status": "E99", "reasoning": "Invalid level"}
        node = {"id": "CR-073", "text": "test"}

        result = ladder._llm_suggest_classification(node)
        assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_failure_returns_none(self, mock_flag, mock_llm, ladder) -> None:
        """Returns None when LLM call fails."""
        mock_llm.return_value = None
        node = {"id": "CR-074", "text": "test"}

        result = ladder._llm_suggest_classification(node)
        assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_reasoning_truncated(self, mock_flag, mock_llm, ladder) -> None:
        """Reasoning is truncated to 200 chars."""
        mock_llm.return_value = {"status": "E2", "reasoning": "x" * 500}
        node = {"id": "CR-075", "text": "test"}

        ladder._llm_suggest_classification(node)
        assert len(node.get("_llm_suggested_reasoning", "")) <= 200

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_never_overrides_deterministic_classify(self, mock_flag, mock_llm, ladder) -> None:
        """Advisory suggestion does NOT change deterministic classification."""
        mock_llm.return_value = {"status": "E5", "reasoning": "LLM says axiom"}
        node = {
            "id": "CR-076",
            "text": "test",
            "reinforcement_count": 0,
            "validation_status": "unvalidated",
        }

        # Deterministic classify should give E0 or E1 for zero reinforcements
        det_result = ladder.classify(node)
        ladder._llm_suggest_classification(node)

        # Re-classify — should be unchanged
        assert ladder.classify(node) == det_result

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_batch_classify_calls_llm(self, mock_flag, mock_llm, ladder) -> None:
        """batch_classify invokes LLM suggestion for each node."""
        mock_llm.return_value = {"status": "E2", "reasoning": "Observed pattern"}
        nodes = [
            {"id": "CR-077", "text": "rule 1", "reinforcement_count": 2},
            {"id": "CR-078", "text": "rule 2", "reinforcement_count": 3},
        ]

        ladder.batch_classify(nodes)
        # Each node should have advisory metadata
        for n in nodes:
            assert "_llm_suggested_status" in n
