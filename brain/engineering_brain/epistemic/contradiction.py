"""Contradiction detection and resolution in the knowledge graph.

Scans CONFLICTS_WITH edges and measures disagreement via Dempster's
conflict factor K. Resolves contradictions using CBF (low K) or
Murphy's weighted averaging (high K).

Integration:
    - Uses CONFLICTS_WITH edges from schema.py EdgeType
    - Injects disbelief (d > 0) into contradicted nodes
    - Reports enable human review of extreme contradictions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from engineering_brain.adapters.base import GraphAdapter
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
class ContradictionReport:
    """Report from contradiction detection between two nodes."""

    node_a_id: str
    node_b_id: str
    opinion_a: OpinionTuple
    opinion_b: OpinionTuple
    conflict_k: float
    severity: ConflictSeverity
    resolved_opinion: OpinionTuple | None = None
    resolution_method: str = ""

    @property
    def is_contradicted(self) -> bool:
        return self.severity in (ConflictSeverity.HIGH, ConflictSeverity.EXTREME)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_a_id": self.node_a_id,
            "node_b_id": self.node_b_id,
            "conflict_k": round(self.conflict_k, 4),
            "severity": self.severity.value,
            "resolution_method": self.resolution_method,
        }


class ContradictionDetector:
    """Detects and resolves contradictions between knowledge nodes."""

    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def detect_all(self) -> list[ContradictionReport]:
        """Scan all CONFLICTS_WITH edges and compute K for each pair."""
        edges = self._graph.get_edges(edge_type="CONFLICTS_WITH")
        reports: list[ContradictionReport] = []
        seen: set[tuple[str, str]] = set()

        for edge in edges:
            a_id = edge["from_id"]
            b_id = edge["to_id"]

            # Avoid duplicates (A↔B = B↔A)
            pair = tuple(sorted([a_id, b_id]))
            if pair in seen:
                continue
            seen.add(pair)

            node_a = self._graph.get_node(a_id)
            node_b = self._graph.get_node(b_id)
            if not node_a or not node_b:
                continue

            op_a = self._node_to_opinion(node_a)
            op_b = self._node_to_opinion(node_b)
            if op_a is None or op_b is None:
                continue

            k = dempster_conflict(op_a, op_b)
            severity = classify_conflict(k)

            if severity != ConflictSeverity.NONE:
                reports.append(
                    ContradictionReport(
                        node_a_id=a_id,
                        node_b_id=b_id,
                        opinion_a=op_a,
                        opinion_b=op_b,
                        conflict_k=k,
                        severity=severity,
                    )
                )

        logger.info(
            "Detected %d contradictions across %d CONFLICTS_WITH edges", len(reports), len(edges)
        )
        return reports

    def detect_for_node(self, node_id: str) -> list[ContradictionReport]:
        """Find contradictions involving a specific node."""
        edges = self._graph.get_edges(node_id=node_id, edge_type="CONFLICTS_WITH")
        reports: list[ContradictionReport] = []

        node = self._graph.get_node(node_id)
        if not node:
            return reports

        op_self = self._node_to_opinion(node)
        if op_self is None:
            return reports

        for edge in edges:
            other_id = edge["to_id"] if edge["from_id"] == node_id else edge["from_id"]
            other_node = self._graph.get_node(other_id)
            if not other_node:
                continue

            op_other = self._node_to_opinion(other_node)
            if op_other is None:
                continue

            k = dempster_conflict(op_self, op_other)
            severity = classify_conflict(k)

            if severity != ConflictSeverity.NONE:
                reports.append(
                    ContradictionReport(
                        node_a_id=node_id,
                        node_b_id=other_id,
                        opinion_a=op_self,
                        opinion_b=op_other,
                        conflict_k=k,
                        severity=severity,
                    )
                )

        return reports

    def resolve(
        self,
        report: ContradictionReport,
        source_trusts: dict[str, float] | None = None,
    ) -> OpinionTuple:
        """Resolve a contradiction based on severity.

        LOW/MODERATE → CBF (mild conflict handled by fusion)
        HIGH/EXTREME → Murphy's WBF with trust weights
        """
        trusts = source_trusts or {}
        trust_a = trusts.get(report.node_a_id, 0.5)
        trust_b = trusts.get(report.node_b_id, 0.5)

        if report.severity in (ConflictSeverity.NONE, ConflictSeverity.LOW):
            resolved = cbf(report.opinion_a, report.opinion_b)
            report.resolution_method = "cbf"

        elif report.severity == ConflictSeverity.MODERATE:
            resolved = murphy_weighted_average(
                [report.opinion_a, report.opinion_b],
                weights=[trust_a, trust_b],
            )
            report.resolution_method = "murphy_wbf"

        else:  # HIGH or EXTREME
            resolved = murphy_weighted_average(
                [report.opinion_a, report.opinion_b],
                weights=[trust_a**2, trust_b**2],
            )
            # EXTREME: inject additional uncertainty
            if report.severity == ConflictSeverity.EXTREME:
                penalty = 0.2
                new_b = resolved.b * (1 - penalty)
                new_d = resolved.d * (1 - penalty)
                new_u = 1.0 - new_b - new_d
                resolved = OpinionTuple(b=new_b, d=new_d, u=new_u, a=resolved.a)
            report.resolution_method = "murphy_trust_squared"

        report.resolved_opinion = resolved
        return resolved

    def inject_disbelief(
        self, node_id: str, reports: list[ContradictionReport]
    ) -> OpinionTuple | None:
        """Inject disbelief into a node based on its contradiction reports.

        For each contradiction, the conflicting node's belief becomes
        disbelief evidence against this node, weighted by K.
        """
        node = self._graph.get_node(node_id)
        if not node:
            return None

        op = self._node_to_opinion(node)
        if op is None:
            return None

        total_disbelief_injection = 0.0
        for report in reports:
            other_op = report.opinion_b if report.node_a_id == node_id else report.opinion_a
            # Inject disbelief proportional to K * other's belief
            total_disbelief_injection += report.conflict_k * other_op.b * 0.3

        if total_disbelief_injection < 1e-9:
            return op

        # Move mass from belief to disbelief
        d_inject = min(total_disbelief_injection, op.b * 0.5)  # cap at half belief
        new_b = op.b - d_inject
        new_d = op.d + d_inject
        new_u = op.u

        # Renormalize
        total = new_b + new_d + new_u
        if total > 1e-15 and abs(total - 1.0) > 1e-9:
            new_b /= total
            new_d /= total
            new_u /= total

        return OpinionTuple(b=new_b, d=new_d, u=new_u, a=op.a)

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
