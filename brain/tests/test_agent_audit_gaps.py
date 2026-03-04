"""Tests covering gaps found in the second audit pass.

Addresses: GAP-01 through GAP-13, F-01 through F-04, F-11, ASSERT-01.
"""

from __future__ import annotations

import os
import tempfile
from unittest import mock

import pytest

from engineering_brain.agent.config import AgentConfig
from engineering_brain.agent.runtime_cards import (
    _parse_card,
    clear_card_cache,
    load_card,
)
from engineering_brain.agent.types import (
    AgentQuery,
    ConfidenceLevel,
    QueryIntent,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_card_cache()
    yield
    clear_card_cache()


def _config(**overrides) -> AgentConfig:
    defaults = dict(
        enabled=True,
        api_key="sk-test",
        model="test-model",
        orchestrator_model="test-orch",
        max_workers=3,
        max_tokens=1024,
        timeout=60,
        cards_dir="",
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


def _mock_brain_access():
    from engineering_brain.agent.brain_access import BrainAccess

    ba = mock.MagicMock(spec=BrainAccess)
    ba.think.return_value = {
        "text": "Brain knowledge",
        "confidence": "PROBABLE",
        "contradictions": [],
        "gaps": [],
        "nodes_consulted": 5,
    }
    ba.format_context.return_value = "## Brain Knowledge\nSome knowledge"
    return ba


def _mock_llm():
    from engineering_brain.agent.llm_client import LLMClient

    return mock.MagicMock(spec=LLMClient)


# =============================================================================
# GAP-01: run_agent and agent_status zero-coverage
# =============================================================================


class TestPublicAPI:
    def test_run_agent_not_configured_raises(self):
        from engineering_brain.agent import run_agent

        brain = mock.MagicMock()
        brain._config = mock.MagicMock()
        brain._config.agent_enabled = False
        brain._config.agent_api_key = ""
        brain._config.agent_model = "m"
        brain._config.agent_orchestrator_model = "m"
        brain._config.agent_max_workers = 3
        brain._config.agent_max_tokens = 4096
        brain._config.agent_timeout = 60
        brain._config.agent_cards_dir = ""

        q = AgentQuery(question="test")
        with pytest.raises(RuntimeError, match="not configured"):
            run_agent(brain, q)

    def test_agent_status_returns_dict(self):
        from engineering_brain.agent import agent_status

        brain = mock.MagicMock()
        brain._config = mock.MagicMock()
        brain._config.agent_enabled = True
        brain._config.agent_api_key = "sk-test"
        brain._config.agent_model = "claude-opus-4-20250514"
        brain._config.agent_orchestrator_model = "claude-opus-4-20250514"
        brain._config.agent_max_workers = 3
        brain._config.agent_max_tokens = 4096
        brain._config.agent_timeout = 60
        brain._config.agent_cards_dir = ""

        status = agent_status(brain)
        assert status["enabled"] is True
        assert status["configured"] is True
        assert "model" in status
        assert "max_workers" in status

    def test_agent_status_disabled(self):
        from engineering_brain.agent import agent_status

        brain = mock.MagicMock()
        brain._config = mock.MagicMock()
        brain._config.agent_enabled = False
        brain._config.agent_api_key = ""
        brain._config.agent_model = "m"
        brain._config.agent_orchestrator_model = "m"
        brain._config.agent_max_workers = 3
        brain._config.agent_max_tokens = 4096
        brain._config.agent_timeout = 60
        brain._config.agent_cards_dir = ""

        status = agent_status(brain)
        assert status["enabled"] is False
        assert status["configured"] is False


# =============================================================================
# GAP-02: AgentConfig __post_init__ clamping
# =============================================================================


class TestConfigClamping:
    def test_max_workers_clamped_to_1(self):
        cfg = _config(max_workers=0)
        assert cfg.max_workers == 1

    def test_max_workers_negative_clamped(self):
        cfg = _config(max_workers=-5)
        assert cfg.max_workers == 1

    def test_max_tokens_clamped_to_1(self):
        cfg = _config(max_tokens=0)
        assert cfg.max_tokens == 1

    def test_timeout_clamped_to_1(self):
        cfg = _config(timeout=-10)
        assert cfg.timeout == 1

    def test_api_key_not_in_repr(self):
        cfg = _config(api_key="sk-super-secret")
        assert "sk-super-secret" not in repr(cfg)


# =============================================================================
# GAP-06: Path traversal validation
# =============================================================================


class TestPathTraversal:
    def test_path_traversal_rejected(self):
        with pytest.raises(ValueError, match="Invalid agent_id"):
            load_card("../../etc/passwd")

    def test_uppercase_rejected(self):
        with pytest.raises(ValueError, match="Invalid agent_id"):
            load_card("MyAgent")

    def test_hyphen_rejected(self):
        with pytest.raises(ValueError, match="Invalid agent_id"):
            load_card("my-agent")

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="Invalid agent_id"):
            load_card("")

    def test_starts_with_number(self):
        with pytest.raises(ValueError, match="Invalid agent_id"):
            load_card("1agent")


# =============================================================================
# GAP-04/05: Runtime card parse edge cases
# =============================================================================


class TestCardParseEdgeCases:
    def test_yaml_not_mapping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            card_path = os.path.join(tmpdir, "bad_card.yml")
            with open(card_path, "w") as f:
                f.write("- item1\n- item2\n")
            with pytest.raises(ValueError, match="YAML mapping"):
                load_card("bad_card", cards_dir=tmpdir)

    def test_parse_card_missing_agent_id(self):
        with pytest.raises(ValueError, match="agent_id"):
            _parse_card({"role": "test"})

    def test_key_skills_non_list_rejected(self):
        with pytest.raises(ValueError, match="Expected a list"):
            _parse_card({"agent_id": "test", "key_skills": "not a list"})

    def test_malformed_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            card_path = os.path.join(tmpdir, "malformed.yml")
            with open(card_path, "w") as f:
                f.write("{{invalid yaml: [unclosed")
            with pytest.raises(ValueError, match="Invalid YAML"):
                load_card("malformed", cards_dir=tmpdir)

    def test_custom_dir_fallback_to_builtin(self):
        """If custom dir doesn't have the card, fall back to built-in."""
        with tempfile.TemporaryDirectory() as tmpdir:
            card = load_card("orchestrator", cards_dir=tmpdir)
            assert card.agent_id == "orchestrator"


# =============================================================================
# F-04/F-02: Non-dict LLM responses in worker
# =============================================================================


class TestWorkerNonDictResponse:
    def test_worker_handles_json_array(self):
        """LLM returning a JSON array instead of object should not crash."""
        from engineering_brain.agent.workers.general import GeneralWorker

        llm = _mock_llm()
        llm.call_json.return_value = {
            "data": [{"unexpected": "array"}],  # list, not dict
            "input_tokens": 10,
            "output_tokens": 10,
        }
        worker = GeneralWorker(_mock_brain_access(), llm, _config())
        result = worker.execute("test")
        assert result.worker_id == "general_worker"
        assert len(result.gaps) >= 1
        assert "non-object" in result.gaps[0].lower() or "non-dict" in result.gaps[0].lower()

    def test_worker_handles_non_dict_claims(self):
        """Non-dict claim items should be skipped."""
        from engineering_brain.agent.workers.general import GeneralWorker

        llm = _mock_llm()
        llm.call_json.return_value = {
            "data": {
                "claims": ["not a dict", {"claim": "valid", "confidence": "high"}],
                "gaps": [],
                "contradictions_found": [],
            },
            "input_tokens": 10,
            "output_tokens": 10,
        }
        worker = GeneralWorker(_mock_brain_access(), llm, _config())
        result = worker.execute("test")
        assert len(result.claims) == 1
        assert result.claims[0].claim == "valid"


# =============================================================================
# F-11: Confidence case sensitivity
# =============================================================================


class TestConfidenceCaseSensitivity:
    def test_worker_uppercase_confidence(self):
        """Worker should handle uppercase confidence from LLM."""
        from engineering_brain.agent.workers.general import GeneralWorker

        llm = _mock_llm()
        llm.call_json.return_value = {
            "data": {
                "claims": [{"claim": "test", "confidence": "HIGH"}],
                "gaps": [],
                "contradictions_found": [],
            },
            "input_tokens": 10,
            "output_tokens": 10,
        }
        worker = GeneralWorker(_mock_brain_access(), llm, _config())
        result = worker.execute("test")
        assert result.claims[0].confidence == ConfidenceLevel.HIGH

    def test_worker_title_case_confidence(self):
        """Worker should handle title-case confidence."""
        from engineering_brain.agent.workers.general import GeneralWorker

        llm = _mock_llm()
        llm.call_json.return_value = {
            "data": {
                "claims": [{"claim": "test", "confidence": "Low"}],
                "gaps": [],
                "contradictions_found": [],
            },
            "input_tokens": 10,
            "output_tokens": 10,
        }
        worker = GeneralWorker(_mock_brain_access(), llm, _config())
        result = worker.execute("test")
        assert result.claims[0].confidence == ConfidenceLevel.LOW


# =============================================================================
# F-03: Synthesis parse error triggers fallback
# =============================================================================


class TestSynthesisParseErrors:
    def test_synthesis_non_dict_response_triggers_fallback(self):
        """If synthesis LLM returns a JSON array, fallback merge should activate."""
        from engineering_brain.agent.orchestrator import Orchestrator

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
                    "claims": [{"claim": "A claim", "confidence": "high"}],
                    "gaps": [],
                    "contradictions_found": [],
                },
                "input_tokens": 100,
                "output_tokens": 100,
            },
            # Synthesis returns a list (not dict)
            {
                "data": ["unexpected", "array"],
                "input_tokens": 100,
                "output_tokens": 100,
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
        # Should fallback-merge, not crash
        assert result.fast_path is False
        assert len(result.claims) >= 1

    def test_synthesis_dicts_in_string_fields_coerced(self):
        """Synthesis with dicts in contradictions/gaps should coerce to strings."""
        from engineering_brain.agent.orchestrator import Orchestrator

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
                "data": {"claims": [], "gaps": [], "contradictions_found": []},
                "input_tokens": 50,
                "output_tokens": 50,
            },
            # Synthesis with dicts where strings expected
            {
                "data": {
                    "summary": "ok",
                    "claims": [],
                    "contradictions": [{"a": "b"}, "normal string"],
                    "gaps": [{"domain": "sec"}, "normal gap"],
                    "overall_confidence": "moderate",
                },
                "input_tokens": 100,
                "output_tokens": 100,
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
        # Dicts should be coerced to strings, not crash
        assert all(isinstance(c, str) for c in result.contradictions)
        assert all(isinstance(g, str) for g in result.gaps)


# =============================================================================
# F-01: {max_workers} placeholder substituted in decompose
# =============================================================================


class TestDecomposePromptPlaceholder:
    def test_max_workers_substituted(self):
        """The {max_workers} placeholder should be replaced in decompose prompt."""
        from engineering_brain.agent.orchestrator import Orchestrator

        ba = _mock_brain_access()
        llm = _mock_llm()
        llm.call_json.return_value = {
            "data": {"sub_questions": [{"question": "q1", "domain": "general", "priority": 1}]},
            "input_tokens": 50,
            "output_tokens": 50,
        }

        orch = Orchestrator(ba, llm, _config(max_workers=5))
        q = AgentQuery(
            question="test",
            intent=QueryIntent.DECISION,
            domain_hints=["security", "performance"],
            max_depth=3,
        )
        orch._decompose(q)

        # Check the system_prompt sent to the LLM
        call_args = llm.call_json.call_args
        system_prompt = (
            call_args[1]["system_prompt"] if "system_prompt" in call_args[1] else call_args[0][0]
        )
        assert "{max_workers}" not in system_prompt
        assert "5" in system_prompt or "1 to 5" in system_prompt


# =============================================================================
# GAP-07/08/09: Decompose edge cases
# =============================================================================


class TestDecomposeEdgeCases:
    def test_empty_subquestions_falls_to_fast_path(self):
        """Empty sub_questions list should fall back to fast path."""
        from engineering_brain.agent.orchestrator import Orchestrator

        ba = _mock_brain_access()
        llm = _mock_llm()
        llm.call_json.return_value = {
            "data": {"sub_questions": []},
            "input_tokens": 50,
            "output_tokens": 50,
        }

        orch = Orchestrator(ba, llm, _config())
        q = AgentQuery(
            question="test",
            intent=QueryIntent.DECISION,
            domain_hints=["security", "performance"],
            max_depth=3,
        )
        result = orch.run(q)
        assert result.fast_path is True
        # Decompose tokens should still be tracked
        assert result.tokens_used >= 100  # decompose consumed 50+50=100 tokens

    def test_non_list_subquestions_falls_to_fast_path(self):
        """Non-list sub_questions should fall back to fast path."""
        from engineering_brain.agent.orchestrator import Orchestrator

        ba = _mock_brain_access()
        llm = _mock_llm()
        llm.call_json.return_value = {
            "data": {"sub_questions": "not a list"},
            "input_tokens": 50,
            "output_tokens": 50,
        }

        orch = Orchestrator(ba, llm, _config())
        q = AgentQuery(
            question="test",
            intent=QueryIntent.DECISION,
            domain_hints=["security", "performance"],
            max_depth=3,
        )
        result = orch.run(q)
        assert result.fast_path is True

    def test_decompose_filters_invalid_subquestions(self):
        """Sub-questions without 'question' field should be filtered."""
        from engineering_brain.agent.orchestrator import Orchestrator

        ba = _mock_brain_access()
        llm = _mock_llm()
        llm.call_json.return_value = {
            "data": {
                "sub_questions": [
                    {"domain": "security"},  # no "question"
                    {"question": "", "domain": "general"},  # empty question (falsy)
                    {"question": "valid q", "domain": "general", "priority": 1},
                ]
            },
            "input_tokens": 50,
            "output_tokens": 50,
        }

        orch = Orchestrator(ba, llm, _config())
        q = AgentQuery(
            question="test",
            intent=QueryIntent.DECISION,
            domain_hints=["security", "performance"],
            max_depth=3,
        )
        sub_qs, tokens = orch._decompose(q)
        assert len(sub_qs) == 1
        assert sub_qs[0]["question"] == "valid q"

    def test_decompose_non_dict_data_returns_empty(self):
        """If LLM returns a JSON array at top level, decompose returns empty."""
        from engineering_brain.agent.orchestrator import Orchestrator

        ba = _mock_brain_access()
        llm = _mock_llm()
        llm.call_json.return_value = {
            "data": ["unexpected", "array"],
            "input_tokens": 50,
            "output_tokens": 50,
        }

        orch = Orchestrator(ba, llm, _config())
        q = AgentQuery(
            question="test",
            intent=QueryIntent.DECISION,
            domain_hints=["security", "performance"],
            max_depth=3,
        )
        sub_qs, tokens = orch._decompose(q)
        assert sub_qs == []
        assert tokens == 100


# =============================================================================
# GAP-10: Worker exception isolation in deep path
# =============================================================================


class TestWorkerExceptionIsolation:
    def test_worker_construction_failure_isolated(self):
        """If a worker class raises on construction, other workers continue."""
        from engineering_brain.agent import workers as workers_mod
        from engineering_brain.agent.orchestrator import Orchestrator

        ba = _mock_brain_access()
        llm = _mock_llm()
        llm.call_json.side_effect = [
            # Decompose: 2 workers
            {
                "data": {
                    "sub_questions": [
                        {"question": "q1", "domain": "bad_domain", "priority": 1},
                        {"question": "q2", "domain": "general", "priority": 2},
                    ]
                },
                "input_tokens": 50,
                "output_tokens": 50,
            },
            # Worker 2 response (worker 1 will fail during get_worker_class)
            {
                "data": {
                    "claims": [{"claim": "ok", "confidence": "high"}],
                    "gaps": [],
                    "contradictions_found": [],
                },
                "input_tokens": 100,
                "output_tokens": 100,
            },
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

        # Make get_worker_class raise for "bad_domain"
        original_get = workers_mod.get_worker_class

        def patched_get(domain):
            if domain == "bad_domain":
                raise RuntimeError("Worker construction failed")
            return original_get(domain)

        orch = Orchestrator(ba, llm, _config())
        q = AgentQuery(
            question="test",
            intent=QueryIntent.DECISION,
            domain_hints=["security", "performance"],
            max_depth=3,
        )

        with mock.patch.object(workers_mod, "get_worker_class", side_effect=patched_get):
            # Need to also patch the orchestrator's imported reference
            with mock.patch(
                "engineering_brain.agent.orchestrator.get_worker_class", side_effect=patched_get
            ):
                result = orch.run(q)

        assert len(result.worker_results) == 2
        # First worker should have gaps from failure
        assert any("failed" in g.lower() for g in result.worker_results[0].gaps)
        # Second worker should succeed
        assert result.worker_results[1].domain == "general"


# =============================================================================
# ASSERT-01: Fix the >= 0 assertion that tests nothing
# =============================================================================


class TestFastPathClaimsCount:
    def test_fast_path_creates_claim_from_text(self):
        """Fast path with brain text should produce exactly 1 claim."""
        from engineering_brain.agent.orchestrator import Orchestrator

        ba = _mock_brain_access()
        orch = Orchestrator(ba, _mock_llm(), _config())

        q = AgentQuery(question="test", intent=QueryIntent.EXPLANATION, max_depth=1)
        result = orch.run(q)
        assert len(result.claims) == 1  # Not >= 0

    def test_fast_path_no_text_no_claims(self):
        """Fast path with empty brain text should produce 0 claims."""
        from engineering_brain.agent.orchestrator import Orchestrator

        ba = _mock_brain_access()
        ba.think.return_value["text"] = ""
        orch = Orchestrator(ba, _mock_llm(), _config())

        q = AgentQuery(question="test", intent=QueryIntent.EXPLANATION, max_depth=1)
        result = orch.run(q)
        assert len(result.claims) == 0
        assert result.summary == "No relevant knowledge found."


# =============================================================================
# GAP-23: Fast path confidence for UNCERTAIN
# =============================================================================


class TestFastPathConfidence:
    def test_uncertain_maps_to_low(self):
        from engineering_brain.agent.orchestrator import Orchestrator

        ba = _mock_brain_access()
        ba.think.return_value["confidence"] = "UNCERTAIN"
        orch = Orchestrator(ba, _mock_llm(), _config())

        q = AgentQuery(question="test", intent=QueryIntent.EXPLANATION, max_depth=1)
        result = orch.run(q)
        assert result.overall_confidence == ConfidenceLevel.LOW

    def test_unknown_confidence_defaults_moderate(self):
        from engineering_brain.agent.orchestrator import Orchestrator

        ba = _mock_brain_access()
        ba.think.return_value["confidence"] = "BANANA"
        orch = Orchestrator(ba, _mock_llm(), _config())

        q = AgentQuery(question="test", intent=QueryIntent.EXPLANATION, max_depth=1)
        result = orch.run(q)
        assert result.overall_confidence == ConfidenceLevel.MODERATE
