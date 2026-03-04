"""DST Evidence Combiner — adaptive fusion strategy based on conflict level.

Currently CBF fusion is used everywhere. This module adds adaptive strategy
selection based on Dempster's conflict factor K:

    K < 0.3  → CBF (low conflict, standard fusion)
    K < 0.7  → Murphy's weighted average (medium conflict)
    K >= 0.7 → Conservative envelope (high conflict, conservative)

Also supports source-trust-weighted combination using the existing
source_trust.py trust tiers.

Feature flag: BRAIN_DST_EVIDENCE (default OFF)

Reference: Josang, A. (2016). Subjective Logic, Ch. 12.
Reference: Murphy, C.K. (2000). Combining belief functions when evidence conflicts.
Reference: Denoeux, T. (2008). Conjunctive and disjunctive combination of belief functions.
"""

from __future__ import annotations

import logging
from typing import Any

from engineering_brain.epistemic.conflict_resolution import (
    dempster_conflict,
    murphy_weighted_average,
)
from engineering_brain.epistemic.fusion import multi_source_cbf
from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.source_trust import SOURCE_TRUST_MAP

logger = logging.getLogger(__name__)


class DSTEvidenceCombiner:
    """Adaptive evidence combination with strategy selection based on conflict."""

    def __init__(
        self,
        cbf_threshold: float = 0.3,
        murphy_threshold: float = 0.7,
    ) -> None:
        """Initialize with conflict thresholds.

        Args:
            cbf_threshold: K below this uses CBF (default 0.3).
            murphy_threshold: K below this uses Murphy (default 0.7).
                K >= murphy_threshold uses conservative envelope.
        """
        self.cbf_threshold = cbf_threshold
        self.murphy_threshold = murphy_threshold

    def combine(
        self,
        opinions: list[OpinionTuple],
        sources: list[str] | None = None,
    ) -> OpinionTuple:
        """Adaptive combination: auto-selects strategy based on conflict.

        Args:
            opinions: List of opinion tuples from different sources.
            sources: Optional source type names (for trust-weighted combination).

        Returns:
            Fused opinion tuple.
        """
        if not opinions:
            return OpinionTuple.vacuous()
        if len(opinions) == 1:
            return opinions[0]

        # Compute aggregate conflict
        k = self._compute_aggregate_conflict(opinions)

        if k < self.cbf_threshold:
            result = self._cbf_combine(opinions)
            logger.debug("DST: CBF fusion (K=%.3f < %.3f)", k, self.cbf_threshold)
        elif k < self.murphy_threshold:
            weights = self._source_weights(sources) if sources else None
            result = self._murphy_combine(opinions, weights)
            logger.debug("DST: Murphy fusion (K=%.3f < %.3f)", k, self.murphy_threshold)
        else:
            result = self._conservative_envelope(opinions)
            logger.debug("DST: Conservative envelope (K=%.3f >= %.3f)", k, self.murphy_threshold)

        return result

    def combine_with_source_trust(
        self,
        evidence: list[dict[str, Any]],
    ) -> OpinionTuple:
        """Weight opinions by source trust before combining.

        Each evidence dict should have:
        - opinion: OpinionTuple or dict with b,d,u,a
        - source_type: str (key in SOURCE_TRUST_MAP)

        Returns:
            Trust-weighted fused opinion.
        """
        if not evidence:
            return OpinionTuple.vacuous()

        opinions: list[OpinionTuple] = []
        weights: list[float] = []

        for item in evidence:
            op = item.get("opinion")
            if op is None:
                continue
            if isinstance(op, dict):
                op = OpinionTuple(
                    b=float(op.get("b", 0.0)),
                    d=float(op.get("d", 0.0)),
                    u=float(op.get("u", 1.0)),
                    a=float(op.get("a", 0.5)),
                )
            source_type = str(item.get("source_type", ""))
            trust = SOURCE_TRUST_MAP.get(source_type, 0.5)
            opinions.append(op)
            weights.append(trust)

        if not opinions:
            return OpinionTuple.vacuous()

        # Use Murphy with trust weights (handles conflict gracefully)
        return murphy_weighted_average(opinions, weights=weights)

    def get_strategy(self, opinions: list[OpinionTuple]) -> str:
        """Determine which strategy would be used for these opinions."""
        if len(opinions) < 2:
            return "identity"
        k = self._compute_aggregate_conflict(opinions)
        if k < self.cbf_threshold:
            return "cbf"
        if k < self.murphy_threshold:
            return "murphy"
        return "conservative_envelope"

    def _compute_aggregate_conflict(self, opinions: list[OpinionTuple]) -> float:
        """Compute the maximum pairwise conflict among all opinions."""
        max_k = 0.0
        for i in range(len(opinions)):
            for j in range(i + 1, len(opinions)):
                k = dempster_conflict(opinions[i], opinions[j])
                max_k = max(max_k, k)
        return max_k

    @staticmethod
    def _cbf_combine(opinions: list[OpinionTuple]) -> OpinionTuple:
        """Standard CBF fusion for low-conflict evidence."""
        return multi_source_cbf(opinions)

    @staticmethod
    def _murphy_combine(
        opinions: list[OpinionTuple],
        weights: list[float] | None = None,
    ) -> OpinionTuple:
        """Murphy's weighted average for medium-conflict evidence."""
        return murphy_weighted_average(opinions, weights=weights)

    @staticmethod
    def _conservative_envelope(opinions: list[OpinionTuple]) -> OpinionTuple:
        """Conservative envelope strategy — takes min belief, max disbelief.

        Note: This is a heuristic approach, not Denoeux's formal cautious conjunction
        which operates on weight functions (commonality/implicability).
        """
        if not opinions:
            return OpinionTuple.vacuous()

        min_b = min(op.b for op in opinions)
        max_d = max(op.d for op in opinions)
        # Remaining mass goes to uncertainty
        u = max(0.0, 1.0 - min_b - max_d)
        a = sum(op.a for op in opinions) / len(opinions)

        # Renormalize
        total = min_b + max_d + u
        if total > 1e-15 and abs(total - 1.0) > 1e-9:
            min_b /= total
            max_d /= total
            u /= total

        return OpinionTuple(b=min_b, d=max_d, u=u, a=a)

    @staticmethod
    def _source_weights(sources: list[str]) -> list[float]:
        """Convert source type names to trust weights."""
        return [SOURCE_TRUST_MAP.get(s, 0.5) for s in sources]
