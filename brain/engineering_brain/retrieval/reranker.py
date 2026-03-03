"""Cross-encoder reranking for the Engineering Knowledge Brain.

Optionally reranks top-K results using a cross-encoder model
(e.g., Voyage rerank-2) for improved precision.

Controlled by BRAIN_RERANKER_ENABLED env var (default: false).
Cost: ~$0.001/query with Voyage rerank-2.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def rerank_results(
    nodes: list[dict[str, Any]],
    query_text: str,
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Rerank scored nodes using a cross-encoder model.

    Falls back to original order if reranking is unavailable.
    """
    if not nodes or not query_text:
        return nodes

    # Try Voyage rerank API
    try:
        return _voyage_rerank(nodes, query_text, top_k)
    except Exception as e:
        logger.debug("Voyage rerank unavailable: %s", e)

    # Fallback: return original scored order
    return nodes[:top_k]


def _voyage_rerank(
    nodes: list[dict[str, Any]],
    query_text: str,
    top_k: int,
) -> list[dict[str, Any]]:
    """Rerank using Voyage AI rerank-2 API."""
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        raise ValueError("VOYAGE_API_KEY not set")

    import voyageai  # type: ignore[import-untyped]

    client = voyageai.Client(api_key=api_key)

    # Build document texts for reranking
    documents: list[str] = []
    for node in nodes:
        text = node.get("text") or node.get("name") or node.get("statement", "")
        why = node.get("why", "")
        documents.append(f"{text} {why}".strip())

    reranking = client.rerank(
        query=query_text,
        documents=documents,
        model="rerank-2",
        top_k=min(top_k, len(documents)),
    )

    # Rebuild nodes in reranked order
    reranked: list[dict[str, Any]] = []
    for result in reranking.results:
        idx = result.index
        node = {**nodes[idx]}
        node["_rerank_score"] = result.relevance_score
        reranked.append(node)

    return reranked
