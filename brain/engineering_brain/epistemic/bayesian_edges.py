"""Bayesian Edge Weights — Beta distribution learning for edge confidence.

Edges are no longer binary (exist or not). Each edge carries a Beta(alpha, beta)
distribution that updates from usage feedback:
- Positive feedback: alpha += 1 (edge was traversed and helpful)
- Negative feedback: beta += 1 (edge was traversed but unhelpful)
- Confidence = alpha / (alpha + beta) (expected value of Beta)

Edge confidence decays over time (shift mass toward uncertainty) and
propagates through multi-hop paths via product of confidences.

Feature flag: BRAIN_BAYESIAN_EDGES (default OFF)
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Per edge-type half-life profiles (days until confidence halves without reinforcement)
EDGE_DECAY_PROFILES: dict[str, float] = {
    "GROUNDS": 3650.0,           # Axiom->Principle: very stable
    "INFORMS": 1825.0,           # Principle->Pattern: stable
    "INSTANTIATES": 730.0,       # Pattern->Rule: moderate
    "EVIDENCED_BY": 365.0,       # Rule->Finding: faster decay
    "CONFLICTS_WITH": 180.0,     # Contradiction: relatively fast
    "WEAKENS": 180.0,            # Negative feedback: fast
    "STRENGTHENS": 365.0,        # Positive feedback: moderate
    "SUPERSEDES": 365.0,         # Version replacement: moderate
    "RELATES_TO": 548.0,         # General relation: moderate-slow
    "PREREQUISITE": 730.0,       # Dependency: moderate
    "DEEPENS": 730.0,            # Elaboration: moderate
    "ALTERNATIVE": 548.0,        # Alternative: moderate
    "TRIGGERS": 365.0,           # Causal: moderate
    "COMPLEMENTS": 548.0,        # Complementary: moderate
    "VALIDATES": 365.0,          # Validation: moderate
}

DEFAULT_HALF_LIFE = 548.0  # 1.5 years


class BayesianEdgeManager:
    """Manages Bayesian (Beta distribution) edge weights."""

    def __init__(self, graph_adapter: Any = None) -> None:
        self._graph = graph_adapter

    def reinforce(self, edge: dict[str, Any], positive: bool) -> dict[str, Any]:
        """Update Beta distribution for an edge based on feedback.

        Args:
            edge: Edge dict with edge_alpha, edge_beta fields.
            positive: True if traversal was helpful.

        Returns:
            Updated edge dict.
        """
        alpha = float(edge.get("edge_alpha", 1.0))
        beta = float(edge.get("edge_beta", 1.0))

        if positive:
            alpha += 1.0
        else:
            beta += 1.0

        confidence = alpha / (alpha + beta)
        count = int(edge.get("reinforcement_count", 0)) + 1
        now = datetime.now(timezone.utc).isoformat()

        edge["edge_alpha"] = alpha
        edge["edge_beta"] = beta
        edge["edge_confidence"] = round(confidence, 6)
        edge["reinforcement_count"] = count
        edge["last_reinforced"] = now
        return edge

    def decay(self, edge: dict[str, Any], hours_elapsed: float) -> dict[str, Any]:
        """Apply temporal decay to edge confidence.

        Decay shifts mass toward the prior (alpha=1, beta=1),
        representing loss of certainty over time.

        Uses exponential interpolation between current posterior and prior Beta(1,1).
        This is an ad-hoc forgetting mechanism rather than a standard Bayesian
        discounting operator, chosen for simplicity and computational efficiency.
        """
        if hours_elapsed <= 0:
            return edge

        edge_type = edge.get("edge_type", "RELATES_TO")
        half_life_days = EDGE_DECAY_PROFILES.get(edge_type, DEFAULT_HALF_LIFE)
        half_life_hours = half_life_days * 24.0

        # Decay factor: exponential approach to prior
        decay_factor = math.exp(-math.log(2) * hours_elapsed / half_life_hours)

        alpha = float(edge.get("edge_alpha", 1.0))
        beta = float(edge.get("edge_beta", 1.0))

        # Decay alpha and beta toward 1.0 (uninformative prior)
        new_alpha = 1.0 + (alpha - 1.0) * decay_factor
        new_beta = 1.0 + (beta - 1.0) * decay_factor

        # Ensure minimums
        new_alpha = max(new_alpha, 1.0)
        new_beta = max(new_beta, 1.0)

        confidence = new_alpha / (new_alpha + new_beta)

        edge["edge_alpha"] = round(new_alpha, 6)
        edge["edge_beta"] = round(new_beta, 6)
        edge["edge_confidence"] = round(confidence, 6)
        return edge

    def propagate_through(self, path_edges: list[dict[str, Any]]) -> float:
        """Compute chain confidence through a path of edges.

        Chain confidence = product of individual edge confidences.
        Longer paths naturally have lower confidence.
        """
        if not path_edges:
            return 0.0
        confidence = 1.0
        for edge in path_edges:
            ec = float(edge.get("edge_confidence", 0.5))
            confidence *= ec
        return confidence

    def batch_update_from_feedback(
        self,
        feedbacks: list[dict[str, Any]],
    ) -> int:
        """Batch update edges from query outcome feedback.

        Each feedback dict: {from_id, to_id, positive}

        Returns:
            Number of edges updated.
        """
        if self._graph is None:
            return 0

        count = 0
        for fb in feedbacks:
            from_id = fb.get("from_id", "")
            to_id = fb.get("to_id", "")
            positive = fb.get("positive", True)

            if not from_id or not to_id:
                continue

            try:
                edges = self._graph.get_edges(node_id=from_id)
                for edge in edges:
                    if edge.get("to_id") == to_id or edge.get("from_id") == to_id:
                        updated = self.reinforce(edge, positive)
                        # Write back to graph
                        self._graph.add_edge(
                            updated["from_id"],
                            updated["to_id"],
                            updated.get("edge_type", "RELATES_TO"),
                            properties={
                                k: v for k, v in updated.items()
                                if k not in ("from_id", "to_id", "edge_type")
                            },
                        )
                        count += 1
            except Exception:
                continue

        return count

    def get_edge_confidence(self, edge: dict[str, Any]) -> float:
        """Get the current confidence of an edge."""
        alpha = float(edge.get("edge_alpha", 1.0))
        beta = float(edge.get("edge_beta", 1.0))
        return alpha / (alpha + beta)

    def get_edge_uncertainty(self, edge: dict[str, Any]) -> float:
        """Return the standard deviation (sigma) of the edge's Beta distribution.

        Higher values indicate greater uncertainty about the edge weight.
        When alpha+beta is small (few observations), uncertainty is maximal.
        """
        alpha = float(edge.get("edge_alpha", 1.0))
        beta = float(edge.get("edge_beta", 1.0))
        total = alpha + beta
        if total < 2:
            return 1.0
        variance = (alpha * beta) / (total * total * (total + 1))
        return math.sqrt(variance)
