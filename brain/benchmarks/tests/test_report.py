"""Tests for report generation."""

from __future__ import annotations

import time

from benchmarks.metrics import MetricSuite
from benchmarks.results import (
    AggregateMetrics,
    BenchmarkResults,
    QueryResult,
    SystemResults,
)


def _make_dummy_results() -> BenchmarkResults:
    """Create minimal results for report generation testing."""
    suite = MetricSuite(
        ndcg_at_5=0.95,
        ndcg_at_10=0.97,
        mrr=1.0,
        recall_at_5=0.8,
        recall_at_10=0.95,
        precision_at_5=0.6,
        precision_at_10=0.5,
        map_score=0.92,
        f1_at_10=0.65,
        latency_ms=12.5,
        result_count=8,
    )

    queries = [
        QueryResult(
            query_id="SEC-01",
            category="security",
            difficulty="easy",
            metrics=suite,
            ranked_ids=["R-001", "R-002"],
            relevant_ids=["R-001"],
        ),
    ]

    agg = AggregateMetrics.from_suites([suite])

    sr = SystemResults(
        system_name="Engineering Brain",
        system_description="Full system",
        queries=queries,
        aggregate=agg,
        per_category={"security": agg},
        per_difficulty={"easy": agg},
        total_latency_ms=12.5,
        total_tokens=0,
    )

    return BenchmarkResults(
        timestamp=time.time(),
        dataset_version="1.0",
        k=10,
        systems={"Engineering Brain": sr},
    )


class TestResultsSerialization:
    def test_to_and_from_json(self, tmp_path):
        results = _make_dummy_results()
        path = tmp_path / "test_results.json"
        results.to_json(path)

        loaded = BenchmarkResults.from_json(path)
        assert loaded.dataset_version == "1.0"
        assert "Engineering Brain" in loaded.systems
        assert loaded.systems["Engineering Brain"].aggregate.avg_ndcg_at_10 == 0.97


class TestReportGenerator:
    def test_generates_html_fallback(self, tmp_path):
        """Test HTML generation (WeasyPrint may not be installed in test env)."""
        results = _make_dummy_results()

        try:
            from benchmarks.report_generator import ReportGenerator

            gen = ReportGenerator(results, output_dir=str(tmp_path))
            output = gen.generate(filename="test_report.pdf")
            # Should produce either PDF or HTML fallback
            assert output.exists()
            assert output.suffix in (".pdf", ".html")
        except ImportError:
            # matplotlib or jinja2 not installed — skip gracefully
            pass
