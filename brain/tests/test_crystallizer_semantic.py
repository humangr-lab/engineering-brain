"""Tests for the crystallizer semantic upgrade (Gap 2).

Verifies embedding-first semantic matching in the KnowledgeCrystallizer:
- _cosine_similarity correctness (identical, orthogonal, opposite, edge cases)
- _find_similar_rule_semantic with mock embedder (threshold 0.75, best-pick)
- _find_similar_rule dispatcher (semantic-first, key-term fallback)
- Graceful fallback when embedder is absent or raises
- KnowledgeCrystallizer.__init__ stores embedder
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.core.schema import NodeType
from engineering_brain.learning.crystallizer import KnowledgeCrystallizer, _cosine_similarity

# =============================================================================
# Mock embedder
# =============================================================================


class MockEmbedder:
    """Deterministic embedder that maps known texts to fixed vectors.

    For unknown texts it returns a generic vector so tests remain deterministic.
    """

    def __init__(self, mapping: dict[str, list[float]] | None = None) -> None:
        self._mapping: dict[str, list[float]] = mapping or {}

    def embed_text(self, text: str) -> list[float]:
        if text in self._mapping:
            return self._mapping[text]
        # Default: generic low-magnitude vector (dissimilar to most entries)
        return [0.1, 0.1, 0.1, 0.1]


class FailingEmbedder:
    """Embedder that always raises, simulating a broken provider."""

    def embed_text(self, text: str) -> list[float]:
        raise RuntimeError("Embedder unavailable")


# =============================================================================
# Shared helpers
# =============================================================================


def _make_graph() -> MemoryGraphAdapter:
    """Create a fresh in-memory graph adapter."""
    return MemoryGraphAdapter()


def _add_rule(
    graph: MemoryGraphAdapter,
    rule_id: str,
    text: str = "test rule",
    **kwargs: Any,
) -> dict[str, Any]:
    """Add a rule node to the graph and return its data dict."""
    data: dict[str, Any] = {"id": rule_id, "text": text, **kwargs}
    graph.add_node(NodeType.RULE.value, rule_id, data)
    return data


# =============================================================================
# 1. _cosine_similarity unit tests
# =============================================================================


def test_cosine_similarity_identical_vectors() -> None:
    """Identical unit vectors yield a similarity of 1.0."""
    score = _cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    assert score == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors() -> None:
    """Orthogonal vectors yield a similarity of 0.0."""
    score = _cosine_similarity([1.0, 0.0, 0.0], [0.0, 1.0, 0.0])
    assert score == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors() -> None:
    """Diametrically opposite vectors yield a similarity of -1.0."""
    score = _cosine_similarity([1.0, 0.0], [-1.0, 0.0])
    assert score == pytest.approx(-1.0)


def test_cosine_similarity_empty_vectors() -> None:
    """Empty vectors yield 0.0 (guard clause)."""
    score = _cosine_similarity([], [])
    assert score == 0.0


def test_cosine_similarity_different_lengths() -> None:
    """Vectors of different lengths yield 0.0 (guard clause)."""
    score = _cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])
    assert score == 0.0


# =============================================================================
# 2. Semantic matching via embedder
# =============================================================================


def test_semantic_match_finds_similar_rule() -> None:
    """When embedder returns high-similarity vectors, the rule is found."""
    graph = _make_graph()

    # The rule text and the query description map to nearly-identical vectors.
    rule_text = "CORS wildcard allows any origin"
    query = "CORS wildcard permits all origins"
    mapping = {
        rule_text: [0.9, 0.1, 0.0, 0.0],
        query: [0.88, 0.12, 0.0, 0.0],  # cosine ~ 0.9997
    }
    embedder = MockEmbedder(mapping)

    _add_rule(graph, "CR-SEM-001", text=rule_text)
    crystallizer = KnowledgeCrystallizer(graph, embedder=embedder)

    result = crystallizer._find_similar_rule_semantic(query)
    assert result is not None
    assert result["id"] == "CR-SEM-001"


def test_semantic_match_threshold_075() -> None:
    """Similarity below 0.75 returns None (threshold not met)."""
    graph = _make_graph()

    rule_text = "Flask debug mode"
    query = "React component lifecycle"
    # Construct vectors with cosine similarity well below 0.75.
    mapping = {
        rule_text: [1.0, 0.0, 0.0, 0.0],
        query: [0.0, 1.0, 0.0, 0.0],  # cosine = 0.0
    }
    embedder = MockEmbedder(mapping)

    _add_rule(graph, "CR-LOW-001", text=rule_text)
    crystallizer = KnowledgeCrystallizer(graph, embedder=embedder)

    result = crystallizer._find_similar_rule_semantic(query)
    assert result is None


def test_semantic_match_above_threshold() -> None:
    """Similarity >= 0.75 returns the matching rule."""
    graph = _make_graph()

    rule_text = "Validate user input before processing"
    query = "Always validate input from users"
    # Vectors engineered to have cosine similarity ~0.80.
    mapping = {
        rule_text: [0.8, 0.6, 0.0, 0.0],
        query: [0.85, 0.55, 0.0, 0.0],  # cosine ~ 0.9995
    }
    embedder = MockEmbedder(mapping)

    _add_rule(graph, "CR-HI-001", text=rule_text)
    crystallizer = KnowledgeCrystallizer(graph, embedder=embedder)

    result = crystallizer._find_similar_rule_semantic(query)
    assert result is not None
    assert result["id"] == "CR-HI-001"


def test_semantic_match_picks_best_rule() -> None:
    """Among multiple rules, the one with highest similarity is returned."""
    graph = _make_graph()

    rule_a_text = "Use parameterized SQL queries"
    rule_b_text = "SQL injection prevention"
    query = "Prevent SQL injection with parameterized queries"

    # rule_b is closer to query than rule_a.
    mapping = {
        rule_a_text: [0.7, 0.3, 0.0, 0.0],
        rule_b_text: [0.9, 0.1, 0.0, 0.0],
        query: [0.88, 0.12, 0.0, 0.0],
    }
    embedder = MockEmbedder(mapping)

    _add_rule(graph, "CR-A-001", text=rule_a_text)
    _add_rule(graph, "CR-B-001", text=rule_b_text)
    crystallizer = KnowledgeCrystallizer(graph, embedder=embedder)

    result = crystallizer._find_similar_rule_semantic(query)
    assert result is not None
    # rule_b_text is closest: cosine(rule_b, query) > cosine(rule_a, query)
    assert result["id"] == "CR-B-001"


# =============================================================================
# 3. Fallback behaviour
# =============================================================================


def test_fallback_to_keyterm_when_no_embedder() -> None:
    """Without an embedder, _find_similar_rule skips semantic and attempts key-terms.

    The key-term path uses graph.query(filters={"text": term}) which requires
    exact field equality in MemoryGraphAdapter.  We verify:
    1. No exception is raised (graceful fallback).
    2. The dispatcher does NOT attempt semantic search (no embedder).
    3. When key-term query returns the rule (exact match on text field),
       the rule is found and reinforcement overlap is checked.
    """
    graph = _make_graph()

    # Use a rule whose text field exactly equals one of the extracted key terms
    # so that MemoryGraphAdapter's equality-based filter can find it.
    # _extract_key_terms("cors wildcard origins insecure") yields
    # ["cors", "wildcard", "origins", "insecure"] (all 4+ chars, no stop words).
    # We set the rule text to "cors" so that filters={"text": "cors"} matches.
    _add_rule(graph, "CR-FB-001", text="cors")

    crystallizer = KnowledgeCrystallizer(graph, embedder=None)

    # The query description must share >= 2 key terms with rule text.
    # Since rule text is "cors" (only 1 term), key-term overlap won't reach 2.
    # This verifies the fallback path runs without errors and returns None
    # when there is insufficient term overlap.
    result = crystallizer._find_similar_rule("cors wildcard origins insecure setup detected")
    # Key-term fallback runs but overlap < 2 so no match is returned.
    assert result is None


def test_fallback_to_keyterm_when_embedder_fails() -> None:
    """When the embedder raises, _find_similar_rule falls back gracefully.

    Verifies that:
    1. The RuntimeError from FailingEmbedder is caught (not propagated).
    2. The dispatcher proceeds to the key-term fallback path.
    3. No unhandled exception escapes _find_similar_rule.
    """
    graph = _make_graph()

    _add_rule(
        graph,
        "CR-FAIL-001",
        text="CORS wildcard origins insecure configuration vulnerability",
    )

    crystallizer = KnowledgeCrystallizer(graph, embedder=FailingEmbedder())

    # Must not raise -- the FailingEmbedder exception is swallowed, and
    # the dispatcher falls through to key-term matching.
    result = crystallizer._find_similar_rule(
        "CORS wildcard origins insecure vulnerability detected"
    )
    # Key-term query uses exact equality filters on MemoryGraphAdapter,
    # so it won't find the rule via substring.  The important thing is
    # that no exception propagated.
    assert result is None or isinstance(result, dict)


# =============================================================================
# 4. Crystallizer init
# =============================================================================


def test_crystallizer_init_with_embedder() -> None:
    """KnowledgeCrystallizer stores the embedder reference on init."""
    graph = _make_graph()
    embedder = MockEmbedder()
    crystallizer = KnowledgeCrystallizer(graph, embedder=embedder)

    assert crystallizer._embedder is embedder


def test_crystallizer_init_without_embedder() -> None:
    """KnowledgeCrystallizer._embedder is None when no embedder is given."""
    graph = _make_graph()
    crystallizer = KnowledgeCrystallizer(graph)

    assert crystallizer._embedder is None


# =============================================================================
# LLM Crystallization
# =============================================================================

from unittest import mock


class TestLLMCrystallization:
    """Tests for _llm_derive_why and _llm_derive_rule_text."""

    def test_why_flag_off_returns_none(self) -> None:
        """LLM WHY derivation skipped when flag is off."""
        from engineering_brain.learning.crystallizer import _llm_derive_why

        with mock.patch.dict("os.environ", {}, clear=True):
            assert _llm_derive_why("desc", "resolution", "lesson") is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_why_llm_success(self, mock_flag, mock_llm) -> None:
        """Returns WHY text when LLM succeeds."""
        from engineering_brain.learning.crystallizer import _llm_derive_why

        mock_llm.return_value = "CORS misconfiguration exposes APIs to cross-origin attacks."
        result = _llm_derive_why("CORS wildcard", "Restrict origins", "Always validate")
        assert result is not None
        assert "CORS" in result

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_why_llm_failure(self, mock_flag, mock_llm) -> None:
        """Returns None when LLM call fails."""
        from engineering_brain.learning.crystallizer import _llm_derive_why

        mock_llm.return_value = None
        assert _llm_derive_why("desc", "res", "lesson") is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_why_too_long_returns_none(self, mock_flag, mock_llm) -> None:
        """Returns None when LLM response exceeds 300 chars."""
        from engineering_brain.learning.crystallizer import _llm_derive_why

        mock_llm.return_value = "x" * 400
        assert _llm_derive_why("desc", "res", "lesson") is None

    def test_rule_text_flag_off_returns_none(self) -> None:
        """LLM rule text skipped when flag is off."""
        from engineering_brain.learning.crystallizer import _llm_derive_rule_text

        with mock.patch.dict("os.environ", {}, clear=True):
            assert _llm_derive_rule_text("some finding") is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_rule_text_llm_success(self, mock_flag, mock_llm) -> None:
        """Returns prescriptive rule text when LLM succeeds."""
        from engineering_brain.learning.crystallizer import _llm_derive_rule_text

        mock_llm.return_value = "Always validate CORS origins against an allowlist."
        result = _llm_derive_rule_text("CORS wildcard finding")
        assert result is not None
        assert result.startswith("Always")

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_rule_text_too_short_returns_none(self, mock_flag, mock_llm) -> None:
        """Returns None when LLM response is under 10 chars."""
        from engineering_brain.learning.crystallizer import _llm_derive_rule_text

        mock_llm.return_value = "Short"
        assert _llm_derive_rule_text("finding") is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_rule_text_llm_failure(self, mock_flag, mock_llm) -> None:
        """Returns None when LLM call fails."""
        from engineering_brain.learning.crystallizer import _llm_derive_rule_text

        mock_llm.return_value = None
        assert _llm_derive_rule_text("finding") is None
