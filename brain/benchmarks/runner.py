"""Orchestrates benchmark runs across multiple systems and datasets."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from pathlib import Path

from .baselines.base import BaselineSystem
from .datasets.loader import DatasetLoader, EvalQuery
from .metrics import MetricSuite, compute_suite
from .results import AggregateMetrics, BenchmarkResults, QueryResult, SystemResults

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Runs benchmarks across systems and collects results."""

    def __init__(
        self,
        systems: list[BaselineSystem],
        dataset_path: str | None = None,
        output_dir: str | None = None,
    ) -> None:
        self._systems = systems
        self._loader = DatasetLoader(dataset_path)
        self._output_dir = Path(output_dir or "brain/benchmarks/reports")

    def run(
        self,
        categories: list[str] | None = None,
        difficulties: list[str] | None = None,
        k: int = 10,
    ) -> BenchmarkResults:
        """Run full benchmark suite across all systems and queries."""
        queries = self._loader.load(categories=categories, difficulties=difficulties)
        logger.info(
            "Running benchmark: %d systems x %d queries (k=%d)",
            len(self._systems),
            len(queries),
            k,
        )

        all_results: dict[str, SystemResults] = {}

        for system in self._systems:
            logger.info("Setting up system: %s", system.name)
            system.setup()
            try:
                system_results = self._run_system(system, queries, k)
                all_results[system.name] = system_results
                logger.info(
                    "  %s: NDCG@%d=%.4f MRR=%.4f Recall@%d=%.4f (%.1fs total)",
                    system.name,
                    k,
                    system_results.aggregate.avg_ndcg_at_10,
                    system_results.aggregate.avg_mrr,
                    k,
                    system_results.aggregate.avg_recall_at_10,
                    system_results.total_latency_ms / 1000,
                )
            finally:
                system.teardown()

        results = BenchmarkResults(
            timestamp=time.time(),
            dataset_version=self._loader.version,
            k=k,
            systems=all_results,
        )

        # Auto-save raw JSON
        ts = time.strftime("%Y%m%d_%H%M%S")
        json_path = self._output_dir / f"results_{ts}.json"
        results.to_json(json_path)
        # Also save as "latest" for easy access
        results.to_json(self._output_dir / "latest.json")
        logger.info("Results saved to %s", json_path)

        return results

    def _run_system(
        self,
        system: BaselineSystem,
        queries: list[EvalQuery],
        k: int,
    ) -> SystemResults:
        """Run all queries through one system."""
        query_results: list[QueryResult] = []
        total_tokens = 0

        for q in queries:
            result = system.query(
                task_description=q.query,
                technologies=q.expected_technologies,
                domains=q.expected_domains,
            )

            relevant = system.determine_relevant_ids(
                result,
                q.expected_technologies,
                q.expected_domains,
                ground_truth_ids=q.ground_truth_ids,
            )

            suite = compute_suite(
                ranked_ids=result.ranked_ids,
                relevant_ids=relevant,
                latency_ms=result.latency_ms,
            )

            total_tokens += result.token_count

            query_results.append(
                QueryResult(
                    query_id=q.id,
                    category=q.category,
                    difficulty=q.difficulty,
                    metrics=suite,
                    ranked_ids=result.ranked_ids,
                    relevant_ids=sorted(relevant),
                )
            )

        # Aggregate
        all_suites = [qr.metrics for qr in query_results]
        aggregate = AggregateMetrics.from_suites(all_suites)

        # Per-category
        by_cat: dict[str, list[MetricSuite]] = defaultdict(list)
        for qr in query_results:
            by_cat[qr.category].append(qr.metrics)
        per_category = {cat: AggregateMetrics.from_suites(suites) for cat, suites in by_cat.items()}

        # Per-difficulty
        by_diff: dict[str, list[MetricSuite]] = defaultdict(list)
        for qr in query_results:
            by_diff[qr.difficulty].append(qr.metrics)
        per_difficulty = {
            diff: AggregateMetrics.from_suites(suites) for diff, suites in by_diff.items()
        }

        return SystemResults(
            system_name=system.name,
            system_description=system.description,
            queries=query_results,
            aggregate=aggregate,
            per_category=per_category,
            per_difficulty=per_difficulty,
            total_latency_ms=sum(s.latency_ms for s in all_suites),
            total_tokens=total_tokens,
        )
