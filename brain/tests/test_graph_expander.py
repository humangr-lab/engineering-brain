"""Tests for multi-hop graph expansion.

Verifies:
- expand_top_results follows edges and returns new nodes
- Deprecated nodes are excluded from expansion
- Expansion discount is applied
- max_expand limit is respected
- Already-seen nodes are not duplicated
- _infer_layer maps ID prefixes correctly
"""

from __future__ import annotations

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.core.schema import EdgeType, NodeType
from engineering_brain.retrieval.graph_expander import _infer_layer, expand_top_results

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_graph_with_hierarchy() -> MemoryGraphAdapter:
    """Build a small knowledge graph with cross-layer edges.

    Structure:
        P-001 (Principle) --INFORMS--> PAT-001 (Pattern)
        PAT-001 --INSTANTIATES--> CR-001 (Rule)
        CR-001 --EVIDENCED_BY--> F-001 (Finding)
    """
    graph = MemoryGraphAdapter()

    graph.add_node(
        NodeType.PRINCIPLE.value,
        "P-001",
        {
            "id": "P-001",
            "name": "Defense in Depth",
            "why": "Multiple layers prevent single point of failure",
        },
    )
    graph.add_node(
        NodeType.PATTERN.value,
        "PAT-001",
        {
            "id": "PAT-001",
            "name": "Deny By Default",
            "intent": "Block unless explicitly allowed",
        },
    )
    graph.add_node(
        NodeType.RULE.value,
        "CR-001",
        {
            "id": "CR-001",
            "text": "Validate CORS origins explicitly",
            "why": "Prevent XSS",
            "technologies": ["flask"],
        },
    )
    graph.add_node(
        "Finding",
        "F-001",
        {
            "id": "F-001",
            "description": "CORS wildcard in server.py",
        },
    )

    # Edges
    graph.add_edge("P-001", "PAT-001", EdgeType.INFORMS.value)
    graph.add_edge("PAT-001", "CR-001", EdgeType.INSTANTIATES.value)
    graph.add_edge("CR-001", "F-001", EdgeType.EVIDENCED_BY.value)

    return graph


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExpandTopResults:
    def test_follows_instantiates_backward(self):
        """From a Rule, follow INSTANTIATES backward to find Pattern."""
        graph = _build_graph_with_hierarchy()
        scored = [{"id": "CR-001", "_relevance_score": 0.8}]

        expanded = expand_top_results(graph, scored, max_expand=5)
        expanded_ids = {n["id"] for n in expanded}

        # Should find PAT-001 via INSTANTIATES (incoming)
        assert "PAT-001" in expanded_ids

    def test_follows_evidenced_by_forward(self):
        """From a Rule, follow EVIDENCED_BY forward to find Finding."""
        graph = _build_graph_with_hierarchy()
        scored = [{"id": "CR-001", "_relevance_score": 0.8}]

        expanded = expand_top_results(graph, scored, max_expand=5)
        expanded_ids = {n["id"] for n in expanded}

        assert "F-001" in expanded_ids

    def test_follows_informs_backward(self):
        """From a Pattern, follow INFORMS backward to find Principle."""
        graph = _build_graph_with_hierarchy()
        scored = [{"id": "PAT-001", "_relevance_score": 0.8}]

        expanded = expand_top_results(graph, scored, max_expand=5)
        expanded_ids = {n["id"] for n in expanded}

        assert "P-001" in expanded_ids

    def test_discount_applied(self):
        """Expanded nodes are tagged with _expansion_discount."""
        graph = _build_graph_with_hierarchy()
        scored = [{"id": "CR-001", "_relevance_score": 0.8}]

        expanded = expand_top_results(graph, scored, discount=0.3)
        for node in expanded:
            assert node["_expansion_discount"] == 0.3
            assert node["_expanded_from"] == "CR-001"

    def test_deprecated_excluded(self):
        """Deprecated nodes are not included in expansion."""
        graph = _build_graph_with_hierarchy()
        # Mark the finding as deprecated
        f_node = graph.get_node("F-001")
        f_node["deprecated"] = True

        scored = [{"id": "CR-001", "_relevance_score": 0.8}]
        expanded = expand_top_results(graph, scored)
        expanded_ids = {n["id"] for n in expanded}

        assert "F-001" not in expanded_ids

    def test_no_duplicates(self):
        """Nodes already in scored_nodes are not returned."""
        graph = _build_graph_with_hierarchy()
        # Include PAT-001 in scored already
        scored = [
            {"id": "CR-001", "_relevance_score": 0.8},
            {"id": "PAT-001", "_relevance_score": 0.5},
        ]

        expanded = expand_top_results(graph, scored)
        expanded_ids = {n["id"] for n in expanded}

        # PAT-001 is already scored, should not appear in expanded
        assert "PAT-001" not in expanded_ids

    def test_max_expand_limit(self):
        """Only top max_expand nodes are expanded from."""
        graph = _build_graph_with_hierarchy()

        # Add extra rules
        for i in range(5):
            rid = f"CR-EXTRA-{i:03d}"
            graph.add_node(
                NodeType.RULE.value,
                rid,
                {
                    "id": rid,
                    "text": f"Extra rule {i}",
                },
            )

        scored = [{"id": f"CR-EXTRA-{i:03d}", "_relevance_score": 0.9 - i * 0.1} for i in range(5)]

        # With max_expand=2, only first 2 nodes are expanded
        expanded = expand_top_results(graph, scored, max_expand=2)
        sources = {n.get("_expanded_from") for n in expanded}
        assert len(sources) <= 2

    def test_empty_scored_returns_empty(self):
        graph = _build_graph_with_hierarchy()
        assert expand_top_results(graph, []) == []

    def test_no_edges_returns_empty(self):
        """Node with no edges → no expansion."""
        graph = MemoryGraphAdapter()
        graph.add_node(
            NodeType.RULE.value,
            "CR-LONELY",
            {
                "id": "CR-LONELY",
                "text": "No connections",
            },
        )

        scored = [{"id": "CR-LONELY", "_relevance_score": 0.8}]
        assert expand_top_results(graph, scored) == []


class TestInferLayer:
    def test_axiom_prefix(self):
        assert _infer_layer({"id": "AX-001"}) == "L1"

    def test_principle_prefix(self):
        assert _infer_layer({"id": "P-001"}) == "L1"

    def test_pattern_prefix(self):
        assert _infer_layer({"id": "PAT-001"}) == "L2"

    def test_cpat_prefix(self):
        assert _infer_layer({"id": "CPAT-abc123"}) == "L2"

    def test_finding_label(self):
        assert _infer_layer({"id": "X-001", "_label": "Finding"}) == "L4"

    def test_default_is_l3(self):
        assert _infer_layer({"id": "UNKNOWN-001"}) == "L3"
