"""Anthropic SDK wrapper for agent LLM calls.

Lazy initialization, retry with exponential backoff, token tracking.
BYOK (Bring Your Own Key) — user provides BRAIN_AGENT_API_KEY.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from engineering_brain.agent.config import AgentConfig

logger = logging.getLogger(__name__)

# Maximum retries for transient API errors
_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds

# Non-retryable Anthropic SDK exception names
_NO_RETRY_EXCEPTIONS = frozenset(
    {
        "AuthenticationError",
        "BadRequestError",
        "PermissionDeniedError",
        "NotFoundError",
        "UnprocessableEntityError",
    }
)

# Regex to extract JSON from markdown code fences
_CODE_FENCE_RE = re.compile(r"```\w*\s*\n?(.*?)```", re.DOTALL)


class LLMClient:
    """Thin wrapper over the Anthropic SDK with retry and token tracking."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._client: Any = None  # Lazy Anthropic client
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

    def _get_client(self) -> Any:
        """Lazy-initialize the Anthropic client."""
        if self._client is not None:
            return self._client
        if not self._config.api_key:
            raise ValueError(
                "BRAIN_AGENT_API_KEY is required. Set the environment variable "
                "or pass it via BrainConfig."
            )
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for the agent system. "
                "Install it with: pip install 'engineering-brain[agent]'"
            ) from None
        self._client = anthropic.Anthropic(
            api_key=self._config.api_key,
            timeout=float(self._config.timeout),
        )
        return self._client

    def call(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Make a single LLM call with retry.

        Returns:
            {
                "text": str,          # Raw response text
                "input_tokens": int,  # Tokens in prompt
                "output_tokens": int, # Tokens in response
            }
        """
        client = self._get_client()
        model = model or self._config.model
        max_tokens = max_tokens or self._config.max_tokens

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                self._total_input_tokens += input_tokens
                self._total_output_tokens += output_tokens

                text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text

                return {
                    "text": text,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }
            except Exception as exc:
                last_error = exc
                # Don't retry on auth/validation errors
                if type(exc).__name__ in _NO_RETRY_EXCEPTIONS:
                    raise
                if attempt < _MAX_RETRIES - 1:
                    delay = _BASE_DELAY * (2**attempt)
                    logger.warning(
                        "LLM call attempt %d/%d failed (%s), retrying in %.1fs",
                        attempt + 1,
                        _MAX_RETRIES,
                        type(exc).__name__,
                        delay,
                    )
                    time.sleep(delay)

        raise RuntimeError(f"LLM call failed after {_MAX_RETRIES} attempts: {last_error}")

    def call_json(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Make an LLM call and parse the response as JSON.

        Returns:
            {
                "data": dict|list,    # Parsed JSON
                "input_tokens": int,
                "output_tokens": int,
            }
        """
        result = self.call(system_prompt, user_message, model=model, max_tokens=max_tokens)
        text = result["text"].strip()

        # Extract JSON from markdown code fences if present
        fence_match = _CODE_FENCE_RE.search(text)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

        return {
            "data": data,
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
        }

    @property
    def total_tokens(self) -> int:
        """Total tokens used across all calls."""
        return self._total_input_tokens + self._total_output_tokens

    @property
    def token_stats(self) -> dict[str, int]:
        """Token usage breakdown."""
        return {
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "total_tokens": self.total_tokens,
        }
