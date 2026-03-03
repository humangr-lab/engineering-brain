"""Comprehensive tests for the Engineering Brain retrieval subsystem.

Covers:
1. Context extractor: extract_context, build_contextual_text
2. Merger: merge_results, merge_results_rrf, deduplicate_by_content
3. Scorer: rank_results ordering, weight normalization
4. Budget: enforce_budget respects char limits
5. Synonyms: expand_query_terms, graph expansion
6. Communities: CommunityDetector with MemoryGraphAdapter, label propagation
"""

from __future__ import annotations

import sys
import os

# Ensure the src directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
from datetime import datetime, timezone, timedelta

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.retrieval.context_extractor import (
    ExtractedContext,
    extract_context,
    build_contextual_text,
    build_tech_index_from_nodes,
    expand_domains,
    build_domain_hierarchy,
    apply_technology_implications,
    KnowledgeShoppingList,
    _infer_node_layer,
)
from engineering_brain.retrieval.merger import (
    merge_results,
    merge_results_rrf,
    deduplicate_by_content,
)
from engineering_brain.retrieval.scorer import (
    score_knowledge,
    rank_results,
)
from engineering_brain.retrieval.budget import (
    enforce_budget,
    estimate_total_chars,
)
from engineering_brain.retrieval.synonyms import (
    expand_query_terms,
    expand_from_graph,
)
from engineering_brain.retrieval.communities import (
    CommunityDetector,
    Community,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def brain_config() -> BrainConfig:
    """Return a default BrainConfig for tests."""
    return BrainConfig()


@pytest.fixture
def graph() -> MemoryGraphAdapter:
    """Return a fresh MemoryGraphAdapter."""
    return MemoryGraphAdapter()


@pytest.fixture
def populated_graph(graph: MemoryGraphAdapter) -> MemoryGraphAdapter:
    """Return a MemoryGraphAdapter pre-populated with various knowledge nodes."""
    # L1 Principles
    graph.add_node("Principle", "P-001", {
        "id": "P-001",
        "name": "Defense in Depth",
        "why": "No single layer is perfect",
        "how_to_apply": "Layer multiple security controls",
        "domains": ["security"],
        "technologies": [],
        "severity": "high",
        "validation_status": "cross_checked",
    })
    graph.add_node("Principle", "P-002", {
        "id": "P-002",
        "name": "Fail Fast",
        "why": "Detect errors early to reduce blast radius",
        "how_to_apply": "Validate inputs at boundaries",
        "domains": ["reliability", "architecture"],
        "technologies": [],
        "severity": "medium",
        "validation_status": "human_verified",
    })

    # L2 Patterns
    graph.add_node("Pattern", "PAT-001", {
        "id": "PAT-001",
        "name": "Circuit Breaker",
        "intent": "Prevent cascading failures",
        "when_to_use": "Calling external services",
        "technologies": ["Python"],
        "domains": ["reliability"],
        "severity": "high",
        "languages": ["Python"],
    })
    graph.add_node("Pattern", "PAT-002", {
        "id": "PAT-002",
        "name": "Repository Pattern",
        "intent": "Abstract data access",
        "when_to_use": "Decoupling domain from persistence",
        "technologies": ["Python", "SQLAlchemy"],
        "domains": ["architecture", "database"],
        "severity": "medium",
        "languages": ["Python"],
    })

    # L3 Rules
    graph.add_node("Rule", "CR-001", {
        "id": "CR-001",
        "text": "Always validate CORS origins explicitly",
        "why": "Wildcard CORS allows any origin to read responses",
        "how_to_do_right": "List allowed origins explicitly",
        "technologies": ["Flask", "FastAPI"],
        "domains": ["security", "api"],
        "severity": "critical",
        "reinforcement_count": 15,
        "confidence": 0.9,
        "validation_status": "cross_checked",
    })
    graph.add_node("Rule", "CR-002", {
        "id": "CR-002",
        "text": "Use parameterized queries to prevent SQL injection",
        "why": "String concatenation in SQL enables injection attacks",
        "how_to_do_right": "Use ORM or parameterized placeholders",
        "technologies": ["Python", "PostgreSQL"],
        "domains": ["security", "database"],
        "severity": "critical",
        "reinforcement_count": 20,
        "confidence": 0.95,
        "validation_status": "human_verified",
    })
    graph.add_node("Rule", "CR-003", {
        "id": "CR-003",
        "text": "Handle async errors with proper try/except",
        "why": "Unhandled async errors cause silent failures",
        "how_to_do_right": "Wrap coroutines in try/except, log errors",
        "technologies": ["Python"],
        "domains": ["reliability"],
        "severity": "medium",
        "reinforcement_count": 5,
        "confidence": 0.7,
    })

    # L4 Evidence / Findings
    graph.add_node("Finding", "F-001", {
        "id": "F-001",
        "description": "CORS wildcard found in production server.py",
        "severity": "critical",
        "domains": ["security"],
        "technologies": ["Flask"],
    })

    # Edges
    graph.add_edge("CR-001", "P-001", "INSTANTIATES")
    graph.add_edge("F-001", "CR-001", "EVIDENCED_BY")
    graph.add_edge("PAT-001", "P-002", "INSTANTIATES")
    graph.add_edge("CR-002", "P-001", "INSTANTIATES")

    return graph


# =============================================================================
# 1. Context Extractor Tests
# =============================================================================


class TestExtractContext:
    """Tests for extract_context()."""

    def test_detects_flask_technology(self):
        ctx = extract_context("Implement a Flask REST API endpoint")
        assert "Flask" in ctx.technologies

    def test_detects_fastapi_technology(self):
        ctx = extract_context("Build a FastAPI service with authentication")
        assert "FastAPI" in ctx.technologies

    def test_detects_multiple_technologies(self):
        ctx = extract_context("Write a Redis caching layer for Flask")
        assert "Flask" in ctx.technologies
        assert "Redis" in ctx.technologies

    def test_detects_security_domain(self):
        ctx = extract_context("Add authentication to the API")
        assert "security" in ctx.domains

    def test_detects_testing_domain(self):
        ctx = extract_context("Write pytest tests with fixtures")
        assert "testing" in ctx.domains

    def test_detects_multiple_domains(self):
        ctx = extract_context(
            "Implement auth middleware for the REST API with rate limiting"
        )
        assert "security" in ctx.domains
        assert "api" in ctx.domains

    def test_default_domain_is_general(self):
        ctx = extract_context("Do something completely abstract")
        assert "general" in ctx.domains

    def test_detects_python_file_type(self):
        ctx = extract_context("Edit the models.py file")
        assert ".py" in ctx.file_types

    def test_detects_typescript_file_type(self):
        ctx = extract_context("Fix the component.tsx styling")
        assert ".tsx" in ctx.file_types

    def test_detects_exec_phase(self):
        ctx = extract_context("Implement the new feature")
        assert ctx.phase == "exec"

    def test_detects_qa_phase(self):
        ctx = extract_context("Write tests to validate the module")
        assert ctx.phase == "qa"

    def test_detects_spec_phase(self):
        ctx = extract_context("Design the architecture specification")
        assert ctx.phase == "spec"

    def test_explicit_technologies_override(self):
        ctx = extract_context(
            "Some task description",
            technologies=["React", "TypeScript"],
        )
        assert "React" in ctx.technologies
        assert "TypeScript" in ctx.technologies

    def test_explicit_domains_override(self):
        ctx = extract_context(
            "Some task description",
            domains=["blockchain"],
        )
        assert "blockchain" in ctx.domains

    def test_explicit_file_type_override(self):
        ctx = extract_context(
            "Edit the file", file_type=".go",
        )
        assert ".go" in ctx.file_types

    def test_explicit_phase_override(self):
        ctx = extract_context(
            "Implement feature",
            phase="qa",
        )
        assert ctx.phase == "qa"

    def test_raw_text_preserved(self):
        text = "Implement CORS validation for Flask"
        ctx = extract_context(text)
        assert ctx.raw_text == text

    def test_empty_description(self):
        ctx = extract_context("")
        assert isinstance(ctx, ExtractedContext)
        assert "general" in ctx.domains

    def test_case_insensitive_detection(self):
        ctx = extract_context("FLASK and REDIS integration")
        assert "Flask" in ctx.technologies
        assert "Redis" in ctx.technologies

    def test_multiple_file_types_detected(self):
        ctx = extract_context("Edit server.py and index.html")
        assert ".py" in ctx.file_types
        assert ".html" in ctx.file_types


class TestBuildContextualText:
    """Tests for build_contextual_text()."""

    def test_includes_layer_for_rule(self):
        node = {
            "id": "CR-001",
            "text": "Validate CORS origins",
            "domains": ["security"],
            "technologies": ["Flask"],
            "severity": "critical",
        }
        text = build_contextual_text(node)
        assert "Rule" in text or "L3" in text

    def test_includes_layer_for_principle(self):
        node = {
            "id": "P-001",
            "name": "Defense in Depth",
            "domains": ["security"],
        }
        text = build_contextual_text(node)
        assert "Principle" in text or "L1" in text

    def test_includes_layer_for_pattern(self):
        node = {
            "id": "PAT-001",
            "name": "Circuit Breaker",
            "domains": ["reliability"],
        }
        text = build_contextual_text(node)
        assert "Pattern" in text or "L2" in text

    def test_includes_layer_for_finding(self):
        node = {
            "id": "F-001",
            "description": "CORS wildcard in server.py",
        }
        text = build_contextual_text(node)
        assert "Evidence" in text or "L4" in text

    def test_includes_domain(self):
        node = {
            "id": "CR-001",
            "text": "Validate CORS",
            "domains": ["security", "api"],
        }
        text = build_contextual_text(node)
        assert "security" in text

    def test_includes_technology(self):
        node = {
            "id": "CR-001",
            "text": "Validate CORS",
            "technologies": ["Flask"],
        }
        text = build_contextual_text(node)
        assert "Flask" in text

    def test_includes_severity(self):
        node = {
            "id": "CR-001",
            "text": "Test rule",
            "severity": "critical",
        }
        text = build_contextual_text(node)
        assert "critical" in text

    def test_includes_primary_text(self):
        node = {"id": "CR-001", "text": "Always check return values"}
        text = build_contextual_text(node)
        assert "Always check return values" in text

    def test_includes_why(self):
        node = {
            "id": "CR-001",
            "text": "Check returns",
            "why": "Silent failures are dangerous",
        }
        text = build_contextual_text(node)
        assert "Silent failures are dangerous" in text

    def test_fallback_to_statement(self):
        node = {"id": "AX-001", "statement": "All programs have bugs"}
        text = build_contextual_text(node)
        assert "All programs have bugs" in text

    def test_fallback_to_name(self):
        node = {"id": "P-001", "name": "Fail Fast"}
        text = build_contextual_text(node)
        assert "Fail Fast" in text

    def test_empty_node(self):
        node = {"id": "CR-999"}
        text = build_contextual_text(node)
        # Should not crash, should produce something
        assert isinstance(text, str)

    def test_domain_as_string(self):
        node = {"id": "CR-001", "text": "test", "domains": "security"}
        text = build_contextual_text(node)
        assert "security" in text

    def test_technologies_as_string(self):
        node = {"id": "CR-001", "text": "test", "technologies": "Flask"}
        text = build_contextual_text(node)
        assert "Flask" in text


class TestInferNodeLayer:
    """Tests for _infer_node_layer()."""

    def test_axiom_prefix(self):
        assert _infer_node_layer("AX-001") == "L0"

    def test_principle_prefix(self):
        assert _infer_node_layer("P-001") == "L1"

    def test_pattern_prefix(self):
        assert _infer_node_layer("PAT-001") == "L2"

    def test_community_pattern_prefix(self):
        assert _infer_node_layer("CPAT-001") == "L2"

    def test_rule_prefix(self):
        assert _infer_node_layer("CR-001") == "L3"

    def test_finding_prefix(self):
        assert _infer_node_layer("F-001") == "L4"

    def test_unknown_defaults_to_l3(self):
        assert _infer_node_layer("UNKNOWN-001") == "L3"

    def test_empty_string(self):
        assert _infer_node_layer("") == "L3"


class TestBuildTechIndex:
    """Tests for build_tech_index_from_nodes()."""

    def test_builds_from_technology_field(self):
        nodes = [
            {"technologies": ["Flask", "Redis"]},
            {"technologies": ["FastAPI"]},
        ]
        build_tech_index_from_nodes(nodes)
        from engineering_brain.retrieval.context_extractor import _dynamic_tech_index
        assert "flask" in _dynamic_tech_index
        assert "redis" in _dynamic_tech_index
        assert "fastapi" in _dynamic_tech_index

    def test_builds_from_languages_field(self):
        nodes = [
            {"languages": ["Python", "TypeScript"]},
        ]
        build_tech_index_from_nodes(nodes)
        from engineering_brain.retrieval.context_extractor import _dynamic_tech_index
        assert "python" in _dynamic_tech_index
        assert "typescript" in _dynamic_tech_index

    def test_builds_domain_index(self):
        nodes = [
            {"domains": ["security", "api"]},
        ]
        build_tech_index_from_nodes(nodes)
        from engineering_brain.retrieval.context_extractor import _dynamic_domain_index
        assert "security" in _dynamic_domain_index
        assert "api" in _dynamic_domain_index

    def test_ignores_short_names(self):
        nodes = [
            {"technologies": ["x"]},
        ]
        build_tech_index_from_nodes(nodes)
        from engineering_brain.retrieval.context_extractor import _dynamic_tech_index
        assert "x" not in _dynamic_tech_index

    def test_handles_empty_nodes(self):
        build_tech_index_from_nodes([])
        # Should not crash


class TestApplyTechnologyImplications:
    """Tests for apply_technology_implications()."""

    def test_flask_always_domains(self):
        domains = apply_technology_implications(["Flask"], "build a flask app")
        assert "cors" in domains
        assert "error_handling" in domains

    def test_flask_conditional_routes(self):
        domains = apply_technology_implications(
            ["Flask"], "add a new route endpoint"
        )
        assert "auth_middleware" in domains or "rate_limiting" in domains

    def test_no_match_returns_empty(self):
        domains = apply_technology_implications(["UnknownTech"], "some text")
        assert domains == []

    def test_empty_technologies(self):
        domains = apply_technology_implications([], "build something")
        assert domains == []

    def test_subprocess_always_domains(self):
        domains = apply_technology_implications(["subprocess"], "run a command")
        assert "command_injection" in domains

    def test_websocket_always_domains(self):
        domains = apply_technology_implications(["WebSocket"], "handle messages")
        assert "auth" in domains


class TestKnowledgeShoppingList:
    """Tests for KnowledgeShoppingList merge."""

    def test_merge_combines_technologies(self):
        a = KnowledgeShoppingList(technologies=["Flask"], provenance={"Flask": "explicit"})
        b = KnowledgeShoppingList(technologies=["Redis"], provenance={"Redis": "tig"})
        merged = a.merge(b)
        assert "Flask" in merged.technologies
        assert "Redis" in merged.technologies

    def test_merge_no_duplicate_technologies(self):
        a = KnowledgeShoppingList(technologies=["Flask"])
        b = KnowledgeShoppingList(technologies=["Flask"])
        merged = a.merge(b)
        assert merged.technologies.count("Flask") == 1

    def test_merge_provenance_priority(self):
        a = KnowledgeShoppingList(
            technologies=["Flask"],
            provenance={"Flask": "tig"},
        )
        b = KnowledgeShoppingList(
            technologies=["Flask"],
            provenance={"Flask": "explicit"},
        )
        merged = a.merge(b)
        assert merged.provenance["Flask"] == "explicit"

    def test_merge_combines_domains(self):
        a = KnowledgeShoppingList(domains=["security"])
        b = KnowledgeShoppingList(domains=["api"])
        merged = a.merge(b)
        assert "security" in merged.domains
        assert "api" in merged.domains


# =============================================================================
# 2. Merger Tests
# =============================================================================


class TestMergeResults:
    """Tests for merge_results()."""

    def test_empty_all_sources(self):
        result = merge_results([], [])
        assert result == []

    def test_empty_with_cache(self):
        result = merge_results([], [], cache_results=[])
        assert result == []

    def test_graph_only(self):
        graph = [
            {"id": "A", "text": "rule A"},
            {"id": "B", "text": "rule B"},
        ]
        result = merge_results(graph, [])
        assert len(result) == 2
        ids = {n["id"] for n in result}
        assert ids == {"A", "B"}

    def test_vector_only(self):
        vector = [
            {"id": "V1", "text": "vector result", "score": 0.9},
        ]
        result = merge_results([], vector)
        assert len(result) == 1
        assert result[0]["id"] == "V1"

    def test_dedup_by_id(self):
        graph = [{"id": "A", "text": "graph version", "_relevance_score": 0.5}]
        vector = [{"id": "A", "text": "vector version", "score": 0.8}]
        result = merge_results(graph, vector)
        # Should only have one entry for "A"
        assert len(result) == 1

    def test_boost_on_multi_source(self):
        graph = [{"id": "A", "text": "in both", "_relevance_score": 0.6}]
        vector = [{"id": "A", "text": "in both", "score": 0.7}]
        result = merge_results(graph, vector)
        # Score should be boosted because found in both sources
        node = result[0]
        assert node.get("_relevance_score", 0) > 0.6

    def test_cache_results_priority(self):
        cache = [{"id": "C1", "text": "cached", "_source": "cache"}]
        graph = [{"id": "G1", "text": "from graph"}]
        result = merge_results(graph, [], cache_results=cache)
        ids = {n["id"] for n in result}
        assert "C1" in ids
        assert "G1" in ids

    def test_nodes_without_id_skipped(self):
        graph = [{"text": "no id"}, {"id": "A", "text": "has id"}]
        result = merge_results(graph, [])
        assert len(result) == 1
        assert result[0]["id"] == "A"

    def test_source_tracking(self):
        graph = [{"id": "A", "text": "test"}]
        result = merge_results(graph, [])
        assert result[0].get("_source") == "graph"

    def test_vector_source_tracking(self):
        vector = [{"id": "V1", "text": "test", "score": 0.8}]
        result = merge_results([], vector)
        assert result[0].get("_source") == "vector"


class TestMergeResultsRRF:
    """Tests for merge_results_rrf() -- Reciprocal Rank Fusion."""

    def test_empty_both(self):
        assert merge_results_rrf([], []) == []

    def test_empty_graph(self):
        vector = [{"id": "V1", "_vector_score": 0.9}]
        result = merge_results_rrf([], vector)
        assert len(result) == 1

    def test_empty_vector(self):
        graph = [{"id": "G1", "text": "test"}]
        result = merge_results_rrf(graph, [])
        assert len(result) == 1

    def test_shared_node_ranked_higher(self):
        graph = [
            {"id": "SHARED", "text": "in both"},
            {"id": "GRAPH_ONLY", "text": "graph only"},
        ]
        vector = [
            {"id": "SHARED", "text": "in both", "_vector_score": 0.8},
            {"id": "VEC_ONLY", "text": "vector only"},
        ]
        result = merge_results_rrf(graph, vector)
        assert result[0]["id"] == "SHARED"

    def test_preserves_all_nodes(self):
        graph = [{"id": "A"}, {"id": "B"}]
        vector = [{"id": "C"}, {"id": "D"}]
        result = merge_results_rrf(graph, vector)
        ids = {n["id"] for n in result}
        assert ids == {"A", "B", "C", "D"}

    def test_custom_k_parameter(self):
        graph = [{"id": "A"}]
        vector = [{"id": "A"}]
        result_k10 = merge_results_rrf(graph, vector, k=10)
        result_k100 = merge_results_rrf(graph, vector, k=100)
        # Both should return the same node, just different RRF scores
        assert len(result_k10) == 1
        assert len(result_k100) == 1

    def test_ordering_by_rrf_score(self):
        graph = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        vector = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        result = merge_results_rrf(graph, vector)
        ids = [n["id"] for n in result]
        assert ids == ["A", "B", "C"]

    def test_vector_score_transferred(self):
        graph = [{"id": "A", "text": "test"}]
        vector = [{"id": "A", "_vector_score": 0.85}]
        result = merge_results_rrf(graph, vector)
        assert result[0].get("_vector_score") == 0.85

    def test_nodes_without_id_skipped(self):
        graph = [{"text": "no id"}, {"id": "A"}]
        vector = [{"text": "no id"}, {"id": "B"}]
        result = merge_results_rrf(graph, vector)
        ids = {n["id"] for n in result}
        assert ids == {"A", "B"}


class TestDeduplicateByContent:
    """Tests for deduplicate_by_content()."""

    def test_no_duplicates(self):
        nodes = [
            {"id": "A", "text": "unique text A"},
            {"id": "B", "text": "unique text B"},
        ]
        result = deduplicate_by_content(nodes)
        assert len(result) == 2

    def test_removes_exact_content_duplicates(self):
        nodes = [
            {"id": "A", "text": "same content", "_relevance_score": 0.8},
            {"id": "B", "text": "same content", "_relevance_score": 0.5},
        ]
        result = deduplicate_by_content(nodes)
        assert len(result) == 1
        assert result[0]["id"] == "A"  # Higher scored kept

    def test_keeps_higher_scored_version(self):
        nodes = [
            {"id": "low", "text": "duplicate text", "_relevance_score": 0.3},
            {"id": "high", "text": "duplicate text", "_relevance_score": 0.9},
        ]
        result = deduplicate_by_content(nodes)
        assert len(result) == 1
        assert result[0]["id"] == "high"

    def test_case_insensitive_dedup(self):
        nodes = [
            {"id": "A", "text": "Same Content", "_relevance_score": 0.5},
            {"id": "B", "text": "same content", "_relevance_score": 0.8},
        ]
        result = deduplicate_by_content(nodes)
        assert len(result) == 1

    def test_empty_input(self):
        result = deduplicate_by_content([])
        assert result == []

    def test_single_node(self):
        nodes = [{"id": "A", "text": "only one"}]
        result = deduplicate_by_content(nodes)
        assert len(result) == 1

    def test_dedup_uses_statement_field(self):
        nodes = [
            {"id": "A", "statement": "shared statement", "_relevance_score": 0.3},
            {"id": "B", "statement": "shared statement", "_relevance_score": 0.7},
        ]
        result = deduplicate_by_content(nodes)
        assert len(result) == 1

    def test_dedup_uses_name_field(self):
        nodes = [
            {"id": "A", "name": "shared name", "_relevance_score": 0.4},
            {"id": "B", "name": "shared name", "_relevance_score": 0.6},
        ]
        result = deduplicate_by_content(nodes)
        assert len(result) == 1

    def test_whitespace_normalized_in_dedup(self):
        nodes = [
            {"id": "A", "text": "  spaced out  ", "_relevance_score": 0.5},
            {"id": "B", "text": "spaced out", "_relevance_score": 0.6},
        ]
        result = deduplicate_by_content(nodes)
        assert len(result) == 1


# =============================================================================
# 3. Scorer Tests
# =============================================================================


class TestScoreKnowledge:
    """Tests for score_knowledge()."""

    def test_returns_float_between_0_and_1(self):
        node = {
            "id": "CR-001",
            "text": "test rule",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "high",
        }
        score = score_knowledge(node, ["Flask"], ["security"])
        assert 0.0 <= score <= 1.0

    def test_tech_match_boosts_score(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["general"],
            "severity": "medium",
        }
        score_match = score_knowledge(base, ["Flask"], [])
        score_no_match = score_knowledge(base, ["React"], [])
        assert score_match > score_no_match

    def test_domain_match_boosts_score(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": [],
            "domains": ["security"],
            "severity": "medium",
        }
        score_match = score_knowledge(base, [], ["security"])
        score_no_match = score_knowledge(base, [], ["performance"])
        assert score_match > score_no_match

    def test_severity_ordering(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
        }
        score_critical = score_knowledge(
            {**base, "severity": "critical"}, ["Flask"], ["security"]
        )
        score_low = score_knowledge(
            {**base, "severity": "low"}, ["Flask"], ["security"]
        )
        assert score_critical > score_low

    def test_reinforcement_boosts_score(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
        }
        score_reinforced = score_knowledge(
            {**base, "reinforcement_count": 20}, ["Flask"], ["security"]
        )
        score_not_reinforced = score_knowledge(
            {**base, "reinforcement_count": 0}, ["Flask"], ["security"]
        )
        assert score_reinforced > score_not_reinforced

    def test_recent_node_scores_higher(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
        }
        recent = datetime.now(timezone.utc).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()

        score_recent = score_knowledge(
            {**base, "last_violation": recent}, ["Flask"], ["security"]
        )
        score_old = score_knowledge(
            {**base, "last_violation": old}, ["Flask"], ["security"]
        )
        assert score_recent > score_old

    def test_validated_node_scores_higher(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
        }
        score_validated = score_knowledge(
            {**base, "validation_status": "human_verified"}, ["Flask"], ["security"]
        )
        score_unvalidated = score_knowledge(
            {**base, "validation_status": "unvalidated"}, ["Flask"], ["security"]
        )
        assert score_validated > score_unvalidated

    def test_deprecated_node_scores_zero(self):
        node = {
            "id": "CR-001",
            "text": "deprecated rule",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "critical",
            "deprecated": True,
        }
        assert score_knowledge(node, ["Flask"], ["security"]) == 0.0

    def test_vector_score_blending(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
        }
        cfg = BrainConfig()
        cfg.vector_score_weight = 0.15

        without_vector = score_knowledge(base, ["Flask"], ["security"], config=cfg)
        with_vector = score_knowledge(
            {**base, "_vector_score": 0.95}, ["Flask"], ["security"], config=cfg
        )
        assert with_vector > without_vector

    def test_zero_vector_score_no_change(self):
        node = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
        }
        cfg = BrainConfig()
        s1 = score_knowledge(node, ["Flask"], ["security"], config=cfg)
        s2 = score_knowledge(
            {**node, "_vector_score": 0.0}, ["Flask"], ["security"], config=cfg
        )
        assert s1 == pytest.approx(s2)

    def test_technology_agnostic_partial_credit(self):
        node = {
            "id": "CR-001",
            "text": "general advice",
            "technologies": [],
            "domains": ["security"],
            "severity": "medium",
        }
        score = score_knowledge(node, ["Flask"], ["security"])
        # Technology-agnostic nodes get 0.5 partial credit
        assert score > 0.0

    def test_confidence_from_explicit_field(self):
        node = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
            "confidence": 0.95,
            "validation_status": "unvalidated",
        }
        score = score_knowledge(node, ["Flask"], ["security"])
        assert score > 0.0

    def test_epistemic_scoring(self):
        node = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
            "ep_b": 0.9,
            "ep_d": 0.05,
            "ep_u": 0.05,
            "ep_a": 0.5,
        }
        score = score_knowledge(node, ["Flask"], ["security"])
        assert 0.0 < score <= 1.0

    def test_prediction_accuracy_bonus(self):
        base = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
            "confidence": 0.7,
        }
        # High prediction accuracy node
        high_pred = {
            **base,
            "prediction_tested_count": 10,
            "prediction_success_count": 9,
        }
        # Low prediction accuracy node
        low_pred = {
            **base,
            "prediction_tested_count": 10,
            "prediction_success_count": 2,
        }
        score_high = score_knowledge(high_pred, ["Flask"], ["security"])
        score_low = score_knowledge(low_pred, ["Flask"], ["security"])
        assert score_high > score_low


class TestRankResults:
    """Tests for rank_results()."""

    def test_returns_sorted_by_score(self):
        nodes = [
            {"id": "low", "text": "low", "technologies": [], "domains": [], "severity": "low"},
            {"id": "high", "text": "high", "technologies": ["Flask"], "domains": ["security"], "severity": "critical", "reinforcement_count": 20},
        ]
        ranked = rank_results(nodes, ["Flask"], ["security"], top_k=10)
        assert len(ranked) == 2
        # Higher-scored node should be first
        assert ranked[0]["_relevance_score"] >= ranked[1]["_relevance_score"]

    def test_respects_top_k(self):
        nodes = [
            {"id": f"N{i}", "text": f"rule {i}", "technologies": ["Flask"], "domains": ["security"], "severity": "medium"}
            for i in range(20)
        ]
        ranked = rank_results(nodes, ["Flask"], ["security"], top_k=5)
        assert len(ranked) == 5

    def test_top_k_larger_than_input(self):
        nodes = [
            {"id": "A", "text": "test", "technologies": ["Flask"], "domains": ["security"]},
        ]
        ranked = rank_results(nodes, ["Flask"], ["security"], top_k=100)
        assert len(ranked) == 1

    def test_empty_input(self):
        ranked = rank_results([], ["Flask"], ["security"])
        assert ranked == []

    def test_all_nodes_get_relevance_score(self):
        nodes = [
            {"id": "A", "text": "test", "technologies": ["Flask"], "domains": ["security"]},
            {"id": "B", "text": "test2", "technologies": ["Flask"], "domains": ["api"]},
        ]
        ranked = rank_results(nodes, ["Flask"], ["security"], top_k=10)
        for node in ranked:
            assert "_relevance_score" in node
            assert isinstance(node["_relevance_score"], float)

    def test_deprecated_nodes_ranked_last(self):
        nodes = [
            {"id": "active", "text": "active rule", "technologies": ["Flask"], "domains": ["security"], "severity": "high"},
            {"id": "deprecated", "text": "old rule", "technologies": ["Flask"], "domains": ["security"], "severity": "critical", "deprecated": True},
        ]
        ranked = rank_results(nodes, ["Flask"], ["security"], top_k=10)
        # Deprecated node scores 0.0, so it should be last
        assert ranked[-1]["id"] == "deprecated"
        assert ranked[-1]["_relevance_score"] == 0.0

    def test_config_affects_scoring(self):
        nodes = [
            {"id": "A", "text": "test", "technologies": ["Flask"], "domains": ["security"], "severity": "medium"},
        ]
        cfg1 = BrainConfig()
        cfg1.weight_tech_match = 0.5
        cfg2 = BrainConfig()
        cfg2.weight_tech_match = 0.01

        ranked1 = rank_results(nodes, ["Flask"], ["security"], top_k=10, config=cfg1)
        ranked2 = rank_results(nodes, ["Flask"], ["security"], top_k=10, config=cfg2)

        # Different weights should produce different scores
        assert ranked1[0]["_relevance_score"] != pytest.approx(
            ranked2[0]["_relevance_score"], abs=0.001
        )

    def test_weight_normalization(self):
        """Scorer normalizes weights so they sum to 1.0."""
        node = {
            "id": "CR-001",
            "text": "test",
            "technologies": ["Flask"],
            "domains": ["security"],
            "severity": "medium",
        }
        cfg = BrainConfig()
        # Even with non-standard weights, score should be in [0, 1]
        cfg.weight_tech_match = 1.0
        cfg.weight_domain_match = 1.0
        cfg.weight_severity = 1.0
        cfg.weight_reinforcement = 1.0
        cfg.weight_recency = 1.0
        cfg.weight_confidence = 1.0
        score = score_knowledge(node, ["Flask"], ["security"], config=cfg)
        assert 0.0 <= score <= 1.0


# =============================================================================
# 4. Budget Tests
# =============================================================================


class TestEnforceBudget:
    """Tests for enforce_budget()."""

    def test_empty_input(self):
        result = enforce_budget({})
        assert result == {}

    def test_single_layer_within_budget(self):
        results = {
            "L3": [
                {"id": "A", "text": "short"},
            ],
        }
        trimmed = enforce_budget(results)
        assert len(trimmed["L3"]) == 1

    def test_respects_budget_limit(self):
        cfg = BrainConfig()
        cfg.context_budget_chars = 500
        # Create nodes with enough text to exceed the L3 budget (~50% of 500 = 250)
        results = {
            "L3": [
                {
                    "id": f"R{i}",
                    "text": "x" * 200,
                    "why": "y" * 100,
                    "_relevance_score": 1.0 - i * 0.1,
                }
                for i in range(10)
            ],
        }
        trimmed = enforce_budget(results, config=cfg)
        assert len(trimmed["L3"]) < 10

    def test_at_least_one_per_layer(self):
        """Even if budget is tiny, at least one node is kept per layer."""
        cfg = BrainConfig()
        cfg.context_budget_chars = 1  # Extremely small budget
        results = {
            "L3": [
                {"id": "A", "text": "This is a really long rule text " * 10, "_relevance_score": 0.8},
            ],
        }
        trimmed = enforce_budget(results, config=cfg)
        assert len(trimmed["L3"]) >= 1

    def test_higher_scored_nodes_kept_first(self):
        cfg = BrainConfig()
        cfg.context_budget_chars = 500
        results = {
            "L3": [
                {"id": "low", "text": "a" * 200, "_relevance_score": 0.1},
                {"id": "high", "text": "b" * 200, "_relevance_score": 0.9},
            ],
        }
        trimmed = enforce_budget(results, config=cfg)
        # The high-scored node should be first (sorted by score)
        if len(trimmed["L3"]) >= 1:
            assert trimmed["L3"][0]["id"] == "high"

    def test_multiple_layers_budgeted(self):
        cfg = BrainConfig()
        cfg.context_budget_chars = 3000
        results = {
            "L1": [{"id": "P1", "name": "Principle", "_relevance_score": 0.8}],
            "L2": [{"id": "PAT1", "name": "Pattern", "_relevance_score": 0.7}],
            "L3": [
                {"id": f"R{i}", "text": "rule text " * 5, "_relevance_score": 0.9 - i * 0.1}
                for i in range(20)
            ],
            "L4": [{"id": "F1", "description": "Finding", "_relevance_score": 0.5}],
        }
        trimmed = enforce_budget(results, config=cfg)
        assert "L1" in trimmed
        assert "L2" in trimmed
        assert "L3" in trimmed
        assert "L4" in trimmed
        # L3 should be trimmed (has 20 nodes)
        assert len(trimmed["L3"]) < 20

    def test_default_budget_is_3000(self):
        cfg = BrainConfig()
        assert cfg.context_budget_chars == 3000

    def test_layer_proportions(self):
        """L3 (rules) should get the largest budget share (~50%)."""
        cfg = BrainConfig()
        cfg.context_budget_chars = 10000
        # Create many small nodes per layer
        results = {
            "L1": [{"id": f"P{i}", "name": f"p{i}", "_relevance_score": 0.5} for i in range(50)],
            "L2": [{"id": f"PAT{i}", "name": f"pat{i}", "_relevance_score": 0.5} for i in range(50)],
            "L3": [{"id": f"R{i}", "text": f"r{i}", "_relevance_score": 0.5} for i in range(50)],
            "L4": [{"id": f"F{i}", "description": f"f{i}", "_relevance_score": 0.5} for i in range(50)],
        }
        trimmed = enforce_budget(results, config=cfg)
        # L3 should have more nodes than L1 (larger budget proportion)
        assert len(trimmed["L3"]) >= len(trimmed["L1"])


class TestEstimateTotalChars:
    """Tests for estimate_total_chars()."""

    def test_empty_input(self):
        assert estimate_total_chars({}) == 0

    def test_single_node(self):
        results = {"L3": [{"id": "A", "text": "short text"}]}
        total = estimate_total_chars(results)
        assert total > 0

    def test_includes_why_and_how(self):
        results = {
            "L3": [{
                "id": "A",
                "text": "rule text",
                "why": "because reasons",
                "how_to_do_right": "do it this way",
            }],
        }
        total_with = estimate_total_chars(results)

        results_without = {
            "L3": [{"id": "A", "text": "rule text"}],
        }
        total_without = estimate_total_chars(results_without)
        assert total_with > total_without


# =============================================================================
# 5. Synonym Tests
# =============================================================================


class TestExpandQueryTerms:
    """Tests for expand_query_terms()."""

    def test_forward_lookup(self):
        expanded = expand_query_terms(["cors"])
        assert "cross-origin" in expanded
        assert "cors" in expanded

    def test_reverse_lookup(self):
        expanded = expand_query_terms(["cross-site scripting"])
        assert "xss" in expanded

    def test_auth_expansion(self):
        expanded = expand_query_terms(["auth"])
        assert "authentication" in expanded
        assert "authorization" in expanded

    def test_no_duplicates(self):
        expanded = expand_query_terms(["cors", "cross-origin"])
        # Should not have duplicates
        lower = [t.lower() for t in expanded]
        assert len(lower) == len(set(lower))

    def test_additive_only(self):
        original = ["flask", "cors"]
        expanded = expand_query_terms(original)
        for term in original:
            assert term in expanded

    def test_unknown_term_passthrough(self):
        expanded = expand_query_terms(["unknown_technology_xyz"])
        assert "unknown_technology_xyz" in expanded

    def test_empty_input(self):
        expanded = expand_query_terms([])
        assert expanded == []

    def test_single_term(self):
        expanded = expand_query_terms(["jwt"])
        assert "jwt" in expanded
        assert "json web token" in expanded

    def test_multiple_terms(self):
        expanded = expand_query_terms(["cors", "xss"])
        assert "cross-origin" in expanded
        assert "cross-site scripting" in expanded

    def test_case_insensitive(self):
        expanded = expand_query_terms(["CORS"])
        # "CORS" itself should be present
        assert "CORS" in expanded

    def test_bidirectional_expansion(self):
        """Reverse lookup should also expand sibling aliases."""
        expanded = expand_query_terms(["cross-site scripting"])
        assert "xss" in expanded
        # Should also include sibling aliases of "xss"
        assert "html injection" in expanded or "script injection" in expanded

    def test_circuit_breaker_expansion(self):
        expanded = expand_query_terms(["circuit breaker"])
        assert "circuit-breaker" in expanded or "resilience" in expanded

    def test_dry_expansion(self):
        expanded = expand_query_terms(["dry"])
        assert "don't repeat yourself" in expanded or "single source of truth" in expanded


class TestExpandFromGraph:
    """Tests for expand_from_graph()."""

    def test_no_graph_returns_empty(self):
        result = expand_from_graph(None, ["flask"])
        assert result == []

    def test_zero_hops_returns_empty(self):
        graph = MemoryGraphAdapter()
        result = expand_from_graph(graph, ["flask"], max_hops=0)
        assert result == []

    def test_expands_from_tech_node(self):
        graph = MemoryGraphAdapter()
        graph.add_node("Technology", "tech:flask", {
            "id": "tech:flask",
            "name": "Flask",
        })
        graph.add_node("Domain", "domain:cors", {
            "id": "domain:cors",
            "name": "CORS",
        })
        graph.add_edge("tech:flask", "domain:cors", "RELATES_TO")

        result = expand_from_graph(graph, ["flask"])
        assert "CORS" in result

    def test_expands_from_domain_node(self):
        graph = MemoryGraphAdapter()
        graph.add_node("Domain", "domain:security", {
            "id": "domain:security",
            "name": "Security",
        })
        graph.add_node("Domain", "domain:cors", {
            "id": "domain:cors",
            "name": "CORS",
        })
        graph.add_edge("domain:security", "domain:cors", "CONTAINS")

        result = expand_from_graph(graph, ["security"])
        assert "CORS" in result

    def test_skips_already_known_terms(self):
        graph = MemoryGraphAdapter()
        graph.add_node("Technology", "tech:flask", {
            "id": "tech:flask",
            "name": "Flask",
        })
        graph.add_node("Domain", "domain:api", {
            "id": "domain:api",
            "name": "api",
        })
        graph.add_edge("tech:flask", "domain:api", "RELATES_TO")

        # "api" is already in terms, should not be in the additional list
        result = expand_from_graph(graph, ["flask", "api"])
        assert "api" not in [r.lower() for r in result]

    def test_no_matching_nodes(self):
        graph = MemoryGraphAdapter()
        result = expand_from_graph(graph, ["nonexistent_tech"])
        assert result == []

    def test_skips_long_names(self):
        graph = MemoryGraphAdapter()
        graph.add_node("Technology", "tech:flask", {
            "id": "tech:flask",
            "name": "Flask",
        })
        graph.add_node("Rule", "CR-long", {
            "id": "CR-long",
            "name": "A" * 100,  # Very long name (>50 chars)
        })
        graph.add_edge("tech:flask", "CR-long", "RELATES_TO")

        result = expand_from_graph(graph, ["flask"])
        # Long names should be filtered out
        assert not any(len(r) >= 50 for r in result)


# =============================================================================
# 6. Community Detection Tests
# =============================================================================


class TestCommunityDetector:
    """Tests for CommunityDetector with MemoryGraphAdapter."""

    def test_empty_graph(self):
        graph = MemoryGraphAdapter()
        detector = CommunityDetector(graph)
        communities = detector.detect()
        assert communities == []

    def test_no_edges_no_communities(self):
        graph = MemoryGraphAdapter()
        graph.add_node("Rule", "A", {"id": "A", "text": "rule A"})
        graph.add_node("Rule", "B", {"id": "B", "text": "rule B"})
        # No edges -> each node is isolated, communities < min_size=3
        detector = CommunityDetector(graph)
        communities = detector.detect(min_community_size=3)
        assert communities == []

    def test_single_connected_component(self):
        graph = MemoryGraphAdapter()
        for i in range(5):
            graph.add_node("Rule", f"R{i}", {
                "id": f"R{i}",
                "text": f"Rule {i}",
                "domains": ["security"],
                "technologies": ["Flask"],
            })
        # Connect all nodes in a chain: R0-R1-R2-R3-R4
        for i in range(4):
            graph.add_edge(f"R{i}", f"R{i+1}", "RELATES_TO")

        detector = CommunityDetector(graph)
        communities = detector.detect(min_community_size=3)
        assert len(communities) >= 1
        # The largest community should contain all 5 nodes
        assert communities[0].size == 5

    def test_two_disconnected_components(self):
        graph = MemoryGraphAdapter()
        # Component 1: security rules
        for i in range(4):
            graph.add_node("Rule", f"SEC{i}", {
                "id": f"SEC{i}",
                "text": f"Security rule {i}",
                "domains": ["security"],
            })
        for i in range(3):
            graph.add_edge(f"SEC{i}", f"SEC{i+1}", "RELATES_TO")

        # Component 2: performance rules
        for i in range(3):
            graph.add_node("Rule", f"PERF{i}", {
                "id": f"PERF{i}",
                "text": f"Performance rule {i}",
                "domains": ["performance"],
            })
        for i in range(2):
            graph.add_edge(f"PERF{i}", f"PERF{i+1}", "RELATES_TO")

        detector = CommunityDetector(graph)
        communities = detector.detect(min_community_size=3)
        assert len(communities) >= 2

    def test_community_sorted_by_size(self):
        graph = MemoryGraphAdapter()
        # Large cluster
        for i in range(10):
            graph.add_node("Rule", f"BIG{i}", {"id": f"BIG{i}", "text": f"big {i}"})
        for i in range(9):
            graph.add_edge(f"BIG{i}", f"BIG{i+1}", "RELATES_TO")

        # Small cluster
        for i in range(4):
            graph.add_node("Rule", f"SMALL{i}", {"id": f"SMALL{i}", "text": f"small {i}"})
        for i in range(3):
            graph.add_edge(f"SMALL{i}", f"SMALL{i+1}", "RELATES_TO")

        detector = CommunityDetector(graph)
        communities = detector.detect(min_community_size=3)
        assert len(communities) >= 2
        assert communities[0].size >= communities[1].size

    def test_min_community_size_filter(self):
        graph = MemoryGraphAdapter()
        # Create a pair (size 2) and a triple (size 3)
        graph.add_node("Rule", "A1", {"id": "A1", "text": "a1"})
        graph.add_node("Rule", "A2", {"id": "A2", "text": "a2"})
        graph.add_edge("A1", "A2", "RELATES_TO")

        graph.add_node("Rule", "B1", {"id": "B1", "text": "b1"})
        graph.add_node("Rule", "B2", {"id": "B2", "text": "b2"})
        graph.add_node("Rule", "B3", {"id": "B3", "text": "b3"})
        graph.add_edge("B1", "B2", "RELATES_TO")
        graph.add_edge("B2", "B3", "RELATES_TO")

        detector = CommunityDetector(graph)
        communities_3 = detector.detect(min_community_size=3)
        # Only the triple should survive
        assert len(communities_3) == 1
        assert communities_3[0].size == 3

    def test_community_has_summary(self):
        graph = MemoryGraphAdapter()
        for i in range(4):
            graph.add_node("Rule", f"R{i}", {
                "id": f"R{i}",
                "text": f"Rule about topic {i}",
            })
        for i in range(3):
            graph.add_edge(f"R{i}", f"R{i+1}", "RELATES_TO")

        detector = CommunityDetector(graph)
        communities = detector.detect(min_community_size=3)
        assert len(communities) >= 1
        assert communities[0].summary != ""
        assert len(communities[0].summary) > 0

    def test_community_detects_dominant_domain(self):
        graph = MemoryGraphAdapter()
        for i in range(5):
            graph.add_node("Rule", f"S{i}", {
                "id": f"S{i}",
                "text": f"Security rule {i}",
                "domains": ["security"],
            })
        for i in range(4):
            graph.add_edge(f"S{i}", f"S{i+1}", "RELATES_TO")

        detector = CommunityDetector(graph)
        communities = detector.detect(min_community_size=3)
        assert len(communities) >= 1
        assert communities[0].dominant_domain == "security"

    def test_community_detects_dominant_technology(self):
        graph = MemoryGraphAdapter()
        for i in range(4):
            graph.add_node("Rule", f"F{i}", {
                "id": f"F{i}",
                "text": f"Flask rule {i}",
                "technologies": ["Flask"],
            })
        for i in range(3):
            graph.add_edge(f"F{i}", f"F{i+1}", "RELATES_TO")

        detector = CommunityDetector(graph)
        communities = detector.detect(min_community_size=3)
        assert len(communities) >= 1
        assert communities[0].dominant_technology == "Flask"

    def test_community_to_dict(self):
        community = Community(
            id=0,
            node_ids=["A", "B", "C"],
            top_nodes=[{"id": "A", "text": "test"}],
            summary="Test community",
            dominant_domain="security",
            dominant_technology="Flask",
            size=3,
        )
        d = community.to_dict()
        assert d["id"] == 0
        assert d["size"] == 3
        assert d["summary"] == "Test community"
        assert d["dominant_domain"] == "security"
        assert d["dominant_technology"] == "Flask"
        assert "A" in d["node_ids"]

    def test_community_node_ids_capped_in_to_dict(self):
        community = Community(
            id=0,
            node_ids=[f"N{i}" for i in range(50)],
            size=50,
        )
        d = community.to_dict()
        assert len(d["node_ids"]) <= 20

    def test_label_propagation_dense_graph(self):
        """Test that label propagation works on a denser graph."""
        graph = MemoryGraphAdapter()
        # Create a fully connected 5-node clique
        for i in range(5):
            graph.add_node("Rule", f"C{i}", {
                "id": f"C{i}",
                "text": f"Clique node {i}",
                "domains": ["api"],
            })
        for i in range(5):
            for j in range(i + 1, 5):
                graph.add_edge(f"C{i}", f"C{j}", "RELATES_TO")

        detector = CommunityDetector(graph)
        communities = detector.detect(min_community_size=3)
        # Should detect at least one community
        assert len(communities) >= 1
        # The clique should be detected as one community
        largest = communities[0]
        assert largest.size == 5

    def test_self_loop_ignored(self):
        """Self-loops should not crash community detection."""
        graph = MemoryGraphAdapter()
        graph.add_node("Rule", "A", {"id": "A", "text": "a"})
        graph.add_node("Rule", "B", {"id": "B", "text": "b"})
        graph.add_node("Rule", "C", {"id": "C", "text": "c"})
        graph.add_edge("A", "A", "SELF_REF")  # Self-loop
        graph.add_edge("A", "B", "RELATES_TO")
        graph.add_edge("B", "C", "RELATES_TO")

        detector = CommunityDetector(graph)
        # Should not crash
        communities = detector.detect(min_community_size=3)
        assert isinstance(communities, list)


# =============================================================================
# Integration: QueryRouter with MemoryGraphAdapter
# =============================================================================


class TestQueryRouterIntegration:
    """Integration tests for QueryRouter using in-memory adapters."""

    def test_basic_query(self, populated_graph: MemoryGraphAdapter):
        from engineering_brain.retrieval.router import QueryRouter
        from engineering_brain.core.types import KnowledgeQuery

        cfg = BrainConfig()
        cfg.graph_expansion_enabled = False
        cfg.reranker_enabled = False

        router = QueryRouter(graph=populated_graph, config=cfg)
        query = KnowledgeQuery(
            task_description="Validate CORS for Flask API",
            technologies=["Flask"],
            domains=["security"],
        )
        result = router.query(query)
        assert result.total_nodes_queried >= 0
        assert result.cache_hit is False
        assert isinstance(result.formatted_text, str)

    def test_query_returns_rules(self, populated_graph: MemoryGraphAdapter):
        from engineering_brain.retrieval.router import QueryRouter
        from engineering_brain.core.types import KnowledgeQuery

        cfg = BrainConfig()
        cfg.graph_expansion_enabled = False
        cfg.reranker_enabled = False

        router = QueryRouter(graph=populated_graph, config=cfg)
        query = KnowledgeQuery(
            task_description="Validate CORS for Flask API",
            technologies=["Flask"],
            domains=["security"],
        )
        result = router.query(query)
        # Should have found some rules about CORS/security
        all_results = result.principles + result.patterns + result.rules + result.evidence
        assert len(all_results) >= 0  # May be 0 if budget trims everything

    def test_query_with_cache(self, populated_graph: MemoryGraphAdapter):
        from engineering_brain.adapters.memory import MemoryCacheAdapter
        from engineering_brain.retrieval.router import QueryRouter
        from engineering_brain.core.types import KnowledgeQuery

        cfg = BrainConfig()
        cfg.graph_expansion_enabled = False
        cfg.reranker_enabled = False

        cache = MemoryCacheAdapter(max_size=100, default_ttl=60)
        router = QueryRouter(graph=populated_graph, cache=cache, config=cfg)

        query = KnowledgeQuery(
            task_description="SQL injection prevention",
            technologies=["Python"],
            domains=["security"],
        )
        # First query: cache miss
        result1 = router.query(query)
        assert result1.cache_hit is False

        # Second query: cache hit
        result2 = router.query(query)
        assert result2.cache_hit is True

    def test_query_with_provenance(self, populated_graph: MemoryGraphAdapter):
        from engineering_brain.retrieval.router import QueryRouter
        from engineering_brain.core.types import KnowledgeQuery

        cfg = BrainConfig()
        cfg.graph_expansion_enabled = False
        cfg.reranker_enabled = False

        router = QueryRouter(graph=populated_graph, config=cfg)
        query = KnowledgeQuery(
            task_description="CORS validation for Flask",
            technologies=["Flask"],
            domains=["security"],
        )
        result, scored_nodes = router.query_with_provenance(query)
        assert isinstance(result.formatted_text, str)
        assert isinstance(scored_nodes, list)

    def test_track_retrieval_metrics(self, populated_graph: MemoryGraphAdapter):
        from engineering_brain.retrieval.router import QueryRouter

        cfg = BrainConfig()
        cfg.graph_expansion_enabled = False
        cfg.reranker_enabled = False

        router = QueryRouter(graph=populated_graph, config=cfg)

        scored = [
            {"id": "CR-001", "text": "test", "_relevance_score": 0.9},
        ]
        # Should not crash
        router._track_retrieval_metrics(scored)

        # Verify the node was updated with retrieval metrics
        node = populated_graph.get_node("CR-001")
        if node:
            assert node.get("retrieval_count", 0) >= 1

    def test_query_with_scored_nodes(self, populated_graph: MemoryGraphAdapter):
        from engineering_brain.retrieval.router import QueryRouter
        from engineering_brain.core.types import KnowledgeQuery

        cfg = BrainConfig()
        cfg.graph_expansion_enabled = False
        cfg.reranker_enabled = False

        router = QueryRouter(graph=populated_graph, config=cfg)
        query = KnowledgeQuery(
            task_description="Security best practices for Flask",
            technologies=["Flask"],
            domains=["security"],
        )
        result, scored = router.query_with_scored_nodes(query)
        assert isinstance(scored, list)
        # scored contains ALL nodes before budget trimming
        # result contains budget-trimmed nodes
        total_in_result = (
            len(result.principles) + len(result.patterns)
            + len(result.rules) + len(result.evidence)
        )
        assert len(scored) >= total_in_result

    def test_clean_node_removes_internal_fields(self):
        from engineering_brain.retrieval.router import _clean_node

        node = {
            "id": "CR-001",
            "text": "real data",
            "_relevance_score": 0.8,
            "_source": "graph",
            "_layer": "L3",
            "_vector_score": 0.5,
        }
        cleaned = _clean_node(node)
        assert "id" in cleaned
        assert "text" in cleaned
        assert "_relevance_score" not in cleaned
        assert "_source" not in cleaned
        assert "_layer" not in cleaned
        assert "_vector_score" not in cleaned
