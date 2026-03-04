"""Layer-aware initial opinions for the Engineering Brain.

Each cortical layer has a stability score that maps to an initial
opinion prior. Deeper layers (L0 Axioms) have near-dogmatic belief;
surface layers (L5 Context) are nearly vacuous.
"""

from __future__ import annotations

from typing import Any

from engineering_brain.core.schema import Layer
from engineering_brain.epistemic.fusion import multi_source_cbf
from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.source_trust import source_to_opinion

# Layer -> initial opinion prior
_LAYER_PRIORS: dict[str, OpinionTuple] = {
    "L0": OpinionTuple(b=0.95, d=0.0, u=0.05, a=0.9),  # near-dogmatic
    "L1": OpinionTuple(b=0.80, d=0.0, u=0.20, a=0.7),  # high confidence
    "L2": OpinionTuple(b=0.55, d=0.0, u=0.45, a=0.5),  # moderate
    "L3": OpinionTuple(b=0.30, d=0.0, u=0.70, a=0.5),  # uncertain
    "L4": OpinionTuple(b=0.15, d=0.0, u=0.85, a=0.5),  # low
    "L5": OpinionTuple(b=0.05, d=0.0, u=0.95, a=0.5),  # ephemeral
}


def initial_opinion_for_layer(layer: Layer | str) -> OpinionTuple:
    """Get the initial opinion prior for a cortical layer."""
    key = layer.value if hasattr(layer, "value") else str(layer)
    return _LAYER_PRIORS.get(key, _LAYER_PRIORS["L3"])


def bootstrap_opinion(layer: Layer | str, sources: list[Any]) -> OpinionTuple:
    """Compute initial opinion from layer prior + source evidence.

    If sources exist, CBF-fuses the layer prior with each source's
    opinion. If no sources, returns the layer prior alone.
    """
    prior = initial_opinion_for_layer(layer)

    if not sources:
        return prior

    source_opinions = [source_to_opinion(s) for s in sources]
    # Fuse prior with all source opinions via CBF
    return multi_source_cbf([prior] + source_opinions)
