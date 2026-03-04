"""Tests for the KnowledgeAssembler — LLM-powered knowledge pack curation.

Covers:
1. Query classification (SIMPLE/MODERATE/COMPLEX → DIRECT/CURATED/SYNTHESIZED)
2. Candidate filtering (score cutoff, node cap, vertical coverage, dedup)
3. DIRECT assembly (no LLM, bookend structure)
4. CURATED assembly (LLM JSON selection + hydration)
5. SYNTHESIZED assembly (LLM markdown generation)
6. Validation + quality scoring
7. Fallback on LLM failure
8. Feature flag gating
9. Edge cases (empty nodes, no candidates, budget guard)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from unittest import mock

import pytest

from engineering_brain.core.config import BrainConfig
from engineering_brain.retrieval.knowledge_assembler import (
    AssemblyStrategy,
    KnowledgeAssembler,
    QueryComplexity,
)

# =============================================================================
# Helpers
# =============================================================================


@dataclass
class MockContext:
    technologies: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    file_types: list[str] = field(default_factory=list)
    phase: str = "exec"
    raw_text: str = ""
    facet_tags: dict = field(default_factory=dict)


def _node(
    nid: str, text: str, score: float, layer: str = "L3", severity: str = "medium", **kw
) -> dict:
    return {
        "id": nid,
        "text": text,
        "_relevance_score": score,
        "_layer": layer,
        "severity": severity,
        "validation_status": "unvalidated",
        "reinforcement_count": 0,
        "why": kw.get("why", ""),
        "how_to_do_right": kw.get("how", ""),
        **{k: v for k, v in kw.items() if k not in ("why", "how")},
    }


def _make_assembler(**config_kw) -> KnowledgeAssembler:
    cfg = BrainConfig(**config_kw) if config_kw else BrainConfig()
    return KnowledgeAssembler(config=cfg)


# Standard test nodes
CORS_RULE = _node(
    "CR-SEC-001",
    "Always set explicit CORS origins",
    0.85,
    severity="critical",
    why="Wildcard allows any domain",
    how="Use flask_cors.CORS(app, origins=[...])",
)
AUTH_RULE = _node(
    "CR-AUTH-001",
    "Validate JWT tokens on every request",
    0.75,
    severity="high",
    why="Prevents unauthorized access",
    how="Use @jwt_required decorator",
)
SQL_RULE = _node(
    "CR-DB-001",
    "Use parameterized queries for SQL",
    0.70,
    severity="critical",
    why="Prevents SQL injection",
    how="Use cursor.execute(query, params)",
)
CACHE_PATTERN = _node(
    "P-CACHE-001", "Cache-Aside Pattern", 0.60, layer="L2", why="Reduces database load"
)
PRINCIPLE = _node(
    "PR-SEC-001",
    "Defense in Depth",
    0.55,
    layer="L1",
    why="Multiple security layers prevent single-point failure",
)
LOW_SCORE = _node("CR-LOW-001", "Use consistent naming", 0.10, why="Readability")

STANDARD_NODES = [CORS_RULE, AUTH_RULE, SQL_RULE, CACHE_PATTERN, PRINCIPLE, LOW_SCORE]


# =============================================================================
# 1. Query Classification
# =============================================================================


class TestQueryClassification:
    def test_simple_short_query(self):
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"], domains=["security"])
        complexity, strategy = a._classify("what is CORS?", ctx, 5)
        assert complexity == QueryComplexity.SIMPLE
        assert strategy == AssemblyStrategy.DIRECT

    def test_simple_one_tech_few_nodes(self):
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        complexity, _ = a._classify("explain CORS", ctx, 8)
        assert complexity == QueryComplexity.SIMPLE

    def test_moderate_multi_word(self):
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask", "Redis"])
        complexity, strategy = a._classify(
            "Flask CORS security best practices for production APIs",
            ctx,
            15,
        )
        assert complexity == QueryComplexity.MODERATE
        assert strategy == AssemblyStrategy.CURATED

    def test_complex_multi_tech(self):
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask", "Redis", "PostgreSQL"])
        complexity, strategy = a._classify(
            "Flask with Redis and PostgreSQL",
            ctx,
            20,
        )
        assert complexity == QueryComplexity.COMPLEX
        assert strategy == AssemblyStrategy.SYNTHESIZED

    def test_complex_multi_domain(self):
        a = _make_assembler()
        ctx = MockContext(domains=["security", "performance", "caching"])
        complexity, _ = a._classify("optimize security and caching", ctx, 10)
        assert complexity == QueryComplexity.COMPLEX

    def test_complex_architecture_keyword(self):
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        complexity, strategy = a._classify(
            "design a Flask microservice architecture",
            ctx,
            20,
        )
        assert complexity == QueryComplexity.COMPLEX
        assert strategy == AssemblyStrategy.SYNTHESIZED

    def test_complex_design_keyword(self):
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        complexity, _ = a._classify("design the auth system", ctx, 15)
        assert complexity == QueryComplexity.COMPLEX

    def test_complex_migrate_keyword(self):
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        complexity, _ = a._classify("migrate from Flask to FastAPI", ctx, 10)
        assert complexity == QueryComplexity.COMPLEX

    def test_moderate_default_case(self):
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"], domains=["security"])
        complexity, strategy = a._classify(
            "implement Flask CORS middleware for API endpoints",
            ctx,
            15,
        )
        assert complexity == QueryComplexity.MODERATE
        assert strategy == AssemblyStrategy.CURATED

    def test_simple_with_many_nodes_becomes_moderate(self):
        """Even short queries become MODERATE if >10 nodes matched."""
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"], domains=["security"])
        complexity, _ = a._classify("CORS setup", ctx, 15)
        assert complexity == QueryComplexity.MODERATE

    def test_empty_context(self):
        a = _make_assembler()
        ctx = MockContext()
        complexity, strategy = a._classify("help me", ctx, 3)
        assert complexity == QueryComplexity.SIMPLE
        assert strategy == AssemblyStrategy.DIRECT


# =============================================================================
# 2. Candidate Filtering
# =============================================================================


class TestCandidateFiltering:
    def test_score_cutoff_simple(self):
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        candidates = a._filter_candidates(STANDARD_NODES, QueryComplexity.SIMPLE, ctx)
        # Simple cutoff is 0.45, so LOW_SCORE (0.10) should be filtered
        ids = [n["id"] for n in candidates]
        assert "CR-LOW-001" not in ids

    def test_score_cutoff_complex(self):
        a = _make_assembler()
        ctx = MockContext()
        candidates = a._filter_candidates(STANDARD_NODES, QueryComplexity.COMPLEX, ctx)
        # Complex cutoff is 0.20, so LOW_SCORE (0.10) filtered but rest kept
        ids = [n["id"] for n in candidates]
        assert "CR-LOW-001" not in ids
        assert "CR-SEC-001" in ids

    def test_node_cap_applied(self):
        """Should cap at 8 for SIMPLE."""
        a = _make_assembler()
        ctx = MockContext()
        many_nodes = [_node(f"N-{i}", f"Node {i}", 0.9 - i * 0.01) for i in range(20)]
        candidates = a._filter_candidates(many_nodes, QueryComplexity.SIMPLE, ctx)
        assert len(candidates) <= 8

    def test_vertical_coverage_adds_missing_layers(self):
        """Should add L1 node even if below cutoff, if no L1 in candidates."""
        a = _make_assembler()
        ctx = MockContext()
        # All L3 nodes with L1 node below cutoff
        l3_nodes = [_node(f"R-{i}", f"Rule {i}", 0.8 - i * 0.05) for i in range(5)]
        l1_node = _node("PR-001", "Principle", 0.15, layer="L1")
        all_nodes = l3_nodes + [l1_node]
        candidates = a._filter_candidates(all_nodes, QueryComplexity.MODERATE, ctx)
        ids = [n["id"] for n in candidates]
        assert "PR-001" in ids  # Added for vertical coverage

    def test_dedup_removes_redundant(self):
        """Near-identical nodes should be collapsed."""
        a = _make_assembler()
        ctx = MockContext()
        nodes = [
            _node("A", "Always set explicit CORS origins in Flask", 0.9, why="Prevents attacks"),
            _node("B", "Always set explicit CORS origins in Flask", 0.8, why="Prevents attacks"),
            _node("C", "Use parameterized SQL queries always", 0.7, why="Prevents injection"),
        ]
        candidates = a._filter_candidates(nodes, QueryComplexity.MODERATE, ctx)
        ids = [n["id"] for n in candidates]
        # A and B are identical → only A should survive, B is filtered
        assert "A" in ids
        assert "B" not in ids
        assert "C" in ids

    def test_empty_input(self):
        a = _make_assembler()
        ctx = MockContext()
        assert a._filter_candidates([], QueryComplexity.SIMPLE, ctx) == []


# =============================================================================
# 3. DIRECT Assembly
# =============================================================================


class TestDirectAssembly:
    def test_formats_top_nodes(self):
        a = _make_assembler()
        formatted, included, excluded = a._assemble_direct(STANDARD_NODES[:3], 3000)
        assert len(formatted) > 0
        assert "CORS" in formatted or "JWT" in formatted
        assert len(included) > 0

    def test_respects_budget(self):
        a = _make_assembler()
        formatted, _, _ = a._assemble_direct(STANDARD_NODES, 500)
        assert len(formatted) <= 500 + 50  # some tolerance for truncation notice

    def test_empty_nodes(self):
        a = _make_assembler()
        formatted, included, excluded = a._assemble_direct([], 3000)
        assert formatted == ""
        assert included == set()


# =============================================================================
# 4. CURATED Assembly (mocked LLM)
# =============================================================================


class TestCuratedAssembly:
    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_selects_and_orders(self, mock_flag, mock_llm):
        mock_llm.return_value = {
            "selected": [
                {"id": "CR-SEC-001", "treatment": "full"},
                {"id": "CR-AUTH-001", "treatment": "summary"},
            ],
            "summary_hint": "Flask security requires CORS and auth.",
        }
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"], domains=["security"])
        formatted, included, excluded = a._assemble_curated(
            "Flask security",
            ctx,
            STANDARD_NODES[:3],
            6000,
        )
        assert "CORS" in formatted
        assert "CR-SEC-001" not in excluded
        assert "CR-SEC-001" in included

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_failure_falls_back_to_direct(self, mock_flag, mock_llm):
        mock_llm.return_value = None
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        formatted, included, excluded = a._assemble_curated(
            "Flask",
            ctx,
            STANDARD_NODES[:3],
            6000,
        )
        # Should still produce output via direct fallback
        assert len(formatted) > 0

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_malformed_response(self, mock_flag, mock_llm):
        mock_llm.return_value = {"wrong_key": "value"}
        a = _make_assembler()
        ctx = MockContext()
        formatted, _, _ = a._assemble_curated("test", ctx, STANDARD_NODES[:3], 6000)
        assert len(formatted) > 0  # Fell back to direct

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_empty_selected(self, mock_flag, mock_llm):
        mock_llm.return_value = {"selected": [], "summary_hint": ""}
        a = _make_assembler()
        ctx = MockContext()
        formatted, _, _ = a._assemble_curated("test", ctx, STANDARD_NODES[:3], 6000)
        assert len(formatted) > 0  # Fell back to direct

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_summary_treatment_renders_compact(self, mock_flag, mock_llm):
        mock_llm.return_value = {
            "selected": [{"id": "CR-SEC-001", "treatment": "summary"}],
            "summary_hint": "CORS basics.",
        }
        a = _make_assembler()
        ctx = MockContext()
        formatted, _, _ = a._assemble_curated("CORS", ctx, [CORS_RULE], 6000)
        # Summary treatment should include text but NOT WHY/DO sub-fields
        assert "CORS" in formatted
        assert "WHY:" not in formatted
        assert "DO:" not in formatted

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_full_treatment_includes_why_do(self, mock_flag, mock_llm):
        mock_llm.return_value = {
            "selected": [{"id": "CR-SEC-001", "treatment": "full"}],
            "summary_hint": "CORS security.",
        }
        a = _make_assembler()
        ctx = MockContext()
        formatted, _, _ = a._assemble_curated("CORS", ctx, [CORS_RULE], 6000)
        assert "WHY:" in formatted
        assert "DO:" in formatted

    def test_budget_guard_falls_back_to_direct(self):
        """If input serialization > 3x budget, skip LLM."""
        a = _make_assembler()
        ctx = MockContext()
        # Very small budget with many nodes → budget guard triggers
        many_nodes = [_node(f"N-{i}", "Long text " * 50, 0.5) for i in range(20)]
        formatted, _, _ = a._assemble_curated("test", ctx, many_nodes, 100)
        assert len(formatted) > 0  # Direct fallback


# =============================================================================
# 5. SYNTHESIZED Assembly (mocked LLM)
# =============================================================================


class TestSynthesizedAssembly:
    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_produces_markdown(self, mock_flag, mock_llm):
        mock_llm.return_value = (
            "## Authentication\n"
            "- [CRITICAL][VERIFIED] Always validate JWT tokens\n"
            "  WHY: Prevents unauthorized access\n\n"
            "## CORS\n"
            "- [HIGH] Set explicit origins\n"
            "  DO: Use flask_cors with specific origins\n\n"
            "## Caveats\n"
            "- [GAP] No rate limiting knowledge found"
        )
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask", "Redis", "PostgreSQL"])
        formatted, included, excluded = a._assemble_synthesized(
            "design Flask microservice",
            ctx,
            STANDARD_NODES,
            12000,
        )
        assert "## Authentication" in formatted
        assert "## CORS" in formatted
        assert "## Caveats" in formatted

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_failure_falls_back(self, mock_flag, mock_llm):
        mock_llm.return_value = None
        a = _make_assembler()
        ctx = MockContext()
        formatted, _, _ = a._assemble_synthesized("test", ctx, STANDARD_NODES[:3], 12000)
        assert len(formatted) > 0  # Direct fallback

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_respects_budget_via_enforce(self, mock_flag, mock_llm):
        mock_llm.return_value = "## Section\n" + "x" * 20000
        a = _make_assembler()
        ctx = MockContext()
        formatted, _, _ = a._assemble_synthesized("test", ctx, STANDARD_NODES[:3], 5000)
        assert len(formatted) <= 5000

    def test_budget_guard_falls_back_to_direct(self):
        a = _make_assembler()
        ctx = MockContext()
        many_nodes = [_node(f"N-{i}", "Long text " * 50, 0.5) for i in range(20)]
        formatted, _, _ = a._assemble_synthesized("test", ctx, many_nodes, 100)
        assert len(formatted) > 0


# =============================================================================
# 6. Validation + Quality Scoring
# =============================================================================


class TestValidation:
    def test_high_quality_output(self):
        a = _make_assembler()
        text = (
            "## Brain: CORS security\n\n"
            "### Critical Guidance\n"
            "- [CRITICAL][VERIFIED] Always set explicit CORS origins\n"
            "  WHY: Wildcard allows any domain\n"
            "  DO: Use flask_cors.CORS(app, origins=[...])\n"
        )
        candidates = [CORS_RULE]
        _, quality = a._validate(text, candidates, {"CR-SEC-001"}, 3000)
        assert quality >= 0.7

    def test_low_quality_empty_text(self):
        a = _make_assembler()
        _, quality = a._validate("", [CORS_RULE], set(), 3000)
        assert quality < 0.5

    def test_budget_violation_reduces_quality(self):
        a = _make_assembler()
        text = "x" * 5000
        _, quality = a._validate(text, [CORS_RULE], {"CR-SEC-001"}, 1000)
        assert quality < 0.8  # Budget violation penalizes

    def test_missing_critical_node_reduces_quality(self):
        a = _make_assembler()
        text = "## Some\n- Some text\n  WHY: reason\n  DO: action"
        # CORS_RULE is critical but NOT included
        _, quality = a._validate(text, [CORS_RULE], set(), 3000)
        assert quality < 0.8

    def test_structure_score_components(self):
        a = _make_assembler()
        # Has all structure elements
        good_text = "## Header\n- bullet point\n  WHY: reason\n  DO: action"
        _, good_q = a._validate(good_text, [], set(), 3000)
        # Has none
        bad_text = "plain text no structure"
        _, bad_q = a._validate(bad_text, [], set(), 3000)
        assert good_q > bad_q


# =============================================================================
# 7. Full Assemble Pipeline
# =============================================================================


class TestAssemblePipeline:
    def test_flag_off_returns_fallback(self):
        """When flag is off, uses deterministic pipeline."""
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        with mock.patch.dict(os.environ, {}, clear=True):
            result = a.assemble("Flask CORS", ctx, STANDARD_NODES)
        assert result.fallback_used is True
        assert result.strategy == "direct"
        assert len(result.formatted_text) > 0

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_moderate_query_uses_curated(self, mock_flag, mock_llm):
        mock_llm.return_value = {
            "selected": [
                {"id": "CR-SEC-001", "treatment": "full"},
                {"id": "CR-AUTH-001", "treatment": "summary"},
            ],
            "summary_hint": "Flask security guidance.",
        }
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask", "Redis"], domains=["security"])
        # Need >10 nodes and multi-word query to avoid SIMPLE classification
        many_nodes = STANDARD_NODES + [
            _node(f"X-{i}", f"Extra rule {i}", 0.5 + i * 0.01) for i in range(8)
        ]
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble(
                "implement Flask CORS middleware for secure API endpoints with Redis caching",
                ctx,
                many_nodes,
            )
        assert result.strategy == "curated"
        assert result.fallback_used is False
        assert "CORS" in result.formatted_text

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_complex_query_uses_synthesized(self, mock_flag, mock_llm):
        mock_llm.return_value = (
            "## Security\n"
            "- [CRITICAL] Set explicit CORS origins\n"
            "  WHY: Prevents cross-origin attacks\n"
            "  DO: Configure flask_cors\n\n"
            "## Caveats\n"
            "- No caching knowledge found"
        )
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask", "Redis", "PostgreSQL"])
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble(
                "design a Flask microservice with auth, caching, and rate limiting",
                ctx,
                STANDARD_NODES,
            )
        assert result.strategy == "synthesized"
        assert "## Security" in result.formatted_text

    def test_simple_query_uses_direct(self):
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        # Need to set env so flag check in assemble works — but actually
        # for SIMPLE queries, even with assembly enabled, strategy is DIRECT
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble("what is CORS?", ctx, STANDARD_NODES[:5])
        assert result.strategy == "direct"

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_failure_triggers_fallback(self, mock_flag, mock_llm):
        mock_llm.return_value = None
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"], domains=["security"])
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble(
                "implement Flask CORS middleware for API endpoints",
                ctx,
                STANDARD_NODES,
            )
        # Should have fallen back within curated → direct
        assert len(result.formatted_text) > 0

    def test_empty_scored_nodes(self):
        a = _make_assembler()
        ctx = MockContext()
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble("something", ctx, [])
        assert "No relevant knowledge" in result.formatted_text

    def test_all_nodes_below_cutoff(self):
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        low_nodes = [_node(f"N-{i}", f"Low node {i}", 0.05) for i in range(5)]
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble("Flask CORS", ctx, low_nodes)
        # Should still produce output (vertical coverage or empty result)
        assert len(result.formatted_text) > 0

    def test_low_quality_is_metadata_only(self):
        """Low quality score is recorded but does NOT trigger fallback."""
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"], domains=["security"])
        # Mock curated to return low-quality output (empty text)
        with (
            mock.patch.object(a, "_is_assembly_enabled", return_value=True),
            mock.patch.object(
                a, "_classify", return_value=(QueryComplexity.MODERATE, AssemblyStrategy.CURATED)
            ),
            mock.patch.object(a, "_assemble_curated", return_value=("", set(), [])),
        ):
            result = a.assemble(
                "implement Flask CORS middleware for API endpoints",
                ctx,
                [CORS_RULE, AUTH_RULE],
            )
        # Quality is low but no fallback — quality is metadata, not a gate
        assert result.quality_score < 0.4
        assert result.fallback_used is False


# =============================================================================
# 8. Node Rendering
# =============================================================================


class TestNodeRendering:
    def test_full_treatment_with_all_fields(self):
        a = _make_assembler()
        node = _node(
            "TEST", "Test rule", 0.8, severity="critical", why="Test reason", how="Test action"
        )
        node["validation_status"] = "cross_checked"
        node["reinforcement_count"] = 5
        node["when_applies"] = "Always"
        rendered = a._render_node(node, "full")
        assert "[CRITICAL]" in rendered
        assert "[VERIFIED]" in rendered
        assert "[5x]" in rendered
        assert "WHY: Test reason" in rendered
        assert "DO: Test action" in rendered
        assert "WHEN: Always" in rendered

    def test_summary_treatment_compact(self):
        a = _make_assembler()
        rendered = a._render_node(CORS_RULE, "summary")
        assert "WHY:" not in rendered
        assert "DO:" not in rendered
        assert "CORS" in rendered

    def test_prediction_rendering(self):
        a = _make_assembler()
        node = dict(CORS_RULE)
        node["prediction_if"] = "wildcard CORS used"
        node["prediction_then"] = "XSS attacks possible"
        node["prediction_tested_count"] = 10
        node["prediction_success_count"] = 8
        rendered = a._render_node(node, "full")
        assert "PREDICT:" in rendered
        assert "80%" in rendered


# =============================================================================
# 9. Serialization
# =============================================================================


class TestSerialization:
    def test_serializes_core_fields(self):
        a = _make_assembler()
        result = a._serialize_candidates([CORS_RULE])
        assert "CR-SEC-001" in result
        assert "0.85" in result
        assert "critical" in result
        assert "CORS" in result

    def test_truncates_long_text(self):
        a = _make_assembler()
        long_node = _node("LONG", "x" * 500, 0.5, why="y" * 300)
        result = a._serialize_candidates([long_node])
        # Text should be truncated at 200 chars
        assert len(result) < 500 + 300 + 200

    def test_multiple_nodes_serialized(self):
        a = _make_assembler()
        result = a._serialize_candidates(STANDARD_NODES[:3])
        assert "CR-SEC-001" in result
        assert "CR-AUTH-001" in result
        assert "CR-DB-001" in result


# =============================================================================
# 10. Utility Methods
# =============================================================================


class TestUtilities:
    def test_extract_mentioned_ids(self):
        a = _make_assembler()
        text = "Based on CR-SEC-001 and CR-AUTH-001, you should..."
        ids = a._extract_mentioned_ids(text, STANDARD_NODES)
        assert "CR-SEC-001" in ids
        assert "CR-AUTH-001" in ids
        assert "CR-DB-001" not in ids

    def test_extract_no_ids_uses_content_fallback(self):
        """If no IDs in text, content-overlap fallback infers mentioned nodes."""
        a = _make_assembler()
        text = "Set explicit CORS origins and validate JWT tokens."
        ids = a._extract_mentioned_ids(text, STANDARD_NODES)
        # Fallback matches by word overlap — CORS rule and auth rule have overlapping words
        assert len(ids) >= 1

    def test_extract_truly_unrelated_returns_empty(self):
        """Completely unrelated text returns empty even with fallback."""
        a = _make_assembler()
        text = "The weather forecast predicts rain tomorrow afternoon."
        ids = a._extract_mentioned_ids(text, STANDARD_NODES)
        assert ids == set()

    def test_extract_hallucinated_ids_ignored(self):
        """LLM-hallucinated IDs that don't match candidates are ignored."""
        a = _make_assembler()
        text = "Based on HALLUCINATED-001 and CR-SEC-001, you should..."
        ids = a._extract_mentioned_ids(text, STANDARD_NODES)
        assert "CR-SEC-001" in ids
        assert "HALLUCINATED-001" not in ids
        assert len(ids) == 1

    def test_split_by_layer(self):
        a = _make_assembler()
        by_layer = a._split_by_layer(STANDARD_NODES)
        assert len(by_layer["L1"]) == 1
        assert len(by_layer["L2"]) == 1
        assert len(by_layer["L3"]) >= 3

    def test_empty_result(self):
        a = _make_assembler()
        result = a._empty_result(0.0)
        assert "No relevant knowledge" in result.formatted_text
        assert result.strategy == "direct"

    def test_fallback_produces_valid_output(self):
        a = _make_assembler()
        import time

        result = a._fallback(STANDARD_NODES, 3000, time.time())
        assert result.fallback_used is True
        assert len(result.formatted_text) > 0
        assert len(result.included_nodes) > 0


# =============================================================================
# 11. Config Integration
# =============================================================================


class TestConfigIntegration:
    def test_assembly_flag_default_on(self):
        cfg = BrainConfig()
        assert cfg.llm_knowledge_assembly is True

    def test_assembly_flag_env_override(self):
        with mock.patch.dict(os.environ, {"BRAIN_LLM_KNOWLEDGE_ASSEMBLY": "false"}):
            cfg = BrainConfig()
            assert cfg.llm_knowledge_assembly is False

    def test_assembly_result_type(self):
        from engineering_brain.core.types import AssemblyResult

        r = AssemblyResult()
        assert r.strategy == "direct"
        assert r.quality_score == 0.0
        assert r.fallback_used is False
        assert r.by_layer == {"L1": [], "L2": [], "L3": [], "L4": []}


# =============================================================================
# 12. by_layer in AssemblyResult
# =============================================================================


class TestByLayer:
    def test_direct_assembly_populates_by_layer(self):
        """DIRECT strategy should populate by_layer correctly."""
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble("what is CORS?", ctx, STANDARD_NODES[:5])
        assert result.strategy == "direct"
        # by_layer should be populated from included_nodes
        total = sum(len(v) for v in result.by_layer.values())
        assert total == len(result.included_nodes)

    def test_fallback_populates_by_layer(self):
        """Fallback path should populate by_layer."""
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        with mock.patch.dict(os.environ, {}, clear=True):
            result = a.assemble("Flask CORS", ctx, STANDARD_NODES)
        assert result.fallback_used is True
        assert isinstance(result.by_layer, dict)
        assert "L1" in result.by_layer
        assert "L3" in result.by_layer

    def test_empty_result_has_empty_by_layer(self):
        a = _make_assembler()
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble("something", MockContext(), [])
        assert result.by_layer == {"L1": [], "L2": [], "L3": [], "L4": []}

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_curated_populates_by_layer(self, mock_flag, mock_llm):
        mock_llm.return_value = {
            "selected": [
                {"id": "CR-SEC-001", "treatment": "full"},
                {"id": "P-CACHE-001", "treatment": "summary"},
            ],
            "summary_hint": "Test.",
        }
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask", "Redis"], domains=["security"])
        many_nodes = STANDARD_NODES + [
            _node(f"X-{i}", f"Extra rule {i}", 0.5 + i * 0.01) for i in range(8)
        ]
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble(
                "implement Flask CORS middleware for secure API endpoints with Redis caching",
                ctx,
                many_nodes,
            )
        assert result.strategy == "curated"
        # L2 should have the cache pattern, L3 should have the CORS rule
        assert any(n.get("id") == "P-CACHE-001" for n in result.by_layer.get("L2", []))
        assert any(n.get("id") == "CR-SEC-001" for n in result.by_layer.get("L3", []))


# =============================================================================
# 13. Boundary + Realistic Cases
# =============================================================================


class TestBoundaryCases:
    def test_classification_boundary_10_nodes(self):
        """Exactly 10 nodes with short query → SIMPLE. 11 → MODERATE."""
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        _, strategy_10 = a._classify("CORS?", ctx, 10)
        assert strategy_10 == AssemblyStrategy.DIRECT
        _, strategy_11 = a._classify("CORS?", ctx, 11)
        assert strategy_11 == AssemblyStrategy.CURATED

    def test_classification_boundary_8_words(self):
        """8-word query with 1 tech, 1 domain, ≤10 nodes → SIMPLE."""
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"], domains=["security"])
        c, _ = a._classify("how do I set up CORS headers", ctx, 5)
        assert c == QueryComplexity.SIMPLE
        # 10 words → MODERATE (exceeds 8-word SIMPLE threshold)
        c2, _ = a._classify("how do I set up CORS headers correctly now please", ctx, 5)
        assert c2 == QueryComplexity.MODERATE

    def test_realistic_long_nodes(self):
        """Assembly handles realistic 2000+ char nodes gracefully."""
        a = _make_assembler()
        long_why = "Because " + "security implications are severe and " * 50
        long_how = "To fix this, " + "configure the middleware properly and " * 50
        big_node = _node(
            "BIG-001",
            "Set CORS origins explicitly",
            0.9,
            severity="critical",
            why=long_why[:2000],
            how=long_how[:2000],
        )
        ctx = MockContext(technologies=["Flask"])
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble("CORS", ctx, [big_node])
        assert result.strategy == "direct"
        assert len(result.formatted_text) > 0

    def test_fallback_quality_is_zero(self):
        """Fallback path has quality_score=0.0 (no quality assessment done)."""
        a = _make_assembler()
        import time

        result = a._fallback(STANDARD_NODES, 3000, time.time())
        assert result.quality_score == 0.0

    def test_empty_result_quality_is_zero(self):
        a = _make_assembler()
        result = a._empty_result(0.0)
        assert result.quality_score == 0.0

    def test_full_stack_hyphenated_triggers_complex(self):
        """'full-stack' (hyphenated) should trigger COMPLEX."""
        a = _make_assembler()
        ctx = MockContext(technologies=["React"])
        c, _ = a._classify("build a full-stack application", ctx, 5)
        assert c == QueryComplexity.COMPLEX

    def test_full_stack_spaced_triggers_complex(self):
        """'full stack' (space-separated) should also trigger COMPLEX."""
        a = _make_assembler()
        ctx = MockContext(technologies=["React"])
        c, _ = a._classify("build a full stack application", ctx, 5)
        assert c == QueryComplexity.COMPLEX


# =============================================================================
# 14. Missing Coverage — split_by_layer, rendering, exceptions
# =============================================================================


class TestSplitByLayerLabels:
    def test_label_based_fallback(self):
        """When _layer is missing, _label determines bucket."""
        a = _make_assembler()
        nodes = [
            {"id": "P1", "_label": "Principle", "text": "DRY"},
            {"id": "P2", "_label": "Pattern", "text": "Factory"},
            {"id": "R1", "_label": "Rule", "text": "No wildcards"},
            {"id": "F1", "_label": "Finding", "text": "Bug found"},
            {"id": "C1", "_label": "CodeExample", "text": "Good code"},
            {"id": "T1", "_label": "TestResult", "text": "Passed"},
            {"id": "U1", "_label": "Unknown", "text": "Unknown type"},
        ]
        by_layer = a._split_by_layer(nodes)
        assert any(n["id"] == "P1" for n in by_layer["L1"])
        assert any(n["id"] == "P2" for n in by_layer["L2"])
        assert any(n["id"] == "R1" for n in by_layer["L3"])
        assert any(n["id"] == "F1" for n in by_layer["L4"])
        assert any(n["id"] == "C1" for n in by_layer["L4"])
        assert any(n["id"] == "T1" for n in by_layer["L4"])
        # Unknown defaults to L3 (rules)
        assert any(n["id"] == "U1" for n in by_layer["L3"])


class TestRenderingEdgeCases:
    def test_when_not_applies_rendered(self):
        """when_not_applies should produce NOT WHEN: in full treatment."""
        a = _make_assembler()
        node = _node("T1", "Test rule", 0.8, why="Reason", how="Action")
        node["when_not_applies"] = "In test environments"
        rendered = a._render_node(node, "full")
        assert "NOT WHEN: In test environments" in rendered

    def test_prediction_untested_no_percentage(self):
        """Predictions with tested_count=0 render without percentage."""
        a = _make_assembler()
        node = dict(CORS_RULE)
        node["prediction_if"] = "wildcard CORS used"
        node["prediction_then"] = "XSS attacks possible"
        node["prediction_tested_count"] = 0
        node["prediction_success_count"] = 0
        rendered = a._render_node(node, "full")
        assert "PREDICT:" in rendered
        assert "%" not in rendered
        assert "IF wildcard CORS used THEN XSS attacks possible" in rendered

    def test_node_with_name_instead_of_text(self):
        """Nodes that use 'name' field instead of 'text' should render."""
        a = _make_assembler()
        node = {
            "id": "P1",
            "name": "Cache-Aside Pattern",
            "severity": "medium",
            "validation_status": "unvalidated",
            "reinforcement_count": 0,
        }
        rendered = a._render_node(node, "full")
        assert "Cache-Aside Pattern" in rendered


class TestExceptionFallback:
    def test_unexpected_exception_triggers_fallback(self):
        """Any exception in _assemble_internal triggers graceful fallback."""
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        with (
            mock.patch.object(a, "_is_assembly_enabled", return_value=True),
            mock.patch.object(a, "_classify", side_effect=TypeError("bad type")),
        ):
            result = a.assemble("Flask CORS", ctx, STANDARD_NODES)
        assert result.fallback_used is True
        assert len(result.formatted_text) > 0


class TestCuratedEdgeCases:
    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_returns_string_items_in_selected(self, mock_flag, mock_llm):
        """LLM might return plain string IDs instead of objects."""
        mock_llm.return_value = {
            "selected": ["CR-SEC-001", "CR-AUTH-001"],
            "summary_hint": "Security rules.",
        }
        a = _make_assembler()
        ctx = MockContext()
        formatted, included, _ = a._assemble_curated(
            "security",
            ctx,
            STANDARD_NODES[:3],
            6000,
        )
        assert "CR-SEC-001" in included
        assert "CR-AUTH-001" in included
        assert "CORS" in formatted

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call_json")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_llm_returns_hallucinated_ids(self, mock_flag, mock_llm):
        """LLM returns IDs that don't exist in candidates — falls back to direct."""
        mock_llm.return_value = {
            "selected": [
                {"id": "FAKE-001", "treatment": "full"},
                {"id": "FAKE-002", "treatment": "full"},
            ],
            "summary_hint": "Fake.",
        }
        a = _make_assembler()
        ctx = MockContext()
        formatted, _, _ = a._assemble_curated(
            "security",
            ctx,
            STANDARD_NODES[:3],
            6000,
        )
        # No matching IDs → ordered_nodes empty → falls back to direct
        assert len(formatted) > 0


class TestExtractMentionedIdsAccuracy:
    def test_no_false_positives_on_substring(self):
        """ID 'api' should NOT match inside 'capitalize'."""
        a = _make_assembler()
        nodes = [{"id": "api", "text": "test"}]
        text = "You should capitalize the first letter"
        ids = a._extract_mentioned_ids(text, nodes)
        assert "api" not in ids

    def test_matches_at_word_boundary(self):
        """ID should match when it appears as a standalone term."""
        a = _make_assembler()
        nodes = [{"id": "CR-SEC-001", "text": "test"}]
        text = "Rule CR-SEC-001 is critical"
        ids = a._extract_mentioned_ids(text, nodes)
        assert "CR-SEC-001" in ids

    def test_matches_at_start_and_end(self):
        """ID at the very start or end of text should match."""
        a = _make_assembler()
        nodes = [{"id": "CR-SEC-001", "text": "test"}]
        text = "CR-SEC-001 is important"
        ids = a._extract_mentioned_ids(text, nodes)
        assert "CR-SEC-001" in ids
        text2 = "Important: CR-SEC-001"
        ids2 = a._extract_mentioned_ids(text2, nodes)
        assert "CR-SEC-001" in ids2


class TestAssemblyResultValidation:
    def test_invalid_strategy_rejected(self):
        """AssemblyResult should reject invalid strategy values."""
        from pydantic import ValidationError

        from engineering_brain.core.types import AssemblyResult

        with pytest.raises(ValidationError):
            AssemblyResult(strategy="invalid_strategy")


# =============================================================================
# 15. Limitation Fixes
# =============================================================================


class TestLimitationFixes:
    """Tests for the 3 known limitations fixed in this iteration."""

    def test_content_fallback_matches_paraphrased_text(self):
        """D.1: When LLM paraphrases without IDs, content overlap infers nodes."""
        a = _make_assembler()
        # Paraphrased version of CORS_RULE text without citing the ID
        text = "Always set explicit CORS origins to prevent wildcard attacks"
        ids = a._extract_mentioned_ids(text, [CORS_RULE])
        assert "CR-SEC-001" in ids

    def test_exact_id_match_preferred_over_heuristic(self):
        """D.1: Exact ID match should be preferred (no fallback needed)."""
        a = _make_assembler()
        text = "Based on CR-SEC-001, you should set CORS origins."
        ids = a._extract_mentioned_ids(text, [CORS_RULE])
        assert "CR-SEC-001" in ids

    def test_validate_detects_bold_why(self):
        """D.2: _validate should detect **Why:** and Reason: patterns."""
        a = _make_assembler()
        text = "## Header\n- rule\n  **Why:** security\n  **Do:** configure"
        _, quality = a._validate(text, [], set(), 3000)
        # All 4 structure signals should be detected
        assert quality > 0.3

    def test_validate_detects_reason_action(self):
        """D.2: _validate should detect Reason: and Action: patterns."""
        a = _make_assembler()
        text = "## Header\n- rule\n  Reason: security\n  Action: fix it"
        _, quality = a._validate(text, [], set(), 3000)
        assert quality > 0.3

    def test_validate_detects_em_dash_separator(self):
        """D.2: _validate should handle em-dash separators."""
        a = _make_assembler()
        text = "## Header\n- rule\n  WHY— security matters\n  DO— fix CORS"
        _, quality = a._validate(text, [], set(), 3000)
        assert quality > 0.3

    def test_vertical_coverage_floor_rejects_zero_score(self):
        """D.3: Score 0.0 nodes should not be pulled for vertical coverage."""
        a = _make_assembler()
        ctx = MockContext()
        l3_nodes = [_node(f"R-{i}", f"Rule {i}", 0.8) for i in range(3)]
        l1_zero = _node("PR-ZERO", "Zero principle", 0.0, layer="L1")
        all_nodes = l3_nodes + [l1_zero]
        candidates = a._filter_candidates(all_nodes, QueryComplexity.MODERATE, ctx)
        ids = [n["id"] for n in candidates]
        # Score 0.0 is below the 0.10 floor → should NOT be pulled
        assert "PR-ZERO" not in ids

    def test_vertical_coverage_floor_accepts_above_threshold(self):
        """D.3: Score 0.15 nodes should be pulled for vertical coverage."""
        a = _make_assembler()
        ctx = MockContext()
        l3_nodes = [_node(f"R-{i}", f"Rule {i}", 0.8) for i in range(3)]
        l1_ok = _node("PR-OK", "OK principle", 0.15, layer="L1")
        all_nodes = l3_nodes + [l1_ok]
        candidates = a._filter_candidates(all_nodes, QueryComplexity.MODERATE, ctx)
        ids = [n["id"] for n in candidates]
        assert "PR-OK" in ids


# =============================================================================
# 16. Guardrail Integration in Assembler
# =============================================================================


class TestGuardrailIntegration:
    """Tests for guardrails integration in the assembly pipeline."""

    def test_guardrails_populated_when_flag_on(self):
        """AssemblyResult.guardrails should be populated when BRAIN_GUARDRAILS=true."""
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble("what is CORS?", ctx, STANDARD_NODES[:5])
        assert result.guardrails is not None
        # Should have at least some entries
        total = (
            len(result.guardrails.must_do)
            + len(result.guardrails.must_not_do)
            + len(result.guardrails.should_do)
            + len(result.guardrails.should_not_do)
            + len(result.guardrails.may_do)
        )
        assert total > 0

    def test_guardrails_none_when_flag_off(self):
        """AssemblyResult.guardrails should be None when guardrails disabled."""
        cfg = BrainConfig(guardrails_enabled=False)
        a = KnowledgeAssembler(config=cfg)
        ctx = MockContext(technologies=["Flask"])
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble("what is CORS?", ctx, STANDARD_NODES[:5])
        assert result.guardrails is None

    def test_guardrails_exception_non_blocking(self):
        """Guardrails failure should not break assembly."""
        a = _make_assembler()
        ctx = MockContext(technologies=["Flask"])
        with (
            mock.patch.object(a, "_is_assembly_enabled", return_value=True),
            mock.patch(
                "engineering_brain.retrieval.guardrails.annotate_guardrails",
                side_effect=RuntimeError("guardrails exploded"),
            ),
        ):
            result = a.assemble("what is CORS?", ctx, STANDARD_NODES[:5])
        # Assembly should still succeed, guardrails just None
        assert result.guardrails is None
        assert len(result.formatted_text) > 0

    def test_rendered_output_has_must_section(self):
        """Output should contain MUST DO section when guardrails annotated."""
        a = _make_assembler()
        # Critical + verified + E3 → MUST
        must_node = _node("MUST-001", "Always validate input", 0.9, severity="critical", layer="L3")
        must_node["validation_status"] = "human_verified"
        must_node["epistemic_status"] = "E3"
        ctx = MockContext(technologies=["Flask"])
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble("input validation", ctx, [must_node])
        assert "### MUST DO" in result.formatted_text

    def test_rendered_output_has_obligation_badges(self):
        """Rendered nodes should include [MUST] / [SHOULD] / [MAY] badges."""
        a = _make_assembler()
        must_node = _node("MUST-001", "Always validate input", 0.9, severity="critical", layer="L3")
        must_node["validation_status"] = "human_verified"
        must_node["epistemic_status"] = "E3"
        ctx = MockContext()
        with mock.patch.object(a, "_is_assembly_enabled", return_value=True):
            result = a.assemble("validation", ctx, [must_node])
        assert "[MUST]" in result.formatted_text

    def test_serialization_includes_obligation(self):
        """Serialized candidates should include obligation annotation."""
        a = _make_assembler()
        node = dict(CORS_RULE)
        node["_obligation"] = "MUST"
        serialized = a._serialize_candidates([node])
        assert "Obligation:MUST" in serialized

    def test_backward_compatible_no_guardrails(self):
        """When nodes have no _obligation key, rendering falls back to severity-based."""
        a = _make_assembler()
        ordered = [(CORS_RULE, "full"), (AUTH_RULE, "summary")]
        rendered = a._hydrate_curated(ordered, "test")
        # Should use severity-based sections (no _obligation on nodes)
        assert "### Critical Guidance" in rendered or "### Supporting Knowledge" in rendered
