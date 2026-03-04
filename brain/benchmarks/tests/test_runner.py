"""Tests for the benchmark runner."""

from __future__ import annotations

from benchmarks.baselines.base import BaselineSystem, SystemResult
from benchmarks.datasets.loader import DatasetLoader
from benchmarks.runner import BenchmarkRunner


class MockSystem(BaselineSystem):
    """A trivial system that returns dummy results for testing."""

    @property
    def name(self) -> str:
        return "MockSystem"

    @property
    def description(self) -> str:
        return "Mock system for testing."

    def setup(self) -> None:
        pass

    def query(self, task_description, technologies, domains) -> SystemResult:
        return SystemResult(
            ranked_ids=["R-001", "R-002", "R-003"],
            raw_results=[
                {"id": "R-001", "technologies": ["python", "flask"], "domains": ["security"]},
                {"id": "R-002", "technologies": ["python"], "domains": ["architecture"]},
                {"id": "R-003", "technologies": ["react"], "domains": ["frontend"]},
            ],
            latency_ms=5.0,
        )

    def teardown(self) -> None:
        pass


class TestDatasetLoader:
    def test_loads_golden_v1(self):
        loader = DatasetLoader()
        queries = loader.load()
        assert len(queries) == 50
        assert loader.version == "1.0"

    def test_filter_by_category(self):
        loader = DatasetLoader()
        queries = loader.load(categories=["security"])
        assert all(q.category == "security" for q in queries)
        assert len(queries) == 10

    def test_filter_by_difficulty(self):
        loader = DatasetLoader()
        queries = loader.load(difficulties=["easy"])
        assert all(q.difficulty == "easy" for q in queries)

    def test_categories_property(self):
        loader = DatasetLoader()
        cats = loader.categories
        assert "security" in cats
        assert "architecture" in cats
        assert len(cats) == 5


class TestBenchmarkRunner:
    def test_run_with_mock_system(self, tmp_path):
        runner = BenchmarkRunner(
            systems=[MockSystem()],
            output_dir=str(tmp_path),
        )
        results = runner.run(k=10)

        assert "MockSystem" in results.systems
        sr = results.systems["MockSystem"]
        assert sr.aggregate.count == 50
        assert sr.aggregate.avg_latency_ms > 0
        assert 0.0 <= sr.aggregate.avg_ndcg_at_10 <= 1.0

        # Check JSON was saved
        assert (tmp_path / "latest.json").exists()

    def test_run_filtered(self, tmp_path):
        runner = BenchmarkRunner(
            systems=[MockSystem()],
            output_dir=str(tmp_path),
        )
        results = runner.run(categories=["security"], k=10)
        sr = results.systems["MockSystem"]
        assert sr.aggregate.count == 10
