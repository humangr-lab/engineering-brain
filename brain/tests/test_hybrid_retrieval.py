"""Tests for hybrid retrieval improvements.

Verifies:
- RRF merge combines graph and vector results
- Vector score blending in scorer
- Domain hierarchy expansion
- Query expansion in context extractor
"""

from __future__ import annotations

import pytest

from engineering_brain.core.config import BrainConfig
from engineering_brain.retrieval import context_extractor
from engineering_brain.retrieval.context_extractor import (
    build_domain_hierarchy,
    expand_domains,
)
from engineering_brain.retrieval.merger import merge_results_rrf
from engineering_brain.retrieval.scorer import score_knowledge


# ---------------------------------------------------------------------------
# RRF Merge
# ---------------------------------------------------------------------------

class TestMergeResultsRRF:
    def test_merges_disjoint_sets(self):
        """Graph-only and vector-only nodes both appear in merged result."""
        graph = [{"id": "A", "text": "graph only"}]
        vector = [{"id": "B", "text": "vector only", "_vector_score": 0.9}]

        merged = merge_results_rrf(graph, vector)
        ids = {n["id"] for n in merged}
        assert ids == {"A", "B"}

    def test_shared_nodes_get_higher_rrf(self):
        """A node appearing in both lists gets a higher RRF score than one-list nodes."""
        graph = [
            {"id": "SHARED", "text": "in both"},
            {"id": "GRAPH_ONLY", "text": "graph only"},
        ]
        vector = [
            {"id": "SHARED", "text": "in both", "_vector_score": 0.8},
            {"id": "VEC_ONLY", "text": "vector only", "_vector_score": 0.7},
        ]

        merged = merge_results_rrf(graph, vector)
        # SHARED should be first (higher RRF from appearing in both lists)
        assert merged[0]["id"] == "SHARED"

    def test_vector_score_transferred(self):
        """_vector_score from vector result is transferred to merged node."""
        graph = [{"id": "A", "text": "test"}]
        vector = [{"id": "A", "text": "test", "_vector_score": 0.85}]

        merged = merge_results_rrf(graph, vector)
        assert merged[0].get("_vector_score") == 0.85

    def test_empty_graph_results(self):
        vector = [{"id": "V1", "_vector_score": 0.9}]
        merged = merge_results_rrf([], vector)
        assert len(merged) == 1

    def test_empty_vector_results(self):
        graph = [{"id": "G1", "text": "test"}]
        merged = merge_results_rrf(graph, [])
        assert len(merged) == 1

    def test_both_empty(self):
        assert merge_results_rrf([], []) == []

    def test_preserves_ordering(self):
        """Higher-ranked items in both lists get higher RRF scores."""
        graph = [
            {"id": "A"},
            {"id": "B"},
            {"id": "C"},
        ]
        vector = [
            {"id": "A", "_vector_score": 0.9},
            {"id": "B", "_vector_score": 0.8},
            {"id": "C", "_vector_score": 0.7},
        ]

        merged = merge_results_rrf(graph, vector)
        ids = [n["id"] for n in merged]
        assert ids == ["A", "B", "C"]

    def test_nodes_without_id_skipped(self):
        graph = [{"text": "no id"}, {"id": "A"}]
        vector = [{"text": "no id"}, {"id": "B", "_vector_score": 0.8}]
        merged = merge_results_rrf(graph, vector)
        ids = {n["id"] for n in merged}
        assert ids == {"A", "B"}


# ---------------------------------------------------------------------------
# Vector score in scorer
# ---------------------------------------------------------------------------

class TestVectorScoreSignal:
    def test_vector_score_boosts_relevance(self):
        """A node with high _vector_score should score higher than without."""
        base_node = {
            "id": "CR-001",
            "text": "Validate CORS",
            "technologies": ["flask"],
            "domains": ["security"],
            "severity": "high",
            "reinforcement_count": 5,
            "confidence": 0.7,
        }

        cfg = BrainConfig()
        cfg.vector_score_weight = 0.15

        score_without = score_knowledge(
            base_node, ["flask"], ["security"], config=cfg,
        )
        score_with = score_knowledge(
            {**base_node, "_vector_score": 0.95}, ["flask"], ["security"], config=cfg,
        )

        assert score_with > score_without

    def test_no_vector_score_unchanged(self):
        """Without _vector_score, scorer behaves identically to before."""
        node = {
            "id": "CR-002",
            "text": "Test rule",
            "technologies": ["python"],
            "domains": ["testing"],
            "severity": "medium",
        }
        cfg = BrainConfig()
        cfg.vector_score_weight = 0.15

        s1 = score_knowledge(node, ["python"], ["testing"], config=cfg)
        s2 = score_knowledge({**node, "_vector_score": 0.0}, ["python"], ["testing"], config=cfg)
        assert s1 == pytest.approx(s2)


# ---------------------------------------------------------------------------
# Domain expansion
# ---------------------------------------------------------------------------

class TestDomainExpansion:
    def test_build_hierarchy(self):
        build_domain_hierarchy()
        hierarchy = context_extractor._DOMAIN_HIERARCHY
        assert len(hierarchy) > 0
        # "security" should have children
        assert "security" in hierarchy
        assert len(hierarchy["security"]) > 0

    def test_expand_domains_adds_children(self):
        build_domain_hierarchy()
        expanded = expand_domains(["security"])
        # Should include "security" plus sub-domains like "auth", "cors", etc.
        assert "security" in expanded
        assert len(expanded) > 1

    def test_expand_domains_no_duplicates(self):
        build_domain_hierarchy()
        expanded = expand_domains(["security"])
        # No duplicates in the expanded result
        assert len(expanded) == len(set(expanded))

    def test_expand_unknown_domain_passthrough(self):
        build_domain_hierarchy()
        expanded = expand_domains(["unknown_domain_xyz"])
        assert expanded == ["unknown_domain_xyz"]

    def test_expand_empty(self):
        assert expand_domains([]) == []

    def test_additive_only(self):
        """Expansion never removes original domains."""
        build_domain_hierarchy()
        original = ["api", "security"]
        expanded = expand_domains(original)
        for d in original:
            assert d in expanded
