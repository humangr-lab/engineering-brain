"""Tests for benchmark metrics."""

from __future__ import annotations

from benchmarks.metrics import (
    MetricSuite,
    average_precision,
    compute_suite,
    f1_at_k,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


class TestNDCG:
    def test_perfect_ranking(self):
        ranked = ["a", "b", "c", "d", "e"]
        relevant = {"a", "b", "c"}
        assert abs(ndcg_at_k(ranked, relevant, 5) - 1.0) < 1e-6

    def test_no_relevant(self):
        assert ndcg_at_k(["x", "y", "z"], {"a", "b"}, 3) == 0.0

    def test_empty_results(self):
        assert ndcg_at_k([], {"a"}, 10) == 0.0

    def test_partial_match(self):
        ranked = ["x", "a", "y", "b"]
        relevant = {"a", "b"}
        score = ndcg_at_k(ranked, relevant, 4)
        assert 0.0 < score < 1.0

    def test_unretrieved_relevant_lowers_score(self):
        """Finding 1 of 3 relevant items at rank 1 should NOT be NDCG=1.0.

        The old buggy IDCG only considered relevant items that appeared in
        ranked_ids, inflating the score. The correct IDCG considers all
        relevant items regardless of retrieval.
        """
        ranked = ["a", "x"]
        relevant = {"a", "b", "c"}
        score = ndcg_at_k(ranked, relevant, 2)
        # Correct: DCG=1/log2(2)=1.0, IDCG=1/log2(2)+1/log2(3)=1.631
        # So NDCG ≈ 0.613, definitely < 0.7
        assert score < 0.7
        assert score > 0.5  # But still positive — we did find one


class TestMRR:
    def test_first_relevant(self):
        assert mrr(["a", "b"], {"a"}) == 1.0

    def test_second_relevant(self):
        assert mrr(["b", "a", "c"], {"a"}) == 0.5

    def test_no_relevant(self):
        assert mrr(["x", "y", "z"], {"a"}) == 0.0


class TestRecall:
    def test_full_recall(self):
        assert recall_at_k(["a", "b", "c"], {"a", "b"}, 3) == 1.0

    def test_partial_recall(self):
        assert abs(recall_at_k(["a", "x", "b", "c", "d"], {"a", "b", "c", "d"}, 3) - 0.5) < 1e-6

    def test_empty_relevant(self):
        assert recall_at_k(["a", "b"], set(), 2) == 1.0


class TestPrecision:
    def test_full_precision(self):
        assert precision_at_k(["a", "b"], {"a", "b", "c"}, 2) == 1.0

    def test_half_precision(self):
        assert precision_at_k(["a", "x"], {"a"}, 2) == 0.5

    def test_empty_results(self):
        assert precision_at_k([], {"a"}, 5) == 0.0


class TestAveragePrecision:
    def test_perfect(self):
        assert abs(average_precision(["a", "b", "c"], {"a", "b", "c"}) - 1.0) < 1e-6

    def test_no_relevant(self):
        assert average_precision(["x", "y"], {"a"}) == 0.0

    def test_empty_relevant(self):
        assert average_precision(["a", "b"], set()) == 1.0


class TestF1:
    def test_perfect_f1(self):
        ranked = ["a", "b"]
        relevant = {"a", "b"}
        assert abs(f1_at_k(ranked, relevant, 2) - 1.0) < 1e-6

    def test_zero_f1(self):
        assert f1_at_k(["x", "y"], {"a", "b"}, 2) == 0.0


class TestComputeSuite:
    def test_returns_metric_suite(self):
        suite = compute_suite(["a", "b", "c"], {"a", "b"}, latency_ms=42.0)
        assert isinstance(suite, MetricSuite)
        assert suite.latency_ms == 42.0
        assert suite.result_count == 3
        assert 0.0 <= suite.ndcg_at_10 <= 1.0
        assert 0.0 <= suite.mrr <= 1.0
