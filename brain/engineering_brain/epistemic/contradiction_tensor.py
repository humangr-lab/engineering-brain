"""Contradiction Tensor — first-class contradiction entities in the knowledge graph.

Currently contradictions are detected (K factor in reasoning_engine.py) but
discarded after resolution. This module makes contradictions persistent,
trackable, and resolvable graph entities.

Each ContradictionTensor records:
- The two conflicting nodes
- The Dempster-Shafer conflict factor K
- The type of conflict (logical, empirical, temporal, scope)
- Evidence supporting each side
- Resolution status and strategy

Feature flag: BRAIN_CONTRADICTION_TENSOR (default OFF)
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from engineering_brain.epistemic.conflict_resolution import (
    ConflictSeverity,
    classify_conflict,
    dempster_conflict,
    murphy_weighted_average,
)
from engineering_brain.epistemic.fusion import cbf
from engineering_brain.epistemic.opinion import OpinionTuple

logger = logging.getLogger(__name__)


@dataclass
class ContradictionTensor:
    """A first-class entity representing a contradiction between two nodes."""

    id: str
    node_a_id: str
    node_b_id: str
    conflict_factor: float          # Dempster-Shafer K value
    conflict_type: str = "logical"  # logical, empirical, temporal, scope
    severity: str = "moderate"      # from ConflictSeverity
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolution: str | None = None   # None = unresolved
    resolution_strategy: str | None = None  # cbf, murphy, demotion, scope_split
    resolved_at: datetime | None = None
    evidence_for_a: list[str] = field(default_factory=list)
    evidence_for_b: list[str] = field(default_factory=list)
    opinion_a: dict[str, float] = field(default_factory=dict)
    opinion_b: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "node_a_id": self.node_a_id,
            "node_b_id": self.node_b_id,
            "conflict_factor": round(self.conflict_factor, 4),
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "discovered_at": self.discovered_at.isoformat(),
            "resolution": self.resolution,
            "resolution_strategy": self.resolution_strategy,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "evidence_for_a": self.evidence_for_a,
            "evidence_for_b": self.evidence_for_b,
            "opinion_a": self.opinion_a,
            "opinion_b": self.opinion_b,
            "is_resolved": self.resolution is not None,
        }

    @staticmethod
    def make_id(node_a_id: str, node_b_id: str) -> str:
        """Generate deterministic ID from the two node IDs."""
        pair = "-".join(sorted([node_a_id, node_b_id]))
        h = hashlib.sha256(pair.encode()).hexdigest()[:12]
        return f"CT-{h}"


class ContradictionManager:
    """Manages contradiction tensors as first-class graph entities."""

    def __init__(self) -> None:
        self._tensors: dict[str, ContradictionTensor] = {}

    def detect(
        self,
        node_a: dict[str, Any],
        node_b: dict[str, Any],
        conflict_type: str = "logical",
    ) -> ContradictionTensor | None:
        """Detect contradiction between two nodes using Dempster's K.

        Returns a ContradictionTensor if K > 0.3 (at least LOW conflict),
        or None if no significant contradiction found.
        """
        op_a = self._node_to_opinion(node_a)
        op_b = self._node_to_opinion(node_b)
        if op_a is None or op_b is None:
            return None

        k = dempster_conflict(op_a, op_b)
        severity = classify_conflict(k)

        if severity == ConflictSeverity.NONE:
            return None

        a_id = str(node_a.get("id", ""))
        b_id = str(node_b.get("id", ""))
        ct_id = ContradictionTensor.make_id(a_id, b_id)

        # If already tracked, update K
        if ct_id in self._tensors:
            existing = self._tensors[ct_id]
            existing.conflict_factor = k
            existing.severity = severity.value
            return existing

        tensor = ContradictionTensor(
            id=ct_id,
            node_a_id=a_id,
            node_b_id=b_id,
            conflict_factor=k,
            conflict_type=conflict_type,
            severity=severity.value,
            opinion_a={"b": op_a.b, "d": op_a.d, "u": op_a.u, "a": op_a.a},
            opinion_b={"b": op_b.b, "d": op_b.d, "u": op_b.u, "a": op_b.a},
        )
        self._tensors[ct_id] = tensor
        logger.info("Detected contradiction %s: %s vs %s (K=%.3f, %s)",
                     ct_id, a_id, b_id, k, severity.value)
        return tensor

    def resolve(
        self,
        tensor: ContradictionTensor,
        strategy: str = "auto",
        source_trusts: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Resolve a contradiction using the specified strategy.

        Strategies:
        - auto: Select based on K value (cbf for low, murphy for high)
        - cbf: Cumulative Belief Fusion
        - murphy: Murphy's weighted average
        - demotion: Demote the weaker node to E0
        - scope_split: Both are correct in different scopes (no fusion)
        """
        op_a = OpinionTuple(**tensor.opinion_a) if tensor.opinion_a else OpinionTuple.vacuous()
        op_b = OpinionTuple(**tensor.opinion_b) if tensor.opinion_b else OpinionTuple.vacuous()
        trusts = source_trusts or {}
        trust_a = trusts.get(tensor.node_a_id, 0.5)
        trust_b = trusts.get(tensor.node_b_id, 0.5)

        if strategy == "auto":
            k = tensor.conflict_factor
            if k < 0.3:
                strategy = "cbf"
            elif k < 0.7:
                strategy = "murphy"
            else:
                strategy = "demotion"

        resolved_opinion: OpinionTuple | None = None
        resolution_text = ""

        if strategy == "cbf":
            resolved_opinion = cbf(op_a, op_b)
            resolution_text = "Fused via CBF (low conflict)"

        elif strategy == "murphy":
            resolved_opinion = murphy_weighted_average(
                [op_a, op_b], weights=[trust_a, trust_b]
            )
            resolution_text = "Fused via Murphy's WBF"

        elif strategy == "demotion":
            # Demote the node with lower belief
            if op_a.b >= op_b.b:
                resolution_text = f"Demoted {tensor.node_b_id} (lower belief)"
                resolved_opinion = op_a
            else:
                resolution_text = f"Demoted {tensor.node_a_id} (lower belief)"
                resolved_opinion = op_b

        elif strategy == "scope_split":
            resolution_text = "Scope split — both valid in different contexts"
            resolved_opinion = None

        tensor.resolution = resolution_text
        tensor.resolution_strategy = strategy
        tensor.resolved_at = datetime.now(timezone.utc)

        logger.info("Resolved %s via %s: %s", tensor.id, strategy, resolution_text)

        return {
            "tensor_id": tensor.id,
            "strategy": strategy,
            "resolution": resolution_text,
            "resolved_opinion": {
                "b": resolved_opinion.b,
                "d": resolved_opinion.d,
                "u": resolved_opinion.u,
                "a": resolved_opinion.a,
            } if resolved_opinion else None,
        }

    def get_unresolved(self) -> list[ContradictionTensor]:
        """List all unresolved contradictions."""
        return [t for t in self._tensors.values() if t.resolution is None]

    def get_all(self) -> list[ContradictionTensor]:
        """List all tracked contradictions."""
        return list(self._tensors.values())

    def get_for_node(self, node_id: str) -> list[ContradictionTensor]:
        """Get all contradictions involving a specific node."""
        return [
            t for t in self._tensors.values()
            if t.node_a_id == node_id or t.node_b_id == node_id
        ]

    def add_evidence(
        self,
        tensor_id: str,
        supporting_node: str,
        evidence_node_id: str,
    ) -> bool:
        """Add evidence supporting one side of a contradiction."""
        tensor = self._tensors.get(tensor_id)
        if tensor is None:
            return False
        if supporting_node == tensor.node_a_id:
            if evidence_node_id not in tensor.evidence_for_a:
                tensor.evidence_for_a.append(evidence_node_id)
        elif supporting_node == tensor.node_b_id:
            if evidence_node_id not in tensor.evidence_for_b:
                tensor.evidence_for_b.append(evidence_node_id)
        else:
            return False
        return True

    @property
    def total(self) -> int:
        return len(self._tensors)

    @property
    def unresolved_count(self) -> int:
        return len(self.get_unresolved())

    @staticmethod
    def _node_to_opinion(node: dict[str, Any]) -> OpinionTuple | None:
        """Extract OpinionTuple from node properties."""
        ep_b = node.get("ep_b")
        if ep_b is None:
            return None
        b = float(ep_b)
        d = float(node.get("ep_d", 0.0))
        u = float(node.get("ep_u", max(0.0, 1.0 - b - d)))  # maintain b+d+u=1 invariant
        a = float(node.get("ep_a", 0.5))
        return OpinionTuple(b=b, d=d, u=u, a=a)
