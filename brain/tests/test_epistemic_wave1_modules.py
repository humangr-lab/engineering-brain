"""Deep unit tests for Wave 1 epistemic modules — mathematical correctness,
invariants, and edge cases.

Complements the existing tests in:
- test_wave1_epistemic.py (basic happy paths)
- test_temporal_decay.py (HawkesDecayEngine basics)
- test_contradiction_detector.py (ContradictionDetector with graph)

This file focuses on:
1. bayesian_edges.py  -- Beta distribution math, decay curves, batch_update
2. contradiction_tensor.py -- ContradictionManager lifecycle, evidence, resolution
3. predictive_decay.py -- Knowledge type classification, staleness math, edge cases
4. temporal.py -- Hawkes intensity correctness, mass conservation edge cases
5. contradiction.py -- _node_to_opinion edge cases, moderate conflict path
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from engineering_brain.epistemic.bayesian_edges import (
    DEFAULT_HALF_LIFE,
    EDGE_DECAY_PROFILES,
    BayesianEdgeManager,
)
from engineering_brain.epistemic.contradiction_tensor import (
    ContradictionManager,
    ContradictionTensor,
)
from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.predictive_decay import (
    DECAY_PROFILES,
    STALE_THRESHOLD,
    PredictiveDecayEngine,
)
from engineering_brain.epistemic.temporal import (
    LAYER_DECAY_PROFILES,
    HawkesDecayEngine,
    get_decay_engine,
)

# ===========================================================================
# Section 1: BayesianEdgeManager — Beta Distribution Math & Edge Cases
# ===========================================================================


class TestBayesianEdgeBetaMath:
    """Verify mathematical correctness of Beta distribution operations."""

    @pytest.fixture
    def mgr(self):
        return BayesianEdgeManager()

    # --- Confidence = E[Beta(alpha, beta)] = alpha / (alpha + beta) ---

    def test_confidence_equals_expected_value(self, mgr):
        """Confidence must equal the expected value of Beta(alpha, beta)."""
        cases = [
            (1.0, 1.0, 0.5),
            (2.0, 1.0, 2.0 / 3.0),
            (1.0, 2.0, 1.0 / 3.0),
            (10.0, 10.0, 0.5),
            (100.0, 1.0, 100.0 / 101.0),
        ]
        for alpha, beta, expected in cases:
            edge = {"edge_alpha": alpha, "edge_beta": beta}
            conf = mgr.get_edge_confidence(edge)
            assert conf == pytest.approx(expected, abs=1e-9), (
                f"Beta({alpha},{beta}) expected E={expected}, got {conf}"
            )

    def test_uncertainty_formula_matches_beta_std(self, mgr):
        """Uncertainty must equal sigma = sqrt(alpha*beta / (total^2 * (total+1)))."""
        alpha, beta = 5.0, 3.0
        total = alpha + beta
        expected_var = (alpha * beta) / (total * total * (total + 1))
        expected_sigma = math.sqrt(expected_var)

        edge = {"edge_alpha": alpha, "edge_beta": beta}
        assert mgr.get_edge_uncertainty(edge) == pytest.approx(expected_sigma, abs=1e-9)

    def test_uncertainty_maximal_for_minimal_observations(self, mgr):
        """When alpha+beta < 2, uncertainty should be 1.0 (capped)."""
        edge = {"edge_alpha": 0.5, "edge_beta": 0.5}
        assert mgr.get_edge_uncertainty(edge) == 1.0

    def test_uncertainty_decreases_with_more_data(self, mgr):
        """More observations should reduce uncertainty monotonically."""
        uncertainties = []
        for n in [2, 5, 10, 50, 100]:
            edge = {"edge_alpha": float(n), "edge_beta": float(n)}
            uncertainties.append(mgr.get_edge_uncertainty(edge))
        for i in range(len(uncertainties) - 1):
            assert uncertainties[i] > uncertainties[i + 1], (
                f"Uncertainty did not decrease: {uncertainties}"
            )

    def test_confidence_bounded_0_1(self, mgr):
        """Confidence must always be in [0, 1] for any positive alpha, beta."""
        for alpha in [0.01, 0.1, 1.0, 10.0, 1000.0]:
            for beta in [0.01, 0.1, 1.0, 10.0, 1000.0]:
                edge = {"edge_alpha": alpha, "edge_beta": beta}
                conf = mgr.get_edge_confidence(edge)
                assert 0.0 <= conf <= 1.0

    # --- Reinforce sequence invariants ---

    def test_reinforce_alternating_stays_near_half(self, mgr):
        """Equal positive and negative reinforcement should keep confidence near 0.5."""
        edge = {"edge_alpha": 1.0, "edge_beta": 1.0}
        for _ in range(50):
            edge = mgr.reinforce(edge, positive=True)
            edge = mgr.reinforce(edge, positive=False)
        # alpha=51, beta=51 -> 0.5
        assert edge["edge_confidence"] == pytest.approx(0.5, abs=0.01)

    def test_reinforce_preserves_count_monotonicity(self, mgr):
        """reinforcement_count should strictly increase."""
        edge = {"edge_alpha": 1.0, "edge_beta": 1.0, "reinforcement_count": 0}
        prev_count = 0
        for i in range(20):
            edge = mgr.reinforce(edge, positive=(i % 3 != 0))
            assert edge["reinforcement_count"] == prev_count + 1
            prev_count = edge["reinforcement_count"]

    def test_reinforce_sets_last_reinforced(self, mgr):
        """last_reinforced timestamp should be set after reinforcement."""
        edge = {"edge_alpha": 1.0, "edge_beta": 1.0}
        updated = mgr.reinforce(edge, positive=True)
        assert "last_reinforced" in updated
        # Should be a valid ISO timestamp
        datetime.fromisoformat(updated["last_reinforced"])

    def test_reinforce_with_missing_fields_uses_defaults(self, mgr):
        """Edge without explicit alpha/beta should default to Beta(1,1)."""
        edge = {}
        updated = mgr.reinforce(edge, positive=True)
        assert updated["edge_alpha"] == 2.0  # 1.0 + 1.0
        assert updated["edge_beta"] == 1.0
        assert updated["reinforcement_count"] == 1


class TestBayesianEdgeDecayCurves:
    """Verify decay toward Beta(1,1) prior over time."""

    @pytest.fixture
    def mgr(self):
        return BayesianEdgeManager()

    def test_decay_at_exactly_half_life(self, mgr):
        """At exactly one half-life, excess alpha should halve."""
        edge_type = "INSTANTIATES"  # half_life = 730 days
        half_life_hours = EDGE_DECAY_PROFILES[edge_type] * 24.0

        initial_alpha = 11.0  # excess = 10
        edge = {"edge_alpha": initial_alpha, "edge_beta": 1.0, "edge_type": edge_type}
        decayed = mgr.decay(edge, hours_elapsed=half_life_hours)

        # (alpha - 1) * exp(-ln2) = 10 * 0.5 = 5.0, so new_alpha = 6.0
        assert decayed["edge_alpha"] == pytest.approx(6.0, abs=0.01)

    def test_decay_approaches_prior_not_zero(self, mgr):
        """After extreme decay, alpha and beta should approach 1.0, not 0.0."""
        edge = {"edge_alpha": 100.0, "edge_beta": 50.0, "edge_type": "CONFLICTS_WITH"}
        decayed = mgr.decay(edge, hours_elapsed=1_000_000)  # very long time
        assert decayed["edge_alpha"] >= 1.0
        assert decayed["edge_beta"] >= 1.0
        # Confidence should approach 0.5 (Beta(1,1) prior)
        assert decayed["edge_confidence"] == pytest.approx(0.5, abs=0.05)

    def test_decay_negative_hours_no_change(self, mgr):
        """Negative elapsed hours should not change the edge."""
        edge = {"edge_alpha": 10.0, "edge_beta": 5.0}
        result = mgr.decay(edge, hours_elapsed=-100)
        assert result["edge_alpha"] == 10.0
        assert result["edge_beta"] == 5.0

    def test_decay_uses_default_half_life_for_unknown_type(self, mgr):
        """Unknown edge types should use DEFAULT_HALF_LIFE."""
        half_life_hours = DEFAULT_HALF_LIFE * 24.0

        edge = {"edge_alpha": 11.0, "edge_beta": 1.0, "edge_type": "UNKNOWN_TYPE"}
        decayed = mgr.decay(edge, hours_elapsed=half_life_hours)

        # Same logic: excess 10 halves to 5 -> alpha = 6.0
        assert decayed["edge_alpha"] == pytest.approx(6.0, abs=0.01)

    def test_decay_preserves_confidence_direction(self, mgr):
        """If alpha > beta before decay, confidence should remain >= 0.5 unless extreme decay."""
        edge = {"edge_alpha": 20.0, "edge_beta": 5.0, "edge_type": "INFORMS"}
        decayed = mgr.decay(edge, hours_elapsed=365 * 24)  # 1 year
        # Both decay toward 1.0, so the ratio shifts toward 0.5 but does not cross it yet
        assert decayed["edge_confidence"] >= 0.5

    def test_different_edge_types_decay_at_different_rates(self, mgr):
        """GROUNDS (very stable) should decay less than CONFLICTS_WITH (fast)."""
        hours = 365 * 24  # 1 year
        edge_stable = {"edge_alpha": 11.0, "edge_beta": 1.0, "edge_type": "GROUNDS"}
        edge_fast = {"edge_alpha": 11.0, "edge_beta": 1.0, "edge_type": "CONFLICTS_WITH"}

        d_stable = mgr.decay(dict(edge_stable), hours_elapsed=hours)
        d_fast = mgr.decay(dict(edge_fast), hours_elapsed=hours)

        # GROUNDS should retain more alpha than CONFLICTS_WITH
        assert d_stable["edge_alpha"] > d_fast["edge_alpha"]

    def test_all_decay_profiles_have_positive_half_life(self):
        """Every profile must have a positive half-life."""
        for edge_type, half_life in EDGE_DECAY_PROFILES.items():
            assert half_life > 0, f"{edge_type} has non-positive half-life: {half_life}"


class TestBayesianEdgePropagation:
    """Test multi-hop confidence propagation."""

    @pytest.fixture
    def mgr(self):
        return BayesianEdgeManager()

    def test_single_edge_returns_its_confidence(self, mgr):
        edges = [{"edge_confidence": 0.85}]
        assert mgr.propagate_through(edges) == pytest.approx(0.85)

    def test_propagation_decreases_with_length(self, mgr):
        """Longer paths should always have lower confidence."""
        base = {"edge_confidence": 0.9}
        for length in range(1, 6):
            conf = mgr.propagate_through([base] * length)
            assert conf == pytest.approx(0.9**length, abs=1e-9)

    def test_propagation_with_zero_confidence_edge(self, mgr):
        """A zero-confidence edge should make the whole path zero."""
        edges = [
            {"edge_confidence": 0.9},
            {"edge_confidence": 0.0},
            {"edge_confidence": 0.8},
        ]
        assert mgr.propagate_through(edges) == pytest.approx(0.0)

    def test_propagation_with_missing_confidence_uses_default(self, mgr):
        """Missing edge_confidence should default to 0.5."""
        edges = [{}]
        assert mgr.propagate_through(edges) == pytest.approx(0.5)


class TestBayesianEdgeBatchUpdate:
    """Test batch_update_from_feedback with and without graph adapter."""

    def test_batch_update_without_graph_returns_zero(self):
        mgr = BayesianEdgeManager(graph_adapter=None)
        result = mgr.batch_update_from_feedback(
            [
                {"from_id": "A", "to_id": "B", "positive": True},
            ]
        )
        assert result == 0

    def test_batch_update_skips_empty_ids(self):
        mgr = BayesianEdgeManager(graph_adapter=None)
        result = mgr.batch_update_from_feedback(
            [
                {"from_id": "", "to_id": "B", "positive": True},
                {"from_id": "A", "to_id": "", "positive": True},
            ]
        )
        assert result == 0


# ===========================================================================
# Section 2: ContradictionTensor & ContradictionManager — Lifecycle
# ===========================================================================


class TestContradictionTensorDataclass:
    """Test the ContradictionTensor dataclass itself."""

    def test_make_id_is_symmetric(self):
        """make_id(A,B) == make_id(B,A) — order independence."""
        for a, b in [("X", "Y"), ("alpha", "beta"), ("CR-001", "CR-002")]:
            assert ContradictionTensor.make_id(a, b) == ContradictionTensor.make_id(b, a)

    def test_make_id_prefix(self):
        ct_id = ContradictionTensor.make_id("nodeA", "nodeB")
        assert ct_id.startswith("CT-")
        assert len(ct_id) == 15  # "CT-" + 12 hex chars

    def test_make_id_different_pairs_differ(self):
        """Different pairs produce different IDs."""
        id1 = ContradictionTensor.make_id("A", "B")
        id2 = ContradictionTensor.make_id("A", "C")
        assert id1 != id2

    def test_to_dict_complete(self):
        ct = ContradictionTensor(
            id="CT-test123456",
            node_a_id="N1",
            node_b_id="N2",
            conflict_factor=0.65,
            conflict_type="empirical",
            severity="moderate",
            evidence_for_a=["E1"],
            evidence_for_b=["E2", "E3"],
            opinion_a={"b": 0.7, "d": 0.1, "u": 0.2, "a": 0.5},
            opinion_b={"b": 0.1, "d": 0.7, "u": 0.2, "a": 0.5},
        )
        d = ct.to_dict()
        assert d["conflict_type"] == "empirical"
        assert d["severity"] == "moderate"
        assert d["is_resolved"] is False
        assert d["resolved_at"] is None
        assert len(d["evidence_for_a"]) == 1
        assert len(d["evidence_for_b"]) == 2

    def test_to_dict_with_resolution(self):
        now = datetime.now(UTC)
        ct = ContradictionTensor(
            id="CT-resolved123",
            node_a_id="A",
            node_b_id="B",
            conflict_factor=0.5,
            resolution="Fused via CBF",
            resolution_strategy="cbf",
            resolved_at=now,
        )
        d = ct.to_dict()
        assert d["is_resolved"] is True
        assert d["resolved_at"] is not None
        assert d["resolution_strategy"] == "cbf"


class TestContradictionManagerLifecycle:
    """Test the full lifecycle: detect -> add_evidence -> resolve -> query."""

    @pytest.fixture
    def cm(self):
        return ContradictionManager()

    def _make_conflicting_nodes(self):
        """Two nodes with strong opposing opinions."""
        a = {"id": "N1", "ep_b": 0.9, "ep_d": 0.05, "ep_u": 0.05, "ep_a": 0.5}
        b = {"id": "N2", "ep_b": 0.05, "ep_d": 0.9, "ep_u": 0.05, "ep_a": 0.5}
        return a, b

    def _make_agreeing_nodes(self):
        """Two nodes that agree (both believe)."""
        a = {"id": "A1", "ep_b": 0.7, "ep_d": 0.05, "ep_u": 0.25, "ep_a": 0.5}
        b = {"id": "A2", "ep_b": 0.65, "ep_d": 0.1, "ep_u": 0.25, "ep_a": 0.5}
        return a, b

    def test_detect_returns_none_for_agreeing_nodes(self, cm):
        a, b = self._make_agreeing_nodes()
        assert cm.detect(a, b) is None

    def test_detect_returns_tensor_for_conflicting_nodes(self, cm):
        a, b = self._make_conflicting_nodes()
        tensor = cm.detect(a, b)
        assert tensor is not None
        assert tensor.conflict_factor > 0.5
        assert tensor.node_a_id == "N1"
        assert tensor.node_b_id == "N2"
        assert tensor.resolution is None

    def test_detect_returns_none_without_epistemic_data(self, cm):
        a = {"id": "X"}
        b = {"id": "Y"}
        assert cm.detect(a, b) is None

    def test_detect_updates_existing_tensor(self, cm):
        """Re-detecting the same pair should update K, not create a new tensor."""
        a, b = self._make_conflicting_nodes()
        t1 = cm.detect(a, b)
        assert cm.total == 1

        # Slightly different opinions for the same pair
        a2 = {"id": "N1", "ep_b": 0.85, "ep_d": 0.1, "ep_u": 0.05, "ep_a": 0.5}
        t2 = cm.detect(a2, b)
        assert cm.total == 1  # Still one tensor
        assert t1.id == t2.id  # Same object

    def test_total_and_unresolved_count(self, cm):
        a, b = self._make_conflicting_nodes()
        cm.detect(a, b)
        assert cm.total == 1
        assert cm.unresolved_count == 1

        tensor = cm.get_unresolved()[0]
        cm.resolve(tensor, strategy="cbf")

        assert cm.total == 1
        assert cm.unresolved_count == 0

    def test_get_for_node(self, cm):
        a, b = self._make_conflicting_nodes()
        cm.detect(a, b)
        assert len(cm.get_for_node("N1")) == 1
        assert len(cm.get_for_node("N2")) == 1
        assert len(cm.get_for_node("NONEXISTENT")) == 0

    def test_get_all(self, cm):
        a, b = self._make_conflicting_nodes()
        cm.detect(a, b)
        assert len(cm.get_all()) == 1

    def test_add_evidence_for_a(self, cm):
        a, b = self._make_conflicting_nodes()
        tensor = cm.detect(a, b)
        assert tensor is not None
        assert cm.add_evidence(tensor.id, "N1", "evidence-001")
        assert "evidence-001" in tensor.evidence_for_a
        assert "evidence-001" not in tensor.evidence_for_b

    def test_add_evidence_for_b(self, cm):
        a, b = self._make_conflicting_nodes()
        tensor = cm.detect(a, b)
        assert tensor is not None
        assert cm.add_evidence(tensor.id, "N2", "evidence-002")
        assert "evidence-002" in tensor.evidence_for_b

    def test_add_evidence_dedup(self, cm):
        """Adding the same evidence twice should not duplicate."""
        a, b = self._make_conflicting_nodes()
        tensor = cm.detect(a, b)
        assert tensor is not None
        cm.add_evidence(tensor.id, "N1", "ev-dup")
        cm.add_evidence(tensor.id, "N1", "ev-dup")
        assert tensor.evidence_for_a.count("ev-dup") == 1

    def test_add_evidence_wrong_node_returns_false(self, cm):
        a, b = self._make_conflicting_nodes()
        tensor = cm.detect(a, b)
        assert tensor is not None
        assert not cm.add_evidence(tensor.id, "UNKNOWN_NODE", "ev-bad")

    def test_add_evidence_wrong_tensor_id_returns_false(self, cm):
        assert not cm.add_evidence("CT-nonexistent", "N1", "ev-bad")


class TestContradictionManagerResolve:
    """Test all resolution strategies."""

    @pytest.fixture
    def cm(self):
        return ContradictionManager()

    def _make_tensor(
        self, k: float, b_a: float = 0.7, d_a: float = 0.1, b_b: float = 0.1, d_b: float = 0.7
    ) -> ContradictionTensor:
        u_a = 1.0 - b_a - d_a
        u_b = 1.0 - b_b - d_b
        return ContradictionTensor(
            id="CT-test000000",
            node_a_id="A",
            node_b_id="B",
            conflict_factor=k,
            opinion_a={"b": b_a, "d": d_a, "u": u_a, "a": 0.5},
            opinion_b={"b": b_b, "d": d_b, "u": u_b, "a": 0.5},
        )

    def test_auto_selects_cbf_for_low_k(self, cm):
        tensor = self._make_tensor(k=0.2)
        result = cm.resolve(tensor, strategy="auto")
        assert result["strategy"] == "cbf"

    def test_auto_selects_murphy_for_medium_k(self, cm):
        tensor = self._make_tensor(k=0.5)
        result = cm.resolve(tensor, strategy="auto")
        assert result["strategy"] == "murphy"

    def test_auto_selects_demotion_for_high_k(self, cm):
        tensor = self._make_tensor(k=0.85)
        result = cm.resolve(tensor, strategy="auto")
        assert result["strategy"] == "demotion"

    def test_cbf_resolution_produces_valid_opinion(self, cm):
        tensor = self._make_tensor(k=0.2)
        result = cm.resolve(tensor, strategy="cbf")
        op = result["resolved_opinion"]
        assert op is not None
        total = op["b"] + op["d"] + op["u"]
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_murphy_resolution_produces_valid_opinion(self, cm):
        tensor = self._make_tensor(k=0.5)
        result = cm.resolve(tensor, strategy="murphy")
        op = result["resolved_opinion"]
        assert op is not None
        total = op["b"] + op["d"] + op["u"]
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_demotion_keeps_winner(self, cm):
        """Demotion should keep the opinion with higher belief."""
        tensor = self._make_tensor(k=0.85, b_a=0.8, d_a=0.1, b_b=0.2, d_b=0.7)
        result = cm.resolve(tensor, strategy="demotion")
        assert result["resolved_opinion"] is not None
        assert result["resolved_opinion"]["b"] == pytest.approx(0.8, abs=0.01)
        assert "Demoted B" in result["resolution"]

    def test_scope_split_has_no_resolved_opinion(self, cm):
        tensor = self._make_tensor(k=0.5)
        result = cm.resolve(tensor, strategy="scope_split")
        assert result["resolved_opinion"] is None
        assert tensor.resolution_strategy == "scope_split"

    def test_resolve_sets_timestamp(self, cm):
        tensor = self._make_tensor(k=0.5)
        assert tensor.resolved_at is None
        cm.resolve(tensor, strategy="cbf")
        assert tensor.resolved_at is not None

    def test_resolve_with_source_trusts(self, cm):
        tensor = self._make_tensor(k=0.55)
        trusts = {"A": 0.9, "B": 0.1}
        result = cm.resolve(tensor, strategy="murphy", source_trusts=trusts)
        op = result["resolved_opinion"]
        assert op is not None
        # Higher trust for A should push result toward A's opinion
        assert op["b"] > op["d"]

    def test_resolve_vacuous_tensor(self, cm):
        """Tensor with empty opinion dicts should use vacuous opinions."""
        tensor = ContradictionTensor(
            id="CT-vacuous00000",
            node_a_id="A",
            node_b_id="B",
            conflict_factor=0.2,
            opinion_a={},
            opinion_b={},
        )
        result = cm.resolve(tensor, strategy="cbf")
        # Should not crash; vacuous + vacuous = vacuous
        assert result["resolved_opinion"] is not None


# ===========================================================================
# Section 3: PredictiveDecayEngine — Classification, Math, Edge Cases
# ===========================================================================


class TestPredictiveDecayClassification:
    """Test knowledge type inference from node properties."""

    @pytest.fixture
    def engine(self):
        return PredictiveDecayEngine()

    def test_axiom_by_prefix(self, engine):
        assert engine.classify_knowledge_type({"id": "AX-001"}) == "axiom"

    def test_principle_by_prefix(self, engine):
        assert engine.classify_knowledge_type({"id": "P-001"}) == "principle"

    def test_pattern_by_prefix(self, engine):
        assert engine.classify_knowledge_type({"id": "PAT-001"}) == "design_pattern"

    def test_code_pattern_by_prefix(self, engine):
        assert engine.classify_knowledge_type({"id": "CPAT-001"}) == "code_pattern"

    def test_code_evidence_by_prefix(self, engine):
        assert engine.classify_knowledge_type({"id": "CE-001"}) == "code_pattern"

    def test_finding_by_prefix(self, engine):
        assert engine.classify_knowledge_type({"id": "F-001"}) == "test_result"

    def test_test_result_by_prefix(self, engine):
        assert engine.classify_knowledge_type({"id": "TR-001"}) == "test_result"

    def test_task_context_by_prefix(self, engine):
        assert engine.classify_knowledge_type({"id": "TC-001"}) == "task_context"

    def test_critical_rule_by_prefix(self, engine):
        assert engine.classify_knowledge_type({"id": "CR-001"}) == "best_practice"

    def test_security_vuln_overrides_prefix(self, engine):
        """Security severity + security domain should override prefix."""
        node = {
            "id": "CR-SEC-001",
            "severity": "critical",
            "domains": ["security"],
        }
        assert engine.classify_knowledge_type(node) == "security_vuln"

    def test_high_severity_non_security_domain_not_vuln(self, engine):
        """High severity without security domain should not classify as security_vuln."""
        node = {
            "id": "CR-001",
            "severity": "critical",
            "domains": ["design"],
        }
        # Severity is critical but domain is "design", not "security"
        assert engine.classify_knowledge_type(node) != "security_vuln"

    def test_framework_version_detection(self, engine):
        """Technologies with version numbers should classify as framework_version."""
        node = {
            "id": "CR-FW-001",
            "technologies": ["react"],
            "text": "React v3 update breaking changes",
        }
        assert engine.classify_knowledge_type(node) == "framework_version"

    def test_unknown_prefix_defaults_to_best_practice(self, engine):
        assert engine.classify_knowledge_type({"id": "UNKNOWN-001"}) == "best_practice"

    def test_empty_id_defaults_to_best_practice(self, engine):
        assert engine.classify_knowledge_type({}) == "best_practice"


class TestPredictiveDecayFreshnessmath:
    """Verify exponential decay math and reinforcement bonus."""

    @pytest.fixture
    def engine(self):
        return PredictiveDecayEngine()

    def test_freshness_at_zero_age_is_one(self, engine):
        now = datetime.now(UTC)
        node = {"id": "CR-001", "created_at": now.isoformat()}
        assert engine.compute_freshness(node, now) == pytest.approx(1.0, abs=1e-6)

    def test_freshness_at_half_life_is_half(self, engine):
        """At exactly one half-life, freshness should be 0.5."""
        now = datetime.now(UTC)
        profile = DECAY_PROFILES["best_practice"]
        half_life = profile["half_life_days"]
        created = now - timedelta(days=half_life)
        node = {"id": "CR-001", "created_at": created.isoformat()}
        freshness = engine.compute_freshness(node, now)
        assert freshness == pytest.approx(0.5, abs=0.01)

    def test_axiom_freshness_always_one(self, engine):
        """Axioms (infinite half-life) never decay."""
        now = datetime.now(UTC)
        very_old = now - timedelta(days=36500)  # 100 years
        node = {"id": "AX-001", "created_at": very_old.isoformat()}
        assert engine.compute_freshness(node, now) == 1.0

    def test_freshness_bounded_0_1(self, engine):
        """Freshness must always be in [0, 1]."""
        now = datetime.now(UTC)
        for days in [0, 1, 30, 180, 365, 730, 3650, 36500]:
            created = now - timedelta(days=days)
            node = {"id": "CR-001", "created_at": created.isoformat()}
            f = engine.compute_freshness(node, now)
            assert 0.0 <= f <= 1.0, f"Freshness out of bounds at {days} days: {f}"

    def test_unknown_timestamp_returns_half(self, engine):
        """Node without any timestamp should get 0.5 freshness."""
        node = {"id": "CR-001"}
        assert engine.compute_freshness(node) == 0.5

    def test_reinforcement_increases_freshness(self, engine):
        """Reinforced nodes should have higher freshness."""
        now = datetime.now(UTC)
        created = now - timedelta(days=200)
        base = {"id": "CR-001", "created_at": created.isoformat(), "reinforcement_count": 0}
        reinforced = {"id": "CR-001", "created_at": created.isoformat(), "reinforcement_count": 5}
        f_base = engine.compute_freshness(base, now)
        f_reinforced = engine.compute_freshness(reinforced, now)
        assert f_reinforced > f_base

    def test_reinforcement_capped_at_30_percent(self, engine):
        """Reinforcement bonus capped at 30% -> freshness should not exceed 1.0."""
        now = datetime.now(UTC)
        node = {
            "id": "CR-001",
            "created_at": now.isoformat(),
            "reinforcement_count": 100,
        }
        assert engine.compute_freshness(node, now) <= 1.0

    def test_task_context_decays_very_fast(self, engine):
        """task_context (half_life=1 day) should be nearly stale after 3 days."""
        now = datetime.now(UTC)
        created = now - timedelta(days=3)
        node = {"id": "TC-001", "created_at": created.isoformat()}
        freshness = engine.compute_freshness(node, now)
        assert freshness < 0.15  # exp(-3 * ln2) ~ 0.125


class TestPredictiveDecayStaleness:
    """Test staleness prediction and at-risk detection."""

    @pytest.fixture
    def engine(self):
        return PredictiveDecayEngine()

    def test_predict_staleness_already_stale(self, engine):
        """Very old node should have days_until_stale == 0."""
        now = datetime.now(UTC)
        very_old = now - timedelta(days=3650)
        node = {"id": "CR-001", "created_at": very_old.isoformat()}
        pred = engine.predict_staleness(node, now)
        assert pred.days_until_stale == 0.0
        assert pred.current_freshness < STALE_THRESHOLD

    def test_predict_staleness_axiom_infinite(self, engine):
        pred = engine.predict_staleness({"id": "AX-001"})
        assert pred.days_until_stale == float("inf")
        assert pred.estimated_stale_date is None
        assert pred.confidence == 1.0

    def test_predict_staleness_fresh_node_future(self, engine):
        now = datetime.now(UTC)
        node = {"id": "CR-001", "created_at": now.isoformat()}
        pred = engine.predict_staleness(node, now)
        assert pred.days_until_stale > 0
        assert pred.estimated_stale_date is not None
        assert pred.estimated_stale_date > now

    def test_confidence_lower_for_volatile_types(self, engine):
        """High-volatility types should have lower prediction confidence."""
        now = datetime.now(UTC)
        # security_vuln: volatility=0.5
        vuln_node = {
            "id": "CR-V",
            "severity": "critical",
            "domains": ["security"],
            "created_at": now.isoformat(),
        }
        # principle: volatility=0.05
        principle_node = {"id": "P-001", "created_at": now.isoformat()}

        p_vuln = engine.predict_staleness(vuln_node, now)
        p_principle = engine.predict_staleness(principle_node, now)
        assert p_principle.confidence > p_vuln.confidence

    def test_confidence_halved_without_timestamp(self, engine):
        """Unknown creation date should reduce confidence by 50%."""
        node_with_ts = {
            "id": "CR-001",
            "created_at": datetime.now(UTC).isoformat(),
        }
        node_without_ts = {"id": "CR-002"}

        p_with = engine.predict_staleness(node_with_ts)
        p_without = engine.predict_staleness(node_without_ts)
        assert p_without.confidence < p_with.confidence

    def test_at_risk_excludes_axioms(self, engine):
        now = datetime.now(UTC)
        nodes = [
            {"id": "AX-001"},
            {"id": "CR-001", "created_at": (now - timedelta(days=500)).isoformat()},
        ]
        at_risk = engine.get_at_risk_nodes(nodes, horizon_days=30, now=now)
        risk_ids = {p.node_id for p in at_risk}
        assert "AX-001" not in risk_ids

    def test_at_risk_sorted_by_urgency(self, engine):
        """Results should be sorted soonest-stale first."""
        now = datetime.now(UTC)
        nodes = [
            {"id": "CR-001", "created_at": (now - timedelta(days=480)).isoformat()},
            {"id": "CR-002", "created_at": (now - timedelta(days=500)).isoformat()},
            {"id": "CR-003", "created_at": (now - timedelta(days=460)).isoformat()},
        ]
        at_risk = engine.get_at_risk_nodes(nodes, horizon_days=365, now=now)
        if len(at_risk) >= 2:
            for i in range(len(at_risk) - 1):
                assert at_risk[i].days_until_stale <= at_risk[i + 1].days_until_stale

    def test_prediction_to_dict(self, engine):
        now = datetime.now(UTC)
        node = {"id": "CR-001", "created_at": now.isoformat()}
        pred = engine.predict_staleness(node, now)
        d = pred.to_dict()
        assert "node_id" in d
        assert "knowledge_type" in d
        assert "current_freshness" in d
        assert "days_until_stale" in d
        assert "confidence" in d

    def test_refresh_node_updates_timestamp_and_count(self, engine):
        node = {"id": "CR-001", "reinforcement_count": 3}
        refreshed = engine.refresh_node(node)
        assert refreshed["reinforcement_count"] == 4
        assert "updated_at" in refreshed

    def test_get_profile_unknown_type(self, engine):
        """Unknown knowledge type should return best_practice profile."""
        profile = engine.get_profile("nonexistent_type")
        assert profile == DECAY_PROFILES["best_practice"]


class TestPredictiveDecayTimestamp:
    """Test timestamp extraction edge cases."""

    def test_datetime_object_with_tz(self):
        engine = PredictiveDecayEngine()
        dt = datetime(2025, 1, 1, tzinfo=UTC)
        node = {"id": "CR-001", "created_at": dt}
        result = engine._get_timestamp(node)
        assert result is not None
        assert result.tzinfo is not None

    def test_datetime_object_without_tz(self):
        engine = PredictiveDecayEngine()
        dt = datetime(2025, 1, 1)
        node = {"id": "CR-001", "created_at": dt}
        result = engine._get_timestamp(node)
        assert result is not None
        assert result.tzinfo == UTC  # should add UTC

    def test_iso_string_with_z(self):
        engine = PredictiveDecayEngine()
        node = {"id": "CR-001", "created_at": "2025-06-15T10:00:00Z"}
        result = engine._get_timestamp(node)
        assert result is not None

    def test_iso_string_with_offset(self):
        engine = PredictiveDecayEngine()
        node = {"id": "CR-001", "created_at": "2025-06-15T10:00:00+00:00"}
        result = engine._get_timestamp(node)
        assert result is not None

    def test_updated_at_preferred_over_created_at(self):
        engine = PredictiveDecayEngine()
        node = {
            "id": "CR-001",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        result = engine._get_timestamp(node)
        assert result is not None
        assert result.year == 2026  # updated_at is checked first

    def test_no_timestamp_returns_none(self):
        engine = PredictiveDecayEngine()
        assert engine._get_timestamp({"id": "CR-001"}) is None

    def test_invalid_timestamp_string_returns_none(self):
        engine = PredictiveDecayEngine()
        assert engine._get_timestamp({"id": "CR-001", "created_at": "not-a-date"}) is None


# ===========================================================================
# Section 4: Temporal (Hawkes) — Intensity Math & Mass Conservation
# ===========================================================================


class TestHawkesIntensityMath:
    """Test mathematical correctness of Hawkes intensity computation."""

    def test_intensity_formula_single_event(self):
        """lambda*(t) = mu + alpha*beta*exp(-beta*(t-ti))"""
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        t_now = 100.0
        t_event = 90.0
        dt = t_now - t_event

        expected = 0.001 + 0.05 * 0.01 * math.exp(-0.01 * dt)
        actual = engine.compute_intensity(t_now, [t_event])
        assert actual == pytest.approx(expected, abs=1e-12)

    def test_intensity_formula_multiple_events(self):
        engine = HawkesDecayEngine(mu=0.002, alpha=0.1, beta=0.02)
        t_now = 200.0
        events = [150.0, 180.0, 195.0]

        expected = 0.002
        for ti in events:
            expected += 0.1 * 0.02 * math.exp(-0.02 * (t_now - ti))

        actual = engine.compute_intensity(t_now, events)
        assert actual == pytest.approx(expected, abs=1e-12)

    def test_zero_mu_zero_events_gives_zero(self):
        """Engine with mu=0 and no events should give intensity 0."""
        engine = HawkesDecayEngine(mu=0.0, alpha=0.05, beta=0.01)
        assert engine.compute_intensity(100.0, []) == 0.0

    def test_future_events_ignored(self):
        """Events at or after now_days should not contribute to intensity."""
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        # event at t=100 same as now, dt=0 -> not > 0 -> skipped
        assert engine.compute_intensity(100.0, [100.0]) == pytest.approx(0.001, abs=1e-9)
        # event at t=110 > now=100 -> skipped
        assert engine.compute_intensity(100.0, [110.0]) == pytest.approx(0.001, abs=1e-9)


class TestHawkesTemporalFactor:
    """Test tau computation and its bounds."""

    def test_tau_always_in_0_1(self):
        """tau must be in [0, 1] for any parameters and events."""
        engine = HawkesDecayEngine(mu=0.01, alpha=0.1, beta=0.05)
        test_cases = [
            (1000000, []),
            (1000000, [999999]),
            (1000000, [500000, 800000, 999990]),
            (1, []),
        ]
        for now, events in test_cases:
            tau = engine.compute_temporal_factor(now, events)
            assert 0.0 <= tau <= 1.0, f"tau={tau} out of bounds for now={now}, events={events}"

    def test_tau_zero_mu_zero_alpha_is_nan_safe(self):
        """mu=0, alpha=0 -> max_intensity=0 -> should return 0.0 safely."""
        engine = HawkesDecayEngine(mu=0.0, alpha=0.0, beta=0.0)
        tau = engine.compute_temporal_factor(1000000, [])
        assert tau == 0.0

    def test_tau_higher_with_more_recent_events(self):
        engine = HawkesDecayEngine(mu=0.001, alpha=0.05, beta=0.01)
        now = 100 * 86400
        tau_no_events = engine.compute_temporal_factor(now, [])
        tau_old_event = engine.compute_temporal_factor(now, [50 * 86400])
        tau_recent_event = engine.compute_temporal_factor(now, [99 * 86400])
        assert tau_recent_event >= tau_old_event >= tau_no_events


class TestHawkesApplyDecayInvariants:
    """Test that apply_decay maintains opinion invariants."""

    def test_mass_conservation_various_opinions(self):
        """b + d + u = 1 must hold after any decay."""
        engine = HawkesDecayEngine(mu=0.005, alpha=0.05, beta=0.01)
        opinions = [
            OpinionTuple(b=0.9, d=0.05, u=0.05, a=0.5),
            OpinionTuple(b=0.0, d=0.0, u=1.0, a=0.5),
            OpinionTuple(b=0.5, d=0.5, u=0.0, a=0.5),
            OpinionTuple(b=0.33, d=0.33, u=0.34, a=0.5),
        ]
        for op in opinions:
            result = engine.apply_decay(
                op, now_unix=10000000, last_decay_unix=0, event_timestamps_unix=[]
            )
            total = result.b + result.d + result.u
            assert total == pytest.approx(1.0, abs=1e-6), (
                f"Mass not conserved for {op}: b+d+u={total}"
            )

    def test_base_rate_preserved_after_decay(self):
        """Decay should not change the base rate 'a'."""
        engine = HawkesDecayEngine(mu=0.005, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.7, d=0.1, u=0.2, a=0.75)
        result = engine.apply_decay(
            op, now_unix=10000000, last_decay_unix=0, event_timestamps_unix=[]
        )
        assert result.a == op.a

    def test_belief_and_disbelief_non_negative_after_decay(self):
        """b and d must never go negative."""
        engine = HawkesDecayEngine(mu=0.01, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.001, d=0.001, u=0.998, a=0.5)
        result = engine.apply_decay(
            op, now_unix=100000000, last_decay_unix=0, event_timestamps_unix=[]
        )
        assert result.b >= 0.0
        assert result.d >= 0.0

    def test_vacuous_opinion_stays_vacuous(self):
        """Vacuous opinion (b=0,d=0,u=1) should remain vacuous after decay."""
        engine = HawkesDecayEngine(mu=0.01, alpha=0.05, beta=0.01)
        op = OpinionTuple(b=0.0, d=0.0, u=1.0, a=0.5)
        result = engine.apply_decay(
            op, now_unix=10000000, last_decay_unix=0, event_timestamps_unix=[]
        )
        assert result.b == pytest.approx(0.0, abs=1e-9)
        assert result.d == pytest.approx(0.0, abs=1e-9)
        assert result.u == pytest.approx(1.0, abs=1e-6)

    def test_l0_axiom_engine_no_decay(self):
        """L0 engine (mu=0) should produce zero decay regardless of time."""
        engine = LAYER_DECAY_PROFILES["L0"]
        op = OpinionTuple(b=0.95, d=0.01, u=0.04, a=0.9)
        result = engine.apply_decay(
            op, now_unix=999999999, last_decay_unix=0, event_timestamps_unix=[]
        )
        assert result.b == pytest.approx(op.b, abs=1e-9)
        assert result.d == pytest.approx(op.d, abs=1e-9)
        assert result.u == pytest.approx(op.u, abs=1e-9)

    def test_l5_decays_much_faster_than_l1(self):
        """L5 (context) should lose much more belief than L1 (principles) over same time."""
        op = OpinionTuple(b=0.8, d=0.0, u=0.2, a=0.5)
        now = 90 * 86400  # 90 days in seconds

        l1_result = LAYER_DECAY_PROFILES["L1"].apply_decay(op, now, 0, [])
        l5_result = LAYER_DECAY_PROFILES["L5"].apply_decay(op, now, 0, [])
        assert l1_result.b > l5_result.b

    def test_get_decay_engine_returns_correct_layer(self):
        for layer_name, expected_engine in LAYER_DECAY_PROFILES.items():
            engine = get_decay_engine(layer_name)
            assert engine.mu == expected_engine.mu
            assert engine.alpha == expected_engine.alpha
            assert engine.beta == expected_engine.beta

    def test_get_decay_engine_unknown_returns_l3(self):
        engine = get_decay_engine("L99")
        l3 = LAYER_DECAY_PROFILES["L3"]
        assert engine.mu == l3.mu


# ===========================================================================
# Section 5: Contradiction Detection — _node_to_opinion edge cases
# ===========================================================================


class TestNodeToOpinionEdgeCases:
    """Test the _node_to_opinion static method used by both
    ContradictionDetector and ContradictionManager."""

    def test_full_opinion_round_trip(self):
        """Node with all ep_ fields should produce exact opinion."""
        node = {"ep_b": 0.6, "ep_d": 0.15, "ep_u": 0.25, "ep_a": 0.7}
        op = ContradictionManager._node_to_opinion(node)
        assert op is not None
        assert op.b == pytest.approx(0.6)
        assert op.d == pytest.approx(0.15)
        assert op.u == pytest.approx(0.25)
        assert op.a == pytest.approx(0.7)

    def test_missing_ep_b_returns_none(self):
        """Without ep_b, we cannot form an opinion."""
        node = {"ep_d": 0.3, "ep_u": 0.7}
        assert ContradictionManager._node_to_opinion(node) is None

    def test_missing_d_defaults_to_zero(self):
        node = {"ep_b": 0.5, "ep_u": 0.5}
        op = ContradictionManager._node_to_opinion(node)
        assert op is not None
        assert op.d == 0.0

    def test_missing_u_computed_from_b_d(self):
        """When ep_u is missing, it should be computed as max(0, 1-b-d)."""
        node = {"ep_b": 0.7, "ep_d": 0.1}
        op = ContradictionManager._node_to_opinion(node)
        assert op is not None
        assert op.u == pytest.approx(0.2, abs=1e-6)

    def test_missing_a_defaults_to_half(self):
        node = {"ep_b": 0.5, "ep_d": 0.2, "ep_u": 0.3}
        op = ContradictionManager._node_to_opinion(node)
        assert op is not None
        assert op.a == 0.5

    def test_bdu_invariant_holds(self):
        """b + d + u = 1 must hold for any valid node."""
        nodes = [
            {"ep_b": 0.8, "ep_d": 0.1, "ep_u": 0.1},
            {"ep_b": 0.0, "ep_d": 0.0, "ep_u": 1.0},
            {"ep_b": 1.0, "ep_d": 0.0, "ep_u": 0.0},
            {"ep_b": 0.33, "ep_d": 0.33, "ep_u": 0.34},
        ]
        for node_data in nodes:
            op = ContradictionManager._node_to_opinion(node_data)
            assert op is not None
            total = op.b + op.d + op.u
            assert total == pytest.approx(1.0, abs=1e-6)

    def test_string_values_converted_to_float(self):
        """ep_ values stored as strings should be converted."""
        node = {"ep_b": "0.6", "ep_d": "0.15", "ep_u": "0.25", "ep_a": "0.7"}
        op = ContradictionManager._node_to_opinion(node)
        assert op is not None
        assert op.b == pytest.approx(0.6)


# ===========================================================================
# Section 6: Decay Profile Consistency Checks
# ===========================================================================


class TestDecayProfileConsistency:
    """Cross-module consistency between EDGE_DECAY_PROFILES and DECAY_PROFILES."""

    def test_all_edge_profiles_have_positive_values(self):
        for edge_type, half_life in EDGE_DECAY_PROFILES.items():
            assert half_life > 0, f"EDGE_DECAY_PROFILES[{edge_type}] = {half_life} <= 0"

    def test_all_knowledge_profiles_have_required_keys(self):
        for ktype, profile in DECAY_PROFILES.items():
            assert "half_life_days" in profile, f"{ktype} missing half_life_days"
            assert "volatility" in profile, f"{ktype} missing volatility"
            assert profile["volatility"] >= 0.0, f"{ktype} has negative volatility"
            assert profile["volatility"] <= 1.0, f"{ktype} volatility > 1.0"

    def test_axiom_is_special(self):
        """Axiom should have infinite half-life and zero volatility."""
        assert DECAY_PROFILES["axiom"]["half_life_days"] == float("inf")
        assert DECAY_PROFILES["axiom"]["volatility"] == 0.0

    def test_task_context_has_shortest_half_life(self):
        """task_context should decay fastest (half_life=1 day)."""
        min_hl = min(
            p["half_life_days"]
            for k, p in DECAY_PROFILES.items()
            if p["half_life_days"] != float("inf")
        )
        assert DECAY_PROFILES["task_context"]["half_life_days"] == min_hl

    def test_layer_profiles_all_present(self):
        """All cortical layers L0-L5 must have a decay profile."""
        for layer in ["L0", "L1", "L2", "L3", "L4", "L5"]:
            assert layer in LAYER_DECAY_PROFILES, f"Missing profile for {layer}"

    def test_layer_profiles_monotonically_faster(self):
        """Higher layers should have higher mu (faster natural decay)."""
        mus = [LAYER_DECAY_PROFILES[f"L{i}"].mu for i in range(6)]
        for i in range(len(mus) - 1):
            assert mus[i] <= mus[i + 1], f"L{i}.mu={mus[i]} > L{i + 1}.mu={mus[i + 1]}"
