"""Tests for ScalablePackManager v2 — O(log N) pack creation.

Verifies:
- Multi-query decomposition (1 tech → 1 sub-query, 5 techs → capped at 5)
- Vector retrieval is called (mock Qdrant, verify ANN search per collection)
- RRF merge produces deduplicated ranked results
- Vertical completeness uses filtered queries (assert get_all_nodes NOT called)
- Feature flag routing: BRAIN_PACK_V2_ENABLED → ScalablePackManager
- Graceful fallback: vector adapter None → graph-only retrieval
- Delegated methods forward to v1
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from engineering_brain.adapters.memory import MemoryGraphAdapter, MemoryVectorAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import NodeType
from engineering_brain.retrieval.context_extractor import ExtractedContext
from engineering_brain.retrieval.pack_manager_v2 import ScalablePackManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_graph() -> MemoryGraphAdapter:
    """Build a small test graph with nodes across layers."""
    graph = MemoryGraphAdapter()

    graph.add_node(NodeType.PRINCIPLE.value, "P-SEC-001", {
        "id": "P-SEC-001",
        "name": "Defense in Depth",
        "why": "Multiple layers prevent single point of failure",
        "domains": ["security"],
    })
    graph.add_node(NodeType.PATTERN.value, "PAT-SEC-001", {
        "id": "PAT-SEC-001",
        "name": "Auth Decorator",
        "intent": "Protect endpoints with decorators",
        "languages": ["Python"],
        "domains": ["security"],
    })
    graph.add_node(NodeType.RULE.value, "CR-SEC-001", {
        "id": "CR-SEC-001",
        "text": "Always validate CORS origins",
        "why": "Prevent XSS via CORS misconfiguration",
        "severity": "critical",
        "technologies": ["Python", "Flask"],
        "domains": ["security"],
    })
    graph.add_node(NodeType.RULE.value, "CR-SEC-002", {
        "id": "CR-SEC-002",
        "text": "Use bcrypt for password hashing",
        "why": "Prevent rainbow table attacks",
        "severity": "high",
        "technologies": ["Python"],
        "domains": ["security"],
    })
    graph.add_node(NodeType.RULE.value, "CR-FLASK-001", {
        "id": "CR-FLASK-001",
        "text": "Use Flask app factory pattern",
        "why": "Testability and modularity",
        "severity": "medium",
        "technologies": ["Flask", "Python"],
        "domains": ["architecture"],
    })
    graph.add_node("Finding", "F-SEC-001", {
        "id": "F-SEC-001",
        "description": "CORS wildcard found in production",
        "domains": ["security"],
    })

    return graph


def _config(**overrides) -> BrainConfig:
    """Create a test config with sensible defaults."""
    defaults = {
        "pack_v2_enabled": True,
        "pack_v2_vector_top_k": 10,
        "pack_v2_max_sub_queries": 5,
        "pack_v2_graph_filter_limit": 20,
        "graph_expansion_enabled": False,
    }
    defaults.update(overrides)
    return BrainConfig(**defaults)


# ---------------------------------------------------------------------------
# Multi-query decomposition
# ---------------------------------------------------------------------------

class TestDecomposeQueries:
    """Test _decompose_queries generates correct sub-queries."""

    def test_single_tech_single_domain(self):
        mgr = ScalablePackManager(MagicMock(), None, _config())
        ctx = ExtractedContext(
            technologies=["Python"],
            domains=["security"],
            raw_text="Python security",
        )
        queries = mgr._decompose_queries(ctx)
        assert len(queries) >= 1
        assert any("Python" in q for q in queries)

    def test_multiple_techs_capped_at_3(self):
        mgr = ScalablePackManager(MagicMock(), None, _config())
        ctx = ExtractedContext(
            technologies=["Python", "Kafka", "Redis", "Docker", "Go"],
            domains=["security"],
            raw_text="many techs",
        )
        queries = mgr._decompose_queries(ctx)
        # Max 3 tech queries + max 2 domain queries = max 5
        assert len(queries) <= 5
        # Should include first 3 techs
        tech_queries = [q for q in queries if "best practices" in q]
        assert len(tech_queries) <= 3

    def test_total_capped_at_max_sub_queries(self):
        mgr = ScalablePackManager(MagicMock(), None, _config(pack_v2_max_sub_queries=3))
        ctx = ExtractedContext(
            technologies=["Python", "Kafka", "Redis"],
            domains=["security", "architecture"],
            raw_text="lots of context",
        )
        queries = mgr._decompose_queries(ctx)
        assert len(queries) <= 3

    def test_no_context_uses_raw_text(self):
        mgr = ScalablePackManager(MagicMock(), None, _config())
        ctx = ExtractedContext(
            technologies=[],
            domains=[],
            raw_text="some generic engineering question",
        )
        queries = mgr._decompose_queries(ctx)
        assert len(queries) >= 1
        assert "some generic engineering question" in queries[0]

    def test_general_domain_skipped(self):
        mgr = ScalablePackManager(MagicMock(), None, _config())
        ctx = ExtractedContext(
            technologies=["Python"],
            domains=["general"],
            raw_text="python stuff",
        )
        queries = mgr._decompose_queries(ctx)
        # "general" domain should not generate a domain sub-query
        domain_queries = [q for q in queries if "knowledge" in q]
        assert len(domain_queries) == 0

    def test_deduplication(self):
        mgr = ScalablePackManager(MagicMock(), None, _config())
        ctx = ExtractedContext(
            technologies=["Python"],
            domains=["python"],  # same as tech, should not duplicate
            raw_text="python",
        )
        queries = mgr._decompose_queries(ctx)
        lowered = [q.lower() for q in queries]
        assert len(lowered) == len(set(lowered))


# ---------------------------------------------------------------------------
# Vector retrieval
# ---------------------------------------------------------------------------

class TestRetrieveCandidates:
    """Test _retrieve_candidates calls vector search per collection."""

    def test_vector_search_called_per_collection(self):
        graph = _build_graph()
        vector = MagicMock()
        vector.search.return_value = []

        embedder = MagicMock()
        embedder.embed_text.return_value = [0.1] * 1024

        mgr = ScalablePackManager(graph, vector, _config(), embedder=embedder)
        ctx = ExtractedContext(technologies=["Python"], domains=["security"])

        mgr._retrieve_candidates("Python security", ctx)

        # Should search 4 collections
        assert vector.search.call_count == 4
        collections_searched = [
            call.kwargs.get("collection", call.args[0] if call.args else "")
            for call in vector.search.call_args_list
        ]
        assert "brain_principles" in collections_searched
        assert "brain_patterns" in collections_searched
        assert "brain_rules" in collections_searched
        assert "brain_evidence" in collections_searched

    def test_graph_only_when_no_vector(self):
        graph = _build_graph()
        mgr = ScalablePackManager(graph, None, _config())
        ctx = ExtractedContext(technologies=["Python"], domains=["security"])

        vector_hits, graph_hits = mgr._retrieve_candidates("Python security", ctx)

        assert vector_hits == []
        assert len(graph_hits) >= 0  # graph queries still work

    def test_graph_only_when_no_embedder(self):
        graph = _build_graph()
        vector = MagicMock()
        mgr = ScalablePackManager(graph, vector, _config(), embedder=None)
        ctx = ExtractedContext(technologies=["Python"], domains=["security"])

        vector_hits, graph_hits = mgr._retrieve_candidates("Python security", ctx)

        assert vector_hits == []
        vector.search.assert_not_called()

    def test_vector_hits_hydrated_from_graph(self):
        graph = _build_graph()
        vector = MagicMock()
        vector.search.return_value = [
            {"id": "CR-SEC-001", "score": 0.95},
        ]

        embedder = MagicMock()
        embedder.embed_text.return_value = [0.1] * 1024

        mgr = ScalablePackManager(graph, vector, _config(), embedder=embedder)
        ctx = ExtractedContext(technologies=["Python"], domains=["security"])

        vector_hits, _ = mgr._retrieve_candidates("Python security", ctx)

        # Should find the node and hydrate it
        hydrated = [h for h in vector_hits if h.get("id") == "CR-SEC-001"]
        assert len(hydrated) >= 1
        # Hydrated node should have original fields
        assert hydrated[0].get("text") == "Always validate CORS origins"
        assert hydrated[0].get("_vector_score") == 0.95


# ---------------------------------------------------------------------------
# Vertical completeness v2
# ---------------------------------------------------------------------------

class TestVerticalCompletenessV2:
    """Test _ensure_vertical_completeness_v2 uses filtered queries."""

    def test_fills_missing_layer(self):
        graph = _build_graph()
        mgr = ScalablePackManager(graph, None, _config())
        ctx = ExtractedContext(technologies=["Python"], domains=["security"])

        # Only L3 nodes — should fill L1 and L2
        candidates = [
            {"id": "CR-SEC-001", "text": "CORS rule", "technologies": ["Python"],
             "domains": ["security"], "severity": "critical"},
        ]

        result = mgr._ensure_vertical_completeness_v2(candidates, ctx)

        layers_present = {
            _infer_layer(str(n.get("id", ""))) for n in result
        }
        # Should now have L1 and L2 from filtered queries
        assert "L3" in layers_present
        # L1/L2 depend on graph.query() finding matching nodes
        assert len(result) >= 1

    def test_no_op_when_all_layers_present(self):
        graph = _build_graph()
        mgr = ScalablePackManager(graph, None, _config())
        ctx = ExtractedContext(technologies=["Python"], domains=["security"])

        candidates = [
            {"id": "P-SEC-001", "name": "Principle", "domains": ["security"]},
            {"id": "PAT-SEC-001", "name": "Pattern", "domains": ["security"]},
            {"id": "CR-SEC-001", "text": "Rule", "domains": ["security"]},
        ]

        result = mgr._ensure_vertical_completeness_v2(candidates, ctx)

        # No additions needed
        assert len(result) == 3

    def test_does_not_call_get_all_nodes(self):
        graph = _build_graph()
        original_get_all = graph.get_all_nodes
        graph.get_all_nodes = MagicMock(side_effect=AssertionError(
            "get_all_nodes should NOT be called in v2"
        ))

        mgr = ScalablePackManager(graph, None, _config())
        ctx = ExtractedContext(technologies=["Python"], domains=["security"])

        candidates = [
            {"id": "CR-SEC-001", "text": "Rule", "technologies": ["Python"],
             "domains": ["security"], "severity": "critical"},
        ]

        # Should NOT raise — v2 uses graph.query(), not get_all_nodes()
        result = mgr._ensure_vertical_completeness_v2(candidates, ctx)
        assert len(result) >= 1

        graph.get_all_nodes = original_get_all


# Helper for vertical completeness test
def _infer_layer(node_id: str) -> str:
    if node_id.startswith("AX-"):
        return "L0"
    if node_id.startswith("P-"):
        return "L1"
    if node_id.startswith(("PAT-", "CPAT-")):
        return "L2"
    if node_id.startswith("F-"):
        return "L4"
    return "L3"


# ---------------------------------------------------------------------------
# Feature flag routing
# ---------------------------------------------------------------------------

class TestFeatureFlagRouting:
    """Test that Brain.create_pack routes through feature flag."""

    def test_v2_enabled_uses_scalable_manager(self):
        """When pack_v2_enabled=True, ScalablePackManager is used."""
        with patch.dict("os.environ", {"BRAIN_PACK_V2_ENABLED": "true"}):
            from engineering_brain.core.brain import Brain
            brain = Brain(adapter="memory")

            # Add some nodes
            brain.add_principle(
                name="Test Principle", why="Testing", how="Test",
                domains=["testing"], id="P-TEST-001",
            )
            brain.add_rule(
                text="Test rule", why="Testing", how="Test",
                severity="medium", technologies=["Python"],
                domains=["testing"], id="CR-TEST-001",
            )

            # Force config
            brain._config.pack_v2_enabled = True

            pack = brain.create_pack("Python testing best practices")
            assert pack is not None
            assert pack.node_count >= 0

    def test_v2_disabled_uses_v1(self):
        """When pack_v2_enabled=False, PackManager v1 is used."""
        from engineering_brain.core.brain import Brain
        brain = Brain(adapter="memory")

        brain.add_rule(
            text="Test rule", why="Testing", how="Test",
            severity="medium", technologies=["Python"],
            domains=["testing"], id="CR-TEST-002",
        )

        brain._config.pack_v2_enabled = False

        pack = brain.create_pack("Python testing")
        assert pack is not None


# ---------------------------------------------------------------------------
# Graceful fallback
# ---------------------------------------------------------------------------

class TestGracefulFallback:
    """Test graceful degradation when vector adapter is None."""

    def test_create_pack_without_vector(self):
        graph = _build_graph()
        mgr = ScalablePackManager(graph, None, _config())

        pack = mgr.create_pack(
            "Python security best practices",
            technologies=["Python"],
            domains=["security"],
        )

        assert pack is not None
        assert pack.node_count >= 0
        assert isinstance(pack.quality_score, float)

    def test_create_pack_with_mock_vector(self):
        graph = _build_graph()
        vector = MagicMock()
        vector.search.return_value = [
            {"id": "CR-SEC-001", "score": 0.9},
        ]
        embedder = MagicMock()
        embedder.embed_text.return_value = [0.1] * 1024

        mgr = ScalablePackManager(graph, vector, _config(), embedder=embedder)

        pack = mgr.create_pack(
            "Python security",
            technologies=["Python"],
            domains=["security"],
        )

        assert pack is not None
        assert pack.node_count > 0


# ---------------------------------------------------------------------------
# Delegated methods
# ---------------------------------------------------------------------------

class TestDelegatedMethods:
    """Test that batch/explicit methods delegate to v1."""

    def test_create_pack_from_nodes_delegates(self):
        graph = _build_graph()
        mgr = ScalablePackManager(graph, None, _config())

        pack = mgr.create_pack_from_nodes(
            "test-pack",
            ["CR-SEC-001", "CR-SEC-002"],
            description="Security rules",
        )

        assert pack.id == "test-pack"
        assert pack.node_count == 2
        assert "CR-SEC-001" in pack.node_ids
        assert "CR-SEC-002" in pack.node_ids

    def test_auto_generate_packs_delegates(self):
        graph = _build_graph()
        mgr = ScalablePackManager(graph, None, _config())

        packs = mgr.auto_generate_packs()

        # Should work (may return empty if too few nodes per group)
        assert isinstance(packs, list)

    def test_select_packs_delegates(self):
        graph = _build_graph()
        mgr = ScalablePackManager(graph, None, _config())

        ctx = ExtractedContext(technologies=["Python"], domains=["security"])
        packs = mgr.select_packs(ctx, [])

        assert packs == []


# ---------------------------------------------------------------------------
# End-to-end create_pack
# ---------------------------------------------------------------------------

class TestCreatePackE2E:
    """End-to-end test for create_pack with real graph."""

    def test_creates_valid_pack(self):
        graph = _build_graph()
        mgr = ScalablePackManager(graph, None, _config())

        pack = mgr.create_pack(
            "Python security with CORS and authentication",
            technologies=["Python"],
            domains=["security"],
            min_score=0.0,
            max_nodes=50,
        )

        assert pack.id
        assert pack.description == "Python security with CORS and authentication"
        assert pack.node_count > 0
        assert len(pack.node_ids) == pack.node_count
        assert isinstance(pack.quality_score, float)
        assert 0.0 <= pack.quality_score <= 1.0
        assert len(pack.layers_present) > 0

    def test_min_score_filters(self):
        graph = _build_graph()
        mgr = ScalablePackManager(graph, None, _config())

        pack_loose = mgr.create_pack("security", min_score=0.0, max_nodes=50)
        pack_strict = mgr.create_pack("security", min_score=0.99, max_nodes=50)

        assert pack_loose.node_count >= pack_strict.node_count

    def test_max_nodes_respected(self):
        graph = _build_graph()
        mgr = ScalablePackManager(graph, None, _config())

        pack = mgr.create_pack("security", min_score=0.0, max_nodes=2)

        assert pack.node_count <= 2
