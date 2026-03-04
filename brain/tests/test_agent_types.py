"""Tests for engineering_brain.agent.types — Pydantic models."""

from __future__ import annotations

import pytest

from engineering_brain.agent.types import (
    AgentQuery,
    ComposedKnowledge,
    ConfidenceLevel,
    EvidenceItem,
    KnowledgeClaim,
    QueryComplexity,
    QueryIntent,
    WorkerResult,
)

# =============================================================================
# Enum tests
# =============================================================================


class TestQueryIntent:
    def test_all_values(self):
        assert set(QueryIntent) == {
            QueryIntent.DECISION,
            QueryIntent.ANALYSIS,
            QueryIntent.INVESTIGATION,
            QueryIntent.EXPLANATION,
            QueryIntent.SYNTHESIS,
        }

    def test_string_values(self):
        assert QueryIntent.DECISION.value == "decision"
        assert QueryIntent.SYNTHESIS.value == "synthesis"


class TestQueryComplexity:
    def test_all_values(self):
        assert set(QueryComplexity) == {
            QueryComplexity.SIMPLE,
            QueryComplexity.MODERATE,
            QueryComplexity.COMPLEX,
        }


class TestConfidenceLevel:
    def test_all_values(self):
        assert set(ConfidenceLevel) == {
            ConfidenceLevel.HIGH,
            ConfidenceLevel.MODERATE,
            ConfidenceLevel.LOW,
            ConfidenceLevel.CONTESTED,
        }


# =============================================================================
# AgentQuery tests
# =============================================================================


class TestAgentQuery:
    def test_minimal(self):
        q = AgentQuery(question="How to secure Flask?")
        assert q.question == "How to secure Flask?"
        assert q.intent == QueryIntent.ANALYSIS
        assert q.domain_hints == []
        assert q.technology_hints == []
        assert q.max_depth == 2

    def test_full(self):
        q = AgentQuery(
            question="JWT vs sessions?",
            intent=QueryIntent.DECISION,
            domain_hints=["security", "architecture"],
            technology_hints=["flask", "redis"],
            context="We need horizontal scaling",
            constraints=["Must work with WebSocket"],
            max_depth=4,
        )
        assert q.intent == QueryIntent.DECISION
        assert len(q.domain_hints) == 2
        assert q.max_depth == 4

    def test_min_length_validation(self):
        with pytest.raises(Exception):
            AgentQuery(question="")

    def test_max_depth_bounds(self):
        with pytest.raises(Exception):
            AgentQuery(question="test", max_depth=0)
        with pytest.raises(Exception):
            AgentQuery(question="test", max_depth=6)

    def test_max_depth_edge_cases(self):
        q1 = AgentQuery(question="test", max_depth=1)
        assert q1.max_depth == 1
        q5 = AgentQuery(question="test", max_depth=5)
        assert q5.max_depth == 5


# =============================================================================
# EvidenceItem tests
# =============================================================================


class TestEvidenceItem:
    def test_minimal(self):
        e = EvidenceItem(node_id="CR-CQ-001")
        assert e.node_id == "CR-CQ-001"
        assert e.confidence == 0.5
        assert e.epistemic_status == "E1"

    def test_full(self):
        e = EvidenceItem(
            node_id="CR-SEC-005",
            node_type="rule",
            layer="L3",
            content="Always validate input",
            confidence=0.9,
            epistemic_status="E3",
            relevance_score=0.85,
        )
        assert e.layer == "L3"
        assert e.relevance_score == 0.85

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            EvidenceItem(node_id="x", confidence=1.5)
        with pytest.raises(Exception):
            EvidenceItem(node_id="x", confidence=-0.1)


# =============================================================================
# KnowledgeClaim tests
# =============================================================================


class TestKnowledgeClaim:
    def test_minimal(self):
        c = KnowledgeClaim(claim="Use prepared statements")
        assert c.confidence == ConfidenceLevel.MODERATE
        assert c.evidence == []

    def test_with_evidence(self):
        c = KnowledgeClaim(
            claim="JWT is stateless",
            confidence=ConfidenceLevel.HIGH,
            evidence=[EvidenceItem(node_id="CR-AUTH-001")],
            reasoning="JWT tokens contain all claims",
        )
        assert len(c.evidence) == 1
        assert c.reasoning != ""


# =============================================================================
# WorkerResult tests
# =============================================================================


class TestWorkerResult:
    def test_minimal(self):
        r = WorkerResult(worker_id="security_worker", domain="security")
        assert r.claims == []
        assert r.tokens_used == 0

    def test_with_claims(self):
        r = WorkerResult(
            worker_id="arch_worker",
            domain="architecture",
            claims=[KnowledgeClaim(claim="Use hexagonal architecture")],
            gaps=["No knowledge about event sourcing"],
            nodes_consulted=15,
            tokens_used=1200,
        )
        assert len(r.claims) == 1
        assert r.nodes_consulted == 15


# =============================================================================
# ComposedKnowledge tests
# =============================================================================


class TestComposedKnowledge:
    def test_minimal(self):
        ck = ComposedKnowledge(query="test?")
        assert ck.fast_path is False
        assert ck.tokens_used == 0

    def test_fast_path(self):
        ck = ComposedKnowledge(
            query="How to validate input?",
            summary="Always validate at boundaries",
            fast_path=True,
        )
        assert ck.fast_path is True

    def test_format_markdown_empty(self):
        ck = ComposedKnowledge(query="test?")
        md = ck.format_markdown()
        assert "## Composed Knowledge" in md
        assert "test?" in md

    def test_format_markdown_full(self):
        ck = ComposedKnowledge(
            query="How to secure Flask?",
            summary="Use CORS, validate input, etc.",
            claims=[
                KnowledgeClaim(
                    claim="Enable CORS properly",
                    confidence=ConfidenceLevel.HIGH,
                    evidence=[EvidenceItem(node_id="CR-SEC-001", layer="L3")],
                ),
            ],
            worker_results=[
                WorkerResult(
                    worker_id="security_worker",
                    domain="security",
                    claims=[KnowledgeClaim(claim="c1")],
                    nodes_consulted=10,
                    tokens_used=500,
                ),
            ],
            contradictions=["Rule A vs Rule B"],
            gaps=["No WebSocket security rules"],
            overall_confidence=ConfidenceLevel.HIGH,
            tokens_used=1500,
        )
        md = ck.format_markdown()
        assert "Summary" in md
        assert "Claims" in md
        assert "Contradictions" in md
        assert "Knowledge Gaps" in md
        assert "Workers" in md
        assert "CR-SEC-001" in md
        assert "security_worker" in md

    def test_format_markdown_with_contradictions_in_claims(self):
        ck = ComposedKnowledge(
            query="test",
            claims=[
                KnowledgeClaim(
                    claim="Use JWT",
                    contradictions=["Sessions are more secure for XSS"],
                ),
            ],
        )
        md = ck.format_markdown()
        assert "Contradiction" in md
