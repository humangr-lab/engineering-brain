"""Abstract base for all benchmark systems."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SystemResult:
    """Standardized result from any benchmark system."""

    ranked_ids: list[str]
    raw_results: list[dict[str, Any]]
    latency_ms: float
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaselineSystem(ABC):
    """Interface that all benchmark systems must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable system name for reports."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description for methodology section."""

    @abstractmethod
    def setup(self) -> None:
        """Initialize the system (seed data, load models, etc.)."""

    @abstractmethod
    def query(
        self,
        task_description: str,
        technologies: list[str],
        domains: list[str],
    ) -> SystemResult:
        """Run a single query and return standardized results."""

    @abstractmethod
    def teardown(self) -> None:
        """Cleanup resources."""

    def determine_relevant_ids(
        self,
        result: SystemResult,
        expected_technologies: list[str],
        expected_domains: list[str],
    ) -> set[str]:
        """Determine which returned IDs are relevant to the query.

        Default: tech/domain overlap (same logic as existing test_evaluation.py).
        """
        relevant = set()
        query_techs = {t.lower() for t in expected_technologies}
        query_domains = {d.lower() for d in expected_domains}

        for item in result.raw_results:
            nid = item.get("id", "")
            if not nid:
                continue
            node_techs = {
                t.lower()
                for t in (item.get("technologies") or item.get("languages") or [])
            }
            node_domains = {
                d.lower() for d in (item.get("domains") or [item.get("domain", "")])
            }
            if (query_techs & node_techs) or (query_domains & node_domains) or not query_techs:
                relevant.add(nid)
        return relevant
