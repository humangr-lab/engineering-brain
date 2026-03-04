"""Tests for bootstrap — computing initial epistemic opinions for all nodes."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.epistemic.bootstrap import _node_layer, bootstrap_all_nodes


class TestNodeLayer:
    def test_axiom_prefix(self):
        assert _node_layer("AX-TYPE-001") == "L0"

    def test_principle_prefix(self):
        assert _node_layer("P-API-CONTRACT") == "L1"

    def test_pattern_prefix(self):
        assert _node_layer("PAT-SEC-AUTH-DECO") == "L2"

    def test_rule_prefix(self):
        assert _node_layer("CR-FLASK-001") == "L3"

    def test_unknown_defaults_l3(self):
        assert _node_layer("UNKNOWN-123") == "L3"


class TestBootstrapAllNodes:
    def _setup_graph_and_cache(self, nodes, cache_entries=None):
        """Helper: create graph with nodes and a temporary cache file."""
        graph = MemoryGraphAdapter()
        for nid, label, data in nodes:
            graph.add_node(label, nid, {"id": nid, **data})

        # Create temp cache
        tmpdir = tempfile.mkdtemp()
        cache = cache_entries or {}
        cache_file = os.path.join(tmpdir, "validation_cache.json")
        with open(cache_file, "w") as f:
            json.dump(cache, f)

        return graph, tmpdir

    def test_bootstrap_assigns_ep_fields(self):
        graph, cache_dir = self._setup_graph_and_cache(
            [
                ("CR-TEST-001", "Rule", {"confidence": 0.5}),
            ]
        )

        stats = bootstrap_all_nodes(graph, cache_dir)
        assert stats["bootstrapped"] == 1

        node = graph.get_node("CR-TEST-001")
        assert node["ep_b"] is not None
        assert node["ep_d"] is not None
        assert node["ep_u"] is not None
        assert node["ep_a"] is not None
        assert abs(node["ep_b"] + node["ep_d"] + node["ep_u"] - 1.0) < 1e-9

    def test_bootstrap_with_sources_reduces_uncertainty(self):
        cache = {
            "v1:CR-TEST-002": {
                "sources": [
                    {"source_type": "official_docs", "verified": True},
                    {"source_type": "package_registry", "verified": True},
                ],
            }
        }
        graph, cache_dir = self._setup_graph_and_cache(
            [("CR-TEST-002", "Rule", {"confidence": 0.5})],
            cache,
        )

        # Also test without sources for comparison
        graph.add_node("Rule", "CR-TEST-003", {"id": "CR-TEST-003", "confidence": 0.5})

        stats = bootstrap_all_nodes(graph, cache_dir)
        assert stats["bootstrapped"] == 2
        assert stats["total_sources_used"] == 2

        with_sources = graph.get_node("CR-TEST-002")
        without_sources = graph.get_node("CR-TEST-003")
        assert with_sources["ep_u"] < without_sources["ep_u"]

    def test_axiom_gets_near_dogmatic(self):
        graph, cache_dir = self._setup_graph_and_cache(
            [
                ("AX-TEST-001", "Axiom", {}),
            ]
        )

        bootstrap_all_nodes(graph, cache_dir)

        node = graph.get_node("AX-TEST-001")
        assert node["ep_b"] >= 0.90
        assert node["ep_u"] <= 0.10

    def test_backward_compat_confidence_set(self):
        graph, cache_dir = self._setup_graph_and_cache(
            [
                ("CR-TEST-004", "Rule", {"confidence": 0.5}),
            ]
        )

        bootstrap_all_nodes(graph, cache_dir)

        node = graph.get_node("CR-TEST-004")
        expected = node["ep_b"] + node["ep_a"] * node["ep_u"]
        assert node["confidence"] == pytest.approx(expected, abs=1e-6)

    def test_empty_graph(self):
        graph, cache_dir = self._setup_graph_and_cache([])
        stats = bootstrap_all_nodes(graph, cache_dir)
        assert stats["bootstrapped"] == 0

    def test_missing_cache_file(self):
        graph = MemoryGraphAdapter()
        graph.add_node("Rule", "CR-X", {"id": "CR-X"})
        stats = bootstrap_all_nodes(graph, "/nonexistent/path")
        # Should still work — just no sources
        assert stats["bootstrapped"] == 1

    def test_multiple_node_types(self):
        graph, cache_dir = self._setup_graph_and_cache(
            [
                ("AX-001", "Axiom", {}),
                ("P-001", "Principle", {}),
                ("PAT-001", "Pattern", {}),
                ("CR-001", "Rule", {}),
            ]
        )

        stats = bootstrap_all_nodes(graph, cache_dir)
        assert stats["bootstrapped"] == 4

        # Verify layer priors are correct
        ax = graph.get_node("AX-001")
        p = graph.get_node("P-001")
        pat = graph.get_node("PAT-001")
        cr = graph.get_node("CR-001")

        # L0 > L1 > L2 > L3 belief
        assert ax["ep_b"] > p["ep_b"] > pat["ep_b"] > cr["ep_b"]
        # L0 < L1 < L2 < L3 uncertainty
        assert ax["ep_u"] < p["ep_u"] < pat["ep_u"] < cr["ep_u"]

    def test_more_sources_yield_lower_uncertainty(self):
        cache = {
            "v1:CR-FEW": {
                "sources": [{"source_type": "official_docs", "verified": True}],
            },
            "v1:CR-MANY": {
                "sources": [
                    {"source_type": "official_docs", "verified": True},
                    {"source_type": "package_registry", "verified": True},
                    {"source_type": "mdn", "verified": True},
                ],
            },
        }
        graph, cache_dir = self._setup_graph_and_cache(
            [
                ("CR-FEW", "Rule", {}),
                ("CR-MANY", "Rule", {}),
            ],
            cache,
        )

        bootstrap_all_nodes(graph, cache_dir)

        few = graph.get_node("CR-FEW")
        many = graph.get_node("CR-MANY")
        assert many["ep_u"] < few["ep_u"]
