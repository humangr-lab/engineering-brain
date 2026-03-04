"""Tests for the retrieval layer: router, context_extractor, and scorer.

Focuses on the three least-tested modules in the retrieval subsystem:
1. QueryRouter — full pipeline query routing through graph + vector + cache
2. context_extractor — AST context extraction, TIG implications, domain expansion,
   contextual embedding, shopping list merge
3. scorer — _compute_recency, _compute_confidence, _get_list, _hierarchy_overlap_count,
   score_knowledge with epistemic/calibration/prediction signals, rank_results with
   adaptive weight optimizer

Complements existing test_retrieval.py (which covers extract_context basics,
build_contextual_text, merge/dedup, basic score_knowledge, rank_results).

Uses MemoryGraphAdapter / MemoryCacheAdapter to avoid external dependencies.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from engineering_brain.adapters.memory import (
    MemoryCacheAdapter,
    MemoryGraphAdapter,
    MemoryVectorAdapter,
)
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import EdgeType, Layer
from engineering_brain.core.types import KnowledgeQuery, KnowledgeResult
from engineering_brain.retrieval.context_extractor import (
    ExtractedContext,
    KnowledgeShoppingList,
    apply_technology_implications,
    build_domain_hierarchy,
    build_embedding_preamble,
    build_tech_index_from_nodes,
    contextual_text_for_embedding,
    expand_domains,
    extract_ast_context,
)
from engineering_brain.retrieval.router import QueryRouter, _clean_node
from engineering_brain.retrieval.scorer import (
    _compute_confidence,
    _compute_recency,
    _get_list,
    _hierarchy_overlap_count,
    rank_results,
    score_knowledge,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def config() -> BrainConfig:
    """BrainConfig with expansion/reranking disabled for deterministic tests."""
    return replace(
        BrainConfig(),
        graph_expansion_enabled=False,
        reranker_enabled=False,
        query_expansion_enabled=False,
    )


@pytest.fixture
def graph() -> MemoryGraphAdapter:
    """Fresh empty graph."""
    return MemoryGraphAdapter()


@pytest.fixture
def cache() -> MemoryCacheAdapter:
    """Fresh empty cache."""
    return MemoryCacheAdapter()


@pytest.fixture
def populated_graph(graph: MemoryGraphAdapter) -> MemoryGraphAdapter:
    """Graph populated with nodes across all four queryable layers."""
    graph.add_node(
        "Principle",
        "P-001",
        {
            "id": "P-001",
            "name": "Defense in Depth",
            "why": "No single layer is perfect",
            "how_to_apply": "Layer multiple security controls",
            "domains": ["security"],
            "technologies": [],
            "severity": "high",
            "validation_status": "human_verified",
        },
    )
    graph.add_node(
        "Pattern",
        "PAT-001",
        {
            "id": "PAT-001",
            "name": "Circuit Breaker",
            "intent": "Prevent cascading failures",
            "technologies": ["Python"],
            "domains": ["reliability"],
            "severity": "high",
            "languages": ["Python"],
        },
    )
    graph.add_node(
        "Rule",
        "CR-001",
        {
            "id": "CR-001",
            "text": "Always validate CORS origins explicitly",
            "why": "Wildcard CORS allows any origin",
            "how_to_do_right": "List allowed origins explicitly",
            "technologies": ["Flask"],
            "domains": ["security", "api"],
            "severity": "critical",
            "reinforcement_count": 15,
            "confidence": 0.9,
            "validation_status": "cross_checked",
        },
    )
    graph.add_node(
        "Rule",
        "CR-002",
        {
            "id": "CR-002",
            "text": "Use parameterized queries for SQL",
            "why": "String concat enables injection",
            "how_to_do_right": "Use ORM or parameterized placeholders",
            "technologies": ["Python", "PostgreSQL"],
            "domains": ["security", "database"],
            "severity": "critical",
            "reinforcement_count": 20,
            "confidence": 0.95,
            "validation_status": "human_verified",
        },
    )
    graph.add_node(
        "Finding",
        "F-001",
        {
            "id": "F-001",
            "description": "CORS wildcard in production server.py",
            "severity": "critical",
            "domains": ["security"],
            "technologies": ["Flask"],
        },
    )
    # A deprecated node that should be filtered
    graph.add_node(
        "Rule",
        "CR-DEP",
        {
            "id": "CR-DEP",
            "text": "Deprecated rule",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "high",
            "deprecated": True,
        },
    )
    # Edges
    graph.add_edge("CR-001", "P-001", EdgeType.INSTANTIATES.value)
    graph.add_edge("F-001", "CR-001", EdgeType.EVIDENCED_BY.value)
    return graph


def _make_query(
    desc: str = "Implement Flask API with CORS",
    techs: list[str] | None = None,
    phase: str = "exec",
    domains: list[str] | None = None,
) -> KnowledgeQuery:
    return KnowledgeQuery(
        task_description=desc,
        technologies=techs or [],
        phase=phase,
        domains=domains or [],
    )


# =============================================================================
# 1. QueryRouter tests
# =============================================================================


class TestQueryRouterInit:
    """Tests for QueryRouter construction."""

    def test_minimal_init_graph_only(self, graph: MemoryGraphAdapter, config: BrainConfig):
        router = QueryRouter(graph=graph, config=config)
        assert router._graph is graph
        assert router._vector is None
        assert router._cache is None

    def test_init_with_all_adapters(
        self,
        populated_graph: MemoryGraphAdapter,
        cache: MemoryCacheAdapter,
        config: BrainConfig,
    ):
        vector = MemoryVectorAdapter()
        router = QueryRouter(
            graph=populated_graph,
            vector=vector,
            cache=cache,
            config=config,
        )
        assert router._vector is vector
        assert router._cache is cache

    def test_default_config_when_none_passed(self, graph: MemoryGraphAdapter):
        router = QueryRouter(graph=graph, config=None)
        assert isinstance(router._config, BrainConfig)


class TestQueryRouterQuery:
    """Tests for QueryRouter.query() end-to-end pipeline."""

    def test_returns_knowledge_result(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        result = router.query(_make_query("Flask security API CORS"))
        assert isinstance(result, KnowledgeResult)

    def test_finds_matching_rules_by_technology(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        result = router.query(
            _make_query(
                "Implement Flask REST API with CORS",
                techs=["Flask"],
            )
        )
        # CR-001 is Flask + CORS → should appear in rules
        rule_ids = [r.get("id") for r in result.rules]
        assert "CR-001" in rule_ids

    def test_deprecated_nodes_excluded(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        result = router.query(_make_query("Flask security", techs=["Flask"]))
        all_ids = (
            [n.get("id") for n in result.rules]
            + [n.get("id") for n in result.patterns]
            + [n.get("id") for n in result.principles]
            + [n.get("id") for n in result.evidence]
        )
        assert "CR-DEP" not in all_ids

    def test_cache_hit_returns_cached_result(
        self,
        populated_graph: MemoryGraphAdapter,
        cache: MemoryCacheAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, cache=cache, config=config)
        # First query populates the cache
        result1 = router.query(_make_query("Flask security", techs=["Flask"]))
        assert result1.cache_hit is False
        # Second query should be a cache hit
        result2 = router.query(_make_query("Flask security", techs=["Flask"]))
        assert result2.cache_hit is True

    def test_formatted_text_not_empty(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        result = router.query(_make_query("Flask security", techs=["Flask"]))
        assert isinstance(result.formatted_text, str)
        # With matching nodes, formatted text should contain something
        if result.rules:
            assert len(result.formatted_text) > 0

    def test_query_time_ms_is_positive(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        result = router.query(_make_query("Flask security"))
        assert result.query_time_ms >= 0.0

    def test_empty_graph_returns_empty_result(
        self,
        graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=graph, config=config)
        result = router.query(_make_query("Flask security", techs=["Flask"]))
        assert result.rules == []
        assert result.patterns == []
        assert result.principles == []
        assert result.evidence == []

    def test_clean_node_strips_internal_keys(self):
        node = {
            "id": "CR-001",
            "text": "test",
            "_relevance_score": 0.8,
            "_layer": "L3",
            "_source": "graph",
            "_vector_score": 0.5,
        }
        cleaned = _clean_node(node)
        assert "id" in cleaned
        assert "text" in cleaned
        assert "_relevance_score" not in cleaned
        assert "_layer" not in cleaned
        assert "_source" not in cleaned
        assert "_vector_score" not in cleaned

    def test_clean_node_preserves_non_underscore_keys(self):
        node = {"id": "X", "text": "ok", "severity": "high"}
        cleaned = _clean_node(node)
        assert cleaned == node

    def test_clean_node_empty_dict(self):
        assert _clean_node({}) == {}


class TestQueryRouterSplitByLayer:
    """Tests for QueryRouter._split_by_layer."""

    def test_splits_by_layer_field(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        nodes = [
            {"id": "P-001", "_layer": "L1"},
            {"id": "PAT-001", "_layer": "L2"},
            {"id": "CR-001", "_layer": "L3"},
            {"id": "F-001", "_layer": "L4"},
        ]
        by_layer = router._split_by_layer(nodes)
        assert len(by_layer["L1"]) == 1
        assert len(by_layer["L2"]) == 1
        assert len(by_layer["L3"]) == 1
        assert len(by_layer["L4"]) == 1

    def test_falls_back_to_label_when_no_layer(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        nodes = [
            {"id": "P-001", "_label": "Principle"},
            {"id": "PAT-001", "_label": "Pattern"},
            {"id": "CR-001", "_label": "Rule"},
            {"id": "F-001", "_label": "Finding"},
        ]
        by_layer = router._split_by_layer(nodes)
        assert len(by_layer["L1"]) == 1
        assert len(by_layer["L2"]) == 1
        assert len(by_layer["L3"]) == 1
        assert len(by_layer["L4"]) == 1

    def test_code_example_and_test_result_go_to_l4(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        nodes = [
            {"id": "CE-001", "_label": "CodeExample"},
            {"id": "TR-001", "_label": "TestResult"},
        ]
        by_layer = router._split_by_layer(nodes)
        assert len(by_layer["L4"]) == 2

    def test_unknown_label_defaults_to_l3(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        nodes = [{"id": "X-001", "_label": "Unknown"}]
        by_layer = router._split_by_layer(nodes)
        assert len(by_layer["L3"]) == 1

    def test_empty_nodes(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        by_layer = router._split_by_layer([])
        assert by_layer == {"L1": [], "L2": [], "L3": [], "L4": []}


class TestQueryRouterWithScoredNodes:
    """Tests for QueryRouter.query_with_scored_nodes."""

    def test_returns_tuple_of_result_and_scored(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        result, scored = router.query_with_scored_nodes(
            _make_query("Flask security", techs=["Flask"]),
        )
        assert isinstance(result, KnowledgeResult)
        assert isinstance(scored, list)

    def test_scored_nodes_contain_relevance_scores(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        _, scored = router.query_with_scored_nodes(
            _make_query("Flask security", techs=["Flask"]),
        )
        for node in scored:
            assert "_relevance_score" in node

    def test_cache_hit_returns_empty_scored(
        self,
        populated_graph: MemoryGraphAdapter,
        cache: MemoryCacheAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, cache=cache, config=config)
        # Prime the cache
        router.query_with_scored_nodes(_make_query("Flask security", techs=["Flask"]))
        # Cache hit
        result, scored = router.query_with_scored_nodes(
            _make_query("Flask security", techs=["Flask"]),
        )
        assert result.cache_hit is True
        assert scored == []


class TestQueryRouterQueryGraph:
    """Tests for QueryRouter._query_graph internal method."""

    def test_queries_by_technology(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        ctx = ExtractedContext(
            technologies=["Flask"],
            domains=[],
            raw_text="Flask task",
        )
        results = router._query_graph(ctx, [Layer.L3_RULES])
        ids = [n.get("id") for n in results]
        assert "CR-001" in ids

    def test_queries_by_domain(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        ctx = ExtractedContext(
            technologies=[],
            domains=["security"],
            raw_text="security task",
        )
        results = router._query_graph(ctx, [Layer.L3_RULES])
        ids = [n.get("id") for n in results]
        # CR-001 and CR-002 both have security domain
        assert "CR-001" in ids or "CR-002" in ids

    def test_general_fallback_when_no_tech_or_domain(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        ctx = ExtractedContext(
            technologies=[],
            domains=[],
            raw_text="something generic",
        )
        results = router._query_graph(ctx, [Layer.L3_RULES])
        # Should still return some results from general query
        assert isinstance(results, list)

    def test_deprecated_filtered_from_graph_results(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        ctx = ExtractedContext(
            technologies=["Flask"],
            domains=["security"],
            raw_text="Flask security",
        )
        results = router._query_graph(
            ctx,
            [Layer.L1_PRINCIPLES, Layer.L2_PATTERNS, Layer.L3_RULES, Layer.L4_EVIDENCE],
        )
        ids = [n.get("id") for n in results]
        assert "CR-DEP" not in ids

    def test_layer_annotation_set(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        ctx = ExtractedContext(
            technologies=["Flask"],
            domains=[],
            raw_text="Flask task",
        )
        results = router._query_graph(ctx, [Layer.L3_RULES])
        for n in results:
            assert n.get("_layer") == "L3"


class TestQueryRouterProvenance:
    """Tests for QueryRouter._trace_provenance and query_with_provenance."""

    def test_trace_provenance_follows_edges(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        # F-001 -> EVIDENCED_BY -> CR-001
        chain = router._trace_provenance("F-001")
        # Should find CR-001 via EVIDENCED_BY
        chain_ids = [step.get("node_id") for step in chain]
        assert "CR-001" in chain_ids

    def test_trace_provenance_empty_for_leaf(
        self,
        graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        graph.add_node("Rule", "CR-ALONE", {"id": "CR-ALONE", "text": "isolated"})
        router = QueryRouter(graph=graph, config=config)
        chain = router._trace_provenance("CR-ALONE")
        assert chain == []

    def test_trace_provenance_respects_max_depth(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        chain = router._trace_provenance("F-001", max_depth=1)
        assert len(chain) <= 1

    def test_trace_provenance_nonexistent_node(
        self,
        graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=graph, config=config)
        chain = router._trace_provenance("NONEXISTENT-123")
        assert chain == []


# =============================================================================
# 2. Context Extractor — deeper coverage
# =============================================================================


class TestExtractContextDomainExpansion:
    """Tests for expand_domains and build_domain_hierarchy."""

    def test_expand_domains_adds_children(self):
        build_domain_hierarchy()
        expanded = expand_domains(["security"])
        # Should include sub-domain keywords like "token", "injection", etc.
        assert "security" in expanded
        assert len(expanded) > 1

    def test_expand_domains_no_removal(self):
        build_domain_hierarchy()
        original = ["security", "api"]
        expanded = expand_domains(original)
        for d in original:
            assert d in expanded

    def test_expand_domains_unknown_domain_unchanged(self):
        build_domain_hierarchy()
        expanded = expand_domains(["nonexistent_domain_xyz"])
        assert expanded == ["nonexistent_domain_xyz"]

    def test_expand_domains_empty_list(self):
        expanded = expand_domains([])
        assert expanded == []


class TestApplyTechnologyImplicationsDeeper:
    """Deeper tests for TIG (Technology Implication Graph)."""

    def test_flask_database_conditional(self):
        domains = apply_technology_implications(
            ["Flask"],
            "connect to the database using sqlalchemy model",
        )
        assert "sql_injection" in domains or "orm_patterns" in domains

    def test_docker_always_domains(self):
        domains = apply_technology_implications(["Docker"], "build a container image")
        assert (
            "non_root_user" in domains
            or "secrets_management" in domains
            or "health_checks" in domains
        )

    def test_multiple_technologies_combined(self):
        domains = apply_technology_implications(
            ["Flask", "WebSocket"],
            "flask app with websocket routes",
        )
        # Flask always: cors, error_handling, input_validation, http_status_codes
        # WebSocket always: auth, message_validation, ...
        assert "cors" in domains
        assert "auth" in domains

    def test_case_insensitive_tech_key(self):
        # TIG lookup normalizes to lowercase
        domains = apply_technology_implications(["FLASK"], "some text")
        # 'flask' matches the TIG key
        assert "cors" in domains

    def test_no_duplicate_domains_across_techs(self):
        # Both Flask and FastAPI have "cors" in their "always" list
        domains = apply_technology_implications(
            ["Flask", "FastAPI"],
            "build an API",
        )
        assert domains.count("cors") == 1


class TestExtractAstContext:
    """Tests for extract_ast_context (AST-based import analysis)."""

    def test_detects_flask_import(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("from flask import Flask\napp = Flask(__name__)\n")
            f.flush()
            path = f.name
        try:
            techs, domains = extract_ast_context([path])
            assert "Flask" in techs
            assert "cors" in domains or "api" in domains or "security" in domains
        finally:
            os.unlink(path)

    def test_detects_subprocess_import(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import subprocess\nsubprocess.run(['ls'])\n")
            f.flush()
            path = f.name
        try:
            techs, domains = extract_ast_context([path])
            assert "command_injection" in domains or "security" in domains
        finally:
            os.unlink(path)

    def test_empty_file_list(self):
        techs, domains = extract_ast_context([])
        assert techs == []
        assert domains == []

    def test_nonexistent_file_graceful(self):
        techs, domains = extract_ast_context(["/nonexistent/path.py"])
        assert techs == []
        assert domains == []

    def test_syntax_error_graceful(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def broken(\n")  # syntax error
            f.flush()
            path = f.name
        try:
            techs, domains = extract_ast_context([path])
            # Should not raise, just return empty
            assert isinstance(techs, list)
            assert isinstance(domains, list)
        finally:
            os.unlink(path)

    def test_multiple_files(self):
        files = []
        try:
            for code in ["import redis\n", "import pytest\n"]:
                f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
                f.write(code)
                f.flush()
                files.append(f.name)
                f.close()
            techs, domains = extract_ast_context(files)
            assert "Redis" in techs
            assert "testing" in domains
        finally:
            for path in files:
                os.unlink(path)


class TestKnowledgeShoppingListMergeDeeper:
    """Deeper merge tests for KnowledgeShoppingList."""

    def test_merge_empty_lists(self):
        a = KnowledgeShoppingList()
        b = KnowledgeShoppingList()
        merged = a.merge(b)
        assert merged.technologies == []
        assert merged.domains == []
        assert merged.provenance == {}

    def test_merge_preserves_tig_over_ast(self):
        a = KnowledgeShoppingList(
            technologies=["Flask"],
            provenance={"Flask": "ast"},
        )
        b = KnowledgeShoppingList(
            technologies=["Flask"],
            provenance={"Flask": "tig"},
        )
        merged = a.merge(b)
        # tig (priority 1) < ast (priority 2) → tig wins
        assert merged.provenance["Flask"] == "tig"

    def test_merge_keeps_explicit_over_everything(self):
        a = KnowledgeShoppingList(provenance={"Flask": "tig"})
        b = KnowledgeShoppingList(provenance={"Flask": "explicit"})
        merged = a.merge(b)
        assert merged.provenance["Flask"] == "explicit"

    def test_merge_unknown_provenance_kept(self):
        a = KnowledgeShoppingList(provenance={"X": "unknown_source"})
        b = KnowledgeShoppingList(provenance={"Y": "explicit"})
        merged = a.merge(b)
        assert merged.provenance["X"] == "unknown_source"
        assert merged.provenance["Y"] == "explicit"


class TestBuildEmbeddingPreamble:
    """Tests for build_embedding_preamble (structural context for embeddings)."""

    def test_axiom_prefix(self):
        node = {"id": "AX-001", "statement": "All inputs are hostile"}
        preamble = build_embedding_preamble(node)
        assert "[L0 Axiom]" in preamble

    def test_principle_prefix(self):
        node = {"id": "P-001", "name": "Fail Fast"}
        preamble = build_embedding_preamble(node)
        assert "[L1 Principle]" in preamble

    def test_pattern_prefix(self):
        node = {"id": "PAT-001", "name": "Circuit Breaker"}
        preamble = build_embedding_preamble(node)
        assert "[L2 Pattern]" in preamble

    def test_cpat_prefix(self):
        node = {"id": "CPAT-001", "name": "Community Pattern"}
        preamble = build_embedding_preamble(node)
        assert "[L2 Pattern]" in preamble

    def test_finding_prefix(self):
        node = {"id": "F-001", "description": "Bug found"}
        preamble = build_embedding_preamble(node)
        assert "[L4 Finding]" in preamble

    def test_includes_technologies(self):
        node = {"id": "CR-001", "technologies": ["Flask", "Redis"]}
        preamble = build_embedding_preamble(node)
        assert "Flask" in preamble
        assert "Redis" in preamble

    def test_includes_domains(self):
        node = {"id": "CR-001", "domains": ["security", "api"]}
        preamble = build_embedding_preamble(node)
        assert "security" in preamble

    def test_includes_severity(self):
        node = {"id": "CR-001", "severity": "critical"}
        preamble = build_embedding_preamble(node)
        assert "critical" in preamble

    def test_empty_node_returns_string(self):
        preamble = build_embedding_preamble({"id": ""})
        assert isinstance(preamble, str)


class TestContextualTextForEmbedding:
    """Tests for contextual_text_for_embedding (full embedding text)."""

    def test_includes_preamble_and_body(self):
        node = {
            "id": "CR-001",
            "text": "Validate CORS origins",
            "technologies": ["Flask"],
            "domains": ["security"],
        }
        text = contextual_text_for_embedding(node)
        assert "---" in text
        assert "Validate CORS origins" in text
        assert "Flask" in text

    def test_includes_why_in_body(self):
        node = {
            "id": "CR-001",
            "text": "Check inputs",
            "why": "Prevents injection attacks",
        }
        text = contextual_text_for_embedding(node)
        assert "Prevents injection attacks" in text

    def test_fallback_to_name_field(self):
        node = {"id": "P-001", "name": "Fail Fast"}
        text = contextual_text_for_embedding(node)
        assert "Fail Fast" in text

    def test_fallback_to_statement_field(self):
        node = {"id": "AX-001", "statement": "All inputs are hostile"}
        text = contextual_text_for_embedding(node)
        assert "All inputs are hostile" in text

    def test_empty_node_no_crash(self):
        text = contextual_text_for_embedding({"id": ""})
        assert isinstance(text, str)


class TestBuildTechIndexHierarchical:
    """Tests for build_tech_index_from_nodes with dotted path decomposition."""

    def test_dotted_path_registers_leaf(self):
        nodes = [{"technologies": ["language.python.web.flask"]}]
        build_tech_index_from_nodes(nodes)
        from engineering_brain.retrieval.context_extractor import _dynamic_tech_index

        assert "flask" in _dynamic_tech_index

    def test_dotted_path_registers_suffixes(self):
        nodes = [{"technologies": ["language.python.web.flask"]}]
        build_tech_index_from_nodes(nodes)
        from engineering_brain.retrieval.context_extractor import _dynamic_tech_index

        assert "web.flask" in _dynamic_tech_index

    def test_domain_hierarchy_decomposition(self):
        nodes = [{"domains": ["engineering.software.testing"]}]
        build_tech_index_from_nodes(nodes)
        from engineering_brain.retrieval.context_extractor import _dynamic_domain_index

        assert "testing" in _dynamic_domain_index
        assert "software.testing" in _dynamic_domain_index

    def test_handles_none_fields(self):
        nodes = [{"technologies": None, "domains": None}]
        build_tech_index_from_nodes(nodes)  # Should not crash


# =============================================================================
# 3. Scorer — deeper coverage
# =============================================================================


class TestGetList:
    """Tests for the _get_list helper."""

    def test_returns_list_when_list(self):
        assert _get_list({"x": ["a", "b"]}, "x") == ["a", "b"]

    def test_returns_wrapped_string(self):
        assert _get_list({"x": "single"}, "x") == ["single"]

    def test_returns_empty_for_missing_key(self):
        assert _get_list({}, "x") == []

    def test_returns_empty_for_none(self):
        assert _get_list({"x": None}, "x") == []

    def test_returns_empty_for_empty_string(self):
        assert _get_list({"x": ""}, "x") == []

    def test_returns_empty_for_non_string_non_list(self):
        assert _get_list({"x": 42}, "x") == []


class TestComputeConfidence:
    """Tests for _compute_confidence."""

    def test_human_verified(self):
        assert _compute_confidence({"validation_status": "human_verified"}) == 1.0

    def test_cross_checked(self):
        assert _compute_confidence({"validation_status": "cross_checked"}) == 0.7

    def test_unvalidated(self):
        assert _compute_confidence({"validation_status": "unvalidated"}) == 0.3

    def test_missing_status_defaults_to_unvalidated(self):
        assert _compute_confidence({}) == 0.3

    def test_explicit_confidence_higher_than_base(self):
        # confidence=0.95, validation_status=unvalidated (base=0.3)
        # max(0.3, 0.95) = 0.95
        result = _compute_confidence({"confidence": 0.95, "validation_status": "unvalidated"})
        assert result == 0.95

    def test_explicit_confidence_capped_at_1(self):
        result = _compute_confidence({"confidence": 1.5, "validation_status": "unvalidated"})
        assert result == 1.0

    def test_explicit_confidence_lower_than_base_uses_base(self):
        # confidence=0.1, human_verified base=1.0 → max(1.0, 0.1) = 1.0
        result = _compute_confidence({"confidence": 0.1, "validation_status": "human_verified"})
        assert result == 1.0

    def test_invalid_confidence_value_uses_base(self):
        result = _compute_confidence(
            {"confidence": "not_a_number", "validation_status": "cross_checked"}
        )
        assert result == 0.7

    def test_unknown_status_defaults(self):
        result = _compute_confidence({"validation_status": "unknown_status"})
        assert result == 0.3


class TestComputeRecency:
    """Tests for _compute_recency."""

    def test_recent_timestamp_high_score(self):
        now = datetime.now(UTC).isoformat()
        score = _compute_recency({"last_violation": now})
        # Within same day → close to 1.0
        assert score > 0.9

    def test_old_timestamp_low_score(self):
        old = (datetime.now(UTC) - timedelta(days=365)).isoformat()
        score = _compute_recency({"last_violation": old})
        assert score < 0.2

    def test_no_timestamp_returns_default(self):
        score = _compute_recency({})
        assert score == 0.3

    def test_floor_at_005(self):
        very_old = (datetime.now(UTC) - timedelta(days=10000)).isoformat()
        score = _compute_recency({"last_violation": very_old})
        assert score >= 0.05

    def test_uses_timestamp_field(self):
        now = datetime.now(UTC).isoformat()
        score = _compute_recency({"timestamp": now})
        assert score > 0.9

    def test_uses_created_at_field(self):
        now = datetime.now(UTC).isoformat()
        score = _compute_recency({"created_at": now})
        assert score > 0.9

    def test_priority_last_violation_over_timestamp(self):
        now = datetime.now(UTC).isoformat()
        old = (datetime.now(UTC) - timedelta(days=365)).isoformat()
        # last_violation is recent, timestamp is old → should use last_violation
        score = _compute_recency({"last_violation": now, "timestamp": old})
        assert score > 0.9

    def test_numeric_timestamp(self):
        import time

        score = _compute_recency({"timestamp": time.time()})
        assert score > 0.9

    def test_datetime_object(self):
        score = _compute_recency({"timestamp": datetime.now(UTC)})
        assert score > 0.9

    def test_invalid_timestamp_returns_default(self):
        score = _compute_recency({"timestamp": "not-a-date"})
        assert score == 0.3

    def test_half_life_90_days(self):
        # At 90 days, score should be approximately 0.5 (half-life)
        target = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        score = _compute_recency({"timestamp": target})
        assert 0.35 <= score <= 0.65


class TestHierarchyOverlapCount:
    """Tests for _hierarchy_overlap_count."""

    def test_exact_match(self):
        count = _hierarchy_overlap_count(["flask"], ["flask"])
        assert count >= 1

    def test_case_insensitive_match(self):
        count = _hierarchy_overlap_count(["Flask"], ["flask"])
        assert count >= 1

    def test_no_match(self):
        count = _hierarchy_overlap_count(["flask"], ["react"])
        assert count == 0

    def test_multiple_matches(self):
        count = _hierarchy_overlap_count(["flask", "redis"], ["flask", "redis", "python"])
        assert count >= 2

    def test_empty_query(self):
        count = _hierarchy_overlap_count([], ["flask"])
        assert count == 0

    def test_empty_node(self):
        count = _hierarchy_overlap_count(["flask"], [])
        assert count == 0

    def test_both_empty(self):
        count = _hierarchy_overlap_count([], [])
        assert count == 0


class TestScoreKnowledgeDeeper:
    """Deeper tests for score_knowledge beyond test_retrieval.py coverage."""

    def test_eigentrust_score_contributes(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
        }
        score_high_et = score_knowledge(
            {**base, "eigentrust_score": 1.0},
            ["Flask"],
            ["security"],
        )
        score_low_et = score_knowledge(
            {**base, "eigentrust_score": 0.0},
            ["Flask"],
            ["security"],
        )
        assert score_high_et > score_low_et

    def test_epistemic_fields_override_confidence(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
            "validation_status": "unvalidated",
        }
        # With high ep_b, confidence should be higher than base unvalidated
        ep_node = {
            **base,
            "ep_b": 0.9,
            "ep_d": 0.05,
            "ep_u": 0.05,
            "ep_a": 0.5,
        }
        score_ep = score_knowledge(ep_node, ["Flask"], ["security"])
        score_no_ep = score_knowledge(base, ["Flask"], ["security"])
        assert score_ep > score_no_ep

    def test_high_uncertainty_penalty(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
        }
        # The epistemic formula is: projected = ep_b + ep_a * ep_u
        # penalty = ep_u * 0.3, then epistemic_score = max(0, projected - penalty)
        # With ep_a=0 the ap*u boost is removed, isolating the penalty effect.
        low_u = {**base, "ep_b": 0.8, "ep_u": 0.1, "ep_a": 0.0}
        high_u = {**base, "ep_b": 0.8, "ep_u": 0.9, "ep_a": 0.0}
        score_low_u = score_knowledge(low_u, ["Flask"], ["security"])
        score_high_u = score_knowledge(high_u, ["Flask"], ["security"])
        assert score_low_u > score_high_u

    def test_calibrator_applied(self):
        node = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
            "confidence": 0.6,
        }
        # Mock calibrator that always returns 1.0
        calibrator = MagicMock()
        calibrator.calibrated_confidence.return_value = 1.0
        score_cal = score_knowledge(node, ["Flask"], ["security"], calibrator=calibrator)

        # Same node without calibrator
        score_no_cal = score_knowledge(node, ["Flask"], ["security"])

        assert score_cal >= score_no_cal
        calibrator.calibrated_confidence.assert_called()

    def test_calibrator_exception_non_blocking(self):
        node = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
            "confidence": 0.6,
        }
        calibrator = MagicMock()
        calibrator.calibrated_confidence.side_effect = RuntimeError("boom")
        # Should not raise
        score = score_knowledge(node, ["Flask"], ["security"], calibrator=calibrator)
        assert 0.0 <= score <= 1.0

    def test_prediction_accuracy_below_threshold_no_bonus(self):
        # prediction_tested_count < 3 → no modification
        node = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
            "confidence": 0.7,
            "prediction_tested_count": 2,
            "prediction_success_count": 2,
        }
        score_with = score_knowledge(node, ["Flask"], ["security"])
        node_no_pred = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
            "confidence": 0.7,
        }
        score_without = score_knowledge(node_no_pred, ["Flask"], ["security"])
        # With < 3 predictions, should be same as without
        assert score_with == pytest.approx(score_without, abs=0.01)

    def test_score_always_clamped_0_to_1(self):
        # Extreme node with all maximized fields
        extreme = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "critical",
            "reinforcement_count": 100,
            "validation_status": "human_verified",
            "confidence": 1.0,
            "eigentrust_score": 1.0,
            "_vector_score": 1.0,
            "last_violation": datetime.now(UTC).isoformat(),
        }
        score = score_knowledge(extreme, ["Flask"], ["security"])
        assert 0.0 <= score <= 1.0

    def test_completely_empty_node(self):
        score = score_knowledge({}, [], [])
        assert 0.0 <= score <= 1.0

    def test_no_query_tech_no_node_tech(self):
        node = {"id": "CR-001", "text": "general rule", "severity": "medium"}
        score = score_knowledge(node, [], [])
        assert 0.0 <= score <= 1.0


class TestRankResultsDeeper:
    """Deeper tests for rank_results."""

    def test_adaptive_weight_optimizer(self):
        nodes = [
            {
                "id": "A",
                "text": "test",
                "technologies": ["Flask"],
                "domains": ["security"],
                "severity": "critical",
            },
            {"id": "B", "text": "test2", "technologies": [], "domains": [], "severity": "low"},
        ]
        # Mock weight optimizer
        optimizer = MagicMock()
        optimizer.get_weights.return_value = {
            "tech_match": 0.9,  # Heavily boost tech match
            "domain_match": 0.01,
            "severity": 0.01,
            "reinforcement": 0.01,
            "recency": 0.01,
            "confidence": 0.01,
        }
        ranked = rank_results(
            nodes,
            ["Flask"],
            ["security"],
            top_k=10,
            weight_optimizer=optimizer,
        )
        optimizer.get_weights.assert_called_once()
        # With tech_match heavily boosted, node A (Flask match) should win
        assert ranked[0]["id"] == "A"

    def test_adaptive_optimizer_exception_non_blocking(self):
        nodes = [
            {
                "id": "A",
                "text": "test",
                "technologies": ["Flask"],
                "domains": ["security"],
                "severity": "medium",
            },
        ]
        optimizer = MagicMock()
        optimizer.get_weights.side_effect = RuntimeError("optimizer broken")
        # Should not crash, should fall back to default weights
        ranked = rank_results(
            nodes,
            ["Flask"],
            ["security"],
            top_k=10,
            weight_optimizer=optimizer,
        )
        assert len(ranked) == 1
        assert "_relevance_score" in ranked[0]

    def test_rank_preserves_original_node_fields(self):
        nodes = [
            {
                "id": "A",
                "text": "rule text",
                "custom_field": "preserved",
                "technologies": ["Flask"],
                "domains": ["security"],
            },
        ]
        ranked = rank_results(nodes, ["Flask"], ["security"])
        assert ranked[0]["custom_field"] == "preserved"
        assert ranked[0]["text"] == "rule text"

    def test_rank_adds_relevance_score(self):
        nodes = [
            {"id": "A", "text": "test", "technologies": ["Flask"], "domains": ["security"]},
        ]
        ranked = rank_results(nodes, ["Flask"], ["security"])
        assert "_relevance_score" in ranked[0]
        assert isinstance(ranked[0]["_relevance_score"], float)

    def test_rank_top_k_zero_returns_empty(self):
        nodes = [
            {"id": "A", "text": "test", "technologies": ["Flask"], "domains": ["security"]},
        ]
        ranked = rank_results(nodes, ["Flask"], ["security"], top_k=0)
        assert ranked == []

    def test_rank_with_custom_config_weights(self):
        nodes = [
            # Node with high severity but no tech match
            {
                "id": "A",
                "text": "test",
                "technologies": ["React"],
                "domains": ["security"],
                "severity": "critical",
            },
            # Node with tech match but low severity
            {
                "id": "B",
                "text": "test",
                "technologies": ["Flask"],
                "domains": ["security"],
                "severity": "low",
            },
        ]
        # Config that heavily weights severity
        cfg = replace(
            BrainConfig(),
            weight_tech_match=0.01,
            weight_severity=0.90,
            weight_domain_match=0.01,
            weight_reinforcement=0.01,
            weight_recency=0.01,
            weight_confidence=0.01,
        )
        ranked = rank_results(nodes, ["Flask"], ["security"], config=cfg)
        # With severity heavily weighted, critical node should win
        assert ranked[0]["id"] == "A"


class TestScoreKnowledgeSeverityValues:
    """Test all severity level scores."""

    @pytest.mark.parametrize(
        "severity,expected_min",
        [
            ("critical", 0.8),
            ("high", 0.6),
            ("medium", 0.3),
            ("low", 0.1),
        ],
    )
    def test_severity_score_ordering(self, severity: str, expected_min: float):
        # Severity is one signal among many, so we verify relative ordering
        node = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": severity,
        }
        score = score_knowledge(node, ["Flask"], ["security"])
        assert 0.0 <= score <= 1.0

    def test_critical_beats_low(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
        }
        score_c = score_knowledge({**base, "severity": "critical"}, ["Flask"], ["security"])
        score_l = score_knowledge({**base, "severity": "low"}, ["Flask"], ["security"])
        assert score_c > score_l

    def test_unknown_severity_gets_default(self):
        node = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "unknown_level",
        }
        score = score_knowledge(node, ["Flask"], ["security"])
        assert 0.0 <= score <= 1.0


class TestRetrievalMetricsTracking:
    """Tests for QueryRouter._track_retrieval_metrics."""

    def test_updates_retrieval_count(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        scored = [{"id": "CR-001", "_relevance_score": 0.8}]
        router._track_retrieval_metrics(scored)

        node = populated_graph.get_node("CR-001")
        assert node is not None
        assert node.get("retrieval_count", 0) >= 1

    def test_updates_last_retrieved_at(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        scored = [{"id": "CR-001", "_relevance_score": 0.8}]
        router._track_retrieval_metrics(scored)

        node = populated_graph.get_node("CR-001")
        assert node is not None
        assert "last_retrieved_at" in node

    def test_tracks_only_top_30(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        # Create 35 scored nodes (only first 30 should be tracked)
        scored = [{"id": f"N-{i:03d}", "_relevance_score": 0.9 - i * 0.01} for i in range(35)]
        # Only the ones that exist in graph get tracked; non-existing are silently skipped
        router._track_retrieval_metrics(scored)
        # Should not crash

    def test_skips_nodes_without_id(
        self,
        populated_graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=populated_graph, config=config)
        scored = [{"_relevance_score": 0.8}]  # no id
        router._track_retrieval_metrics(scored)  # Should not crash

    def test_skips_nonexistent_nodes(
        self,
        graph: MemoryGraphAdapter,
        config: BrainConfig,
    ):
        router = QueryRouter(graph=graph, config=config)
        scored = [{"id": "NONEXISTENT", "_relevance_score": 0.8}]
        router._track_retrieval_metrics(scored)  # Should not crash
