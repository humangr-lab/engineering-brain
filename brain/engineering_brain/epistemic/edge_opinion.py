"""Epistemic opinions on graph edges (relationships).

Not just nodes have opinions — the relationships between them
also carry epistemic weight. A GROUNDS edge from an L0 Axiom
is near-dogmatic; a CONFLICTS_WITH edge carries disbelief.

Edge opinions are computed from:
1. Edge type prior (structural confidence in the relationship)
2. Source node opinion (unreliable source → less certain edge)
3. Target node opinion (modulates relevance)
"""

from __future__ import annotations

from engineering_brain.epistemic.opinion import OpinionTuple

# Edge type → initial opinion prior
EDGE_TYPE_PRIORS: dict[str, OpinionTuple] = {
    # Hierarchical (strong trust flow)
    "GROUNDS": OpinionTuple(b=0.95, d=0.0, u=0.05, a=0.9),
    "INFORMS": OpinionTuple(b=0.85, d=0.0, u=0.15, a=0.7),
    "INSTANTIATES": OpinionTuple(b=0.75, d=0.0, u=0.25, a=0.6),
    "EVIDENCED_BY": OpinionTuple(b=0.70, d=0.0, u=0.30, a=0.5),
    "DEMONSTRATED_BY": OpinionTuple(b=0.65, d=0.0, u=0.35, a=0.5),
    # Evolution (learning)
    "REINFORCES": OpinionTuple(b=0.70, d=0.0, u=0.30, a=0.5),
    "WEAKENS": OpinionTuple(b=0.0, d=0.50, u=0.50, a=0.5),
    "CONFLICTS_WITH": OpinionTuple(b=0.0, d=0.70, u=0.30, a=0.5),
    "SUPERSEDES": OpinionTuple(b=0.60, d=0.10, u=0.30, a=0.5),
    "VARIANT_OF": OpinionTuple(b=0.50, d=0.0, u=0.50, a=0.5),
    # Cross-layer (semantic)
    "APPLIES_TO": OpinionTuple(b=0.60, d=0.0, u=0.40, a=0.5),
    "IN_DOMAIN": OpinionTuple(b=0.60, d=0.0, u=0.40, a=0.5),
    "USED_IN": OpinionTuple(b=0.55, d=0.0, u=0.45, a=0.5),
    # Source attribution
    "CITES": OpinionTuple(b=0.65, d=0.0, u=0.35, a=0.5),
    "SOURCED_FROM": OpinionTuple(b=0.70, d=0.0, u=0.30, a=0.5),
    "VALIDATED_BY": OpinionTuple(b=0.75, d=0.0, u=0.25, a=0.6),
    # Causal
    "CAUSED_BY": OpinionTuple(b=0.55, d=0.0, u=0.45, a=0.5),
    "PREVENTS": OpinionTuple(b=0.60, d=0.0, u=0.40, a=0.5),
}

# Default for unknown edge types
_DEFAULT_EDGE_PRIOR = OpinionTuple(b=0.50, d=0.0, u=0.50, a=0.5)


def edge_prior(edge_type: str) -> OpinionTuple:
    """Get the prior opinion for an edge type."""
    return EDGE_TYPE_PRIORS.get(edge_type, _DEFAULT_EDGE_PRIOR)


def compute_edge_opinion(
    edge_type: str,
    source_opinion: OpinionTuple,
    target_opinion: OpinionTuple,
) -> OpinionTuple:
    """Compute edge opinion modulated by endpoint opinions.

    Logic:
    - Start with edge type prior
    - If source has low evidence strength, inject uncertainty into edge
    - Edge opinion = prior modulated by source's reliability

    The source's evidence_strength (1-u) modulates how much we trust
    the relationship. Unreliable source → uncertain edge.
    """
    prior = edge_prior(edge_type)
    source_strength = source_opinion.evidence_strength  # 1 - u

    # Modulate prior by source reliability
    # If source is uncertain, edge inherits some of that uncertainty
    mod_b = prior.b * source_strength
    mod_d = prior.d * source_strength
    mod_u = 1.0 - mod_b - mod_d

    # Clamp
    mod_u = max(0.0, min(1.0, mod_u))
    mod_b = max(0.0, min(1.0 - mod_u, mod_b))
    mod_d = max(0.0, 1.0 - mod_b - mod_u)

    return OpinionTuple(b=mod_b, d=mod_d, u=mod_u, a=prior.a)
