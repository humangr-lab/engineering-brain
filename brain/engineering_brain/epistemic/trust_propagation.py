"""EigenTrust algorithm for graph-based trust propagation.

Computes global trust values by iterating the trust matrix.
Based on EigenTrust (Kamvar et al., 2003) adapted for the
Engineering Brain knowledge graph.

Algorithm:
    1. Define trusted seed nodes (L0 Axioms, L1 Principles)
    2. Compute local trust weights from edge types
    3. Normalize to trust matrix C: c_ij = w_ij / sum_k(w_ik)
    4. Iterate: t^(k+1) = (1-alpha) * C^T * t^(k) + alpha * p
    5. Converge to stationary trust vector t*

Convergence guaranteed by Perron-Frobenius theorem with teleport alpha > 0.
"""

from __future__ import annotations

import logging
from typing import Any

from engineering_brain.adapters.base import GraphAdapter

logger = logging.getLogger(__name__)


# Edge type → trust weight for Engineering Brain relationships
TRUST_WEIGHTS: dict[str, float] = {
    # Hierarchical (strong trust flow)
    "GROUNDS": 1.0,
    "INFORMS": 0.9,
    "INSTANTIATES": 0.8,
    "EVIDENCED_BY": 0.7,
    "DEMONSTRATED_BY": 0.6,
    # Evolution (learning)
    "REINFORCES": 0.8,
    "WEAKENS": -0.3,
    "CONFLICTS_WITH": -0.5,
    "SUPERSEDES": 0.4,
    "VARIANT_OF": 0.3,
    # Cross-layer (semantic)
    "APPLIES_TO": 0.3,
    "IN_DOMAIN": 0.3,
    "USED_IN": 0.3,
    # Source attribution
    "CITES": 0.5,
    "SOURCED_FROM": 0.6,
    "VALIDATED_BY": 0.7,
    # Causal
    "CAUSED_BY": 0.4,
    "PREVENTS": 0.5,
}


class EigenTrustEngine:
    """EigenTrust: t^(k+1) = (1-alpha)*C^T*t^(k) + alpha*p

    Uses power iteration with teleport/restart for guaranteed convergence.
    Supports incremental updates: when a single edge is added/removed,
    does a local 1-hop update instead of full recomputation.
    """

    def __init__(
        self,
        alpha: float = 0.15,
        max_iterations: int = 30,
        tolerance: float = 1e-6,
    ) -> None:
        self.alpha = alpha
        self.max_iterations = max_iterations
        self.tolerance = tolerance
        # Cache last computed scores for incremental updates
        self._cached_scores: dict[str, float] = {}
        self._cache_valid: bool = False

    def compute(self, graph: GraphAdapter) -> dict[str, float]:
        """Compute EigenTrust scores for all nodes.

        Returns:
            Dict of node_id → trust_score in [0, 1].
        """
        adjacency, seeds = self._build_adjacency(graph)

        # Collect all node IDs (from edges AND from graph itself)
        all_nodes: set[str] = set(adjacency.keys())
        for neighbors in adjacency.values():
            for nid, _ in neighbors:
                all_nodes.add(nid)
        # Include nodes that may have no edges
        for node in graph.get_all_nodes():
            nid = node.get("id", "")
            if nid:
                all_nodes.add(nid)

        n = len(all_nodes)
        if n == 0:
            return {}

        node_list = sorted(all_nodes)
        node_idx = {nid: i for i, nid in enumerate(node_list)}

        # Initialize uniform trust
        trust = [1.0 / n] * n

        # Seed distribution (teleport target)
        if seeds:
            p = [0.0] * n
            active_seeds = [s for s in seeds if s in node_idx]
            if active_seeds:
                seed_weight = 1.0 / len(active_seeds)
                for seed in active_seeds:
                    p[node_idx[seed]] = seed_weight
            else:
                p = [1.0 / n] * n
        else:
            p = [1.0 / n] * n

        # Build normalized outgoing trust (sparse)
        out_trust: dict[int, list[tuple[int, float]]] = {}
        for src_id, neighbors in adjacency.items():
            src_idx = node_idx.get(src_id)
            if src_idx is None:
                continue

            local = []
            for dst_id, weight in neighbors:
                dst_idx = node_idx.get(dst_id)
                if dst_idx is not None and weight > 0:  # Negative edges (WEAKENS, CONFLICTS_WITH) excluded — distrust not propagated (design choice)
                    local.append((dst_idx, weight))

            total = sum(w for _, w in local)
            if total > 1e-15:
                out_trust[src_idx] = [(idx, w / total) for idx, w in local]

        # Power iteration
        for iteration in range(self.max_iterations):
            new_trust = [0.0] * n

            for src_idx, neighbors in out_trust.items():
                for dst_idx, c_ij in neighbors:
                    new_trust[dst_idx] += c_ij * trust[src_idx]

            # Teleport: t' = (1-alpha)*t' + alpha*p
            for i in range(n):
                new_trust[i] = (1 - self.alpha) * new_trust[i] + self.alpha * p[i]

            # Normalize
            total = sum(new_trust)
            if total > 1e-15:
                new_trust = [t / total for t in new_trust]

            # Convergence check
            diff = sum(abs(new_trust[i] - trust[i]) for i in range(n))
            trust = new_trust

            if diff < self.tolerance:
                logger.debug("EigenTrust converged at iteration %d", iteration + 1)
                break

        # Normalize to [0, 1] range (preserves relative ordering, not absolute meaning)
        max_trust = max(trust) if trust else 1.0
        if max_trust > 1e-15:
            trust = [max(t / max_trust, 0.01) for t in trust]

        result = {node_list[i]: trust[i] for i in range(n)}
        self._cached_scores = result
        self._cache_valid = True
        return result

    def incremental_update(
        self, graph: GraphAdapter, affected_node_id: str,
    ) -> dict[str, float]:
        """Incremental EigenTrust update after a single edge add/remove.

        Instead of full power iteration, recomputes trust for the affected
        node and its 1-hop neighbors only. Falls back to full recompute
        if cache is empty.

        Returns dict of {node_id: trust_score} for affected nodes.
        """
        if not self._cache_valid or not self._cached_scores:
            return self.compute(graph)

        # Get 1-hop neighborhood from the affected node
        affected: set[str] = {affected_node_id}
        edges = graph.get_edges(node_id=affected_node_id)
        for edge in edges:
            affected.add(edge["from_id"])
            affected.add(edge["to_id"])

        # Recompute scores for affected nodes only using local trust flow
        adjacency, seeds = self._build_adjacency(graph)
        all_scores = dict(self._cached_scores)

        # Seed bias
        seed_set = seeds & affected if seeds else set()
        seed_bias = 1.0 / max(len(seeds), 1) if seeds else 0.0

        for node_id in affected:
            # Incoming trust from neighbors
            incoming_trust = 0.0
            incoming_edges = graph.get_edges(node_id=node_id)
            for edge in incoming_edges:
                src = edge["from_id"]
                if edge["to_id"] != node_id:
                    continue
                weight = TRUST_WEIGHTS.get(edge["edge_type"], 0.3)
                if weight <= 0:
                    continue
                src_score = all_scores.get(src, 0.5)
                # Normalize by source's total outgoing weight
                src_out = adjacency.get(src, [])
                total_out = sum(w for _, w in src_out if w > 0) or 1.0
                incoming_trust += src_score * (weight / total_out)

            # Apply teleport
            is_seed = node_id in seed_set
            new_score = (1 - self.alpha) * incoming_trust + self.alpha * (seed_bias if is_seed else 0.0)

            # Clamp to [0, 1]
            new_score = min(max(new_score, 0.0), 1.0)
            all_scores[node_id] = new_score

        self._cached_scores = all_scores
        return {nid: all_scores[nid] for nid in affected if nid in all_scores}

    def invalidate_cache(self) -> None:
        """Invalidate the cached scores (call on graph structure change)."""
        self._cache_valid = False
        self._cached_scores = {}

    def _build_adjacency(
        self, graph: GraphAdapter
    ) -> tuple[dict[str, list[tuple[str, float]]], set[str]]:
        """Build weighted adjacency and identify seed nodes from graph."""
        adjacency: dict[str, list[tuple[str, float]]] = {}
        seeds: set[str] = set()

        # Get all edges
        all_edges = graph.get_edges()
        for edge in all_edges:
            src = edge["from_id"]
            dst = edge["to_id"]
            edge_type = edge["edge_type"]

            weight = TRUST_WEIGHTS.get(edge_type, 0.3)
            if weight <= 0:
                continue  # Skip negative trust edges for adjacency

            if src not in adjacency:
                adjacency[src] = []
            adjacency[src].append((dst, weight))

        # Identify seeds: L0 Axioms and L1 Principles
        seeds = self._identify_seeds(graph)

        logger.debug("EigenTrust: %d adjacency nodes, %d seeds",
                      len(adjacency), len(seeds))
        return adjacency, seeds

    def _identify_seeds(self, graph: GraphAdapter) -> set[str]:
        """Identify trusted seed nodes: L0 Axioms + L1 Principles."""
        seeds: set[str] = set()

        # L0 Axioms are the most trusted
        axioms = graph.query(label="Axiom", limit=100)
        for ax in axioms:
            nid = ax.get("id", "")
            if nid:
                seeds.add(nid)

        # L1 Principles are secondary seeds
        principles = graph.query(label="Principle", limit=200)
        for pr in principles:
            nid = pr.get("id", "")
            if nid:
                seeds.add(nid)

        return seeds


class IncrementalEigenTrust:
    """Cached EigenTrust with local updates on new edges.

    Instead of full power iteration on every call, caches trust scores
    and does 1-hop local update when a new edge is added.
    """

    def __init__(self, base_engine: EigenTrustEngine | None = None) -> None:
        self._engine = base_engine or EigenTrustEngine()
        self._cached_scores: dict[str, float] = {}
        self._dirty = True

    @property
    def scores(self) -> dict[str, float]:
        return dict(self._cached_scores)

    def full_compute(self, graph: GraphAdapter) -> dict[str, float]:
        """Full recompute — call when graph has changed significantly."""
        self._cached_scores = self._engine.compute(graph)
        self._dirty = False
        return dict(self._cached_scores)

    def local_update(
        self,
        graph: GraphAdapter,
        affected_node_id: str,
    ) -> dict[str, float]:
        """Update trust for a node and its 1-hop neighbors.

        Much cheaper than full recompute: O(degree) instead of O(n * iterations).
        """
        if self._dirty or not self._cached_scores:
            return self.full_compute(graph)

        # Get affected node's neighbors
        edges = graph.get_edges(node_id=affected_node_id)
        affected_ids = {affected_node_id}
        for edge in edges:
            affected_ids.add(edge.get("from_id", ""))
            affected_ids.add(edge.get("to_id", ""))
        affected_ids.discard("")

        # For each affected node, recompute local trust from incoming edges
        for nid in affected_ids:
            incoming = graph.get_edges(node_id=nid)
            if not incoming:
                continue

            weighted_sum = 0.0
            weight_total = 0.0
            for edge in incoming:
                src = edge.get("from_id", "")
                if src == nid:
                    src = edge.get("to_id", "")
                edge_type = edge.get("edge_type", "")
                w = TRUST_WEIGHTS.get(edge_type, 0.3)
                if w <= 0:
                    continue
                src_trust = self._cached_scores.get(src, 0.5)
                weighted_sum += w * src_trust
                weight_total += w

            if weight_total > 1e-15:
                # Blend: 70% local update + 30% old score (damping)
                local_score = weighted_sum / weight_total
                old_score = self._cached_scores.get(nid, 0.5)
                self._cached_scores[nid] = 0.7 * local_score + 0.3 * old_score

        logger.debug("Incremental trust update: %d nodes affected", len(affected_ids))
        return dict(self._cached_scores)

    def mark_dirty(self) -> None:
        """Mark cache as dirty — next call triggers full recompute."""
        self._dirty = True
