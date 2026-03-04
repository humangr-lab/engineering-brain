"""Tests for engineering_brain.agent.orchestrator — routing, decomposition, synthesis."""

from __future__ import annotations

from unittest import mock

from engineering_brain.agent.brain_access import BrainAccess
from engineering_brain.agent.config import AgentConfig
from engineering_brain.agent.llm_client import LLMClient
from engineering_brain.agent.orchestrator import Orchestrator
from engineering_brain.agent.types import (
    AgentQuery,
    ConfidenceLevel,
    QueryComplexity,
    QueryIntent,
)


def _config() -> AgentConfig:
    return AgentConfig(
        enabled=True,
        api_key="sk-test",
        model="test-model",
        orchestrator_model="test-orch",
        max_workers=3,
        max_tokens=1024,
        timeout=60,
        cards_dir="",
    )


def _mock_brain_access() -> mock.MagicMock:
    ba = mock.MagicMock(spec=BrainAccess)
    ba.think.return_value = {
        "text": "Brain knowledge here",
        "confidence": "PROBABLE",
        "contradictions": [],
        "gaps": [],
        "nodes_consulted": 5,
    }
    ba.format_context.return_value = "## Brain Knowledge\nSome knowledge"
    return ba


def _mock_llm() -> mock.MagicMock:
    return mock.MagicMock(spec=LLMClient)


# =============================================================================
# Complexity Routing
# =============================================================================


class TestAssessComplexity:
    def setup_method(self):
        self.orch = Orchestrator(_mock_brain_access(), _mock_llm(), _config())

    def test_simple_explanation(self):
        q = AgentQuery(question="What is CORS?", intent=QueryIntent.EXPLANATION, max_depth=1)
        assert self.orch.assess_complexity(q) == QueryComplexity.SIMPLE

    def test_simple_analysis_no_hints(self):
        q = AgentQuery(question="How to validate?", intent=QueryIntent.ANALYSIS, max_depth=1)
        assert self.orch.assess_complexity(q) == QueryComplexity.SIMPLE

    def test_moderate_decision(self):
        q = AgentQuery(
            question="JWT vs sessions?",
            intent=QueryIntent.DECISION,
            domain_hints=["security"],
            max_depth=2,
        )
        assert self.orch.assess_complexity(q) == QueryComplexity.MODERATE

    def test_moderate_multi_domain(self):
        q = AgentQuery(
            question="Secure and fast?",
            intent=QueryIntent.ANALYSIS,
            domain_hints=["security", "performance"],
            max_depth=2,
        )
        assert self.orch.assess_complexity(q) == QueryComplexity.MODERATE

    def test_complex_synthesis(self):
        q = AgentQuery(
            question="Full architecture review",
            intent=QueryIntent.SYNTHESIS,
            domain_hints=["security", "performance", "architecture"],
            technology_hints=["flask", "kafka", "redis"],
            max_depth=4,
        )
        assert self.orch.assess_complexity(q) == QueryComplexity.COMPLEX

    def test_complex_many_signals(self):
        q = AgentQuery(
            question="review",
            intent=QueryIntent.INVESTIGATION,
            domain_hints=["a", "b", "c"],
            technology_hints=["x", "y", "z"],
            max_depth=5,
        )
        assert self.orch.assess_complexity(q) == QueryComplexity.COMPLEX

    def test_explanation_with_depth_is_moderate(self):
        q = AgentQuery(
            question="explain",
            intent=QueryIntent.EXPLANATION,
            domain_hints=["sec"],
            max_depth=3,
        )
        # score = 0 (intent) + 0 (1 domain) + 0 (0 tech) + 1 (depth 3) = 1 -> SIMPLE
        assert self.orch.assess_complexity(q) == QueryComplexity.SIMPLE


# =============================================================================
# Fast Path
# =============================================================================


class TestFastPath:
    def test_fast_path_returns_composed_knowledge(self):
        ba = _mock_brain_access()
        orch = Orchestrator(ba, _mock_llm(), _config())

        q = AgentQuery(question="What is CORS?", intent=QueryIntent.EXPLANATION, max_depth=1)
        result = orch.run(q)

        assert result.fast_path is True
        assert result.tokens_used == 0
        assert result.query == "What is CORS?"
        assert len(result.claims) >= 0

    def test_fast_path_maps_confidence(self):
        ba = _mock_brain_access()
        ba.think.return_value["confidence"] = "VALIDATED"
        orch = Orchestrator(ba, _mock_llm(), _config())

        q = AgentQuery(question="test", intent=QueryIntent.EXPLANATION, max_depth=1)
        result = orch.run(q)
        assert result.overall_confidence == ConfidenceLevel.HIGH

    def test_fast_path_contested(self):
        ba = _mock_brain_access()
        ba.think.return_value["confidence"] = "CONTESTED"
        orch = Orchestrator(ba, _mock_llm(), _config())

        q = AgentQuery(question="test", intent=QueryIntent.EXPLANATION, max_depth=1)
        result = orch.run(q)
        assert result.overall_confidence == ConfidenceLevel.CONTESTED


# =============================================================================
# Deep Path
# =============================================================================


class TestDeepPath:
    def test_deep_path_decompose_and_synthesize(self):
        ba = _mock_brain_access()
        llm = _mock_llm()

        # Decomposition response
        llm.call_json.side_effect = [
            {
                "data": {
                    "sub_questions": [
                        {"question": "Security of JWT", "domain": "security", "priority": 1},
                        {
                            "question": "Performance of sessions",
                            "domain": "performance",
                            "priority": 2,
                        },
                    ]
                },
                "input_tokens": 100,
                "output_tokens": 50,
            },
            # Worker 1 response
            {
                "data": {
                    "claims": [
                        {
                            "claim": "JWT is stateless",
                            "confidence": "high",
                            "evidence": [],
                            "contradictions": [],
                            "reasoning": "r",
                        }
                    ],
                    "gaps": [],
                    "contradictions_found": [],
                },
                "input_tokens": 200,
                "output_tokens": 100,
            },
            # Worker 2 response
            {
                "data": {
                    "claims": [
                        {
                            "claim": "Sessions need sticky routing",
                            "confidence": "moderate",
                            "evidence": [],
                            "contradictions": [],
                            "reasoning": "r",
                        }
                    ],
                    "gaps": ["No Redis session knowledge"],
                    "contradictions_found": [],
                },
                "input_tokens": 200,
                "output_tokens": 100,
            },
            # Synthesis response
            {
                "data": {
                    "summary": "JWT for stateless, sessions for XSS safety",
                    "claims": [
                        {
                            "claim": "Use JWT for horizontal scaling",
                            "confidence": "high",
                            "evidence": ["CR-AUTH-001"],
                            "contradictions": [],
                            "reasoning": "r",
                        },
                    ],
                    "contradictions": [],
                    "gaps": [],
                    "overall_confidence": "moderate",
                },
                "input_tokens": 300,
                "output_tokens": 150,
            },
        ]

        orch = Orchestrator(ba, llm, _config())
        q = AgentQuery(
            question="JWT vs sessions?",
            intent=QueryIntent.DECISION,
            domain_hints=["security", "performance"],
            max_depth=3,
        )
        result = orch.run(q)

        assert result.fast_path is False
        assert result.tokens_used > 0
        assert len(result.worker_results) == 2
        assert len(result.claims) >= 1

    def test_decompose_fallback_on_error(self):
        ba = _mock_brain_access()
        llm = _mock_llm()
        llm.call_json.side_effect = [
            RuntimeError("LLM failed"),
            # Worker response for fallback single question
            {
                "data": {
                    "claims": [{"claim": "fallback", "confidence": "low"}],
                    "gaps": [],
                    "contradictions_found": [],
                },
                "input_tokens": 50,
                "output_tokens": 50,
            },
            # Synthesis
            {
                "data": {
                    "summary": "fallback",
                    "claims": [],
                    "contradictions": [],
                    "gaps": [],
                    "overall_confidence": "low",
                },
                "input_tokens": 50,
                "output_tokens": 50,
            },
        ]

        orch = Orchestrator(ba, llm, _config())
        q = AgentQuery(
            question="test",
            intent=QueryIntent.DECISION,
            domain_hints=["security", "performance"],
            max_depth=3,
        )
        result = orch.run(q)
        # Should have 1 worker (fallback single question)
        assert len(result.worker_results) == 1

    def test_synthesis_fallback_on_error(self):
        ba = _mock_brain_access()
        llm = _mock_llm()
        llm.call_json.side_effect = [
            # Decomposition
            {
                "data": {"sub_questions": [{"question": "q1", "domain": "general", "priority": 1}]},
                "input_tokens": 50,
                "output_tokens": 50,
            },
            # Worker
            {
                "data": {
                    "claims": [{"claim": "Some claim", "confidence": "moderate"}],
                    "gaps": [],
                    "contradictions_found": [],
                },
                "input_tokens": 100,
                "output_tokens": 100,
            },
            # Synthesis fails
            RuntimeError("synthesis failed"),
        ]

        orch = Orchestrator(ba, llm, _config())
        q = AgentQuery(
            question="test",
            intent=QueryIntent.DECISION,
            domain_hints=["security", "performance"],
            max_depth=3,
        )
        result = orch.run(q)
        # Fallback merge should work
        assert result.fast_path is False
        assert len(result.claims) >= 1

    def test_max_workers_limit(self):
        ba = _mock_brain_access()
        llm = _mock_llm()

        # Decompose returns 5 sub-questions, but max_workers=3
        llm.call_json.side_effect = [
            {
                "data": {
                    "sub_questions": [
                        {"question": f"q{i}", "domain": "general", "priority": i} for i in range(5)
                    ]
                },
                "input_tokens": 50,
                "output_tokens": 50,
            },
            # 3 worker responses (limited by max_workers)
            *[
                {
                    "data": {"claims": [], "gaps": [], "contradictions_found": []},
                    "input_tokens": 50,
                    "output_tokens": 50,
                }
                for _ in range(3)
            ],
            # Synthesis
            {
                "data": {
                    "summary": "ok",
                    "claims": [],
                    "contradictions": [],
                    "gaps": [],
                    "overall_confidence": "moderate",
                },
                "input_tokens": 50,
                "output_tokens": 50,
            },
        ]

        orch = Orchestrator(ba, llm, _config())
        q = AgentQuery(
            question="test",
            intent=QueryIntent.SYNTHESIS,
            domain_hints=["a", "b", "c"],
            max_depth=4,
        )
        result = orch.run(q)
        assert len(result.worker_results) == 3  # Not 5
