"""Tests for OpinionTuple — Subjective Logic opinion dataclass."""

from __future__ import annotations

import math
import pytest

from engineering_brain.epistemic.opinion import OpinionTuple


# --- Construction & Validation ---


class TestConstruction:
    def test_basic_creation(self):
        o = OpinionTuple(b=0.6, d=0.1, u=0.3, a=0.5)
        assert o.b == 0.6
        assert o.d == 0.1
        assert o.u == 0.3
        assert o.a == 0.5

    def test_default_base_rate(self):
        o = OpinionTuple(b=0.5, d=0.2, u=0.3)
        assert o.a == 0.5

    def test_frozen(self):
        o = OpinionTuple(b=0.5, d=0.2, u=0.3)
        with pytest.raises(AttributeError):
            o.b = 0.9  # type: ignore[misc]

    def test_bdu_must_sum_to_one(self):
        with pytest.raises(ValueError, match="must equal 1.0"):
            OpinionTuple(b=0.5, d=0.5, u=0.5)

    def test_bdu_tolerance(self):
        # Within 1e-6 tolerance — should not raise
        o = OpinionTuple(b=0.3333333, d=0.3333333, u=0.3333334)
        assert abs(o.b + o.d + o.u - 1.0) < 1e-6

    def test_negative_value_rejected(self):
        with pytest.raises(ValueError, match="must be in"):
            OpinionTuple(b=-0.1, d=0.1, u=1.0)

    def test_value_above_one_rejected(self):
        with pytest.raises(ValueError, match="must be in"):
            OpinionTuple(b=1.1, d=0.0, u=0.0)

    def test_base_rate_bounds(self):
        with pytest.raises(ValueError, match="must be in"):
            OpinionTuple(b=0.5, d=0.0, u=0.5, a=1.5)

    def test_all_zero_rejected(self):
        with pytest.raises(ValueError, match="must equal 1.0"):
            OpinionTuple(b=0.0, d=0.0, u=0.0)


# --- Properties ---


class TestProperties:
    def test_projected_probability(self):
        o = OpinionTuple(b=0.6, d=0.1, u=0.3, a=0.5)
        assert o.projected_probability == pytest.approx(0.6 + 0.5 * 0.3)

    def test_projected_probability_vacuous(self):
        o = OpinionTuple.vacuous(a=0.7)
        assert o.projected_probability == pytest.approx(0.7)

    def test_projected_probability_dogmatic(self):
        o = OpinionTuple.dogmatic_belief()
        assert o.projected_probability == pytest.approx(1.0)

    def test_evidence_strength(self):
        o = OpinionTuple(b=0.6, d=0.1, u=0.3)
        assert o.evidence_strength == pytest.approx(0.7)

    def test_evidence_strength_vacuous(self):
        assert OpinionTuple.vacuous().evidence_strength == pytest.approx(0.0)

    def test_shannon_entropy_dogmatic(self):
        o = OpinionTuple.dogmatic_belief()
        assert o.shannon_entropy == pytest.approx(0.0)

    def test_shannon_entropy_vacuous(self):
        o = OpinionTuple.vacuous()
        assert o.shannon_entropy == pytest.approx(0.0)  # only u=1.0, -1*log2(1)=0

    def test_shannon_entropy_uniform(self):
        o = OpinionTuple(b=1 / 3, d=1 / 3, u=1 / 3)
        expected = -3 * (1 / 3) * math.log2(1 / 3)
        assert o.shannon_entropy == pytest.approx(expected, abs=1e-9)

    def test_to_confidence_equals_pp(self):
        o = OpinionTuple(b=0.8, d=0.05, u=0.15, a=0.6)
        assert o.to_confidence() == pytest.approx(o.projected_probability)


# --- Factory Methods ---


class TestFactories:
    def test_vacuous(self):
        v = OpinionTuple.vacuous()
        assert v.b == 0.0
        assert v.d == 0.0
        assert v.u == 1.0
        assert v.a == 0.5

    def test_vacuous_custom_a(self):
        v = OpinionTuple.vacuous(a=0.8)
        assert v.a == 0.8

    def test_dogmatic_belief(self):
        d = OpinionTuple.dogmatic_belief()
        assert d.b == 1.0
        assert d.d == 0.0
        assert d.u == 0.0

    def test_dogmatic_disbelief(self):
        d = OpinionTuple.dogmatic_disbelief()
        assert d.b == 0.0
        assert d.d == 1.0
        assert d.u == 0.0

    def test_from_confidence_default(self):
        o = OpinionTuple.from_confidence(0.8)
        # P(x) = b + a*u should ≈ 0.8
        assert o.projected_probability == pytest.approx(0.8, abs=0.05)
        assert abs(o.b + o.d + o.u - 1.0) < 1e-6

    def test_from_confidence_low(self):
        o = OpinionTuple.from_confidence(0.2, uncertainty=0.5)
        assert o.projected_probability == pytest.approx(0.2, abs=0.05)
        assert abs(o.b + o.d + o.u - 1.0) < 1e-6

    def test_from_confidence_zero_uncertainty(self):
        o = OpinionTuple.from_confidence(0.9, uncertainty=0.0)
        assert o.b == pytest.approx(0.9)
        assert o.u == pytest.approx(0.0)

    def test_from_confidence_full_uncertainty(self):
        o = OpinionTuple.from_confidence(0.5, uncertainty=1.0, a=0.5)
        # b = max(0, 0.5 - 0.5*1.0) = 0.0
        assert o.b == pytest.approx(0.0)
        assert o.u == pytest.approx(1.0)


# --- Serialization ---


class TestSerialization:
    def test_to_dict(self):
        o = OpinionTuple(b=0.6, d=0.1, u=0.3, a=0.7)
        d = o.to_dict()
        assert d == {
            "ep_b": 0.6,
            "ep_d": 0.1,
            "ep_u": 0.3,
            "ep_a": 0.7,
        }

    def test_to_dict_rounding(self):
        o = OpinionTuple(b=1 / 3, d=1 / 3, u=1 / 3, a=0.5)
        d = o.to_dict()
        assert all(isinstance(v, float) for v in d.values())
        # Rounded to 6 decimal places
        assert d["ep_b"] == round(1 / 3, 6)

    def test_from_dict_roundtrip(self):
        original = OpinionTuple(b=0.75, d=0.05, u=0.20, a=0.6)
        d = original.to_dict()
        restored = OpinionTuple.from_dict(d)
        assert restored.b == pytest.approx(original.b, abs=1e-5)
        assert restored.d == pytest.approx(original.d, abs=1e-5)
        assert restored.u == pytest.approx(original.u, abs=1e-5)
        assert restored.a == pytest.approx(original.a, abs=1e-5)

    def test_from_dict_renormalization(self):
        # Simulate float drift: sum > 1
        d = {"ep_b": 0.6001, "ep_d": 0.1001, "ep_u": 0.3001, "ep_a": 0.5}
        o = OpinionTuple.from_dict(d)
        assert abs(o.b + o.d + o.u - 1.0) < 1e-6

    def test_from_dict_missing_keys(self):
        d = {}  # all missing
        o = OpinionTuple.from_dict(d)
        assert o.b == 0.0
        assert o.d == 0.0
        assert o.u == 1.0
        assert o.a == 0.5
