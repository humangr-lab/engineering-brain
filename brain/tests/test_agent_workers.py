"""Tests for engineering_brain.agent.worker + workers/* — domain workers."""

from __future__ import annotations

from unittest import mock

from engineering_brain.agent.brain_access import BrainAccess
from engineering_brain.agent.config import AgentConfig
from engineering_brain.agent.llm_client import LLMClient
from engineering_brain.agent.types import ConfidenceLevel
from engineering_brain.agent.workers import (
    WORKER_REGISTRY,
    get_worker_class,
    resolve_domain,
)
from engineering_brain.agent.workers.architecture import ArchitectureWorker
from engineering_brain.agent.workers.general import GeneralWorker
from engineering_brain.agent.workers.security import SecurityWorker


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
    ba.format_context.return_value = "## Brain Knowledge\nSome knowledge"
    return ba


def _mock_llm_success() -> mock.MagicMock:
    llm = mock.MagicMock(spec=LLMClient)
    llm.call_json.return_value = {
        "data": {
            "claims": [
                {
                    "claim": "Always validate input",
                    "confidence": "high",
                    "evidence": [{"node_id": "CR-SEC-001", "relevance": "direct match"}],
                    "contradictions": [],
                    "reasoning": "Brain evidence is clear",
                },
                {
                    "claim": "Use parameterized queries",
                    "confidence": "moderate",
                    "evidence": ["CR-SQL-002"],
                    "contradictions": ["Some say ORMs are enough"],
                    "reasoning": "Defense in depth",
                },
            ],
            "gaps": ["No GraphQL injection rules"],
            "contradictions_found": ["ORM vs raw SQL debate"],
        },
        "input_tokens": 200,
        "output_tokens": 150,
    }
    return llm


# =============================================================================
# Registry tests
# =============================================================================


class TestWorkerRegistry:
    def test_all_domains_registered(self):
        assert "architecture" in WORKER_REGISTRY
        assert "security" in WORKER_REGISTRY
        assert "performance" in WORKER_REGISTRY
        assert "debugging" in WORKER_REGISTRY
        assert "general" in WORKER_REGISTRY

    def test_resolve_domain_direct(self):
        assert resolve_domain("security") == "security"
        assert resolve_domain("Architecture") == "architecture"

    def test_resolve_domain_aliases(self):
        assert resolve_domain("sec") == "security"
        assert resolve_domain("arch") == "architecture"
        assert resolve_domain("perf") == "performance"
        assert resolve_domain("debug") == "debugging"
        assert resolve_domain("design") == "architecture"
        assert resolve_domain("incident") == "debugging"
        assert resolve_domain("optimization") == "performance"

    def test_resolve_domain_unknown(self):
        assert resolve_domain("unknown") == "unknown"

    def test_get_worker_class_known(self):
        assert get_worker_class("security") is SecurityWorker
        assert get_worker_class("architecture") is ArchitectureWorker

    def test_get_worker_class_alias(self):
        assert get_worker_class("sec") is SecurityWorker

    def test_get_worker_class_fallback(self):
        assert get_worker_class("unknown_domain") is GeneralWorker


# =============================================================================
# Worker execution tests
# =============================================================================


class TestWorkerExecution:
    def test_security_worker_execute(self):
        worker = SecurityWorker(_mock_brain_access(), _mock_llm_success(), _config())
        result = worker.execute("How to prevent SQL injection?")

        assert result.worker_id == "security_worker"
        assert result.domain == "security"
        assert len(result.claims) == 2
        assert result.claims[0].confidence == ConfidenceLevel.HIGH
        assert result.claims[0].evidence[0].node_id == "CR-SEC-001"
        assert result.claims[1].evidence[0].node_id == "CR-SQL-002"
        assert result.gaps == ["No GraphQL injection rules"]
        assert result.tokens_used == 350

    def test_architecture_worker_domains(self):
        worker = ArchitectureWorker(_mock_brain_access(), _mock_llm_success(), _config())
        assert "architecture" in worker._get_domains()

    def test_general_worker_no_domain_filter(self):
        worker = GeneralWorker(_mock_brain_access(), _mock_llm_success(), _config())
        assert worker._get_domains() == []

    def test_worker_llm_failure(self):
        llm = mock.MagicMock(spec=LLMClient)
        llm.call_json.side_effect = RuntimeError("API error")

        worker = SecurityWorker(_mock_brain_access(), llm, _config())
        result = worker.execute("test")

        assert result.worker_id == "security_worker"
        assert len(result.claims) == 0
        assert len(result.gaps) == 1
        assert "failed" in result.gaps[0].lower()

    def test_worker_passes_technologies(self):
        ba = _mock_brain_access()
        worker = SecurityWorker(ba, _mock_llm_success(), _config())
        worker.execute("test", technologies=["flask", "redis"])

        ba.format_context.assert_called_once()
        call_kwargs = ba.format_context.call_args
        assert call_kwargs[1]["technologies"] == ["flask", "redis"]


class TestWorkerParsing:
    def test_parse_string_evidence(self):
        """Workers should handle both dict and string evidence."""
        llm = mock.MagicMock(spec=LLMClient)
        llm.call_json.return_value = {
            "data": {
                "claims": [{"claim": "test", "evidence": ["NODE-001", "NODE-002"]}],
                "gaps": [],
                "contradictions_found": [],
            },
            "input_tokens": 10,
            "output_tokens": 10,
        }
        worker = GeneralWorker(_mock_brain_access(), llm, _config())
        result = worker.execute("test")
        assert result.claims[0].evidence[0].node_id == "NODE-001"

    def test_parse_invalid_confidence(self):
        """Invalid confidence should default to MODERATE."""
        llm = mock.MagicMock(spec=LLMClient)
        llm.call_json.return_value = {
            "data": {
                "claims": [{"claim": "test", "confidence": "INVALID"}],
                "gaps": [],
                "contradictions_found": [],
            },
            "input_tokens": 10,
            "output_tokens": 10,
        }
        worker = GeneralWorker(_mock_brain_access(), llm, _config())
        result = worker.execute("test")
        assert result.claims[0].confidence == ConfidenceLevel.MODERATE

    def test_parse_empty_claims(self):
        llm = mock.MagicMock(spec=LLMClient)
        llm.call_json.return_value = {
            "data": {"claims": [], "gaps": ["big gap"], "contradictions_found": []},
            "input_tokens": 10,
            "output_tokens": 10,
        }
        worker = GeneralWorker(_mock_brain_access(), llm, _config())
        result = worker.execute("test")
        assert len(result.claims) == 0
        assert result.gaps == ["big gap"]
