"""Measures resilience against adversarial knowledge injection."""

from __future__ import annotations

import logging

from ..baselines.brain_system import BrainSystem
from ..datasets.loader import DatasetLoader
from ..metrics import MetricSuite, compute_suite
from ..results import AggregateMetrics, RobustnessScenarioResult
from .knowledge_injector import KnowledgeInjector

logger = logging.getLogger(__name__)


class RobustnessRunner:
    """Runs robustness evaluation by injecting adversarial knowledge."""

    def __init__(
        self,
        dataset_path: str | None = None,
        adversarial_path: str | None = None,
    ) -> None:
        self._dataset_path = dataset_path
        self._adversarial_path = adversarial_path

    def run(
        self,
        scenarios: list[str] | None = None,
    ) -> list[RobustnessScenarioResult]:
        """Run robustness evaluation for specified scenarios."""
        injector = KnowledgeInjector(self._adversarial_path)
        if scenarios is None:
            scenarios = injector.get_scenarios()

        loader = DatasetLoader(self._dataset_path)
        queries = loader.load()

        # Get clean baseline
        logger.info("Running clean baseline...")
        baseline_agg = self._run_clean(queries)

        results: list[RobustnessScenarioResult] = []
        for scenario in scenarios:
            logger.info("Testing scenario: %s", scenario)
            result = self._run_scenario(
                scenario,
                injector,
                queries,
                baseline_agg,
            )
            results.append(result)

        return results

    def _run_clean(self, queries: list) -> AggregateMetrics:
        """Run baseline with clean knowledge."""
        system = BrainSystem()
        system.setup()
        try:
            suites = self._eval_queries(system, queries)
            return AggregateMetrics.from_suites(suites)
        finally:
            system.teardown()

    def _run_scenario(
        self,
        scenario: str,
        injector: KnowledgeInjector,
        queries: list,
        baseline_agg: AggregateMetrics,
    ) -> RobustnessScenarioResult:
        """Run one adversarial scenario and measure impact."""
        system = BrainSystem()
        system.setup()
        try:
            # Inject adversarial rules
            injected_ids = injector.inject(system._brain, scenario)
            injected_set = set(injected_ids)

            # Run queries and track contamination
            suites: list[MetricSuite] = []
            total_returned = 0
            total_contaminated = 0
            total_detected = 0

            for q in queries:
                result = system.query(
                    task_description=q.query,
                    technologies=q.expected_technologies,
                    domains=q.expected_domains,
                )

                # Check contamination
                for raw in result.raw_results:
                    total_returned += 1
                    if raw.get("id", "") in injected_set:
                        total_contaminated += 1
                    # Check if adversarial node was detected
                    if raw.get("_adversarial") and (
                        raw.get("validation_status") in ("conflicting", "deprecated", "quarantined")
                        or raw.get("deprecated", False)
                    ):
                        total_detected += 1

                relevant = system.determine_relevant_ids(
                    result,
                    q.expected_technologies,
                    q.expected_domains,
                )
                suite = compute_suite(
                    ranked_ids=result.ranked_ids,
                    relevant_ids=relevant,
                    latency_ms=result.latency_ms,
                )
                suites.append(suite)

            degraded_agg = AggregateMetrics.from_suites(suites)

            contamination_rate = total_contaminated / total_returned if total_returned > 0 else 0.0
            detection_rate = total_detected / len(injected_ids) if injected_ids else 0.0
            degradation = (
                (degraded_agg.avg_ndcg_at_10 - baseline_agg.avg_ndcg_at_10)
                / baseline_agg.avg_ndcg_at_10
                if baseline_agg.avg_ndcg_at_10 > 0
                else 0.0
            )
            # Resilience: 1.0 = perfect (no contamination, full detection, no degradation)
            resilience = (
                (1.0 - contamination_rate) * 0.4
                + detection_rate * 0.3
                + max(0.0, 1.0 + degradation) * 0.3
            )

            return RobustnessScenarioResult(
                scenario=scenario,
                injected_count=len(injected_ids),
                contamination_rate=contamination_rate,
                detection_rate=detection_rate,
                baseline_ndcg=baseline_agg.avg_ndcg_at_10,
                degraded_ndcg=degraded_agg.avg_ndcg_at_10,
                degradation_pct=degradation,
                resilience_score=resilience,
            )
        finally:
            system.teardown()

    def _eval_queries(self, system: BrainSystem, queries: list) -> list[MetricSuite]:
        """Evaluate all queries and return metric suites."""
        suites: list[MetricSuite] = []
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
            )
            suite = compute_suite(
                ranked_ids=result.ranked_ids,
                relevant_ids=relevant,
                latency_ms=result.latency_ms,
            )
            suites.append(suite)
        return suites
