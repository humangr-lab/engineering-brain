"""Tests for Dempster conflict detection and Murphy's weighted averaging."""

from __future__ import annotations

import pytest

from engineering_brain.epistemic.conflict_resolution import (
    ConflictSeverity,
    classify_conflict,
    dempster_conflict,
    murphy_weighted_average,
)
from engineering_brain.epistemic.opinion import OpinionTuple


class TestDempsterConflict:
    def test_agreeing_opinions_zero_conflict(self):
        a = OpinionTuple(b=0.8, d=0.0, u=0.2, a=0.5)
        b = OpinionTuple(b=0.7, d=0.0, u=0.3, a=0.5)
        assert dempster_conflict(a, b) == pytest.approx(0.0, abs=1e-9)

    def test_total_contradiction(self):
        a = OpinionTuple(b=1.0, d=0.0, u=0.0, a=0.5)
        b = OpinionTuple(b=0.0, d=1.0, u=0.0, a=0.5)
        assert dempster_conflict(a, b) == pytest.approx(1.0, abs=1e-9)

    def test_partial_conflict(self):
        a = OpinionTuple(b=0.6, d=0.1, u=0.3, a=0.5)
        b = OpinionTuple(b=0.1, d=0.6, u=0.3, a=0.5)
        k = dempster_conflict(a, b)
        assert 0.0 < k < 1.0
        # K = 0.6*0.6 + 0.1*0.1 = 0.36 + 0.01 = 0.37
        assert k == pytest.approx(0.37, abs=1e-6)

    def test_symmetric(self):
        a = OpinionTuple(b=0.5, d=0.2, u=0.3, a=0.5)
        b = OpinionTuple(b=0.3, d=0.4, u=0.3, a=0.5)
        assert dempster_conflict(a, b) == pytest.approx(dempster_conflict(b, a), abs=1e-9)

    def test_vacuous_gives_zero(self):
        a = OpinionTuple(b=0.8, d=0.1, u=0.1, a=0.5)
        b = OpinionTuple.vacuous()
        assert dempster_conflict(a, b) == pytest.approx(0.0, abs=1e-9)


class TestClassifyConflict:
    def test_none(self):
        assert classify_conflict(0.0) == ConflictSeverity.NONE
        assert classify_conflict(0.29) == ConflictSeverity.NONE

    def test_low(self):
        assert classify_conflict(0.3) == ConflictSeverity.LOW
        assert classify_conflict(0.49) == ConflictSeverity.LOW

    def test_moderate(self):
        assert classify_conflict(0.5) == ConflictSeverity.MODERATE
        assert classify_conflict(0.69) == ConflictSeverity.MODERATE

    def test_high(self):
        assert classify_conflict(0.7) == ConflictSeverity.HIGH
        assert classify_conflict(0.89) == ConflictSeverity.HIGH

    def test_extreme(self):
        assert classify_conflict(0.9) == ConflictSeverity.EXTREME
        assert classify_conflict(1.0) == ConflictSeverity.EXTREME


class TestMurphyWeightedAverage:
    def test_empty_returns_vacuous(self):
        result = murphy_weighted_average([])
        assert result.u == pytest.approx(1.0, abs=1e-9)

    def test_single_returns_self(self):
        op = OpinionTuple(b=0.7, d=0.1, u=0.2, a=0.5)
        result = murphy_weighted_average([op])
        assert result.b == pytest.approx(op.b, abs=1e-9)

    def test_mass_conservation(self):
        ops = [
            OpinionTuple(b=0.8, d=0.1, u=0.1, a=0.5),
            OpinionTuple(b=0.1, d=0.7, u=0.2, a=0.5),
        ]
        result = murphy_weighted_average(ops)
        total = result.b + result.d + result.u
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_robust_under_high_conflict(self):
        """Murphy should produce reasonable result even with K > 0.7."""
        a = OpinionTuple(b=0.9, d=0.0, u=0.1, a=0.5)
        b = OpinionTuple(b=0.0, d=0.8, u=0.2, a=0.5)
        k = dempster_conflict(a, b)
        assert k > 0.7  # high conflict

        result = murphy_weighted_average([a, b])
        assert 0.0 < result.b < 1.0
        assert 0.0 < result.d < 1.0
        total = result.b + result.d + result.u
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_with_weights(self):
        a = OpinionTuple(b=0.9, d=0.0, u=0.1, a=0.5)
        b = OpinionTuple(b=0.1, d=0.8, u=0.1, a=0.5)
        # Heavy weight on a → result should favor a
        result = murphy_weighted_average([a, b], weights=[0.9, 0.1])
        assert result.b > result.d

    def test_equal_weights_default(self):
        ops = [
            OpinionTuple(b=0.6, d=0.1, u=0.3, a=0.5),
            OpinionTuple(b=0.4, d=0.2, u=0.4, a=0.5),
        ]
        result_default = murphy_weighted_average(ops)
        result_explicit = murphy_weighted_average(ops, weights=[0.5, 0.5])
        assert result_default.b == pytest.approx(result_explicit.b, abs=1e-6)
