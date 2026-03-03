"""Tests for the Thought Enhancement Layer.

Tests confidence tier classification, in-result contradiction detection,
query-relevant gap identification, metacognitive summary, enhanced formatting,
Brain.think() integration, and MCP tool handler.
"""

from __future__ import annotations

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.core.types import (
    ConfidenceTier,
    EnhancedKnowledgeResult,
    KnowledgeQuery,
    KnowledgeResult,
)
from engineering_brain.retrieval.context_extractor import ExtractedContext
from engineering_brain.retrieval.thought_enhancer import ThoughtEnhancer


# =========================================================================
# Fixtures
# =========================================================================


def _graph_with_nodes(*nodes):
    """Create a MemoryGraphAdapter pre-loaded with node dicts."""
    g = MemoryGraphAdapter()
    for n in nodes:
        label = "Rule"
        nid = n.get("id", "")
        if nid.startswith("P-"):
            label = "Principle"
        elif nid.startswith("PAT-"):
            label = "Pattern"
        elif nid.startswith("AX-"):
            label = "Axiom"
        g.add_node(label, nid, n)
    return g


def _make_rule(
    node_id,
    b=None, d=None, u=None, a=0.5,
    confidence=0.5, validation_status="unvalidated",
    eigentrust_score=0.5, technologies=None, domains=None,
    text="", why="", how_to_do_right="", severity="medium",
):
    node = {
        "id": node_id,
        "_layer": "L3",
        "text": text or f"Rule {node_id}",
        "why": why,
        "how_to_do_right": how_to_do_right,
        "severity": severity,
        "confidence": confidence,
        "validation_status": validation_status,
        "eigentrust_score": eigentrust_score,
        "technologies": technologies or [],
        "domains": domains or [],
    }
    if b is not None:
        node.update({"ep_b": b, "ep_d": d or 0.0, "ep_u": u or (1 - b - (d or 0.0)), "ep_a": a})
    return node


def _make_principle(node_id, b=None, d=None, u=None, a=0.5, **kw):
    node = _make_rule(node_id, b=b, d=d, u=u, a=a, **kw)
    node["_layer"] = "L1"
    node["name"] = node.pop("text")
    return node


def _ctx(technologies=None, domains=None, phase="exec"):
    return ExtractedContext(
        technologies=technologies or [],
        domains=domains or [],
        file_types=[],
        phase=phase,
    )


def _base_result(total_queried=10):
    return KnowledgeResult(total_nodes_queried=total_queried)


def _query(desc="test query", technologies=None, domains=None):
    return KnowledgeQuery(
        task_description=desc,
        technologies=technologies or [],
        domains=domains or [],
    )


# =========================================================================
# TestConfidenceTierClassification
# =========================================================================


class TestConfidenceTierClassification:
    """Test the decision tree for confidence tier assignment."""

    def test_validated_requires_all_four_signals(self):
        node = _make_rule(
            "CR-001", b=0.7, d=0.0, u=0.15, a=0.5,
            validation_status="cross_checked", eigentrust_score=0.5,
        )
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)
        assessments = enhancer._classify_confidence_tiers([node])
        assert assessments[0]["tier"] == ConfidenceTier.VALIDATED.value

    def test_contested_overrides_when_disbelief_high(self):
        node = _make_rule(
            "CR-001", b=0.5, d=0.4, u=0.1, a=0.5,
            validation_status="cross_checked", eigentrust_score=0.8,
        )
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)
        assessments = enhancer._classify_confidence_tiers([node])
        assert assessments[0]["tier"] == ConfidenceTier.CONTESTED.value

    def test_probable_mid_range_epistemic(self):
        node = _make_rule(
            "CR-001", b=0.55, d=0.0, u=0.45, a=0.5,
            validation_status="unvalidated", eigentrust_score=0.3,
        )
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)
        assessments = enhancer._classify_confidence_tiers([node])
        # P = 0.55 + 0.5*0.45 = 0.775, E = 0.55, but validation is unvalidated
        # so not validated. P >= 0.6 and E >= 0.3 → PROBABLE
        assert assessments[0]["tier"] == ConfidenceTier.PROBABLE.value

    def test_uncertain_low_epistemic(self):
        node = _make_rule(
            "CR-001", b=0.2, d=0.0, u=0.8, a=0.5,
            validation_status="unvalidated", eigentrust_score=0.1,
        )
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)
        assessments = enhancer._classify_confidence_tiers([node])
        assert assessments[0]["tier"] == ConfidenceTier.UNCERTAIN.value

    def test_fallback_validated_no_epistemic_data(self):
        node = _make_rule("CR-001", confidence=0.8, validation_status="human_verified")
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)
        assessments = enhancer._classify_confidence_tiers([node])
        assert assessments[0]["tier"] == ConfidenceTier.VALIDATED.value

    def test_fallback_probable_no_epistemic_data(self):
        node = _make_rule("CR-001", confidence=0.6, validation_status="unvalidated")
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)
        assessments = enhancer._classify_confidence_tiers([node])
        assert assessments[0]["tier"] == ConfidenceTier.PROBABLE.value

    def test_fallback_uncertain_no_epistemic_data(self):
        node = _make_rule("CR-001", confidence=0.3, validation_status="unvalidated")
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)
        assessments = enhancer._classify_confidence_tiers([node])
        assert assessments[0]["tier"] == ConfidenceTier.UNCERTAIN.value


# =========================================================================
# TestInResultContradictionDetection
# =========================================================================


class TestInResultContradictionDetection:
    """Test contradiction detection scoped to result set only."""

    def test_detects_contradiction_between_result_nodes(self):
        n1 = _make_rule("CR-001", b=0.8, d=0.1, u=0.1)
        n2 = _make_rule("CR-002", b=0.1, d=0.8, u=0.1)
        g = _graph_with_nodes(n1, n2)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")

        enhancer = ThoughtEnhancer(graph=g)
        contradictions = enhancer._detect_in_result_contradictions([n1, n2])
        assert len(contradictions) == 1
        assert contradictions[0]["conflict_k"] > 0.3

    def test_ignores_conflict_outside_result_set(self):
        n1 = _make_rule("CR-001", b=0.8, d=0.1, u=0.1)
        n2 = _make_rule("CR-002", b=0.1, d=0.8, u=0.1)
        n3 = _make_rule("CR-003", b=0.9, d=0.0, u=0.1)
        g = _graph_with_nodes(n1, n2, n3)
        g.add_edge("CR-001", "CR-003", "CONFLICTS_WITH")

        enhancer = ThoughtEnhancer(graph=g)
        # Only n1 and n2 in result; n3 is NOT in result
        contradictions = enhancer._detect_in_result_contradictions([n1, n2])
        assert len(contradictions) == 0

    def test_deduplicates_bidirectional_conflicts(self):
        n1 = _make_rule("CR-001", b=0.8, d=0.1, u=0.1)
        n2 = _make_rule("CR-002", b=0.1, d=0.8, u=0.1)
        g = _graph_with_nodes(n1, n2)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")
        g.add_edge("CR-002", "CR-001", "CONFLICTS_WITH")

        enhancer = ThoughtEnhancer(graph=g)
        contradictions = enhancer._detect_in_result_contradictions([n1, n2])
        assert len(contradictions) == 1

    def test_no_conflicts_returns_empty(self):
        n1 = _make_rule("CR-001", b=0.8, d=0.0, u=0.2)
        n2 = _make_rule("CR-002", b=0.7, d=0.0, u=0.3)
        g = _graph_with_nodes(n1, n2)

        enhancer = ThoughtEnhancer(graph=g)
        contradictions = enhancer._detect_in_result_contradictions([n1, n2])
        assert len(contradictions) == 0

    def test_handles_nodes_without_epistemic_data(self):
        n1 = _make_rule("CR-001")
        n2 = _make_rule("CR-002")
        g = _graph_with_nodes(n1, n2)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")

        enhancer = ThoughtEnhancer(graph=g)
        contradictions = enhancer._detect_in_result_contradictions([n1, n2])
        # Still reports contradiction, uses fallback K=0.5
        assert len(contradictions) == 1
        assert contradictions[0]["conflict_k"] == 0.5

    def test_high_conflict_description_says_strong(self):
        n1 = _make_rule("CR-001", b=0.9, d=0.0, u=0.1)
        n2 = _make_rule("CR-002", b=0.0, d=0.9, u=0.1)
        g = _graph_with_nodes(n1, n2)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")

        enhancer = ThoughtEnhancer(graph=g)
        contradictions = enhancer._detect_in_result_contradictions([n1, n2])
        assert "STRONG CONFLICT" in contradictions[0]["description"]

    def test_low_conflict_filtered_out(self):
        # Two nodes that agree — K will be near 0 → ConflictSeverity.NONE → not reported
        n1 = _make_rule("CR-001", b=0.8, d=0.0, u=0.2)
        n2 = _make_rule("CR-002", b=0.7, d=0.0, u=0.3)
        g = _graph_with_nodes(n1, n2)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")

        enhancer = ThoughtEnhancer(graph=g)
        contradictions = enhancer._detect_in_result_contradictions([n1, n2])
        assert len(contradictions) == 0


# =========================================================================
# TestQueryGapIdentification
# =========================================================================


class TestQueryGapIdentification:
    """Test the 5 gap detection methods."""

    def test_missing_technology_gap(self):
        node = _make_rule("CR-001", b=0.8, d=0.0, u=0.2, technologies=["flask"])
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)

        ctx = _ctx(technologies=["flask", "redis"])
        gaps = enhancer._identify_query_gaps(ctx, [node])
        types = [g_["gap_type"] for g_ in gaps]
        assert "missing_technology" in types

    def test_no_missing_technology_when_covered(self):
        node = _make_rule("CR-001", b=0.8, d=0.0, u=0.2, technologies=["flask"])
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)

        ctx = _ctx(technologies=["flask"])
        gaps = enhancer._identify_query_gaps(ctx, [node])
        types = [g_["gap_type"] for g_ in gaps]
        assert "missing_technology" not in types

    def test_missing_principles_gap(self):
        node = _make_rule("CR-001", b=0.8, d=0.0, u=0.2)
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)

        ctx = _ctx()
        gaps = enhancer._identify_query_gaps(ctx, [node])
        types = [g_["gap_type"] for g_ in gaps]
        assert "missing_principles" in types

    def test_high_aggregate_uncertainty(self):
        nodes = [
            _make_rule(f"CR-{i:03d}", b=0.1, d=0.0, u=0.9)
            for i in range(5)
        ]
        g = _graph_with_nodes(*nodes)
        enhancer = ThoughtEnhancer(graph=g)

        ctx = _ctx()
        gaps = enhancer._identify_query_gaps(ctx, nodes)
        types = [g_["gap_type"] for g_ in gaps]
        assert "high_aggregate_uncertainty" in types

    def test_unsupported_rules_gap(self):
        nodes = [_make_rule(f"CR-{i:03d}", b=0.8, d=0.0, u=0.2) for i in range(4)]
        g = _graph_with_nodes(*nodes)
        # No EVIDENCED_BY edges → all unsupported → > 50%
        enhancer = ThoughtEnhancer(graph=g)

        ctx = _ctx()
        gaps = enhancer._identify_query_gaps(ctx, nodes)
        types = [g_["gap_type"] for g_ in gaps]
        assert "unsupported_rules" in types

    def test_no_gaps_for_well_covered_query(self):
        principle = _make_principle("P-001", b=0.8, d=0.0, u=0.2)
        rule = _make_rule("CR-001", b=0.8, d=0.0, u=0.2, technologies=["flask"])
        g = _graph_with_nodes(principle, rule)
        g.add_edge("CR-001", "P-001", "EVIDENCED_BY")

        enhancer = ThoughtEnhancer(graph=g)
        ctx = _ctx(technologies=["flask"])
        gaps = enhancer._identify_query_gaps(ctx, [principle, rule])
        # All covered: tech present, principles present, low uncertainty, rules supported
        assert len(gaps) == 0


# =========================================================================
# TestMetacognitiveSummary
# =========================================================================


class TestOverallConfidence:
    """Test overall confidence determination edge cases."""

    def test_empty_assessments_returns_empty_overall(self):
        """Regression: 0 >= 0*0.7 was True, falsely returning 'validated'."""
        g = MemoryGraphAdapter()
        enhancer = ThoughtEnhancer(graph=g)
        result = enhancer.enhance(
            query=_query(), query_context=_ctx(),
            scored_nodes=[], base_result=_base_result(total_queried=0),
        )
        assert result.overall_confidence == ""
        assert result.confidence_distribution == {}

    def test_single_validated_node_is_validated(self):
        node = _make_rule(
            "CR-001", b=0.7, d=0.0, u=0.15,
            validation_status="cross_checked", eigentrust_score=0.5,
        )
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)
        result = enhancer.enhance(
            query=_query(), query_context=_ctx(),
            scored_nodes=[node], base_result=_base_result(),
        )
        assert result.overall_confidence == ConfidenceTier.VALIDATED.value


class TestMetacognitiveSummary:
    """Test metacognitive summary generation."""

    def test_empty_returns_no_knowledge_message(self):
        g = MemoryGraphAdapter()
        enhancer = ThoughtEnhancer(graph=g)
        meta = enhancer._compose_metacognitive_summary([], [], [], 0)
        assert "no relevant knowledge" in meta.lower()

    def test_high_confidence_message(self):
        assessments = [
            {"tier": "validated", "node_id": f"CR-{i:03d}"}
            for i in range(8)
        ] + [
            {"tier": "probable", "node_id": "CR-008"},
            {"tier": "uncertain", "node_id": "CR-009"},
        ]
        g = MemoryGraphAdapter()
        enhancer = ThoughtEnhancer(graph=g)
        meta = enhancer._compose_metacognitive_summary(assessments, [], [], 20)
        assert "HIGH CONFIDENCE" in meta

    def test_contested_dominates(self):
        assessments = [
            {"tier": "contested", "node_id": f"CR-{i:03d}"}
            for i in range(5)
        ] + [
            {"tier": "validated", "node_id": "CR-005"},
        ]
        g = MemoryGraphAdapter()
        enhancer = ThoughtEnhancer(graph=g)
        meta = enhancer._compose_metacognitive_summary(assessments, [], [], 10)
        assert "CONTESTED" in meta

    def test_contradictions_add_warning(self):
        assessments = [{"tier": "validated", "node_id": "CR-001"}]
        contradictions = [{
            "severity": "high",
            "description": "test conflict",
            "node_a_id": "CR-001",
            "node_b_id": "CR-002",
        }]
        g = MemoryGraphAdapter()
        enhancer = ThoughtEnhancer(graph=g)
        meta = enhancer._compose_metacognitive_summary(assessments, contradictions, [], 5)
        assert "WARNING" in meta

    def test_gaps_appear_in_summary(self):
        assessments = [{"tier": "uncertain", "node_id": "CR-001"}]
        gaps = [{"severity": 0.8, "description": "No knowledge for Redis"}]
        g = MemoryGraphAdapter()
        enhancer = ThoughtEnhancer(graph=g)
        meta = enhancer._compose_metacognitive_summary(assessments, [], gaps, 5)
        assert "Redis" in meta

    def test_low_confidence_message(self):
        assessments = [
            {"tier": "uncertain", "node_id": f"CR-{i:03d}"}
            for i in range(8)
        ]
        g = MemoryGraphAdapter()
        enhancer = ThoughtEnhancer(graph=g)
        meta = enhancer._compose_metacognitive_summary(assessments, [], [], 20)
        assert "LOW CONFIDENCE" in meta


# =========================================================================
# TestEnhancedFormatting
# =========================================================================


class TestEnhancedFormatting:
    """Test the epistemically-annotated markdown output."""

    def test_output_contains_brain_assessment(self):
        node = _make_rule("CR-001", b=0.8, d=0.0, u=0.2, text="Use HTTPS")
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)

        result = enhancer.enhance(
            query=_query(), query_context=_ctx(),
            scored_nodes=[node], base_result=_base_result(),
        )
        assert "## Brain Assessment" in result.enhanced_text

    def test_tiers_appear_as_sections(self):
        validated = _make_rule(
            "CR-001", b=0.7, d=0.0, u=0.15,
            validation_status="cross_checked", eigentrust_score=0.5,
            text="Validate inputs",
        )
        uncertain = _make_rule("CR-002", b=0.2, d=0.0, u=0.8, text="Maybe cache")
        g = _graph_with_nodes(validated, uncertain)
        enhancer = ThoughtEnhancer(graph=g)

        result = enhancer.enhance(
            query=_query(), query_context=_ctx(),
            scored_nodes=[validated, uncertain], base_result=_base_result(),
        )
        assert "[VALIDATED]" in result.enhanced_text
        assert "[UNCERTAIN]" in result.enhanced_text

    def test_contradictions_section_present(self):
        n1 = _make_rule("CR-001", b=0.8, d=0.1, u=0.1, text="Enable CORS")
        n2 = _make_rule("CR-002", b=0.1, d=0.8, u=0.1, text="Disable CORS")
        g = _graph_with_nodes(n1, n2)
        g.add_edge("CR-001", "CR-002", "CONFLICTS_WITH")

        enhancer = ThoughtEnhancer(graph=g)
        result = enhancer.enhance(
            query=_query(), query_context=_ctx(),
            scored_nodes=[n1, n2], base_result=_base_result(),
        )
        assert "## Contradictions Detected" in result.enhanced_text

    def test_gaps_section_present(self):
        node = _make_rule("CR-001", b=0.8, d=0.0, u=0.2, technologies=["flask"])
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)

        result = enhancer.enhance(
            query=_query(technologies=["flask", "redis"]),
            query_context=_ctx(technologies=["flask", "redis"]),
            scored_nodes=[node], base_result=_base_result(),
        )
        assert "## Knowledge Gaps" in result.enhanced_text

    def test_budget_enforced(self):
        nodes = [
            _make_rule(f"CR-{i:03d}", b=0.5, d=0.0, u=0.5, text=f"Rule {i} " * 20)
            for i in range(20)
        ]
        g = _graph_with_nodes(*nodes)
        enhancer = ThoughtEnhancer(graph=g)

        result = enhancer.enhance(
            query=_query(), query_context=_ctx(),
            scored_nodes=nodes, base_result=_base_result(),
            budget_chars=500,
        )
        assert len(result.enhanced_text) <= 500

    def test_node_tag_format(self):
        node = _make_rule(
            "CR-001", b=0.7, d=0.0, u=0.15,
            validation_status="cross_checked", eigentrust_score=0.5,
        )
        g = _graph_with_nodes(node)
        enhancer = ThoughtEnhancer(graph=g)
        assessment = enhancer._classify_confidence_tiers([node])[0]
        tag = enhancer._format_node_tag(assessment)
        assert "VALIDATED" in tag
        assert "P=" in tag
        assert "CROSS-CHECKED" in tag


# =========================================================================
# TestBrainThinkIntegration
# =========================================================================


class TestBrainThinkIntegration:
    """Integration tests using the full Brain.think() method."""

    def test_think_returns_enhanced_result(self):
        from engineering_brain.core.brain import Brain

        brain = Brain()
        brain.seed()

        result = brain.think(
            "Flask CORS security in production",
            technologies=["Flask", "CORS"],
        )
        assert isinstance(result, EnhancedKnowledgeResult)
        assert result.metacognitive_summary != ""
        assert result.enhanced_text != ""
        assert result.overall_confidence != ""

    def test_think_confidence_distribution_sums_correctly(self):
        from engineering_brain.core.brain import Brain

        brain = Brain()
        brain.seed()

        result = brain.think("Python error handling best practices", technologies=["Python"])
        total = sum(result.confidence_distribution.values())
        assert total == len(result.assessments)

    def test_think_with_bootstrapped_brain(self):
        from engineering_brain.core.brain import Brain

        brain = Brain()
        brain.seed()
        brain.bootstrap_epistemic()

        result = brain.think("Flask security")
        assert isinstance(result, EnhancedKnowledgeResult)
        # With bootstrapped epistemic data, assessments should have projected_probability > 0
        for a in result.assessments:
            assert a["projected_probability"] >= 0.0


# =========================================================================
# TestMCPToolHandler
# =========================================================================


class TestMCPToolHandler:
    """Test the brain_think MCP tool handler."""

    def test_handler_returns_enhanced_output(self):
        from engineering_brain.mcp_server import _handle_brain_think

        response = _handle_brain_think({"query": "Flask CORS security"})
        assert "Engineering Brain" in response
        assert "Enhanced Epistemic Query" in response

    def test_handler_empty_query_returns_error(self):
        from engineering_brain.mcp_server import _handle_brain_think

        response = _handle_brain_think({})
        assert "Error" in response

    def test_handler_with_technologies(self):
        from engineering_brain.mcp_server import _handle_brain_think

        response = _handle_brain_think({
            "query": "Flask security",
            "technologies": ["Flask"],
        })
        assert "Confidence" in response

    def test_brain_think_tool_registered(self):
        from engineering_brain.mcp_server import TOOLS, _TOOL_HANDLERS

        tool_names = [t["name"] for t in TOOLS]
        assert "brain_think" in tool_names
        assert "brain_think" in _TOOL_HANDLERS
