"""Dead letter queue for failed Engineering Brain operations (O-09).

Failed embeddings, writes, validations are appended to a JSONL file
for periodic retry or manual review. Never blocks the main pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PATH = os.path.join(
    os.path.expanduser("~"),
    ".engineering_brain",
    "dead_letters.jsonl",
)


class DeadLetterQueue:
    """Append-only dead letter queue backed by JSONL file."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path or os.getenv("BRAIN_DEAD_LETTER_PATH", _DEFAULT_PATH)
        self._count = 0

    def append(
        self,
        operation: str,
        input_data: Any,
        error: str,
        retryable: bool = True,
    ) -> None:
        """Append a failed operation to the dead letter queue.

        Never raises — all errors are silently logged.
        """
        entry = {
            "timestamp": time.time(),
            "operation": operation,
            "input_data": _safe_serialize(input_data),
            "error": str(error)[:500],
            "retryable": retryable,
        }
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
            self._count += 1
            logger.debug("Dead letter: %s — %s", operation, error[:100])
        except Exception as exc:
            logger.warning("Failed to write dead letter: %s", exc)

    def count(self) -> int:
        """Approximate count of dead letters (session-local + file)."""
        try:
            if os.path.exists(self._path):
                with open(self._path) as f:
                    return sum(1 for _ in f)
        except Exception:
            pass
        return self._count

    def read_all(self, limit: int = 100) -> list[dict[str, Any]]:
        """Read dead letters (most recent first)."""
        entries: list[dict[str, Any]] = []
        try:
            if not os.path.exists(self._path):
                return entries
            with open(self._path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except Exception:
            pass
        return entries[-limit:]

    def clear(self) -> int:
        """Clear all dead letters. Returns count of cleared entries."""
        count = self.count()
        try:
            if os.path.exists(self._path):
                os.remove(self._path)
            self._count = 0
        except Exception:
            pass
        return count


def _safe_serialize(data: Any) -> Any:
    """Make data JSON-safe by truncating large values."""
    if isinstance(data, dict):
        return {k: _safe_serialize(v) for k, v in list(data.items())[:20]}
    if isinstance(data, (list, tuple)):
        return [_safe_serialize(v) for v in data[:10]]
    if isinstance(data, str) and len(data) > 500:
        return data[:500] + "..."
    if isinstance(data, bytes):
        return f"<bytes len={len(data)}>"
    return data


# Module-level singleton
_dlq: DeadLetterQueue | None = None


def get_dead_letter_queue() -> DeadLetterQueue:
    """Get or create the global dead letter queue singleton."""
    global _dlq  # noqa: PLW0603
    if _dlq is None:
        _dlq = DeadLetterQueue()
    return _dlq
