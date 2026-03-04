"""Versioned dataset loader with schema validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class EvalQuery:
    """A single evaluation query from the dataset."""

    id: str
    query: str
    category: str
    difficulty: str
    expected_technologies: list[str]
    expected_domains: list[str]


class DatasetLoader:
    """Loads and validates benchmark datasets from versioned YAML files."""

    def __init__(self, path: str | None = None) -> None:
        if path is None:
            path = str(Path(__file__).parent / "golden_v1.yaml")
        self._path = Path(path)
        with open(self._path) as f:
            self._data = yaml.safe_load(f)
        self.version: str = self._data.get("version", "unknown")

    def load(
        self,
        categories: list[str] | None = None,
        difficulties: list[str] | None = None,
    ) -> list[EvalQuery]:
        """Load queries, optionally filtered by category or difficulty."""
        queries = []
        for q in self._data.get("queries", []):
            cat = q.get("category", "unknown")
            diff = q.get("difficulty", "medium")
            if categories and cat not in categories:
                continue
            if difficulties and diff not in difficulties:
                continue
            queries.append(
                EvalQuery(
                    id=q["id"],
                    query=q["query"],
                    category=cat,
                    difficulty=diff,
                    expected_technologies=q.get("expected_technologies", []),
                    expected_domains=q.get("expected_domains", []),
                )
            )
        return queries

    @property
    def categories(self) -> list[str]:
        """All unique categories in the dataset."""
        return sorted({q.get("category", "unknown") for q in self._data.get("queries", [])})

    @property
    def total_queries(self) -> int:
        return len(self._data.get("queries", []))
