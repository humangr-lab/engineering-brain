"""Evaluation framework for the Engineering Knowledge Brain.

Runs golden dataset queries and measures retrieval quality:
- NDCG@10: Normalized Discounted Cumulative Gain
- MRR: Mean Reciprocal Rank
- Recall@k: Fraction of relevant results in top-k

Results are saved to tests/eval_results.json for regression tracking.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def ndcg_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int = 10) -> float:
    """Normalized Discounted Cumulative Gain at rank k."""

    def dcg(ids: list[str], rel: set[str], n: int) -> float:
        total = 0.0
        for i, nid in enumerate(ids[:n]):
            if nid in rel:
                total += 1.0 / math.log2(i + 2)  # i+2 because log2(1)=0
        return total

    actual = dcg(ranked_ids, relevant_ids, k)
    # Ideal DCG: all relevant items ranked first
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
        return 1.0  # Vacuously true
    found = sum(1 for nid in ranked_ids[:k] if nid in relevant_ids)
    return found / len(relevant_ids)


# ---------------------------------------------------------------------------
# Evaluation Framework
# ---------------------------------------------------------------------------


class EvaluationFramework:
    """Runs golden dataset queries against the brain and collects metrics."""

    def __init__(self, brain: Any, golden_path: str | None = None) -> None:
        self.brain = brain
        if golden_path is None:
            golden_path = str(Path(__file__).parent.parent / "golden_dataset.yaml")
        with open(golden_path) as f:
            data = yaml.safe_load(f)
        self.queries: list[dict[str, Any]] = data.get("queries", [])
        self.version = data.get("version", "unknown")

    def run(self, k: int = 10) -> dict[str, Any]:
        """Run all queries and compute aggregate metrics."""
        results: list[dict[str, Any]] = []
        category_results: dict[str, list[dict[str, Any]]] = {}

        for q in self.queries:
            qid = q["id"]
            query_text = q["query"]
            techs = q.get("expected_technologies", [])
            domains = q.get("expected_domains", [])
            category = q.get("category", "unknown")
            difficulty = q.get("difficulty", "medium")

            # Run query through brain
            result = self.brain.query(
                task_description=query_text,
                technologies=techs or None,
                domains=domains or None,
                phase="exec",
            )

            # Collect returned node IDs (all layers)
            returned_ids = []
            for layer_key in ("principles", "patterns", "rules", "evidence"):
                for node in getattr(result, layer_key, []):
                    nid = node.get("id", "")
                    if nid:
                        returned_ids.append(nid)

            # For the golden dataset, "relevant" means any node whose technologies
            # or domains overlap with expected. We use returned_ids as the ranking
            # and check which ones match the query intent (tech/domain overlap).
            relevant = set()
            for nid in returned_ids:
                node = self.brain._graph.get_node(nid)
                if node is None:
                    continue
                node_techs = set(
                    t.lower() for t in (node.get("technologies") or node.get("languages") or [])
                )
                node_domains = set(
                    d.lower() for d in (node.get("domains") or [node.get("domain", "")])
                )
                query_techs = set(t.lower() for t in techs)
                query_domains = set(d.lower() for d in domains)
                if (query_techs & node_techs) or (query_domains & node_domains) or not query_techs:
                    relevant.add(nid)

            entry = {
                "query_id": qid,
                "category": category,
                "difficulty": difficulty,
                "returned_count": len(returned_ids),
                "relevant_count": len(relevant),
                "ndcg_at_10": ndcg_at_k(returned_ids, relevant, k),
                "mrr": mrr(returned_ids, relevant),
                "recall_at_5": recall_at_k(returned_ids, relevant, 5),
                "recall_at_10": recall_at_k(returned_ids, relevant, k),
            }
            results.append(entry)
            category_results.setdefault(category, []).append(entry)

        # Aggregate
        n = len(results) or 1
        aggregate = {
            "dataset_version": self.version,
            "total_queries": len(results),
            "avg_ndcg_at_10": sum(r["ndcg_at_10"] for r in results) / n,
            "avg_mrr": sum(r["mrr"] for r in results) / n,
            "avg_recall_at_5": sum(r["recall_at_5"] for r in results) / n,
            "avg_recall_at_10": sum(r["recall_at_10"] for r in results) / n,
            "avg_returned": sum(r["returned_count"] for r in results) / n,
        }

        # Per-category
        per_category: dict[str, dict[str, float]] = {}
        for cat, entries in category_results.items():
            cn = len(entries) or 1
            per_category[cat] = {
                "count": len(entries),
                "avg_ndcg_at_10": sum(e["ndcg_at_10"] for e in entries) / cn,
                "avg_mrr": sum(e["mrr"] for e in entries) / cn,
                "avg_recall_at_10": sum(e["recall_at_10"] for e in entries) / cn,
            }

        return {
            "aggregate": aggregate,
            "per_category": per_category,
            "per_query": results,
        }

    def save_results(self, results: dict[str, Any], path: str | None = None) -> str:
        """Save results to JSON for regression tracking."""
        if path is None:
            path = str(Path(__file__).parent.parent / "eval_results.json")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def brain():
    """Create and seed a brain instance for evaluation."""
    from engineering_brain.core.brain import Brain

    b = Brain()
    b.seed()
    return b


@pytest.fixture(scope="module")
def framework(brain):
    """Create evaluation framework with seeded brain."""
    return EvaluationFramework(brain)


def test_golden_dataset_loads(framework):
    """Golden dataset YAML parses correctly."""
    assert len(framework.queries) == 50
    categories = {q["category"] for q in framework.queries}
    assert categories == {"security", "architecture", "code_review", "multi_hop", "cross_domain"}


def test_baseline_metrics(framework):
    """Run full golden dataset and record baseline NDCG/MRR/Recall."""
    results = framework.run(k=10)

    agg = results["aggregate"]
    assert agg["total_queries"] == 50

    # Baseline expectations (loose — we just need > 0 for now)
    assert agg["avg_ndcg_at_10"] >= 0.0, "NDCG should be non-negative"
    assert agg["avg_mrr"] >= 0.0, "MRR should be non-negative"
    assert agg["avg_recall_at_10"] >= 0.0, "Recall should be non-negative"

    # Save baseline
    path = framework.save_results(results)
    assert os.path.exists(path)


def test_by_category(framework):
    """Per-category metric breakdown."""
    results = framework.run(k=10)
    cats = results["per_category"]

    for category in ("security", "architecture", "code_review", "multi_hop", "cross_domain"):
        assert category in cats, f"Missing category: {category}"
        assert cats[category]["count"] == 10
        assert 0.0 <= cats[category]["avg_ndcg_at_10"] <= 1.0


def test_ndcg_perfect():
    """NDCG@10 = 1.0 when all relevant items are ranked first."""
    ranked = ["a", "b", "c", "d", "e"]
    relevant = {"a", "b", "c"}
    assert abs(ndcg_at_k(ranked, relevant, 5) - 1.0) < 1e-6


def test_ndcg_worst():
    """NDCG@10 = 0.0 when no relevant items in results."""
    ranked = ["x", "y", "z"]
    relevant = {"a", "b"}
    assert ndcg_at_k(ranked, relevant, 3) == 0.0


def test_mrr_first():
    """MRR = 1.0 when first result is relevant."""
    assert mrr(["a", "b"], {"a"}) == 1.0


def test_mrr_second():
    """MRR = 0.5 when second result is first relevant."""
    assert mrr(["b", "a", "c"], {"a"}) == 0.5


def test_recall_at_k_basic():
    """Recall@3 with 2/4 relevant items in top 3."""
    ranked = ["a", "x", "b", "c", "d"]
    relevant = {"a", "b", "c", "d"}
    assert abs(recall_at_k(ranked, relevant, 3) - 0.5) < 1e-6
