"""Tests for the disbelief axis — polarity="negative" produces d > 0."""

from __future__ import annotations

import pytest

from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.fusion import cbf
from engineering_brain.epistemic.source_trust import source_to_opinion


class TestSourceToOpinionPolarity:
    def test_positive_polarity_default(self):
        """Default polarity is positive: b > 0, d = 0."""
        op = source_to_opinion({"source_type": "official_docs"})
        assert op.b > 0.0
        assert op.d == 0.0
        assert abs(op.b + op.d + op.u - 1.0) < 1e-9

    def test_positive_polarity_explicit(self):
        """Explicit positive polarity: same as default."""
        op = source_to_opinion({"source_type": "official_docs"}, polarity="positive")
        assert op.b > 0.0
        assert op.d == 0.0

    def test_negative_polarity_produces_disbelief(self):
        """polarity='negative' produces d > 0, b = 0."""
        op = source_to_opinion({"source_type": "official_docs"}, polarity="negative")
        assert op.b == 0.0
        assert op.d > 0.0
        assert abs(op.b + op.d + op.u - 1.0) < 1e-9

    def test_negative_polarity_d_matches_positive_b(self):
        """Negative polarity should have d = positive's b (trust swapped)."""
        pos = source_to_opinion({"source_type": "official_docs"}, polarity="positive")
        neg = source_to_opinion({"source_type": "official_docs"}, polarity="negative")
        assert neg.d == pytest.approx(pos.b, abs=1e-9)
        assert neg.u == pytest.approx(pos.u, abs=1e-9)

    def test_negative_stackoverflow(self):
        """Negative polarity works for StackOverflow sources too."""
        source = {"source_type": "stackoverflow", "vote_count": 50, "is_accepted_answer": True}
        neg = source_to_opinion(source, polarity="negative")
        assert neg.b == 0.0
        assert neg.d > 0.0

    def test_negative_cve(self):
        """Negative polarity works for CVE sources."""
        source = {"source_type": "security_cve", "cvss_score": 9.0}
        neg = source_to_opinion(source, polarity="negative")
        assert neg.b == 0.0
        assert neg.d > 0.0


class TestCBFWithDisbelief:
    def test_cbf_with_negative_evidence_increases_d(self):
        """CBF-fusing positive opinion with negative evidence should increase d."""
        current = OpinionTuple(b=0.7, d=0.0, u=0.3, a=0.5)
        negative = OpinionTuple(b=0.0, d=0.5, u=0.5, a=0.5)
        fused = cbf(current, negative)
        assert fused.d > current.d
        assert abs(fused.b + fused.d + fused.u - 1.0) < 1e-9

    def test_repeated_negative_evidence_drives_d_up(self):
        """Repeated negative evidence should progressively increase d."""
        opinion = OpinionTuple(b=0.7, d=0.0, u=0.3, a=0.5)
        negative = OpinionTuple(b=0.0, d=0.6, u=0.4, a=0.5)

        for _ in range(5):
            opinion = cbf(opinion, negative)

        assert opinion.d > 0.3  # d significantly increased
        assert opinion.b < 0.5  # b significantly decreased
        assert abs(opinion.b + opinion.d + opinion.u - 1.0) < 1e-9

    def test_mixed_evidence_produces_nonzero_b_and_d(self):
        """Fusing positive and negative evidence should produce both b > 0 and d > 0."""
        positive = OpinionTuple(b=0.6, d=0.0, u=0.4, a=0.5)
        negative = OpinionTuple(b=0.0, d=0.5, u=0.5, a=0.5)
        fused = cbf(positive, negative)
        assert fused.b > 0.0
        assert fused.d > 0.0
        assert abs(fused.b + fused.d + fused.u - 1.0) < 1e-9

    def test_backward_compat_default_polarity(self):
        """Default source_to_opinion behavior unchanged (b > 0, d = 0)."""
        for st in ["official_docs", "stackoverflow", "mdn", "owasp"]:
            op = source_to_opinion({"source_type": st})
            assert op.d == 0.0
            assert op.b > 0.0
