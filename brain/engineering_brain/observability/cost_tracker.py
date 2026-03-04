"""Cost tracking for Engineering Brain API calls (O-05).

Tracks embedding calls (Voyage), validation API calls (PyPI, npm, NVD),
and optional LLM calls (reranker, concept naming). Logs per-query and
per-run totals. Thread-safe singleton pattern.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Approximate costs per API call
_COST_MAP = {
    "voyage_embed": 0.00012,  # ~$0.12/1M tokens, ~1K tokens per call
    "voyage_rerank": 0.001,  # ~$0.05/1K queries
    "pypi_check": 0.0,  # Free
    "npm_check": 0.0,  # Free
    "nvd_check": 0.0,  # Free (with API key)
    "so_check": 0.0,  # Free (with API key)
    "github_check": 0.0,  # Free (with token)
    "official_docs": 0.0,  # Free
}


@dataclass
class CostEntry:
    """A single cost entry."""

    operation: str
    cost: float
    timestamp: float
    details: str = ""


@dataclass
class CostTracker:
    """Tracks API call costs for the Engineering Brain."""

    entries: list[CostEntry] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, operation: str, count: int = 1, details: str = "") -> None:
        """Record an API call cost."""
        unit_cost = _COST_MAP.get(operation, 0.0)
        total = unit_cost * count
        entry = CostEntry(
            operation=operation,
            cost=total,
            timestamp=time.time(),
            details=details,
        )
        with self._lock:
            self.entries.append(entry)
        if total > 0:
            logger.debug("Cost: %s x%d = $%.6f (%s)", operation, count, total, details)

    def total_cost(self) -> float:
        """Total cost across all entries."""
        with self._lock:
            return sum(e.cost for e in self.entries)

    def cost_by_operation(self) -> dict[str, float]:
        """Cost breakdown by operation type."""
        with self._lock:
            result: dict[str, float] = {}
            for e in self.entries:
                result[e.operation] = result.get(e.operation, 0.0) + e.cost
            return result

    def call_counts(self) -> dict[str, int]:
        """Call count by operation type."""
        with self._lock:
            result: dict[str, int] = {}
            for e in self.entries:
                result[e.operation] = result.get(e.operation, 0) + 1
            return result

    def summary(self) -> dict[str, Any]:
        """Full cost summary."""
        return {
            "total_cost_usd": round(self.total_cost(), 6),
            "total_calls": len(self.entries),
            "by_operation": self.cost_by_operation(),
            "call_counts": self.call_counts(),
        }

    def reset(self) -> None:
        """Clear all entries."""
        with self._lock:
            self.entries.clear()


# Module-level singleton
_tracker: CostTracker | None = None
_tracker_lock = threading.Lock()


def get_cost_tracker() -> CostTracker:
    """Get or create the global cost tracker singleton."""
    global _tracker  # noqa: PLW0603
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = CostTracker()
    return _tracker
