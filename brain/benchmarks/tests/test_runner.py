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
        assert loader.version == "2.0"

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

    def test_ground_truth_ids_loaded(self):
        loader = DatasetLoader()
        queries = loader.load()
        # All v2.0 queries have ground truth
        for q in queries:
            assert q.ground_truth_ids is not None, f"{q.id} missing ground truth"
            assert len(q.ground_truth_ids) >= 5, f"{q.id} has too few ground truth IDs"

    def test_ground_truth_used_over_heuristic(self):
        """When ground truth is provided, it is used instead of tech/domain overlap."""
        from benchmarks.baselines.base import BaselineSystem

        system = MockSystem()
        result = system.query("test", ["python"], ["security"])
        # With ground truth, should return exactly those IDs
        relevant = system.determine_relevant_ids(
            result, ["python"], ["security"],
            ground_truth_ids=["GT-001", "GT-002"],
        )
        assert relevant == {"GT-001", "GT-002"}
        # Without ground truth, falls back to heuristic
        relevant_heuristic = system.determine_relevant_ids(
            result, ["python"], ["security"],
        )
        assert "R-001" in relevant_heuristic  # python+security overlap


class TestStrengthsDataset:
    def test_loads_brain_strengths_v1(self):
        from pathlib import Path

        path = str(Path(__file__).parent.parent / "datasets" / "brain_strengths_v1.yaml")
        loader = DatasetLoader(path)
        queries = loader.load()
        assert len(queries) == 20
        assert loader.version == "1.0"

    def test_strengths_categories(self):
        from pathlib import Path

        path = str(Path(__file__).parent.parent / "datasets" / "brain_strengths_v1.yaml")
        loader = DatasetLoader(path)
        cats = loader.categories
        assert "multi_hop_deep" in cats
        assert "domain_depth" in cats
        assert "contradiction" in cats
        assert "obsolescence" in cats
        assert len(cats) == 4

    def test_strengths_ground_truth(self):
        from pathlib import Path

        path = str(Path(__file__).parent.parent / "datasets" / "brain_strengths_v1.yaml")
        loader = DatasetLoader(path)
        queries = loader.load()
        for q in queries:
            assert q.ground_truth_ids is not None, f"{q.id} missing ground truth"
            assert len(q.ground_truth_ids) >= 5, f"{q.id} has too few ground truth IDs"

    def test_strengths_per_category_count(self):
        from pathlib import Path

        path = str(Path(__file__).parent.parent / "datasets" / "brain_strengths_v1.yaml")
        loader = DatasetLoader(path)
        queries = loader.load()
        from collections import Counter

        counts = Counter(q.category for q in queries)
        assert counts["multi_hop_deep"] == 5
        assert counts["domain_depth"] == 5
        assert counts["contradiction"] == 5
        assert counts["obsolescence"] == 5


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
