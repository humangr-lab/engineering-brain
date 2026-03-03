"""Active gap identification — the brain knows what it doesn't know.

Analyzes the knowledge graph to find:
1. High-uncertainty nodes (ep_u > 0.7 with few reinforcements)
2. Unsupported rules (L3 with no L4 evidence)
3. Orphan patterns (L2 with no L3 instantiations)
4. Ungrounded principles (L1 with no L0 grounding)
5. Contradicted nodes without resolution
6. Stale nodes not accessed in a long time

Each gap has a severity score and suggested action.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from engineering_brain.adapters.base import GraphAdapter

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeGap:
    """A specific gap in the brain's knowledge."""

    gap_type: str           # "high_uncertainty", "missing_evidence", etc.
    node_id: str | None     # specific node, or None for structural gaps
    description: str
    severity: float         # 0-1, higher = more urgent
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_type": self.gap_type,
            "node_id": self.node_id,
            "description": self.description,
            "severity": round(self.severity, 3),
            "suggested_action": self.suggested_action,
        }


class GapAnalyzer:
    """Identifies what the brain doesn't know and should learn."""

    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def analyze(self) -> list[KnowledgeGap]:
        """Full gap analysis. Returns prioritized list (highest severity first)."""
        gaps: list[KnowledgeGap] = []
        gaps.extend(self._find_high_uncertainty_nodes())
        gaps.extend(self._find_unsupported_rules())
        gaps.extend(self._find_orphan_patterns())
        gaps.extend(self._find_ungrounded_principles())
        gaps.extend(self._find_contradicted_without_resolution())

        # Sort by severity descending
        gaps.sort(key=lambda g: g.severity, reverse=True)

        logger.info("Gap analysis: %d gaps found", len(gaps))
        return gaps

    def summary(self) -> dict[str, int]:
        """Gap counts by type."""
        gaps = self.analyze()
        counts: dict[str, int] = {}
        for g in gaps:
            counts[g.gap_type] = counts.get(g.gap_type, 0) + 1
        return counts

    def _find_high_uncertainty_nodes(self) -> list[KnowledgeGap]:
        """Nodes with ep_u > 0.7 and few reinforcements."""
        gaps: list[KnowledgeGap] = []
        for node in self._graph.get_all_nodes():
            ep_u = node.get("ep_u")
            if ep_u is None:
                continue
            ep_u = float(ep_u)
            if ep_u <= 0.7:
                continue
            reinforcement = int(node.get("reinforcement_count", 0))
            if reinforcement >= 3:
                continue

            node_id = node.get("id", "")
            severity = min(1.0, ep_u * 0.8 + (1.0 if reinforcement == 0 else 0.0) * 0.2)
            gaps.append(KnowledgeGap(
                gap_type="high_uncertainty",
                node_id=node_id,
                description=f"Node {node_id} has uncertainty {ep_u:.2f} with {reinforcement} reinforcements",
                severity=severity,
                suggested_action=f"Find authoritative sources for {node_id}",
            ))
        return gaps

    def _find_unsupported_rules(self) -> list[KnowledgeGap]:
        """L3 rules with zero EVIDENCED_BY edges from L4."""
        gaps: list[KnowledgeGap] = []
        rules = self._graph.query(label="Rule", limit=2000)
        for rule in rules:
            node_id = rule.get("id", "")
            if not node_id:
                continue
            evidence_edges = self._graph.get_edges(
                node_id=node_id, edge_type="EVIDENCED_BY", direction="outgoing"
            )
            if len(evidence_edges) == 0:
                gaps.append(KnowledgeGap(
                    gap_type="missing_evidence",
                    node_id=node_id,
                    description=f"Rule {node_id} has no evidence (EVIDENCED_BY edges)",
                    severity=0.6,
                    suggested_action=f"Add L4 evidence for rule {node_id}",
                ))
        return gaps

    def _find_orphan_patterns(self) -> list[KnowledgeGap]:
        """L2 patterns with no INSTANTIATES edges from L3 rules."""
        gaps: list[KnowledgeGap] = []
        patterns = self._graph.query(label="Pattern", limit=500)
        for pattern in patterns:
            node_id = pattern.get("id", "")
            if not node_id:
                continue
            inst_edges = self._graph.get_edges(
                node_id=node_id, edge_type="INSTANTIATES", direction="incoming"
            )
            if len(inst_edges) == 0:
                gaps.append(KnowledgeGap(
                    gap_type="orphan_pattern",
                    node_id=node_id,
                    description=f"Pattern {node_id} has no instantiating rules",
                    severity=0.5,
                    suggested_action=f"Create L3 rules that instantiate {node_id}",
                ))
        return gaps

    def _find_ungrounded_principles(self) -> list[KnowledgeGap]:
        """L1 principles with no GROUNDS edges from L0 axioms."""
        gaps: list[KnowledgeGap] = []
        principles = self._graph.query(label="Principle", limit=200)
        for principle in principles:
            node_id = principle.get("id", "")
            if not node_id:
                continue
            ground_edges = self._graph.get_edges(
                node_id=node_id, edge_type="GROUNDS", direction="incoming"
            )
            if len(ground_edges) == 0:
                gaps.append(KnowledgeGap(
                    gap_type="ungrounded_principle",
                    node_id=node_id,
                    description=f"Principle {node_id} has no grounding axioms",
                    severity=0.4,
                    suggested_action=f"Link {node_id} to an L0 axiom via GROUNDS",
                ))
        return gaps

    def _find_contradicted_without_resolution(self) -> list[KnowledgeGap]:
        """Nodes in CONFLICTS_WITH but no resolution recorded."""
        gaps: list[KnowledgeGap] = []
        conflict_edges = self._graph.get_edges(edge_type="CONFLICTS_WITH")
        seen: set[str] = set()

        for edge in conflict_edges:
            for nid in (edge["from_id"], edge["to_id"]):
                if nid in seen:
                    continue
                seen.add(nid)
                node = self._graph.get_node(nid)
                if not node:
                    continue
                # If node has no recorded resolution
                if not node.get("contradiction_resolved"):
                    gaps.append(KnowledgeGap(
                        gap_type="unresolved_contradiction",
                        node_id=nid,
                        description=f"Node {nid} has unresolved contradictions",
                        severity=0.7,
                        suggested_action=f"Resolve contradictions for {nid}",
                    ))
        return gaps
