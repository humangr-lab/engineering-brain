"""Cross-consistency test: OpinionTuple (Brain) ≡ Opinion (ESL) for same inputs.

Ensures the two independent implementations produce identical results,
preventing drift between the engineering_brain and pipeline_v2 systems.

Covers: projected_probability, CBF fusion, Dempster conflict, Murphy's averaging.
"""

from __future__ import annotations

import pytest

from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.fusion import cbf as brain_cbf
from engineering_brain.epistemic.conflict_resolution import (
    dempster_conflict as brain_dempster,
    murphy_weighted_average as brain_murphy,
)


# Common test pairs
_PAIRS = [
    (0.6, 0.1, 0.3, 0.5),
    (0.8, 0.0, 0.2, 0.7),
    (0.0, 0.0, 1.0, 0.5),
    (1.0, 0.0, 0.0, 0.5),
    (0.3, 0.3, 0.4, 0.5),
    (0.0, 0.9, 0.1, 0.5),
]


class TestCrossConsistency:
    """Verify Brain's OpinionTuple matches ESL's Opinion for same inputs."""

    def _try_import_esl(self):
        """Try to import ESL Opinion. Skip test if not available."""
        try:
            from pipeline_v2.knowledge.epistemic.opinion import Opinion
            from pipeline_v2.knowledge.epistemic.fusion import cumulative_belief_fusion
            return Opinion, cumulative_belief_fusion
        except ImportError:
            pytest.skip("pipeline_v2 ESL not available for cross-consistency test")

    def _try_import_esl_conflict(self):
        """Try to import ESL conflict resolution. Skip if not available."""
        try:
            from pipeline_v2.knowledge.epistemic.opinion import Opinion
            from pipeline_v2.knowledge.epistemic.conflict_resolution import (
                dempster_conflict,
                murphy_weighted_average,
            )
            return Opinion, dempster_conflict, murphy_weighted_average
        except ImportError:
            pytest.skip("pipeline_v2 ESL conflict resolution not available")

    def test_projected_probability_matches(self):
        Opinion, _ = self._try_import_esl()

        for b, d, u, a in _PAIRS:
            brain = OpinionTuple(b=b, d=d, u=u, a=a)
            esl = Opinion(b=b, d=d, u=u, a=a)
            brain_pp = brain.projected_probability
            esl_pp = esl.projected_probability
            assert brain_pp == pytest.approx(esl_pp, abs=1e-9), (
                f"PP mismatch for ({b},{d},{u},{a}): brain={brain_pp}, esl={esl_pp}"
            )

    def test_cbf_fusion_matches(self):
        _, esl_cbf = self._try_import_esl()
        from pipeline_v2.knowledge.epistemic.opinion import Opinion

        a = OpinionTuple(b=0.6, d=0.1, u=0.3, a=0.5)
        b = OpinionTuple(b=0.4, d=0.2, u=0.4, a=0.5)
        brain_fused = brain_cbf(a, b)

        esl_a = Opinion(b=0.6, d=0.1, u=0.3, a=0.5)
        esl_b = Opinion(b=0.4, d=0.2, u=0.4, a=0.5)
        esl_fused = esl_cbf(esl_a, esl_b)

        assert brain_fused.b == pytest.approx(esl_fused.b, abs=1e-6)
        assert brain_fused.d == pytest.approx(esl_fused.d, abs=1e-6)
        assert brain_fused.u == pytest.approx(esl_fused.u, abs=1e-6)

    # =================================================================
    # NEW: Dempster conflict cross-consistency
    # =================================================================

    def test_dempster_conflict_agreeing_opinions(self):
        """K for two agreeing opinions should match between implementations."""
        Opinion, esl_dempster, _ = self._try_import_esl_conflict()

        a_vals = (0.7, 0.1, 0.2, 0.5)
        b_vals = (0.6, 0.1, 0.3, 0.5)

        brain_k = brain_dempster(
            OpinionTuple(b=a_vals[0], d=a_vals[1], u=a_vals[2], a=a_vals[3]),
            OpinionTuple(b=b_vals[0], d=b_vals[1], u=b_vals[2], a=b_vals[3]),
        )
        esl_k = esl_dempster(
            Opinion(b=a_vals[0], d=a_vals[1], u=a_vals[2], a=a_vals[3]),
            Opinion(b=b_vals[0], d=b_vals[1], u=b_vals[2], a=b_vals[3]),
        )
        assert brain_k == pytest.approx(esl_k, abs=1e-9)

    def test_dempster_conflict_contradicting_opinions(self):
        """K for contradicting opinions should match between implementations."""
        Opinion, esl_dempster, _ = self._try_import_esl_conflict()

        a_vals = (0.9, 0.0, 0.1, 0.5)
        b_vals = (0.0, 0.9, 0.1, 0.5)

        brain_k = brain_dempster(
            OpinionTuple(b=a_vals[0], d=a_vals[1], u=a_vals[2], a=a_vals[3]),
            OpinionTuple(b=b_vals[0], d=b_vals[1], u=b_vals[2], a=b_vals[3]),
        )
        esl_k = esl_dempster(
            Opinion(b=a_vals[0], d=a_vals[1], u=a_vals[2], a=a_vals[3]),
            Opinion(b=b_vals[0], d=b_vals[1], u=b_vals[2], a=b_vals[3]),
        )
        assert brain_k == pytest.approx(esl_k, abs=1e-9)
        assert brain_k > 0.8  # high conflict

    def test_dempster_conflict_symmetric(self):
        """K(A,B) == K(B,A) in both implementations."""
        Opinion, esl_dempster, _ = self._try_import_esl_conflict()

        a_vals = (0.7, 0.1, 0.2, 0.5)
        b_vals = (0.2, 0.6, 0.2, 0.5)

        brain_k_ab = brain_dempster(
            OpinionTuple(b=a_vals[0], d=a_vals[1], u=a_vals[2], a=a_vals[3]),
            OpinionTuple(b=b_vals[0], d=b_vals[1], u=b_vals[2], a=b_vals[3]),
        )
        brain_k_ba = brain_dempster(
            OpinionTuple(b=b_vals[0], d=b_vals[1], u=b_vals[2], a=b_vals[3]),
            OpinionTuple(b=a_vals[0], d=a_vals[1], u=a_vals[2], a=a_vals[3]),
        )
        esl_k = esl_dempster(
            Opinion(b=a_vals[0], d=a_vals[1], u=a_vals[2], a=a_vals[3]),
            Opinion(b=b_vals[0], d=b_vals[1], u=b_vals[2], a=b_vals[3]),
        )
        assert brain_k_ab == pytest.approx(brain_k_ba, abs=1e-9)
        assert brain_k_ab == pytest.approx(esl_k, abs=1e-9)

    # =================================================================
    # NEW: Murphy's weighted averaging cross-consistency
    # =================================================================

    def test_murphy_two_opinions(self):
        """Murphy's averaging with 2 opinions should match both implementations."""
        Opinion, _, esl_murphy = self._try_import_esl_conflict()

        ops = [(0.7, 0.1, 0.2, 0.5), (0.3, 0.5, 0.2, 0.5)]

        brain_result = brain_murphy([
            OpinionTuple(b=o[0], d=o[1], u=o[2], a=o[3]) for o in ops
        ])
        esl_result = esl_murphy([
            Opinion(b=o[0], d=o[1], u=o[2], a=o[3]) for o in ops
        ])

        assert brain_result.b == pytest.approx(esl_result.b, abs=1e-6)
        assert brain_result.d == pytest.approx(esl_result.d, abs=1e-6)
        assert brain_result.u == pytest.approx(esl_result.u, abs=1e-6)

    def test_murphy_three_opinions(self):
        """Murphy's averaging with 3 opinions should match."""
        Opinion, _, esl_murphy = self._try_import_esl_conflict()

        ops = [
            (0.7, 0.1, 0.2, 0.5),
            (0.3, 0.5, 0.2, 0.5),
            (0.5, 0.2, 0.3, 0.5),
        ]

        brain_result = brain_murphy([
            OpinionTuple(b=o[0], d=o[1], u=o[2], a=o[3]) for o in ops
        ])
        esl_result = esl_murphy([
            Opinion(b=o[0], d=o[1], u=o[2], a=o[3]) for o in ops
        ])

        assert brain_result.b == pytest.approx(esl_result.b, abs=1e-6)
        assert brain_result.d == pytest.approx(esl_result.d, abs=1e-6)
        assert brain_result.u == pytest.approx(esl_result.u, abs=1e-6)

    def test_murphy_high_conflict(self):
        """Murphy's robustness under high conflict should match."""
        Opinion, _, esl_murphy = self._try_import_esl_conflict()

        ops = [(0.9, 0.0, 0.1, 0.5), (0.0, 0.9, 0.1, 0.5)]

        brain_result = brain_murphy([
            OpinionTuple(b=o[0], d=o[1], u=o[2], a=o[3]) for o in ops
        ])
        esl_result = esl_murphy([
            Opinion(b=o[0], d=o[1], u=o[2], a=o[3]) for o in ops
        ])

        assert brain_result.b == pytest.approx(esl_result.b, abs=1e-6)
        assert brain_result.d == pytest.approx(esl_result.d, abs=1e-6)
        # Mass conservation in both
        assert abs(brain_result.b + brain_result.d + brain_result.u - 1.0) < 1e-9
        assert abs(esl_result.b + esl_result.d + esl_result.u - 1.0) < 1e-9

    def test_murphy_with_custom_weights(self):
        """Murphy's with custom weights should match."""
        Opinion, _, esl_murphy = self._try_import_esl_conflict()

        ops = [(0.8, 0.0, 0.2, 0.5), (0.2, 0.6, 0.2, 0.5)]
        weights = [0.7, 0.3]

        brain_result = brain_murphy(
            [OpinionTuple(b=o[0], d=o[1], u=o[2], a=o[3]) for o in ops],
            weights,
        )
        esl_result = esl_murphy(
            [Opinion(b=o[0], d=o[1], u=o[2], a=o[3]) for o in ops],
            weights,
        )

        assert brain_result.b == pytest.approx(esl_result.b, abs=1e-6)
        assert brain_result.d == pytest.approx(esl_result.d, abs=1e-6)
        assert brain_result.u == pytest.approx(esl_result.u, abs=1e-6)
