"""Tests for Hawkes temporal decay engine."""

from __future__ import annotations

import pytest

from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.temporal import (
    LAYER_DECAY_PROFILES,
    HawkesDecayEngine,
    get_decay_engine,
)


class TestHawkesIntensity:
    def test_baseline_only_no_events(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        intensity = engine.compute_intensity(100.0, [])
        assert intensity == pytest.approx(0.001, abs=1e-9)

    def test_recent_event_increases_intensity(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        baseline = engine.compute_intensity(100.0, [])
        with_event = engine.compute_intensity(100.0, [99.0])
        assert with_event > baseline

    def test_old_event_has_less_effect(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        recent = engine.compute_intensity(100.0, [99.0])
        old = engine.compute_intensity(100.0, [50.0])
        assert recent > old

    def test_multiple_events_accumulate(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        one_event = engine.compute_intensity(100.0, [99.0])
        two_events = engine.compute_intensity(100.0, [98.0, 99.0])
        assert two_events > one_event


class TestTemporalFactor:
    def test_no_events_low_tau(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        # No events → tau should be low (only baseline)
        tau = engine.compute_temporal_factor(8640000, [])
        assert 0.0 < tau <= 1.0

    def test_recent_events_high_tau(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        now = 8640000  # 100 days in seconds
        events = [now - 86400, now - 3600]  # 1 day ago, 1 hour ago
        tau = engine.compute_temporal_factor(now, events)
        assert tau > 0.5

    def test_tau_bounded_0_1(self):
        engine = HawkesDecayEngine(mu=0.01, alpha=0.1, beta=0.05)
        tau = engine.compute_temporal_factor(1000000, [999999, 999998])
        assert 0.0 <= tau <= 1.0


class TestApplyDecay:
    def test_no_elapsed_time_no_change(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.8, d=0.1, u=0.1, a=0.5)
        result = engine.apply_decay(
            op, now_unix=1000, last_decay_unix=1000, event_timestamps_unix=[]
        )
        assert result.b == pytest.approx(op.b, abs=1e-9)

    def test_belief_decays_to_uncertainty(self):
        engine = HawkesDecayEngine(mu=0.01, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.8, d=0.1, u=0.1, a=0.5)
        # Decay over 365 days with no events
        now = 365 * 86400
        result = engine.apply_decay(op, now_unix=now, last_decay_unix=0, event_timestamps_unix=[])
        assert result.b < op.b  # belief decreased
        assert result.u > op.u  # uncertainty increased
        assert result.d < op.d  # disbelief also decayed

    def test_mass_conservation_after_decay(self):
        engine = HawkesDecayEngine(mu=0.005, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.6, d=0.2, u=0.2, a=0.5)
        result = engine.apply_decay(
            op, now_unix=10000000, last_decay_unix=0, event_timestamps_unix=[]
        )
        total = result.b + result.d + result.u
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_disbelief_also_decays(self):
        """Disbelief decays to uncertainty too — forgotten contradiction != proven truth."""
        engine = HawkesDecayEngine(mu=0.005, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.1, d=0.7, u=0.2, a=0.5)
        result = engine.apply_decay(
            op, now_unix=10000000, last_decay_unix=0, event_timestamps_unix=[]
        )
        assert result.d < op.d
        assert result.u > op.u

    def test_events_slow_decay(self):
        """Active reinforcement events should slow down decay."""
        engine = HawkesDecayEngine(mu=0.005, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.8, d=0.0, u=0.2, a=0.5)
        now = 100 * 86400

        # Without events
        no_events = engine.apply_decay(
            op, now_unix=now, last_decay_unix=0, event_timestamps_unix=[]
        )
        # With recent events
        events = [now - 86400 * i for i in range(1, 10)]
        with_events = engine.apply_decay(
            op, now_unix=now, last_decay_unix=0, event_timestamps_unix=events
        )

        assert with_events.b > no_events.b  # more belief preserved

    def test_backward_time_no_change(self):
        engine = HawkesDecayEngine(mu=0.01, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.8, d=0.0, u=0.2, a=0.5)
        result = engine.apply_decay(op, now_unix=100, last_decay_unix=200, event_timestamps_unix=[])
        assert result.b == pytest.approx(op.b, abs=1e-9)


class TestLayerDecayProfiles:
    def test_l0_never_decays(self):
        engine = LAYER_DECAY_PROFILES["L0"]
        op = OpinionTuple(b=0.95, d=0.0, u=0.05, a=0.9)
        result = engine.apply_decay(
            op, now_unix=100000000, last_decay_unix=0, event_timestamps_unix=[]
        )
        assert result.b == pytest.approx(op.b, abs=1e-9)

    def test_l5_decays_fast(self):
        engine = LAYER_DECAY_PROFILES["L5"]
        op = OpinionTuple(b=0.8, d=0.0, u=0.2, a=0.5)
        # 30 days
        result = engine.apply_decay(
            op, now_unix=30 * 86400, last_decay_unix=0, event_timestamps_unix=[]
        )
        assert result.b < op.b * 0.95  # significant decay

    def test_l3_moderate_decay(self):
        engine = LAYER_DECAY_PROFILES["L3"]
        op = OpinionTuple(b=0.8, d=0.0, u=0.2, a=0.5)
        # 180 days
        result = engine.apply_decay(
            op, now_unix=180 * 86400, last_decay_unix=0, event_timestamps_unix=[]
        )
        assert result.b < op.b  # some decay
        assert result.b > 0.1  # but not completely gone

    def test_deeper_layers_decay_slower(self):
        op = OpinionTuple(b=0.8, d=0.0, u=0.2, a=0.5)
        now = 365 * 86400  # 1 year

        l2 = LAYER_DECAY_PROFILES["L2"].apply_decay(op, now, 0, [])
        l3 = LAYER_DECAY_PROFILES["L3"].apply_decay(op, now, 0, [])
        l4 = LAYER_DECAY_PROFILES["L4"].apply_decay(op, now, 0, [])

        # L2 should preserve more belief than L3, L3 more than L4
        assert l2.b > l3.b > l4.b

    def test_get_decay_engine_default(self):
        engine = get_decay_engine("UNKNOWN")
        assert engine.mu == LAYER_DECAY_PROFILES["L3"].mu
