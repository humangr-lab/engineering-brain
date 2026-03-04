"""Information retrieval metrics for benchmark evaluation.

All metrics return float in [0.0, 1.0].
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSuite:
    """All metrics for a single query evaluation."""

    ndcg_at_5: float
    ndcg_at_10: float
    mrr: float
    recall_at_5: float
    recall_at_10: float
    precision_at_5: float
    precision_at_10: float
    map_score: float
    f1_at_10: float
    latency_ms: float
    result_count: int


def ndcg_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    """Normalized Discounted Cumulative Gain at rank k."""

    def dcg(ids: list[str], rel: set[str], n: int) -> float:
        total = 0.0
        for i, nid in enumerate(ids[:n]):
            if nid in rel:
                total += 1.0 / math.log2(i + 2)
        return total

    actual = dcg(ranked_ids, relevant_ids, k)
    ideal_ranked = sorted(ranked_ids, key=lambda x: x in relevant_ids, reverse=True)
    ideal = dcg(ideal_ranked, relevant_ids, k)
    if ideal < 1e-9:
        return 0.0
    return actual / ideal


def mrr(ranked_ids: list[str], relevant_ids: set[str]) -> float:
    """Mean Reciprocal Rank — rank position of first relevant result."""
    for i, nid in enumerate(ranked_ids):
        if nid in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0


def recall_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    """Fraction of relevant items found in top-k results."""
    if not relevant_ids:
        return 1.0
    found = sum(1 for nid in ranked_ids[:k] if nid in relevant_ids)
    return found / len(relevant_ids)


def precision_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    """Fraction of top-k results that are relevant."""
    top_k = ranked_ids[:k]
    if not top_k:
        return 0.0
    found = sum(1 for nid in top_k if nid in relevant_ids)
    return found / len(top_k)


def average_precision(ranked_ids: list[str], relevant_ids: set[str]) -> float:
    """Average precision across all recall levels."""
    if not relevant_ids:
        return 1.0
    total = 0.0
    hits = 0
    for i, nid in enumerate(ranked_ids):
        if nid in relevant_ids:
            hits += 1
            total += hits / (i + 1)
    if hits == 0:
        return 0.0
    return total / len(relevant_ids)


def f1_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    """F1 score at rank k (harmonic mean of precision and recall)."""
    p = precision_at_k(ranked_ids, relevant_ids, k)
    r = recall_at_k(ranked_ids, relevant_ids, k)
    if p + r < 1e-9:
        return 0.0
    return 2 * p * r / (p + r)


def compute_suite(
    ranked_ids: list[str],
    relevant_ids: set[str],
    latency_ms: float,
) -> MetricSuite:
    """Compute all metrics for a single query."""
    return MetricSuite(
        ndcg_at_5=ndcg_at_k(ranked_ids, relevant_ids, 5),
        ndcg_at_10=ndcg_at_k(ranked_ids, relevant_ids, 10),
        mrr=mrr(ranked_ids, relevant_ids),
        recall_at_5=recall_at_k(ranked_ids, relevant_ids, 5),
        recall_at_10=recall_at_k(ranked_ids, relevant_ids, 10),
        precision_at_5=precision_at_k(ranked_ids, relevant_ids, 5),
        precision_at_10=precision_at_k(ranked_ids, relevant_ids, 10),
        map_score=average_precision(ranked_ids, relevant_ids),
        f1_at_10=f1_at_k(ranked_ids, relevant_ids, 10),
        latency_ms=latency_ms,
        result_count=len(ranked_ids),
    )
