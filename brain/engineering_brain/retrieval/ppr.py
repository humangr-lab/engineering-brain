"""Personalized PageRank for multi-hop knowledge retrieval.

HippoRAG-style graph traversal: instead of BFS with fixed hops,
PPR computes a personalized importance distribution from seed nodes,
naturally weighting nearby and well-connected knowledge higher.

Reference: Page, L. et al. (1999). The PageRank Citation Ranking.
"""

from __future__ import annotations

from typing import Any


def personalized_pagerank(
    adjacency: dict[str, list[str]],
    seed_nodes: list[str],
    alpha: float = 0.15,
    iterations: int = 20,
) -> dict[str, float]:
    """Compute Personalized PageRank from seed nodes.

    Args:
        adjacency: node_id -> list of neighbor node_ids (undirected).
        seed_nodes: Starting nodes (uniform teleport distribution).
        alpha: Teleport probability (higher = stay closer to seeds).
        iterations: Power iteration count.

    Returns:
        node_id -> PPR activation score (sums to ~1.0).
    """
    if not seed_nodes or not adjacency:
        return {}

    all_nodes = set(adjacency.keys())
    for neighbors in adjacency.values():
        all_nodes.update(neighbors)

    # Teleport vector: uniform over seed nodes
    teleport: dict[str, float] = {}
    seed_set = set(seed_nodes) & all_nodes
    if not seed_set:
        return {}
    seed_weight = 1.0 / len(seed_set)
    for node in seed_set:
        teleport[node] = seed_weight

    # Initialize scores
    scores: dict[str, float] = {n: 0.0 for n in all_nodes}
    for n, w in teleport.items():
        scores[n] = w

    # Power iteration
    for _ in range(iterations):
        new_scores: dict[str, float] = {n: 0.0 for n in all_nodes}
        for node in all_nodes:
            neighbors = adjacency.get(node, [])
            if not neighbors:
                continue
            share = scores[node] / len(neighbors)
            for neighbor in neighbors:
                if neighbor in new_scores:
                    new_scores[neighbor] += (1 - alpha) * share
        # Add teleport
        for node in all_nodes:
            new_scores[node] += alpha * teleport.get(node, 0.0)
        scores = new_scores

    return scores


def build_adjacency_from_edges(
    edges: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Build undirected adjacency list from graph edges."""
    adj: dict[str, list[str]] = {}
    for edge in edges:
        src = edge.get("from_id", "")
        dst = edge.get("to_id", "")
        if not src or not dst:
            continue
        adj.setdefault(src, []).append(dst)
        adj.setdefault(dst, []).append(src)
    return adj
