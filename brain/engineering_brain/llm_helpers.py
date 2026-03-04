"""Lightweight LLM helper for brain module enhancements.

Design:
- Lazy import of anthropic SDK (not required for normal operation)
- Returns None on ANY failure — callers always fall back to heuristic
- 2-attempt retry with exponential backoff
- Reads BRAIN_AGENT_API_KEY first, falls back to ANTHROPIC_API_KEY
- Model via BRAIN_LLM_MODEL env var
- No dependencies on engineering_brain.agent (independent subsystem)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

_CODE_FENCE_RE = re.compile(r"```\w*\s*\n?(.*?)```", re.DOTALL)
_DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Non-retryable error class names (same list as agent/llm_client.py)
_NO_RETRY = frozenset(
    {
        "AuthenticationError",
        "BadRequestError",
        "PermissionDeniedError",
        "NotFoundError",
        "UnprocessableEntityError",
    }
)


def is_llm_enabled(flag_name: str) -> bool:
    """Check if the named feature flag env var is truthy AND an API key exists."""
    flag = os.getenv(flag_name, "false").lower() in ("true", "1", "yes")
    if not flag:
        return False
    return bool(os.getenv("BRAIN_AGENT_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))


def _get_client() -> Any:
    """Lazy-build Anthropic client. Returns None if SDK or key unavailable."""
    try:
        import anthropic  # noqa: F811
    except ImportError:
        return None
    api_key = os.getenv("BRAIN_AGENT_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def brain_llm_call(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    max_tokens: int = 200,
) -> str | None:
    """Make a single LLM call. Returns response text or None on any failure."""
    client = _get_client()
    if client is None:
        return None
    resolved_model = model or os.getenv("BRAIN_LLM_MODEL", _DEFAULT_MODEL)
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=resolved_model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            return text.strip() or None
        except Exception as exc:
            if type(exc).__name__ in _NO_RETRY:
                logger.debug("brain_llm_call: non-retryable: %s", exc)
                return None
            if attempt == 0:
                time.sleep(1.0)
    return None


def brain_llm_call_json(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    max_tokens: int = 300,
) -> dict[str, Any] | None:
    """Make an LLM call and parse JSON response. Returns dict or None."""
    text = brain_llm_call(system_prompt, user_message, model=model, max_tokens=max_tokens)
    if text is None:
        return None
    fence_match = _CODE_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None
