"""Tests for CBF fusion — Cumulative Belief Fusion operators."""

from __future__ import annotations

import pytest

from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.fusion import cbf, multi_source_cbf


# --- CBF Pairwise ---


class TestCBF:
    def test_uncertainty_decreases(self):
        """Core CBF invariant: u_fused < min(u_A, u_B) for non-dogmatic."""
        a = OpinionTuple(b=0.6, d=0.0, u=0.4, a=0.5)
        b = OpinionTuple(b=0.7, d=0.0, u=0.3, a=0.5)
        fused = cbf(a, b)
        assert fused.u < min(a.u, b.u)

    def test_mass_conservation(self):
        """b + d + u = 1 after fusion."""
        a = OpinionTuple(b=0.5, d=0.1, u=0.4, a=0.5)
        b = OpinionTuple(b=0.3, d=0.2, u=0.5, a=0.5)
        fused = cbf(a, b)
        assert abs(fused.b + fused.d + fused.u - 1.0) < 1e-9

    def test_vacuous_is_identity(self):
        """Fusing with vacuous opinion should return ~the other opinion."""
        a = OpinionTuple(b=0.7, d=0.1, u=0.2, a=0.5)
        v = OpinionTuple.vacuous()
        fused = cbf(a, v)
        assert fused.b == pytest.approx(a.b, abs=1e-6)
        assert fused.d == pytest.approx(a.d, abs=1e-6)
        assert fused.u == pytest.approx(a.u, abs=1e-6)

    def test_vacuous_identity_reversed(self):
        """Order shouldn't matter for vacuous identity."""
        a = OpinionTuple(b=0.7, d=0.1, u=0.2, a=0.5)
        v = OpinionTuple.vacuous()
        fused = cbf(v, a)
        assert fused.b == pytest.approx(a.b, abs=1e-6)

    def test_dogmatic_a_dominates(self):
        """If A is dogmatic (u=0), result should be A."""
        a = OpinionTuple.dogmatic_belief()
        b = OpinionTuple(b=0.3, d=0.2, u=0.5, a=0.5)
        fused = cbf(a, b)
        assert fused.b == pytest.approx(1.0)
        assert fused.u == pytest.approx(0.0)

    def test_dogmatic_b_dominates(self):
        """If B is dogmatic (u=0), result should be B."""
        a = OpinionTuple(b=0.3, d=0.2, u=0.5, a=0.5)
        b = OpinionTuple.dogmatic_disbelief()
        fused = cbf(a, b)
        assert fused.b == pytest.approx(0.0)
        assert fused.d == pytest.approx(1.0)

    def test_both_dogmatic_conflicting_returns_uncertainty(self):
        """Both dogmatic + conflicting: return maximum uncertainty (H14 fix)."""
        a = OpinionTuple.dogmatic_belief()
        b = OpinionTuple.dogmatic_disbelief()
        fused = cbf(a, b)
        # conflict = 1.0*1.0 + 0.0*0.0 = 1.0 > 0.5 → max uncertainty
        assert fused.b == pytest.approx(0.0)
        assert fused.d == pytest.approx(0.0)
        assert fused.u == pytest.approx(1.0)
        assert fused.a == pytest.approx(0.5)

    def test_both_dogmatic_agreeing_averages(self):
        """Both dogmatic + agreeing: safe to average (H14 low-conflict path)."""
        a = OpinionTuple(b=0.9, d=0.1, u=0.0, a=0.5)
        b = OpinionTuple(b=0.8, d=0.2, u=0.0, a=0.5)
        fused = cbf(a, b)
        # conflict = 0.9*0.2 + 0.1*0.8 = 0.26 < 0.5 → average
        assert fused.b == pytest.approx(0.85)
        assert fused.d == pytest.approx(0.15)
        assert fused.u == pytest.approx(0.0)

    def test_base_rate_averaged(self):
        a = OpinionTuple(b=0.5, d=0.0, u=0.5, a=0.3)
        b = OpinionTuple(b=0.5, d=0.0, u=0.5, a=0.7)
        fused = cbf(a, b)
        assert fused.a == pytest.approx(0.5)

    def test_symmetric(self):
        """CBF(A,B) ≈ CBF(B,A) for commutativity."""
        a = OpinionTuple(b=0.6, d=0.1, u=0.3, a=0.5)
        b = OpinionTuple(b=0.4, d=0.2, u=0.4, a=0.5)
        f1 = cbf(a, b)
        f2 = cbf(b, a)
        assert f1.b == pytest.approx(f2.b, abs=1e-9)
        assert f1.d == pytest.approx(f2.d, abs=1e-9)
        assert f1.u == pytest.approx(f2.u, abs=1e-9)

    def test_belief_increases_with_agreement(self):
        """Two agreeing sources → higher belief than either alone."""
        a = OpinionTuple(b=0.6, d=0.0, u=0.4, a=0.5)
        b = OpinionTuple(b=0.7, d=0.0, u=0.3, a=0.5)
        fused = cbf(a, b)
        assert fused.b > max(a.b, b.b)

    def test_disbelief_with_conflicting(self):
        """When sources disagree, both b and d > 0."""
        a = OpinionTuple(b=0.7, d=0.0, u=0.3, a=0.5)
        b = OpinionTuple(b=0.0, d=0.6, u=0.4, a=0.5)
        fused = cbf(a, b)
        assert fused.b > 0
        assert fused.d > 0
        assert fused.u < min(a.u, b.u)


# --- Multi-source CBF ---


class TestMultiSourceCBF:
    def test_empty_returns_vacuous(self):
        result = multi_source_cbf([])
        assert result.b == 0.0
        assert result.d == 0.0
        assert result.u == 1.0

    def test_single_opinion_identity(self):
        o = OpinionTuple(b=0.7, d=0.1, u=0.2, a=0.5)
        result = multi_source_cbf([o])
        assert result.b == pytest.approx(o.b)
        assert result.d == pytest.approx(o.d)
        assert result.u == pytest.approx(o.u)

    def test_monotonic_uncertainty_reduction(self):
        """Adding more agreeing sources reduces uncertainty monotonically."""
        source = OpinionTuple(b=0.6, d=0.0, u=0.4, a=0.5)
        prev_u = 1.0
        for n in range(1, 6):
            result = multi_source_cbf([source] * n)
            assert result.u < prev_u or (n == 1 and result.u == source.u)
            prev_u = result.u

    def test_n_sources_mass_conservation(self):
        sources = [
            OpinionTuple(b=0.5, d=0.1, u=0.4, a=0.5),
            OpinionTuple(b=0.6, d=0.0, u=0.4, a=0.5),
            OpinionTuple(b=0.7, d=0.1, u=0.2, a=0.5),
        ]
        result = multi_source_cbf(sources)
        assert abs(result.b + result.d + result.u - 1.0) < 1e-9

    def test_many_sources_drive_uncertainty_low(self):
        """10 agreeing sources → very low uncertainty."""
        sources = [OpinionTuple(b=0.6, d=0.0, u=0.4, a=0.5)] * 10
        result = multi_source_cbf(sources)
        assert result.u < 0.10
        assert result.b > 0.90
