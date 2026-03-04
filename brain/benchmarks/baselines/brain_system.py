"""Engineering Brain as a benchmark system — full feature set."""

from __future__ import annotations

import os
import time
from typing import Any

from .base import BaselineSystem, SystemResult


class BrainSystem(BaselineSystem):
    """The Engineering Brain with all features enabled (default config)."""

    def __init__(self, config_overrides: dict[str, str] | None = None) -> None:
        self._overrides = config_overrides or {}
        self._brain: Any = None
        self._original_env: dict[str, str | None] = {}

    @property
    def name(self) -> str:
        return "Engineering Brain"

    @property
    def description(self) -> str:
        return (
            "Full Engineering Brain with 6-layer knowledge graph, 7-signal scoring, "
            "adaptive weights (Thompson Sampling), cross-layer inference, link prediction, "
            "ontology alignment, guardrails, and LLM enhancements."
        )

    def setup(self) -> None:
        # Save and apply overrides
        for key, value in self._overrides.items():
            self._original_env[key] = os.environ.get(key)
            os.environ[key] = value

        from engineering_brain.core.brain import Brain

        self._brain = Brain()
        self._brain.seed()

    def query(
        self,
        task_description: str,
        technologies: list[str],
        domains: list[str],
    ) -> SystemResult:
        start = time.monotonic()
        result = self._brain.query(
            task_description=task_description,
            technologies=technologies or None,
            domains=domains or None,
            phase="exec",
        )
        elapsed = (time.monotonic() - start) * 1000

        ranked_ids: list[str] = []
        raw_results: list[dict[str, Any]] = []
        for layer_key in ("principles", "patterns", "rules", "evidence"):
            for node in getattr(result, layer_key, []):
                nid = node.get("id", "")
                if nid:
                    ranked_ids.append(nid)
                    raw_results.append(node)

        return SystemResult(
            ranked_ids=ranked_ids,
            raw_results=raw_results,
            latency_ms=elapsed,
            token_count=0,
            metadata={
                "query_time_ms": getattr(result, "query_time_ms", elapsed),
                "cache_hit": getattr(result, "cache_hit", False),
            },
        )

    def teardown(self) -> None:
        # Restore original env
        for key, original in self._original_env.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original
        self._original_env.clear()
        self._brain = None
