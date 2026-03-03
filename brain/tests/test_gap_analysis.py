"""Tests for active gap identification."""

from __future__ import annotations

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.epistemic.gap_analysis import GapAnalyzer, KnowledgeGap


class TestHighUncertaintyNodes:
    def test_detects_high_uncertainty(self):
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001", "ep_u": 0.85, "reinforcement_count": 0})
        g.add_node("Rule", "CR-002", {"id": "CR-002", "ep_u": 0.3, "reinforcement_count": 5})

        analyzer = GapAnalyzer(g)
        gaps = analyzer._find_high_uncertainty_nodes()
        assert len(gaps) == 1
        assert gaps[0].node_id == "CR-001"
        assert gaps[0].gap_type == "high_uncertainty"

    def test_skips_well_reinforced(self):
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001", "ep_u": 0.8, "reinforcement_count": 5})

        analyzer = GapAnalyzer(g)
        gaps = analyzer._find_high_uncertainty_nodes()
        assert len(gaps) == 0

    def test_skips_nodes_without_ep(self):
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001", "confidence": 0.5})

        analyzer = GapAnalyzer(g)
        gaps = analyzer._find_high_uncertainty_nodes()
        assert len(gaps) == 0


class TestUnsupportedRules:
    def test_detects_rules_without_evidence(self):
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001"})
        g.add_node("Rule", "CR-002", {"id": "CR-002"})
        g.add_node("Finding", "F-001", {"id": "F-001"})
        g.add_edge("CR-002", "F-001", "EVIDENCED_BY")

        analyzer = GapAnalyzer(g)
        gaps = analyzer._find_unsupported_rules()
        assert len(gaps) == 1
        assert gaps[0].node_id == "CR-001"
        assert gaps[0].gap_type == "missing_evidence"

    def test_supported_rule_not_flagged(self):
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001"})
        g.add_node("Finding", "F-001", {"id": "F-001"})
        g.add_edge("CR-001", "F-001", "EVIDENCED_BY")

        analyzer = GapAnalyzer(g)
        gaps = analyzer._find_unsupported_rules()
        assert len(gaps) == 0


class TestOrphanPatterns:
    def test_detects_patterns_without_rules(self):
        g = MemoryGraphAdapter()
        g.add_node("Pattern", "PAT-001", {"id": "PAT-001"})

        analyzer = GapAnalyzer(g)
        gaps = analyzer._find_orphan_patterns()
        assert len(gaps) == 1
        assert gaps[0].gap_type == "orphan_pattern"

    def test_linked_pattern_not_flagged(self):
        g = MemoryGraphAdapter()
        g.add_node("Pattern", "PAT-001", {"id": "PAT-001"})
        g.add_node("Rule", "CR-001", {"id": "CR-001"})
        g.add_edge("CR-001", "PAT-001", "INSTANTIATES")

        analyzer = GapAnalyzer(g)
        gaps = analyzer._find_orphan_patterns()
        assert len(gaps) == 0


class TestUngroundedPrinciples:
    def test_detects_ungrounded(self):
        g = MemoryGraphAdapter()
        g.add_node("Principle", "P-001", {"id": "P-001"})

        analyzer = GapAnalyzer(g)
        gaps = analyzer._find_ungrounded_principles()
        assert len(gaps) == 1
        assert gaps[0].gap_type == "ungrounded_principle"

    def test_grounded_not_flagged(self):
        g = MemoryGraphAdapter()
        g.add_node("Principle", "P-001", {"id": "P-001"})
        g.add_node("Axiom", "AX-001", {"id": "AX-001"})
        g.add_edge("AX-001", "P-001", "GROUNDS")

        analyzer = GapAnalyzer(g)
        gaps = analyzer._find_ungrounded_principles()
        assert len(gaps) == 0


class TestContradictedWithoutResolution:
    def test_detects_unresolved(self):
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001"})
        g.add_node("Rule", "CR-002", {"id": "CR-002"})
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")

        analyzer = GapAnalyzer(g)
        gaps = analyzer._find_contradicted_without_resolution()
        assert len(gaps) == 2  # both nodes flagged

    def test_resolved_not_flagged(self):
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001", "contradiction_resolved": True})
        g.add_node("Rule", "CR-002", {"id": "CR-002", "contradiction_resolved": True})
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")

        analyzer = GapAnalyzer(g)
        gaps = analyzer._find_contradicted_without_resolution()
        assert len(gaps) == 0


class TestFullAnalysis:
    def test_analyze_combines_all_types(self):
        g = MemoryGraphAdapter()
        # High uncertainty
        g.add_node("Rule", "CR-001", {"id": "CR-001", "ep_u": 0.9, "reinforcement_count": 0})
        # Orphan pattern
        g.add_node("Pattern", "PAT-001", {"id": "PAT-001"})
        # Ungrounded principle
        g.add_node("Principle", "P-001", {"id": "P-001"})

        analyzer = GapAnalyzer(g)
        gaps = analyzer.analyze()
        types = {g.gap_type for g in gaps}
        assert "high_uncertainty" in types
        assert "orphan_pattern" in types
        assert "ungrounded_principle" in types

    def test_sorted_by_severity(self):
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001", "ep_u": 0.9, "reinforcement_count": 0})
        g.add_node("Pattern", "PAT-001", {"id": "PAT-001"})

        analyzer = GapAnalyzer(g)
        gaps = analyzer.analyze()
        severities = [g.severity for g in gaps]
        assert severities == sorted(severities, reverse=True)

    def test_summary_counts(self):
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001", "ep_u": 0.8, "reinforcement_count": 0})
        g.add_node("Rule", "CR-002", {"id": "CR-002", "ep_u": 0.9, "reinforcement_count": 1})

        analyzer = GapAnalyzer(g)
        summary = analyzer.summary()
        assert summary.get("high_uncertainty", 0) == 2

    def test_empty_graph_no_gaps(self):
        g = MemoryGraphAdapter()
        analyzer = GapAnalyzer(g)
        gaps = analyzer.analyze()
        assert len(gaps) == 0
