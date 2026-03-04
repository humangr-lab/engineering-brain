"""Anti-context-rot utilities for the Engineering Knowledge Brain.

Prevents knowledge overload by filtering low-marginal-value nodes
and enforcing hard token limits on assembled output.

Two mechanisms:
1. Marginal value filter: Jaccard word-overlap dedup — drops nodes that
   add less than 15% new information vs already-included nodes.
2. Token limit enforcer: hard ceiling on assembled text length.
"""

from __future__ import annotations

import re
from typing import Any


def _word_set(node: dict[str, Any]) -> set[str]:
    """Extract a word set from a node's primary text fields."""
    parts: list[str] = []
    for key in (
        "text",
        "name",
        "statement",
        "description",
        "why",
        "how_to_do_right",
        "how_to_apply",
        "intent",
    ):
        val = node.get(key, "")
        if val:
            parts.append(str(val))
    text = " ".join(parts).lower()
    # Strip punctuation, split on whitespace
    words = set(re.findall(r"[a-z0-9]+", text))
    # Remove ultra-common stop words that inflate overlap
    # Only remove truly content-free words. Keep semantically meaningful ones
    # like "when", "how", "why", "then", "because" — these matter in rules.
    words -= {
        "the",
        "a",
        "an",
        "is",
        "are",
        "to",
        "in",
        "of",
        "and",
        "or",
        "for",
        "it",
        "on",
        "be",
        "as",
        "at",
        "by",
        "no",
        "but",
        "from",
        "with",
        "this",
        "that",
        "you",
        "your",
    }
    return words


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two word sets."""
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


def filter_marginal_value(
    scored_nodes: list[dict[str, Any]],
    min_marginal: float = 0.15,
    max_overlap: float = 0.65,
) -> list[dict[str, Any]]:
    """Remove nodes whose marginal information is below threshold.

    Walks nodes in score order (highest first). For each candidate,
    computes Jaccard overlap with the UNION of already-accepted nodes.
    If overlap exceeds ``max_overlap`` AND the candidate adds fewer
    than ``min_marginal`` fraction of new words, it is excluded.

    This preserves the highest-scored nodes and eliminates redundant
    lower-scored duplicates — e.g., 5 CORS rules that all say
    "set specific origins" collapse to the 1-2 best-supported.

    Parameters
    ----------
    scored_nodes:
        Nodes sorted by ``_relevance_score`` descending.
    min_marginal:
        Minimum fraction of new words a node must contribute.
        Default 0.15 = at least 15% of the node's words must be novel.
    max_overlap:
        Jaccard threshold above which marginal check triggers.
        Default 0.65 = only check nodes that are >65% similar to accepted pool.

    Returns
    -------
    Filtered list preserving original order.
    """
    if not scored_nodes:
        return []

    accepted: list[dict[str, Any]] = []
    accepted_words: set[str] = set()

    for node in scored_nodes:
        node_words = _word_set(node)

        # Always accept if we have no accepted nodes yet
        if not accepted_words:
            accepted.append(node)
            accepted_words |= node_words
            continue

        # Compute overlap with accepted pool
        overlap = _jaccard(node_words, accepted_words)

        if overlap > max_overlap:
            # Check marginal contribution: how many NEW words does this node add?
            new_words = node_words - accepted_words
            if not node_words:
                continue
            marginal_ratio = len(new_words) / len(node_words)
            if marginal_ratio < min_marginal:
                # Node is redundant — skip
                continue

        accepted.append(node)
        accepted_words |= node_words

    return accepted


def enforce_token_limit(
    text: str,
    max_chars: int,
) -> str:
    """Hard ceiling on assembled text length.

    If ``text`` exceeds ``max_chars``, truncates at the last complete
    markdown section boundary (``##`` or ``###``) that fits, and appends
    a truncation notice.

    Parameters
    ----------
    text:
        The assembled markdown text.
    max_chars:
        Maximum allowed characters.

    Returns
    -------
    Text guaranteed to be ≤ max_chars characters.
    """
    if len(text) <= max_chars:
        return text

    # Try to cut at a section boundary
    truncation_notice = "\n\n[...truncated to budget]"
    target = max_chars - len(truncation_notice)

    if target <= 0:
        return text[:max_chars]

    # Find last section header (## or ###) before target
    candidate = text[:target]
    last_section = candidate.rfind("\n##")
    if last_section > target * 0.3:
        # Cut at section boundary (keep at least 30% of content)
        return candidate[:last_section].rstrip() + truncation_notice

    # No good section boundary — cut at last newline
    last_nl = candidate.rfind("\n")
    if last_nl > target * 0.5:
        return candidate[:last_nl].rstrip() + truncation_notice

    # Brute force cut
    return candidate.rstrip() + truncation_notice


def estimate_tokens(text: str, chars_per_token: float = 3.5) -> int:
    """Rough token estimate from character count."""
    return int(len(text) / chars_per_token)
