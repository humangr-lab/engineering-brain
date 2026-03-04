"""Tests for engineering_brain.agent.llm_client — Anthropic SDK wrapper.

All tests use mocked Anthropic SDK — zero real API calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from engineering_brain.agent.config import AgentConfig
from engineering_brain.agent.llm_client import LLMClient


def _make_config(api_key: str = "sk-test") -> AgentConfig:
    return AgentConfig(
        enabled=True,
        api_key=api_key,
        model="test-model",
        orchestrator_model="test-orch",
        max_workers=3,
        max_tokens=1024,
        timeout=60,
        cards_dir="",
    )


def _mock_response(text: str, input_tokens: int = 10, output_tokens: int = 20):
    """Build a mock Anthropic response."""
    block = SimpleNamespace(text=text)
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(content=[block], usage=usage)


class TestLLMClient:
    def test_lazy_init_no_key(self):
        client = LLMClient(_make_config(api_key=""))
        with pytest.raises(ValueError, match="BRAIN_AGENT_API_KEY"):
            client._get_client()

    @mock.patch("engineering_brain.agent.llm_client.LLMClient._get_client")
    def test_call_success(self, mock_get_client):
        mock_anthropic = mock.MagicMock()
        mock_anthropic.messages.create.return_value = _mock_response("Hello world")
        mock_get_client.return_value = mock_anthropic

        client = LLMClient(_make_config())
        result = client.call("system", "user")

        assert result["text"] == "Hello world"
        assert result["input_tokens"] == 10
        assert result["output_tokens"] == 20

    @mock.patch("engineering_brain.agent.llm_client.LLMClient._get_client")
    def test_call_json_success(self, mock_get_client):
        mock_anthropic = mock.MagicMock()
        mock_anthropic.messages.create.return_value = _mock_response('{"key": "value"}')
        mock_get_client.return_value = mock_anthropic

        client = LLMClient(_make_config())
        result = client.call_json("system", "user")

        assert result["data"] == {"key": "value"}

    @mock.patch("engineering_brain.agent.llm_client.LLMClient._get_client")
    def test_call_json_with_code_fences(self, mock_get_client):
        mock_anthropic = mock.MagicMock()
        mock_anthropic.messages.create.return_value = _mock_response(
            '```json\n{"key": "value"}\n```'
        )
        mock_get_client.return_value = mock_anthropic

        client = LLMClient(_make_config())
        result = client.call_json("system", "user")
        assert result["data"] == {"key": "value"}

    @mock.patch("engineering_brain.agent.llm_client.LLMClient._get_client")
    def test_call_json_invalid(self, mock_get_client):
        mock_anthropic = mock.MagicMock()
        mock_anthropic.messages.create.return_value = _mock_response("not json at all")
        mock_get_client.return_value = mock_anthropic

        client = LLMClient(_make_config())
        with pytest.raises(ValueError, match="invalid JSON"):
            client.call_json("system", "user")

    @mock.patch("engineering_brain.agent.llm_client.LLMClient._get_client")
    def test_token_tracking(self, mock_get_client):
        mock_anthropic = mock.MagicMock()
        mock_anthropic.messages.create.return_value = _mock_response("ok", 100, 200)
        mock_get_client.return_value = mock_anthropic

        client = LLMClient(_make_config())
        client.call("s", "u")
        assert client.total_tokens == 300
        assert client.token_stats["input_tokens"] == 100
        assert client.token_stats["output_tokens"] == 200

        # Second call
        client.call("s", "u")
        assert client.total_tokens == 600

    @mock.patch("engineering_brain.agent.llm_client.time.sleep")
    @mock.patch("engineering_brain.agent.llm_client.LLMClient._get_client")
    def test_retry_on_transient_error(self, mock_get_client, mock_sleep):
        mock_anthropic = mock.MagicMock()
        # Fail twice, succeed third time
        mock_anthropic.messages.create.side_effect = [
            ConnectionError("timeout"),
            ConnectionError("timeout"),
            _mock_response("recovered"),
        ]
        mock_get_client.return_value = mock_anthropic

        client = LLMClient(_make_config())
        result = client.call("s", "u")
        assert result["text"] == "recovered"
        assert mock_sleep.call_count == 2

    @mock.patch("engineering_brain.agent.llm_client.time.sleep")
    @mock.patch("engineering_brain.agent.llm_client.LLMClient._get_client")
    def test_retry_exhausted(self, mock_get_client, mock_sleep):
        mock_anthropic = mock.MagicMock()
        mock_anthropic.messages.create.side_effect = ConnectionError("always fails")
        mock_get_client.return_value = mock_anthropic

        client = LLMClient(_make_config())
        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            client.call("s", "u")

    @mock.patch("engineering_brain.agent.llm_client.LLMClient._get_client")
    def test_no_retry_on_auth_error(self, mock_get_client):
        mock_anthropic = mock.MagicMock()

        class AuthenticationError(Exception):
            pass

        err = AuthenticationError("bad key")
        err.__class__.__name__ = "AuthenticationError"
        # We need type(err).__name__ to be "AuthenticationError"
        mock_anthropic.messages.create.side_effect = err
        mock_get_client.return_value = mock_anthropic

        client = LLMClient(_make_config())
        # Should raise immediately without retry
        with pytest.raises(type(err)):
            client.call("s", "u")

    @mock.patch("engineering_brain.agent.llm_client.LLMClient._get_client")
    def test_call_uses_custom_model(self, mock_get_client):
        mock_anthropic = mock.MagicMock()
        mock_anthropic.messages.create.return_value = _mock_response("ok")
        mock_get_client.return_value = mock_anthropic

        client = LLMClient(_make_config())
        client.call("s", "u", model="custom-model", max_tokens=512)

        call_kwargs = mock_anthropic.messages.create.call_args[1]
        assert call_kwargs["model"] == "custom-model"
        assert call_kwargs["max_tokens"] == 512
