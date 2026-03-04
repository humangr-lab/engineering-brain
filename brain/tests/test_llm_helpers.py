"""Tests for engineering_brain.llm_helpers — shared LLM infrastructure.

Covers:
1. is_llm_enabled: flag + API key checks
2. _get_client: lazy Anthropic client creation
3. brain_llm_call: text responses, retries, non-retryable errors
4. brain_llm_call_json: JSON parsing, code fence stripping, fallback
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from types import SimpleNamespace
from unittest import mock

# =============================================================================
# 1. is_llm_enabled
# =============================================================================


class TestIsLLMEnabled:
    """Feature flag + API key gating."""

    def test_flag_false_no_key(self) -> None:
        """Returns False when flag is off and no key."""
        from engineering_brain.llm_helpers import is_llm_enabled

        with mock.patch.dict(os.environ, {}, clear=True):
            assert is_llm_enabled("BRAIN_LLM_FOO") is False

    def test_flag_true_no_key(self) -> None:
        """Returns False when flag is on but no API key."""
        from engineering_brain.llm_helpers import is_llm_enabled

        with mock.patch.dict(os.environ, {"BRAIN_LLM_FOO": "true"}, clear=True):
            assert is_llm_enabled("BRAIN_LLM_FOO") is False

    def test_flag_false_with_key(self) -> None:
        """Returns False when flag is off even with API key."""
        from engineering_brain.llm_helpers import is_llm_enabled

        env = {"BRAIN_LLM_FOO": "false", "BRAIN_AGENT_API_KEY": "sk-test"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert is_llm_enabled("BRAIN_LLM_FOO") is False

    def test_flag_true_with_brain_key(self) -> None:
        """Returns True when flag on + BRAIN_AGENT_API_KEY set."""
        from engineering_brain.llm_helpers import is_llm_enabled

        env = {"BRAIN_LLM_FOO": "true", "BRAIN_AGENT_API_KEY": "sk-test"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert is_llm_enabled("BRAIN_LLM_FOO") is True

    def test_flag_true_with_anthropic_key(self) -> None:
        """Returns True when flag on + ANTHROPIC_API_KEY set (fallback)."""
        from engineering_brain.llm_helpers import is_llm_enabled

        env = {"BRAIN_LLM_FOO": "1", "ANTHROPIC_API_KEY": "sk-test"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert is_llm_enabled("BRAIN_LLM_FOO") is True

    def test_flag_yes_variant(self) -> None:
        """Accepts 'yes' as truthy value."""
        from engineering_brain.llm_helpers import is_llm_enabled

        env = {"BRAIN_LLM_FOO": "yes", "BRAIN_AGENT_API_KEY": "sk-test"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert is_llm_enabled("BRAIN_LLM_FOO") is True


# =============================================================================
# 2. _get_client
# =============================================================================


class TestGetClient:
    """Lazy Anthropic client creation."""

    def test_no_sdk_returns_none(self) -> None:
        """Returns None when anthropic SDK not installed."""
        from engineering_brain.llm_helpers import _get_client

        with mock.patch.dict("sys.modules", {"anthropic": None}):
            assert _get_client() is None

    def test_no_key_returns_none(self) -> None:
        """Returns None when no API key set."""
        from engineering_brain.llm_helpers import _get_client

        with mock.patch.dict(os.environ, {}, clear=True):
            result = _get_client()
            # Without API key, should return None
            assert result is None

    @mock.patch("engineering_brain.llm_helpers.anthropic", create=True)
    def test_with_key_returns_client(self, mock_anthropic_mod: mock.MagicMock) -> None:
        """Returns Anthropic client when key is available."""
        from engineering_brain.llm_helpers import _get_client

        mock_client = mock.MagicMock()
        # We need to mock the import inside the function
        mock_module = mock.MagicMock()
        mock_module.Anthropic.return_value = mock_client

        env = {"BRAIN_AGENT_API_KEY": "sk-test"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.dict("sys.modules", {"anthropic": mock_module}):
                result = _get_client()
                assert result is mock_client


# =============================================================================
# 3. brain_llm_call
# =============================================================================


def _mock_response(text: str) -> SimpleNamespace:
    """Build a minimal mock Anthropic response."""
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


class TestBrainLLMCall:
    """Text response LLM calls."""

    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_success(self, mock_get: mock.MagicMock) -> None:
        """Returns text on successful call."""
        from engineering_brain.llm_helpers import brain_llm_call

        mock_client = mock.MagicMock()
        mock_client.messages.create.return_value = _mock_response("Hello world")
        mock_get.return_value = mock_client

        result = brain_llm_call("system", "user")
        assert result == "Hello world"

    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_empty_response_returns_none(self, mock_get: mock.MagicMock) -> None:
        """Returns None for empty/whitespace-only response."""
        from engineering_brain.llm_helpers import brain_llm_call

        mock_client = mock.MagicMock()
        mock_client.messages.create.return_value = _mock_response("   ")
        mock_get.return_value = mock_client

        assert brain_llm_call("system", "user") is None

    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_no_client_returns_none(self, mock_get: mock.MagicMock) -> None:
        """Returns None when no client available."""
        from engineering_brain.llm_helpers import brain_llm_call

        mock_get.return_value = None
        assert brain_llm_call("system", "user") is None

    @mock.patch("engineering_brain.llm_helpers.time.sleep")
    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_retry_on_transient_error(
        self, mock_get: mock.MagicMock, mock_sleep: mock.MagicMock
    ) -> None:
        """Retries once on transient error, then succeeds."""
        from engineering_brain.llm_helpers import brain_llm_call

        mock_client = mock.MagicMock()
        mock_client.messages.create.side_effect = [
            ConnectionError("timeout"),
            _mock_response("recovered"),
        ]
        mock_get.return_value = mock_client

        result = brain_llm_call("system", "user")
        assert result == "recovered"
        mock_sleep.assert_called_once_with(1.0)

    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_no_retry_on_auth_error(self, mock_get: mock.MagicMock) -> None:
        """Does not retry on AuthenticationError."""
        from engineering_brain.llm_helpers import brain_llm_call

        mock_client = mock.MagicMock()
        exc = type("AuthenticationError", (Exception,), {})("bad key")
        mock_client.messages.create.side_effect = exc
        mock_get.return_value = mock_client

        assert brain_llm_call("system", "user") is None
        assert mock_client.messages.create.call_count == 1

    @mock.patch("engineering_brain.llm_helpers.time.sleep")
    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_all_retries_exhausted(
        self, mock_get: mock.MagicMock, mock_sleep: mock.MagicMock
    ) -> None:
        """Returns None when all retries fail."""
        from engineering_brain.llm_helpers import brain_llm_call

        mock_client = mock.MagicMock()
        mock_client.messages.create.side_effect = ConnectionError("timeout")
        mock_get.return_value = mock_client

        assert brain_llm_call("system", "user") is None
        assert mock_client.messages.create.call_count == 2

    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_custom_model(self, mock_get: mock.MagicMock) -> None:
        """Passes custom model to API."""
        from engineering_brain.llm_helpers import brain_llm_call

        mock_client = mock.MagicMock()
        mock_client.messages.create.return_value = _mock_response("ok")
        mock_get.return_value = mock_client

        brain_llm_call("sys", "usr", model="claude-opus-4-20250514")
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-20250514"


# =============================================================================
# 4. brain_llm_call_json
# =============================================================================


class TestBrainLLMCallJSON:
    """JSON parsing from LLM responses."""

    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_valid_json(self, mock_get: mock.MagicMock) -> None:
        """Parses plain JSON response."""
        from engineering_brain.llm_helpers import brain_llm_call_json

        mock_client = mock.MagicMock()
        payload = json.dumps({"technologies": ["Flask"], "domains": ["security"]})
        mock_client.messages.create.return_value = _mock_response(payload)
        mock_get.return_value = mock_client

        result = brain_llm_call_json("sys", "usr")
        assert result == {"technologies": ["Flask"], "domains": ["security"]}

    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_code_fenced_json(self, mock_get: mock.MagicMock) -> None:
        """Extracts JSON from ```json ... ``` fences."""
        from engineering_brain.llm_helpers import brain_llm_call_json

        mock_client = mock.MagicMock()
        payload = '```json\n{"key": "value"}\n```'
        mock_client.messages.create.return_value = _mock_response(payload)
        mock_get.return_value = mock_client

        result = brain_llm_call_json("sys", "usr")
        assert result == {"key": "value"}

    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_invalid_json_returns_none(self, mock_get: mock.MagicMock) -> None:
        """Returns None for malformed JSON."""
        from engineering_brain.llm_helpers import brain_llm_call_json

        mock_client = mock.MagicMock()
        mock_client.messages.create.return_value = _mock_response("not json at all")
        mock_get.return_value = mock_client

        assert brain_llm_call_json("sys", "usr") is None

    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_json_list_returns_none(self, mock_get: mock.MagicMock) -> None:
        """Returns None when JSON is a list (not dict)."""
        from engineering_brain.llm_helpers import brain_llm_call_json

        mock_client = mock.MagicMock()
        mock_client.messages.create.return_value = _mock_response('["a", "b"]')
        mock_get.return_value = mock_client

        assert brain_llm_call_json("sys", "usr") is None

    @mock.patch("engineering_brain.llm_helpers._get_client")
    def test_llm_failure_returns_none(self, mock_get: mock.MagicMock) -> None:
        """Returns None when underlying LLM call fails."""
        from engineering_brain.llm_helpers import brain_llm_call_json

        mock_get.return_value = None
        assert brain_llm_call_json("sys", "usr") is None
