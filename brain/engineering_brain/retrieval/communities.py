"""Community detection for the Engineering Knowledge Brain (GraphRAG-lite).

Runs connected-component analysis (or Leiden if available) to discover
knowledge communities — clusters of densely-connected nodes that represent
coherent knowledge areas.

Each community gets an auto-generated summary (from its top-N node texts).
Useful for global queries like "what security patterns exist?" and for
understanding knowledge graph topology.

Algorithm priority:
1. Leiden (if python-igraph + leidenalg installed) — best quality
2. Label propagation (networkx) — good quality, no deps
3. Connected components (pure Python) — always works
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from engineering_brain.adapters.base import GraphAdapter

logger = logging.getLogger(__name__)


@dataclass
class Community:
    """A knowledge community — densely-connected subgraph."""

    id: int
    node_ids: list[str] = field(default_factory=list)
    top_nodes: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    dominant_domain: str = ""
    dominant_technology: str = ""
    size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "size": self.size,
            "summary": self.summary,
            "dominant_domain": self.dominant_domain,
            "dominant_technology": self.dominant_technology,
            "node_ids": self.node_ids[:20],
        }


class CommunityDetector:
    """Detects communities in the knowledge graph."""

    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def detect(self, min_community_size: int = 3) -> list[Community]:
        """Detect communities using the best available algorithm.

        Returns list of Community objects, sorted by size descending.
        """
        adjacency = self._build_undirected_adjacency()
        if not adjacency:
            return []

        # Try Leiden → label propagation → connected components
        communities = self._leiden_communities(adjacency)
        if communities is None:
            communities = self._label_propagation(adjacency)
        if communities is None:
            communities = self._connected_components(adjacency)

        # Filter by minimum size
        communities = [c for c in communities if len(c) >= min_community_size]

        # Build Community objects
        result: list[Community] = []
        for i, node_ids in enumerate(communities):
            community = self._build_community(i, node_ids)
            result.append(community)

        result.sort(key=lambda c: c.size, reverse=True)
        return result

    def _build_undirected_adjacency(self) -> dict[str, set[str]]:
        """Build undirected adjacency list from graph edges."""
        adj: dict[str, set[str]] = {}
        try:
            edges = self._graph.get_edges()
        except Exception:
            return adj

        for edge in edges:
            a = edge.get("from_id", "")
            b = edge.get("to_id", "")
            if not a or not b or a == b:
                continue
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)

        return adj

    def _leiden_communities(
        self, adjacency: dict[str, set[str]],
    ) -> list[list[str]] | None:
        """Try Leiden algorithm via python-igraph + leidenalg."""
        try:
            import igraph as ig
            import leidenalg
        except ImportError:
            return None

        nodes = sorted(adjacency.keys())
        node_idx = {nid: i for i, nid in enumerate(nodes)}

        edges: list[tuple[int, int]] = []
        for src, neighbors in adjacency.items():
            src_i = node_idx[src]
            for dst in neighbors:
                dst_i = node_idx.get(dst)
                if dst_i is not None and src_i < dst_i:
                    edges.append((src_i, dst_i))

        g = ig.Graph(n=len(nodes), edges=edges, directed=False)
        partition = leidenalg.find_partition(g, leidenalg.ModularityVertexPartition)

        communities: dict[int, list[str]] = {}
        for node_i, comm_id in enumerate(partition.membership):
            communities.setdefault(comm_id, []).append(nodes[node_i])

        return list(communities.values())

    def _label_propagation(
        self, adjacency: dict[str, set[str]],
    ) -> list[list[str]] | None:
        """Label propagation community detection (pure Python)."""
        import random

        labels: dict[str, int] = {nid: i for i, nid in enumerate(adjacency)}
        nodes = list(adjacency.keys())

        for _ in range(20):  # Max iterations
            changed = False
            random.shuffle(nodes)
            for node in nodes:
                neighbors = adjacency.get(node, set())
                if not neighbors:
                    continue
                # Count neighbor labels
                label_counts: dict[int, int] = {}
                for nb in neighbors:
                    lb = labels.get(nb, -1)
                    if lb >= 0:
                        label_counts[lb] = label_counts.get(lb, 0) + 1
                if label_counts:
                    max_count = max(label_counts.values())
                    best_labels = [lb for lb, c in label_counts.items() if c == max_count]
                    new_label = min(best_labels)  # Deterministic tie-breaking
                    if new_label != labels[node]:
                        labels[node] = new_label
                        changed = True
            if not changed:
                break

        # Group by label
        communities: dict[int, list[str]] = {}
        for nid, lb in labels.items():
            communities.setdefault(lb, []).append(nid)

        return list(communities.values())

    def _connected_components(
        self, adjacency: dict[str, set[str]],
    ) -> list[list[str]]:
        """Simple connected components (always works, no dependencies)."""
        visited: set[str] = set()
        components: list[list[str]] = []

        for start in adjacency:
            if start in visited:
                continue
            component: list[str] = []
            stack = [start]
            while stack:
                node = stack.pop()
                if node in visited:
                    continue
                visited.add(node)
                component.append(node)
                for neighbor in adjacency.get(node, set()):
                    if neighbor not in visited:
                        stack.append(neighbor)
            if component:
                components.append(component)

        return components

    def _build_community(self, comm_id: int, node_ids: list[str]) -> Community:
        """Build a Community with summary from node texts."""
        top_nodes: list[dict[str, Any]] = []
        domain_counts: dict[str, int] = {}
        tech_counts: dict[str, int] = {}

        for nid in node_ids[:50]:  # Sample up to 50 nodes
            node = self._graph.get_node(nid)
            if not node:
                continue

            # Collect domain/tech stats
            for d in (node.get("domains") or []):
                domain_counts[d] = domain_counts.get(d, 0) + 1
            for t in (node.get("technologies") or node.get("languages") or []):
                tech_counts[t] = tech_counts.get(t, 0) + 1

            text = (
                node.get("text", "")
                or node.get("name", "")
                or node.get("statement", "")
            )
            if text:
                top_nodes.append({"id": nid, "text": text[:100]})

        # Auto-generate summary from top node texts
        summary_parts = [n["text"] for n in top_nodes[:5]]
        summary = " | ".join(summary_parts) if summary_parts else f"Community {comm_id}"

        dominant_domain = max(domain_counts, key=domain_counts.get) if domain_counts else ""
        dominant_tech = max(tech_counts, key=tech_counts.get) if tech_counts else ""

        return Community(
            id=comm_id,
            node_ids=node_ids,
            top_nodes=top_nodes[:10],
            summary=summary[:300],
            dominant_domain=dominant_domain,
            dominant_technology=dominant_tech,
            size=len(node_ids),
        )
