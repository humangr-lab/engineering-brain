"""Tests for baseline system contracts."""

from __future__ import annotations

import inspect

from benchmarks.baselines.base import BaselineSystem, SystemResult
from benchmarks.baselines.brain_system import BrainSystem
from benchmarks.baselines.graph_rag import GraphRAGSystem
from benchmarks.baselines.naive_rag import NaiveRAGSystem


class TestBaselineContracts:
    """Verify all baselines implement the BaselineSystem ABC correctly."""

    def _check_system(self, cls):
        assert issubclass(cls, BaselineSystem)
        instance = cls()
        assert isinstance(instance.name, str)
        assert len(instance.name) > 0
        assert isinstance(instance.description, str)
        assert len(instance.description) > 0
        # Check methods exist
        assert callable(instance.setup)
        assert callable(instance.query)
        assert callable(instance.teardown)
        assert callable(instance.determine_relevant_ids)

    def test_brain_system(self):
        self._check_system(BrainSystem)

    def test_naive_rag_system(self):
        self._check_system(NaiveRAGSystem)

    def test_graph_rag_system(self):
        self._check_system(GraphRAGSystem)

    def test_brain_system_name(self):
        assert BrainSystem().name == "Engineering Brain"

    def test_naive_rag_name(self):
        assert NaiveRAGSystem().name == "Naive RAG"

    def test_graph_rag_name(self):
        assert GraphRAGSystem().name == "GraphRAG"


class TestSystemResult:
    def test_default_values(self):
        result = SystemResult(
            ranked_ids=["a", "b"],
            raw_results=[{"id": "a"}, {"id": "b"}],
            latency_ms=10.0,
        )
        assert result.token_count == 0
        assert result.metadata == {}
