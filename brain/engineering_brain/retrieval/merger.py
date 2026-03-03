"""Result merger for the Engineering Knowledge Brain.

Merges results from multiple sources (graph, vector, cache) into
a single deduplicated, ranked result set. Handles cross-shard
deduplication and score normalization.
"""

from __future__ import annotations

import hashlib
from typing import Any


def merge_results(
    graph_results: list[dict[str, Any]],
    vector_results: list[dict[str, Any]],
    cache_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge results from graph, vector, and cache sources.

    Deduplicates by node ID (keeps highest-scored version).
    Normalizes scores to 0.0-1.0 range.
    """
    merged: dict[str, dict[str, Any]] = {}

    # Process cache results first (highest priority — already scored)
    for node in (cache_results or []):
        nid = _node_id(node)
        if nid:
            node["_source"] = node.get("_source", "cache")
            merged[nid] = node

    # Process graph results
    for node in graph_results:
        nid = _node_id(node)
        if not nid:
            continue
        node["_source"] = "graph"
        existing = merged.get(nid)
        if existing is None:
            merged[nid] = node
        else:
            # Keep the one with higher relevance score, but merge extra fields
            existing_score = existing.get("_relevance_score", 0.0)
            new_score = node.get("_relevance_score", 0.0)
            if new_score > existing_score:
                node["_sources"] = _merge_sources(existing, node)
                merged[nid] = node
            else:
                existing["_sources"] = _merge_sources(existing, node)

    # Process vector results
    for node in vector_results:
        nid = _node_id(node)
        if not nid:
            # Vector results may use metadata.id
            nid = (node.get("metadata") or {}).get("id", "")
        if not nid:
            continue
        # Convert vector score to relevance_score if not present
        if "_relevance_score" not in node:
            node["_relevance_score"] = node.get("score", 0.0)
        node["_source"] = "vector"
        existing = merged.get(nid)
        if existing is None:
            merged[nid] = node
        else:
            existing_score = existing.get("_relevance_score", 0.0)
            new_score = node.get("_relevance_score", 0.0)
            # Boost score when found in multiple sources
            if existing_score > 0 and new_score > 0:
                boosted = min(existing_score + new_score * 0.3, 1.0)
                existing["_relevance_score"] = boosted
                existing["_sources"] = _merge_sources(existing, node)

    return list(merged.values())


def merge_results_rrf(
    graph_results: list[dict[str, Any]],
    vector_results: list[dict[str, Any]],
    k: int = 60,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion merge of graph + vector results.

    RRF score = sum(1 / (k + rank_i)) across all ranking lists.
    Produces a unified candidate list combining keyword and semantic matches.
    """
    scores: dict[str, float] = {}
    node_map: dict[str, dict[str, Any]] = {}

    # Graph results (1-based ranks per standard RRF)
    for rank, node in enumerate(graph_results, start=1):
        nid = _node_id(node)
        if not nid:
            continue
        scores[nid] = scores.get(nid, 0.0) + 1.0 / (k + rank)
        if nid not in node_map:
            node_map[nid] = node

    # Vector results (1-based ranks per standard RRF)
    for rank, node in enumerate(vector_results, start=1):
        nid = _node_id(node)
        if not nid:
            continue
        scores[nid] = scores.get(nid, 0.0) + 1.0 / (k + rank)
        if nid not in node_map:
            node_map[nid] = node
        else:
            # Transfer vector score to existing node
            node_map[nid]["_vector_score"] = node.get("_vector_score", 0.0)

    # Sort by RRF score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [node_map[nid] for nid, _ in ranked if nid in node_map]


def deduplicate_by_content(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate nodes by content similarity (text/statement/name).

    If two nodes have very similar text but different IDs, keep the one
    with the higher score.
    """
    seen_texts: dict[str, dict[str, Any]] = {}
    result: list[dict[str, Any]] = []

    for node in nodes:
        text = _node_text(node).lower().strip()
        text_key = hashlib.md5(text.encode()).hexdigest()

        if text_key in seen_texts:
            existing = seen_texts[text_key]
            if node.get("_relevance_score", 0) > existing.get("_relevance_score", 0):
                # Replace with higher-scored version
                result = [n for n in result if _node_id(n) != _node_id(existing)]
                result.append(node)
                seen_texts[text_key] = node
        else:
            seen_texts[text_key] = node
            result.append(node)

    return result


def _node_id(node: dict[str, Any]) -> str:
    """Extract node ID from various formats."""
    return str(node.get("id", node.get("_id", "")))


def _node_text(node: dict[str, Any]) -> str:
    """Extract the primary text content of a node."""
    return str(
        node.get("text", "")
        or node.get("statement", "")
        or node.get("name", "")
        or node.get("description", "")
    )


def _merge_sources(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Merge source tracking from two nodes."""
    sources: set[str] = set()
    for n in (a, b):
        s = n.get("_source", "")
        if s:
            sources.add(s)
        for s2 in n.get("_sources", []):
            sources.add(s2)
    return sorted(sources)
