"""Systematically toggle feature flags and measure impact."""

from __future__ import annotations

import logging

from ..baselines.brain_system import BrainSystem
from ..datasets.loader import DatasetLoader
from ..metrics import compute_suite
from ..results import AblationResult, AggregateMetrics
from .flag_groups import get_group_flags
from .flag_scanner import FlagInfo, scan_flags

logger = logging.getLogger(__name__)


class AblationRunner:
    """Runs ablation study by toggling each feature flag."""

    def __init__(self, dataset_path: str | None = None, k: int = 10) -> None:
        self._dataset_path = dataset_path
        self._k = k

    def run_full_ablation(self) -> list[AblationResult]:
        """Toggle every boolean feature flag and measure delta."""
        flags = scan_flags()
        logger.info("Ablation: %d flags discovered", len(flags))
        return self._run_flags(flags)

    def run_group_ablation(self, group: str) -> list[AblationResult]:
        """Toggle all flags in a logical group."""
        all_flags = scan_flags()
        group_field_names = set(get_group_flags(group))
        flags = [f for f in all_flags if f.field_name in group_field_names]
        if not flags:
            logger.warning("No flags found for group: %s", group)
            return []
        logger.info("Ablation group '%s': %d flags", group, len(flags))
        return self._run_flags(flags)

    def run_specific_flags(self, flag_names: list[str]) -> list[AblationResult]:
        """Toggle specific flags by field name."""
        all_flags = scan_flags()
        name_set = set(flag_names)
        flags = [f for f in all_flags if f.field_name in name_set]
        return self._run_flags(flags)

    def _run_flags(self, flags: list[FlagInfo]) -> list[AblationResult]:
        """Run baseline, then toggle each flag and measure delta."""
        loader = DatasetLoader(self._dataset_path)
        queries = loader.load()

        # Run baseline (all defaults)
        logger.info("Running baseline...")
        baseline_agg = self._run_with_overrides({}, queries)

        results: list[AblationResult] = []
        for flag in flags:
            # Toggle: if default is True, set to False; if False, set to True
            toggled_value = "false" if flag.default_value else "true"
            logger.info(
                "  Toggling %s (%s -> %s)",
                flag.field_name,
                flag.default_value,
                toggled_value,
            )

            toggled_agg = self._run_with_overrides(
                {flag.env_var: toggled_value},
                queries,
            )

            results.append(
                AblationResult(
                    flag_name=flag.field_name,
                    flag_env_var=flag.env_var,
                    group=flag.group,
                    baseline_ndcg=baseline_agg.avg_ndcg_at_10,
                    toggled_ndcg=toggled_agg.avg_ndcg_at_10,
                    delta_ndcg=toggled_agg.avg_ndcg_at_10 - baseline_agg.avg_ndcg_at_10,
                    baseline_mrr=baseline_agg.avg_mrr,
                    toggled_mrr=toggled_agg.avg_mrr,
                    delta_mrr=toggled_agg.avg_mrr - baseline_agg.avg_mrr,
                    baseline_recall=baseline_agg.avg_recall_at_10,
                    toggled_recall=toggled_agg.avg_recall_at_10,
                    delta_recall=toggled_agg.avg_recall_at_10 - baseline_agg.avg_recall_at_10,
                    baseline_latency_ms=baseline_agg.avg_latency_ms,
                    toggled_latency_ms=toggled_agg.avg_latency_ms,
                    delta_latency_ms=toggled_agg.avg_latency_ms - baseline_agg.avg_latency_ms,
                )
            )

        return sorted(results, key=lambda r: abs(r.delta_ndcg), reverse=True)

    def _run_with_overrides(
        self,
        overrides: dict[str, str],
        queries: list,
    ) -> AggregateMetrics:
        """Run all queries with specific config overrides and return aggregate metrics."""
        from ..metrics import MetricSuite

        system = BrainSystem(config_overrides=overrides)
        system.setup()
        try:
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
            return AggregateMetrics.from_suites(suites)
        finally:
            system.teardown()
