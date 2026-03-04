"""Structured results model — serializable, versionable."""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .metrics import MetricSuite


@dataclass
class QueryResult:
    """Single query result for one system."""

    query_id: str
    category: str
    difficulty: str
    metrics: MetricSuite
    ranked_ids: list[str]
    relevant_ids: list[str]


@dataclass
class AggregateMetrics:
    """Aggregated metrics across multiple queries."""

    count: int
    avg_ndcg_at_5: float
    avg_ndcg_at_10: float
    avg_mrr: float
    avg_recall_at_5: float
    avg_recall_at_10: float
    avg_precision_at_5: float
    avg_precision_at_10: float
    avg_map: float
    avg_f1_at_10: float
    avg_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float

    @classmethod
    def from_suites(cls, suites: list[MetricSuite]) -> AggregateMetrics:
        """Aggregate a list of MetricSuites into summary statistics."""
        n = len(suites) or 1
        latencies = sorted(s.latency_ms for s in suites)
        p95_idx = min(int(0.95 * len(latencies)), len(latencies) - 1)
        return cls(
            count=len(suites),
            avg_ndcg_at_5=sum(s.ndcg_at_5 for s in suites) / n,
            avg_ndcg_at_10=sum(s.ndcg_at_10 for s in suites) / n,
            avg_mrr=sum(s.mrr for s in suites) / n,
            avg_recall_at_5=sum(s.recall_at_5 for s in suites) / n,
            avg_recall_at_10=sum(s.recall_at_10 for s in suites) / n,
            avg_precision_at_5=sum(s.precision_at_5 for s in suites) / n,
            avg_precision_at_10=sum(s.precision_at_10 for s in suites) / n,
            avg_map=sum(s.map_score for s in suites) / n,
            avg_f1_at_10=sum(s.f1_at_10 for s in suites) / n,
            avg_latency_ms=sum(s.latency_ms for s in suites) / n,
            median_latency_ms=statistics.median(latencies) if latencies else 0.0,
            p95_latency_ms=latencies[p95_idx] if latencies else 0.0,
        )


@dataclass
class SystemResults:
    """All results for one system."""

    system_name: str
    system_description: str
    queries: list[QueryResult]
    aggregate: AggregateMetrics
    per_category: dict[str, AggregateMetrics]
    per_difficulty: dict[str, AggregateMetrics]
    total_latency_ms: float
    total_tokens: int


@dataclass
class AblationResult:
    """Result of toggling a single flag."""

    flag_name: str
    flag_env_var: str
    group: str
    baseline_ndcg: float
    toggled_ndcg: float
    delta_ndcg: float
    baseline_mrr: float
    toggled_mrr: float
    delta_mrr: float
    baseline_recall: float
    toggled_recall: float
    delta_recall: float
    baseline_latency_ms: float
    toggled_latency_ms: float
    delta_latency_ms: float


@dataclass
class RobustnessScenarioResult:
    """Result for one adversarial scenario."""

    scenario: str
    injected_count: int
    contamination_rate: float
    detection_rate: float
    baseline_ndcg: float
    degraded_ndcg: float
    degradation_pct: float
    resilience_score: float


@dataclass
class CostProfile:
    """Cost metrics for one system."""

    system_name: str
    avg_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    total_tokens: int
    avg_tokens_per_query: float
    peak_memory_mb: float
    setup_time_s: float


@dataclass
class BenchmarkResults:
    """Complete benchmark run results."""

    timestamp: float
    dataset_version: str
    k: int
    systems: dict[str, SystemResults]
    ablation: list[AblationResult] | None = None
    robustness: list[RobustnessScenarioResult] | None = None
    cost: list[CostProfile] | None = None

    def to_json(self, path: str | Path) -> None:
        """Serialize results to JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2, default=str)

    @classmethod
    def from_json(cls, path: str | Path) -> BenchmarkResults:
        """Deserialize results from JSON."""
        with open(path) as f:
            data = json.load(f)
        return _reconstruct_results(data)


def _reconstruct_results(data: dict[str, Any]) -> BenchmarkResults:
    """Reconstruct BenchmarkResults from a JSON dict."""
    systems = {}
    for name, sdata in data.get("systems", {}).items():
        queries = []
        for q in sdata.get("queries", []):
            queries.append(
                QueryResult(
                    query_id=q["query_id"],
                    category=q["category"],
                    difficulty=q["difficulty"],
                    metrics=MetricSuite(**q["metrics"]),
                    ranked_ids=q["ranked_ids"],
                    relevant_ids=q["relevant_ids"],
                )
            )
        agg = AggregateMetrics(**sdata["aggregate"])
        per_cat = {k: AggregateMetrics(**v) for k, v in sdata.get("per_category", {}).items()}
        per_diff = {k: AggregateMetrics(**v) for k, v in sdata.get("per_difficulty", {}).items()}
        systems[name] = SystemResults(
            system_name=sdata["system_name"],
            system_description=sdata["system_description"],
            queries=queries,
            aggregate=agg,
            per_category=per_cat,
            per_difficulty=per_diff,
            total_latency_ms=sdata["total_latency_ms"],
            total_tokens=sdata["total_tokens"],
        )

    ablation = None
    if data.get("ablation"):
        ablation = [AblationResult(**a) for a in data["ablation"]]

    robustness = None
    if data.get("robustness"):
        robustness = [RobustnessScenarioResult(**r) for r in data["robustness"]]

    cost = None
    if data.get("cost"):
        cost = [CostProfile(**c) for c in data["cost"]]

    return BenchmarkResults(
        timestamp=data["timestamp"],
        dataset_version=data["dataset_version"],
        k=data["k"],
        systems=systems,
        ablation=ablation,
        robustness=robustness,
        cost=cost,
    )
