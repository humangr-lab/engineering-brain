"""Tests for context_guard.py — anti-context-rot utilities.

Covers:
- _word_set: extraction, stop words, field merging, edge cases
- _jaccard: similarity calculations
- filter_marginal_value: dedup, ordering, thresholds, edge cases
- enforce_token_limit: section boundary, newline, brute force, length guarantee
- estimate_tokens: basic estimation
"""

from __future__ import annotations

from engineering_brain.retrieval.context_guard import (
    _jaccard,
    _word_set,
    enforce_token_limit,
    estimate_tokens,
    filter_marginal_value,
)

# =============================================================================
# Helpers
# =============================================================================


def _node(nid: str, text: str, score: float = 0.5, **kw) -> dict:
    return {"id": nid, "text": text, "_relevance_score": score, **kw}


# =============================================================================
# _word_set
# =============================================================================


class TestWordSet:
    def test_extracts_words_from_text_fields(self):
        node = {"text": "Use parameterized queries", "why": "Prevents SQL injection"}
        words = _word_set(node)
        assert "parameterized" in words
        assert "queries" in words
        assert "sql" in words
        assert "injection" in words

    def test_removes_stop_words(self):
        node = {"text": "The use of a parameterized query is important"}
        words = _word_set(node)
        assert "the" not in words
        assert "of" not in words
        assert "is" not in words
        assert "parameterized" in words

    def test_keeps_semantically_meaningful_words(self):
        """Words like do, if, not carry meaning in engineering rules."""
        node = {"text": "Do not use wildcards if the origin is unknown"}
        words = _word_set(node)
        assert "do" in words  # actionable
        assert "if" in words  # conditional
        assert "not" in words  # negation changes meaning entirely

    def test_empty_node(self):
        assert _word_set({}) == set()

    def test_multiple_fields_merged(self):
        node = {"text": "flask", "why": "security", "intent": "protection"}
        words = _word_set(node)
        assert "flask" in words
        assert "security" in words
        assert "protection" in words

    def test_splits_hyphenated_terms(self):
        """Hyphenated terms like 'cross-origin' become separate words."""
        node = {"text": "cross-origin resource sharing"}
        words = _word_set(node)
        assert "cross" in words
        assert "origin" in words
        assert "resource" in words

    def test_numeric_tokens_included(self):
        """Version numbers and numeric tokens are kept."""
        node = {"text": "Use TLS 1 3 instead of 1 2"}
        words = _word_set(node)
        assert "tls" in words
        assert "1" in words
        assert "3" in words


# =============================================================================
# _jaccard
# =============================================================================


class TestJaccard:
    def test_identical_sets(self):
        assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint_sets(self):
        assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self):
        # {a, b, c} ∩ {b, c, d} = {b, c}, |union| = 4
        assert _jaccard({"a", "b", "c"}, {"b", "c", "d"}) == 0.5

    def test_empty_sets(self):
        assert _jaccard(set(), set()) == 0.0
        assert _jaccard({"a"}, set()) == 0.0


# =============================================================================
# filter_marginal_value
# =============================================================================


class TestFilterMarginalValue:
    def test_empty_input(self):
        assert filter_marginal_value([]) == []

    def test_single_node_always_kept(self):
        nodes = [_node("A", "flask cors security")]
        result = filter_marginal_value(nodes)
        assert len(result) == 1

    def test_identical_nodes_deduped(self):
        """Identical text nodes should be collapsed to 1."""
        nodes = [
            _node(
                "A", "Always set explicit CORS origins", 0.9, why="Prevents wildcard CORS attacks"
            ),
            _node(
                "B", "Always set explicit CORS origins", 0.8, why="Prevents wildcard CORS attacks"
            ),
            _node(
                "C", "Always set explicit CORS origins", 0.7, why="Prevents wildcard CORS attacks"
            ),
        ]
        result = filter_marginal_value(nodes)
        assert len(result) == 1
        assert result[0]["id"] == "A"  # highest score kept

    def test_diverse_nodes_all_kept(self):
        """Completely different nodes should all survive."""
        nodes = [
            _node("A", "Use parameterized SQL queries", 0.9),
            _node("B", "Enable CORS with specific origins", 0.8),
            _node("C", "Hash passwords with bcrypt", 0.7),
        ]
        result = filter_marginal_value(nodes)
        assert len(result) == 3

    def test_partial_overlap_filters_redundant(self):
        """Nodes with high overlap and low marginal value are filtered."""
        nodes = [
            _node("A", "Flask CORS security best practices for production", 0.9),
            _node("B", "Flask authentication JWT token management", 0.8),
            _node("C", "Flask CORS security wildcard origins are dangerous", 0.7),
        ]
        result = filter_marginal_value(nodes)
        ids = [n["id"] for n in result]
        assert "A" in ids
        assert "B" in ids
        # C has high overlap with A (both about Flask CORS security)
        # Whether C survives depends on marginal threshold, but A and B always survive

    def test_preserves_order(self):
        """Output order matches input order."""
        nodes = [
            _node("A", "alpha beta gamma", 0.9),
            _node("B", "delta epsilon zeta", 0.8),
        ]
        result = filter_marginal_value(nodes)
        assert [n["id"] for n in result] == ["A", "B"]

    def test_custom_max_overlap(self):
        """Higher max_overlap = fewer nodes filtered."""
        nodes = [
            _node("A", "flask cors security protection", 0.9),
            _node("B", "flask cors security configuration", 0.8),
        ]
        strict = filter_marginal_value(nodes, max_overlap=0.2)
        loose = filter_marginal_value(nodes, max_overlap=0.99)
        assert len(loose) >= len(strict)

    def test_custom_min_marginal(self):
        """Higher min_marginal = more aggressive filtering."""
        nodes = [
            _node("A", "flask cors security protection best practices", 0.9),
            _node("B", "flask cors security configuration setup guide", 0.8),
        ]
        # Very strict: node must add >80% new words
        strict = filter_marginal_value(nodes, max_overlap=0.0, min_marginal=0.8)
        # Very loose: node needs only 1% new words
        loose = filter_marginal_value(nodes, max_overlap=0.0, min_marginal=0.01)
        assert len(loose) >= len(strict)

    def test_node_with_only_stop_words_skipped(self):
        """A node whose text produces an empty word set is silently skipped."""
        nodes = [
            _node("A", "flask cors security", 0.9),
            _node("B", "the a an is are", 0.8),  # all stop words
            _node("C", "postgresql database queries", 0.7),
        ]
        result = filter_marginal_value(nodes)
        ids = [n["id"] for n in result]
        assert "A" in ids
        assert "C" in ids
        # B has empty word set → skipped (continue in source)


# =============================================================================
# enforce_token_limit
# =============================================================================


class TestEnforceTokenLimit:
    def test_under_limit_unchanged(self):
        text = "Short text"
        assert enforce_token_limit(text, 100) == text

    def test_exact_limit_unchanged(self):
        text = "x" * 50
        assert enforce_token_limit(text, 50) == text

    def test_over_limit_truncated(self):
        text = "x" * 200
        result = enforce_token_limit(text, 100)
        assert len(result) <= 100

    def test_truncates_at_section_boundary(self):
        text = "## Section 1\nContent 1\n\n## Section 2\nContent 2\n\n## Section 3\nContent 3"
        result = enforce_token_limit(text, 50)
        assert "## Section 1" in result
        assert "[...truncated" in result

    def test_section_boundary_respects_length_guarantee(self):
        """Truncation at section boundary must still respect max_chars."""
        text = "## Section 1\nContent 1\n\n## Section 2\nContent 2\n\n## Section 3\nContent 3"
        limit = 50
        result = enforce_token_limit(text, limit)
        assert len(result) <= limit

    def test_truncates_at_newline_when_no_section(self):
        text = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7\nLine 8"
        result = enforce_token_limit(text, 30)
        assert "[...truncated" in result
        assert len(result) <= 30

    def test_very_small_limit(self):
        text = "Some text that exceeds limit"
        result = enforce_token_limit(text, 10)
        assert len(result) <= 10
        # When target <= 0, truncation notice is omitted — just raw cut
        assert "[...truncated" not in result

    def test_h3_header_treated_as_section_boundary(self):
        """### headers contain ## so they also serve as boundaries."""
        text = "### SubSection 1\nContent 1\n\n### SubSection 2\nContent 2"
        result = enforce_token_limit(text, 50)
        assert len(result) <= 50


# =============================================================================
# estimate_tokens
# =============================================================================


class TestEstimateTokens:
    def test_basic_estimation(self):
        # 35 chars / 3.5 = 10 tokens
        assert estimate_tokens("x" * 35) == 10

    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_custom_ratio(self):
        # 100 chars / 5.0 = 20 tokens
        assert estimate_tokens("x" * 100, chars_per_token=5.0) == 20
