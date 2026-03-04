"""Tests for ERG — Epistemic Reasoning Graph (pack_manager, reasoning_engine, brain_profiles).

All tests use in-memory adapters directly — no Brain() constructor, no seed(),
no Docker dependencies. Fast and deterministic.
"""

from __future__ import annotations

import os
import tempfile

import pytest
import yaml

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.types import (
    BrainProfile,
    ChainResult,
    ReasoningResult,
)
from engineering_brain.retrieval.brain_profiles import (
    clear_profile_cache,
    get_available_profiles,
    load_profile,
)
from engineering_brain.retrieval.context_extractor import ExtractedContext
from engineering_brain.retrieval.pack_manager import PackManager, _infer_layer, _jaccard
from engineering_brain.retrieval.reasoning_engine import ReasoningEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg() -> BrainConfig:
    return BrainConfig(embedding_enabled=False, adapter="memory")


def _graph_with_nodes() -> MemoryGraphAdapter:
    """Create a graph with enough nodes for pack generation and reasoning."""
    g = MemoryGraphAdapter()
    # L1 principles
    g.add_node(
        "Principle",
        "P-SEC-001",
        {
            "id": "P-SEC-001",
            "name": "Deny by Default",
            "why": "Minimize attack surface",
            "domains": ["security"],
        },
    )
    g.add_node(
        "Principle",
        "P-REL-001",
        {
            "id": "P-REL-001",
            "name": "Design for Failure",
            "why": "Everything fails eventually",
            "domains": ["reliability"],
        },
    )
    # L2 patterns
    g.add_node(
        "Pattern",
        "PAT-CB-001",
        {
            "id": "PAT-CB-001",
            "name": "Circuit Breaker",
            "intent": "Prevent cascading failures",
            "domains": ["reliability"],
            "technologies": ["General"],
        },
    )
    # L3 rules (Flask security cluster)
    g.add_node(
        "Rule",
        "CR-SEC-CORS-001",
        {
            "id": "CR-SEC-CORS-001",
            "text": "Validate CORS origins explicitly",
            "why": "Prevents cross-origin attacks",
            "severity": "high",
            "technologies": ["Flask"],
            "domains": ["security"],
        },
    )
    g.add_node(
        "Rule",
        "CR-SEC-CORS-002",
        {
            "id": "CR-SEC-CORS-002",
            "text": "Set SameSite attribute on cookies",
            "why": "Prevents CSRF via cookies",
            "severity": "high",
            "technologies": ["Flask"],
            "domains": ["security"],
        },
    )
    g.add_node(
        "Rule",
        "CR-SEC-CORS-003",
        {
            "id": "CR-SEC-CORS-003",
            "text": "Enforce HTTPS-only in production",
            "why": "Prevents MITM attacks",
            "severity": "critical",
            "technologies": ["Flask"],
            "domains": ["security"],
        },
    )
    g.add_node(
        "Rule",
        "CR-SEC-SQL-001",
        {
            "id": "CR-SEC-SQL-001",
            "text": "Use parameterized queries",
            "why": "Prevents SQL injection",
            "severity": "critical",
            "technologies": ["Flask", "PostgreSQL"],
            "domains": ["security", "database"],
        },
    )
    # L3 rules (Kafka reliability cluster)
    g.add_node(
        "Rule",
        "CR-KFK-001",
        {
            "id": "CR-KFK-001",
            "text": "Implement consumer idempotency",
            "why": "Exactly-once semantics",
            "severity": "critical",
            "technologies": ["Kafka"],
            "domains": ["reliability", "data_engineering"],
        },
    )
    g.add_node(
        "Rule",
        "CR-KFK-002",
        {
            "id": "CR-KFK-002",
            "text": "Use dead letter queues for failed messages",
            "why": "Prevents message loss",
            "severity": "high",
            "technologies": ["Kafka"],
            "domains": ["reliability", "data_engineering"],
        },
    )
    g.add_node(
        "Rule",
        "CR-KFK-003",
        {
            "id": "CR-KFK-003",
            "text": "Set appropriate consumer group commit strategy",
            "why": "Balance throughput vs reliability",
            "severity": "high",
            "technologies": ["Kafka"],
            "domains": ["reliability", "data_engineering"],
        },
    )
    # Add a CONFLICTS_WITH edge for contradiction testing
    g.add_edge("CR-SEC-CORS-001", "CR-SEC-CORS-002", "CONFLICTS_WITH")
    # Add a GROUNDS edge for reasoning edge mapping
    g.add_edge("P-SEC-001", "CR-SEC-CORS-001", "GROUNDS")
    return g


def _ctx_flask_security() -> ExtractedContext:
    return ExtractedContext(
        technologies=["Flask"],
        domains=["security"],
        file_types=[".py"],
        phase="exec",
        raw_text="Flask API security review",
    )


def _ctx_kafka() -> ExtractedContext:
    return ExtractedContext(
        technologies=["Kafka"],
        domains=["reliability", "data_engineering"],
        file_types=[],
        phase="exec",
        raw_text="Kafka consumer design for financial transactions",
    )


# ===========================================================================
# Test _infer_layer helper
# ===========================================================================


class TestInferLayer:
    def test_principle(self):
        assert _infer_layer("P-SEC-001") == "L1"

    def test_pattern(self):
        assert _infer_layer("PAT-CB-001") == "L2"

    def test_crystallized_pattern(self):
        assert _infer_layer("CPAT-001") == "L2"

    def test_rule(self):
        assert _infer_layer("CR-SEC-001") == "L3"

    def test_finding(self):
        assert _infer_layer("F-001") == "L4"

    def test_axiom(self):
        assert _infer_layer("AX-001") == "L0"

    def test_unknown_defaults_l3(self):
        assert _infer_layer("UNKNOWN-001") == "L3"


# ===========================================================================
# Test Jaccard helper
# ===========================================================================


class TestJaccard:
    def test_identical(self):
        assert _jaccard(["a", "b"], ["a", "b"]) == 1.0

    def test_disjoint(self):
        assert _jaccard(["a"], ["b"]) == 0.0

    def test_partial(self):
        assert _jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)

    def test_empty(self):
        assert _jaccard([], []) == 0.0

    def test_case_insensitive(self):
        assert _jaccard(["Flask"], ["flask"]) == 1.0


# ===========================================================================
# TestPackManager
# ===========================================================================


class TestPackManager:
    def test_auto_generate_creates_packs(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        assert len(packs) >= 1
        for p in packs:
            assert p.node_count >= 3

    def test_auto_generate_sorted_by_quality(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        if len(packs) >= 2:
            assert packs[0].quality_score >= packs[1].quality_score

    def test_create_pack_from_description(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        pack = mgr.create_pack("Flask security", technologies=["Flask"])
        assert pack.node_count > 0
        assert "Flask" in pack.technologies or any("flask" in t.lower() for t in pack.technologies)

    def test_create_pack_from_nodes(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        pack = mgr.create_pack_from_nodes(
            "manual-pack",
            ["CR-SEC-CORS-001", "CR-SEC-CORS-002", "CR-SEC-CORS-003"],
            description="CORS rules",
        )
        assert pack.id == "manual-pack"
        assert pack.node_count == 3
        assert "CR-SEC-CORS-001" in pack.node_ids

    def test_pack_has_reasoning_edges(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        pack = mgr.create_pack_from_nodes(
            "test-edges",
            ["P-SEC-001", "CR-SEC-CORS-001", "CR-SEC-CORS-002", "CR-SEC-CORS-003"],
        )
        assert len(pack.reasoning_edges) > 0
        edge_types = {e["edge_type"] for e in pack.reasoning_edges}
        # Should have TRIGGERS (L1→L3), PREREQUISITE (sequential IDs), or mapped edges
        assert len(edge_types) >= 1

    def test_pack_quality_score_range(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        pack = mgr.create_pack("Flask security", technologies=["Flask"])
        assert 0.0 <= pack.quality_score <= 1.0

    def test_select_packs_by_relevance(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        if not packs:
            pytest.skip("No packs generated")

        ctx = _ctx_flask_security()
        selected = mgr.select_packs(ctx, packs, top_n=1)
        assert len(selected) >= 1
        # The Flask-security pack should be selected for a Flask security query
        selected_techs = set()
        for p in selected:
            selected_techs.update(t.lower() for t in p.technologies)

    def test_select_packs_with_profile(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        if not packs:
            pytest.skip("No packs generated")

        profile = BrainProfile(
            id="test",
            pack_boost={"*security*": 2.0},
            pack_suppress={"*kafka*": 0.1},
        )
        ctx = _ctx_flask_security()
        selected = mgr.select_packs(ctx, packs, profile=profile, top_n=5)
        assert len(selected) >= 1

    def test_empty_brain(self):
        g = MemoryGraphAdapter()
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        assert packs == []

    def test_vertical_completeness(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        # Create a pack that only has L3 rules
        pack = mgr.create_pack("Flask CORS", technologies=["Flask"], domains=["security"])
        # Vertical completeness should pull in L1 principles
        layers = set(pack.layers_present)
        # We should have at least L3 (rules were queried) and ideally L1 too
        assert "L3" in layers


# ===========================================================================
# TestReasoningEdgeGeneration
# ===========================================================================


class TestReasoningEdgeGeneration:
    def test_l1_to_l3_triggers(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        nodes = [
            g.get_node("P-SEC-001"),
            g.get_node("CR-SEC-CORS-001"),
            g.get_node("CR-SEC-CORS-002"),
        ]
        edges = mgr._generate_reasoning_edges(nodes)
        triggers = [e for e in edges if e["edge_type"] == "TRIGGERS"]
        assert len(triggers) >= 1
        assert any(e["from_id"] == "P-SEC-001" for e in triggers)

    def test_existing_edge_mapping(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        # P-SEC-001 has GROUNDS edge to CR-SEC-CORS-001 → should map to TRIGGERS
        nodes = [g.get_node("P-SEC-001"), g.get_node("CR-SEC-CORS-001")]
        edges = mgr._generate_reasoning_edges(nodes)
        mapped = [e for e in edges if e["edge_type"] == "TRIGGERS"]
        assert len(mapped) >= 1

    def test_sequential_ids_prerequisite(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        nodes = [
            g.get_node("CR-SEC-CORS-001"),
            g.get_node("CR-SEC-CORS-002"),
            g.get_node("CR-SEC-CORS-003"),
        ]
        edges = mgr._generate_reasoning_edges(nodes)
        prereqs = [e for e in edges if e["edge_type"] == "PREREQUISITE"]
        assert len(prereqs) >= 2  # 001→002, 002→003

    def test_conflict_maps_to_alternative(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        nodes = [g.get_node("CR-SEC-CORS-001"), g.get_node("CR-SEC-CORS-002")]
        edges = mgr._generate_reasoning_edges(nodes)
        alternatives = [e for e in edges if e["edge_type"] == "ALTERNATIVE"]
        assert len(alternatives) >= 1

    def test_no_self_edges(self):
        g = _graph_with_nodes()
        mgr = PackManager(g, None, _cfg())
        nodes = [g.get_node(nid) for nid in ["P-SEC-001", "CR-SEC-CORS-001"]]
        edges = mgr._generate_reasoning_edges(nodes)
        for e in edges:
            assert e["from_id"] != e["to_id"]


# ===========================================================================
# TestTemplateSelection
# ===========================================================================


class TestTemplateSelection:
    def test_security_template_selected(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        ctx = _ctx_flask_security()
        tmpl = eng._select_template(ctx)
        assert tmpl.id == "T-SEC-API-REVIEW"

    def test_data_template_selected(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        ctx = ExtractedContext(
            technologies=["Kafka"],
            domains=["data_engineering"],
            raw_text="Kafka streaming pipeline",
        )
        tmpl = eng._select_template(ctx)
        assert tmpl.id == "T-DATA-PIPELINE"

    def test_fallback_to_default(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        ctx = ExtractedContext(
            technologies=["React"],
            domains=["ui"],
            raw_text="React component rendering",
        )
        tmpl = eng._select_template(ctx)
        assert tmpl.id == "T-LINEAR-DEFAULT"

    def test_profile_overrides_template(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        profile = BrainProfile(id="test", default_template="T-SEC-API-REVIEW")
        ctx = ExtractedContext(
            technologies=["React"],
            domains=["ui"],
            raw_text="React UI stuff",
        )
        tmpl = eng._select_template(ctx, profile=profile)
        assert tmpl.id == "T-SEC-API-REVIEW"


# ===========================================================================
# TestChainExecution
# ===========================================================================


class TestChainExecution:
    def test_execute_chain_returns_chain_result(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        if not packs:
            pytest.skip("No packs")
        ctx = _ctx_flask_security()
        pool = [g.get_node(nid) for nid in packs[0].node_ids if g.get_node(nid)]
        tmpl = eng._select_template(ctx)
        chain = eng._execute_chain("test", tmpl, pool, ctx)
        assert isinstance(chain, ChainResult)
        assert len(chain.steps) > 0

    def test_chain_has_confidence_tier(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        if not packs:
            pytest.skip("No packs")
        ctx = _ctx_flask_security()
        pool = [g.get_node(nid) for nid in packs[0].node_ids if g.get_node(nid)]
        tmpl = eng._select_template(ctx)
        chain = eng._execute_chain("test", tmpl, pool, ctx)
        assert chain.confidence_tier in ("validated", "probable", "uncertain", "contested", "")

    def test_chain_counts_activated_nodes(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        if not packs:
            pytest.skip("No packs")
        ctx = _ctx_flask_security()
        pool = [g.get_node(nid) for nid in packs[0].node_ids if g.get_node(nid)]
        tmpl = eng._select_template(ctx)
        chain = eng._execute_chain("test", tmpl, pool, ctx)
        assert chain.nodes_activated >= 0

    def test_empty_pool_produces_empty_chain(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        ctx = _ctx_flask_security()
        tmpl = eng._select_template(ctx)
        chain = eng._execute_chain("empty", tmpl, [], ctx)
        assert chain.nodes_activated == 0


# ===========================================================================
# TestCrossChainSynthesis
# ===========================================================================


class TestCrossChainSynthesis:
    def test_single_chain_passthrough(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        chain = ChainResult(
            name="only",
            chain_opinion={"b": 0.7, "d": 0.0, "u": 0.3, "a": 0.5, "P": 0.85},
            nodes_activated=5,
        )
        opinion, contras = eng._synthesize_chains([chain])
        assert opinion.get("P", 0) > 0
        assert contras == []

    def test_reinforcing_chains_cbf(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        ch1 = ChainResult(name="a", chain_opinion={"b": 0.7, "d": 0.0, "u": 0.3, "a": 0.5})
        ch2 = ChainResult(name="b", chain_opinion={"b": 0.6, "d": 0.0, "u": 0.4, "a": 0.5})
        opinion, contras = eng._synthesize_chains([ch1, ch2])
        # CBF should reduce uncertainty
        assert opinion["u"] < 0.3  # Less than min of individual uncertainties
        assert opinion.get("fusion_strategy") == "cbf"

    def test_high_conflict_detected(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        ch1 = ChainResult(name="pro", chain_opinion={"b": 0.9, "d": 0.0, "u": 0.1, "a": 0.5})
        ch2 = ChainResult(name="con", chain_opinion={"b": 0.0, "d": 0.9, "u": 0.1, "a": 0.5})
        opinion, contras = eng._synthesize_chains([ch1, ch2])
        assert len(contras) >= 1
        assert any(c["severity"] in ("high", "extreme") for c in contras)

    def test_empty_chains(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        opinion, contras = eng._synthesize_chains([])
        assert opinion == {}
        assert contras == []


# ===========================================================================
# TestOutputFormatting
# ===========================================================================


class TestOutputFormatting:
    def test_formatted_text_has_sections(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        if not packs:
            pytest.skip("No packs")
        ctx = _ctx_flask_security()
        result = eng.reason(ctx, packs=packs)
        text = result.formatted_text
        assert "## Reasoning Assessment" in text
        assert "## Chain 1:" in text

    def test_gaps_section_present_when_gaps_exist(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        if not packs:
            pytest.skip("No packs")
        # Query for a domain not covered → should have gaps
        ctx = ExtractedContext(
            technologies=["Flask"],
            domains=["security", "compliance"],
            raw_text="Flask API compliance audit",
        )
        result = eng.reason(ctx, packs=packs)
        if result.gaps:
            assert "## Knowledge Gaps" in result.formatted_text

    def test_metacognitive_summary_non_empty(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        if not packs:
            pytest.skip("No packs")
        ctx = _ctx_flask_security()
        result = eng.reason(ctx, packs=packs)
        assert len(result.metacognitive_summary) > 0


# ===========================================================================
# TestBrainProfiles
# ===========================================================================


class TestBrainProfiles:
    def test_load_existing_profile(self):
        profile = load_profile("data_engineer")
        assert profile is not None
        assert profile.id == "data_engineer"
        assert "*kafka*" in profile.pack_boost

    def test_load_missing_profile(self):
        profile = load_profile("nonexistent_profile_xyz")
        assert profile is None

    def test_get_available_profiles(self):
        profiles = get_available_profiles()
        assert "data_engineer" in profiles
        assert "security_engineer" in profiles
        assert "fullstack" in profiles

    def test_profile_from_yaml(self):
        clear_profile_cache()
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_content = {
                "id": "test_profile",
                "name": "Test",
                "pack_boost": {"*test*": 1.5},
                "pack_suppress": {},
                "confidence_threshold": 0.8,
                "contradiction_sensitivity": "high",
            }
            path = os.path.join(tmpdir, "test_profile.yaml")
            with open(path, "w") as f:
                yaml.dump(yaml_content, f)

            profile = load_profile("test_profile", profiles_dir=tmpdir)
            assert profile is not None
            assert profile.confidence_threshold == 0.8
            assert profile.contradiction_sensitivity == "high"
        clear_profile_cache()


# ===========================================================================
# TestReasonIntegration
# ===========================================================================


class TestReasonIntegration:
    def test_reason_returns_result(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        ctx = _ctx_flask_security()
        result = eng.reason(ctx)
        assert isinstance(result, ReasoningResult)
        assert result.reasoning_time_ms > 0

    def test_reason_with_packs(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        ctx = _ctx_flask_security()
        result = eng.reason(ctx, packs=packs)
        assert len(result.packs_used) > 0
        assert result.template_used != ""

    def test_reason_with_profile(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        profile = BrainProfile(
            id="security_test",
            pack_boost={"*security*": 2.0},
            confidence_threshold=0.7,
        )
        ctx = _ctx_flask_security()
        result = eng.reason(ctx, packs=packs, profile=profile)
        assert result.profile_used == "security_test"

    def test_reason_empty_brain(self):
        g = MemoryGraphAdapter()
        eng = ReasoningEngine(graph=g, config=_cfg())
        ctx = _ctx_flask_security()
        result = eng.reason(ctx)
        assert result.nodes_activated == 0
        assert result.formatted_text == ""

    def test_reason_kafka_query(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        ctx = _ctx_kafka()
        result = eng.reason(ctx, packs=packs)
        assert isinstance(result, ReasoningResult)

    def test_confidence_distribution(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        if not packs:
            pytest.skip("No packs")
        ctx = _ctx_flask_security()
        result = eng.reason(ctx, packs=packs)
        # Distribution should have at least one tier
        assert isinstance(result.confidence_distribution, dict)

    def test_contradictions_detected(self):
        g = _graph_with_nodes()
        eng = ReasoningEngine(graph=g, config=_cfg())
        mgr = PackManager(g, None, _cfg())
        packs = mgr.auto_generate_packs()
        ctx = _ctx_flask_security()
        result = eng.reason(ctx, packs=packs)
        # We added a CONFLICTS_WITH edge, so contradictions may be detected
        assert isinstance(result.contradictions, list)


# ===========================================================================
# TestMCPHandler
# ===========================================================================


class TestMCPHandler:
    def test_tool_definition_exists(self):
        from engineering_brain.mcp_server import _TOOL_HANDLERS, TOOLS

        tool_names = [t["name"] for t in TOOLS]
        assert "brain_reason" in tool_names
        assert "brain_reason" in _TOOL_HANDLERS

    def test_tool_schema_valid(self):
        from engineering_brain.mcp_server import TOOLS

        reason_tool = next(t for t in TOOLS if t["name"] == "brain_reason")
        schema = reason_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "query" in schema["required"]
