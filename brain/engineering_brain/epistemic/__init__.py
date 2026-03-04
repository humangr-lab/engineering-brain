"""Epistemic scoring for the Engineering Knowledge Brain.

Lightweight Subjective Logic implementation (Josang 2016) for
opinion-based quality scoring of knowledge nodes.
"""

from engineering_brain.epistemic.conflict_resolution import (
    ConflictSeverity,
    classify_conflict,
    dempster_conflict,
    murphy_weighted_average,
)
from engineering_brain.epistemic.contradiction import (
    ContradictionDetector,
    ContradictionReport,
)
from engineering_brain.epistemic.edge_opinion import (
    EDGE_TYPE_PRIORS,
    compute_edge_opinion,
    edge_prior,
)
from engineering_brain.epistemic.fusion import cbf, multi_source_cbf
from engineering_brain.epistemic.gap_analysis import GapAnalyzer, KnowledgeGap
from engineering_brain.epistemic.layer_opinions import (
    bootstrap_opinion,
    initial_opinion_for_layer,
)
from engineering_brain.epistemic.learned_trust import BetaPrior, LearnedSourceTrust
from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.provenance import ProvenanceChain, ProvenanceRecord
from engineering_brain.epistemic.source_trust import (
    SOURCE_TRUST_MAP,
    source_to_opinion,
)
from engineering_brain.epistemic.temporal import (
    LAYER_DECAY_PROFILES,
    HawkesDecayEngine,
    get_decay_engine,
)
from engineering_brain.epistemic.trust_propagation import EigenTrustEngine

__all__ = [
    "OpinionTuple",
    "cbf",
    "multi_source_cbf",
    "SOURCE_TRUST_MAP",
    "source_to_opinion",
    "initial_opinion_for_layer",
    "bootstrap_opinion",
    "dempster_conflict",
    "murphy_weighted_average",
    "classify_conflict",
    "ConflictSeverity",
    "HawkesDecayEngine",
    "LAYER_DECAY_PROFILES",
    "get_decay_engine",
    "ProvenanceRecord",
    "ProvenanceChain",
    "edge_prior",
    "compute_edge_opinion",
    "EDGE_TYPE_PRIORS",
    "LearnedSourceTrust",
    "BetaPrior",
    "ContradictionDetector",
    "ContradictionReport",
    "GapAnalyzer",
    "KnowledgeGap",
    "EigenTrustEngine",
]
