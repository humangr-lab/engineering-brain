"""Multi-hop graph expansion for knowledge retrieval.

After initial scoring, follows graph edges from top results to discover
related knowledge across layers:
- Rule -> (INSTANTIATES <-) Pattern  (what pattern does this instantiate?)
- Rule -> (EVIDENCED_BY ->) Finding  (what evidence supports this?)
- Pattern -> (INFORMS <-) Principle  (what principle guides this?)
- Any -> (CONFLICTS_WITH) Any        (what contradicts this?)

Properties:
- Config-gated (BRAIN_GRAPH_EXPANSION_ENABLED)
- Discount factor prevents over-boosting expanded results
- Graceful degradation: returns [] on any failure
"""

from __future__ import annotations

import logging
from typing import Any

from engineering_brain.adapters.base import GraphAdapter

logger = logging.getLogger(__name__)

# Expansion edges and their traversal direction
_EXPANSION_EDGES: list[tuple[str, str]] = [
    ("INSTANTIATES", "incoming"),   # Pattern -> Rule: follow backward to find pattern
    ("INFORMS", "incoming"),        # Principle -> Pattern: follow backward
    ("EVIDENCED_BY", "outgoing"),   # Rule -> Finding: follow forward
    ("GROUNDS", "incoming"),        # Axiom -> Principle: follow backward
]


def expand_top_results(
    graph: GraphAdapter,
    scored_nodes: list[dict[str, Any]],
    max_expand: int = 5,
    max_hops: int = 1,
    discount: float = 0.4,
) -> list[dict[str, Any]]:
    """Expand top scored nodes by following knowledge hierarchy edges.

    Returns NEW nodes not already in scored_nodes, tagged with:
    - _expanded_from: ID of the source node
    - _expansion_edge: edge type followed
    - _expansion_discount: discount factor for scoring

    Args:
        graph: Graph adapter for traversal
        scored_nodes: Already-scored result nodes
        max_expand: How many top results to expand from
        max_hops: Maximum traversal depth per edge type
        discount: Score discount for expanded results (0.0-1.0)
    """
    existing_ids = {n.get("id", "") for n in scored_nodes}
    expanded: dict[str, dict[str, Any]] = {}

    for node in scored_nodes[:max_expand]:
        node_id = node.get("id", "")
        if not node_id:
            continue

        for edge_type, direction in _EXPANSION_EDGES:
            try:
                neighbors = graph.traverse(
                    start_id=node_id,
                    edge_type=edge_type,
                    direction=direction,
                    max_depth=max_hops,
                    limit=3,
                )
            except Exception:
                continue

            for neighbor in neighbors:
                nid = neighbor.get("id", "")
                if not nid or nid in existing_ids or nid in expanded:
                    continue
                if neighbor.get("deprecated"):
                    continue
                # Tag with expansion metadata
                neighbor["_expanded_from"] = node_id
                neighbor["_expansion_edge"] = edge_type
                neighbor["_expansion_discount"] = discount
                neighbor["_layer"] = _infer_layer(neighbor)
                expanded[nid] = neighbor

    return list(expanded.values())


def _infer_layer(node: dict[str, Any]) -> str:
    """Infer layer key from node ID prefix or label."""
    nid = node.get("id", "")
    if nid.startswith("AX-"):
        return "L1"  # Axioms displayed with principles
    if nid.startswith("P-"):
        return "L1"
    if nid.startswith("PAT-") or nid.startswith("CPAT-"):
        return "L2"
    label = node.get("_label", "")
    if label == "Finding":
        return "L4"
    if label == "Principle":
        return "L1"
    if label == "Pattern":
        return "L2"
    return "L3"
