"""Tests for graph adapter get_edges() method."""

from __future__ import annotations

from engineering_brain.adapters.memory import MemoryGraphAdapter


class TestGetEdges:
    def _setup_graph(self):
        g = MemoryGraphAdapter()
        g.add_node("Rule", "CR-001", {"id": "CR-001"})
        g.add_node("Rule", "CR-002", {"id": "CR-002"})
        g.add_node("Rule", "CR-003", {"id": "CR-003"})
        g.add_node("Axiom", "AX-001", {"id": "AX-001"})
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")
        g.add_edge("CR-001", "CR-003", "REINFORCES")
        g.add_edge("AX-001", "CR-001", "GROUNDS")
        return g

    def test_no_filters_returns_all(self):
        g = self._setup_graph()
        edges = g.get_edges()
        assert len(edges) == 3

    def test_filter_by_edge_type(self):
        g = self._setup_graph()
        edges = g.get_edges(edge_type="CONFLICTS_WITH")
        assert len(edges) == 1
        assert edges[0]["from_id"] == "CR-001"
        assert edges[0]["to_id"] == "CR-002"

    def test_filter_by_node_id_both(self):
        g = self._setup_graph()
        edges = g.get_edges(node_id="CR-001")
        assert len(edges) == 3  # involved in all 3 edges

    def test_filter_by_node_id_outgoing(self):
        g = self._setup_graph()
        edges = g.get_edges(node_id="CR-001", direction="outgoing")
        assert len(edges) == 2  # CR-001→CR-002, CR-001→CR-003

    def test_filter_by_node_id_incoming(self):
        g = self._setup_graph()
        edges = g.get_edges(node_id="CR-001", direction="incoming")
        assert len(edges) == 1  # AX-001→CR-001

    def test_combined_filters(self):
        g = self._setup_graph()
        edges = g.get_edges(node_id="CR-001", edge_type="CONFLICTS_WITH")
        assert len(edges) == 1

    def test_no_matching_edges(self):
        g = self._setup_graph()
        edges = g.get_edges(edge_type="NONEXISTENT")
        assert len(edges) == 0

    def test_empty_graph(self):
        g = MemoryGraphAdapter()
        edges = g.get_edges()
        assert len(edges) == 0

    def test_node_not_in_any_edge(self):
        g = self._setup_graph()
        g.add_node("Rule", "CR-ALONE", {"id": "CR-ALONE"})
        edges = g.get_edges(node_id="CR-ALONE")
        assert len(edges) == 0
