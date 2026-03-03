"""Tests for Wave 1 Epistemic modules: BayesianEdge, PredictiveDecay,
ContradictionTensor, DSTEvidence, BM25, PPR."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from engineering_brain.epistemic.bayesian_edges import BayesianEdgeManager, EDGE_DECAY_PROFILES
from engineering_brain.epistemic.predictive_decay import (
    PredictiveDecayEngine,
    DECAY_PROFILES,
    DecayPrediction,
)
from engineering_brain.epistemic.contradiction_tensor import (
    ContradictionManager,
    ContradictionTensor,
)
from engineering_brain.epistemic.dst_evidence import DSTEvidenceCombiner
from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.retrieval.bm25 import BM25Index
from engineering_brain.retrieval.ppr import personalized_pagerank, build_adjacency_from_edges


# ===========================================================================
# BayesianEdgeManager
# ===========================================================================


class TestBayesianEdgeManager:
    @pytest.fixture
    def manager(self):
        return BayesianEdgeManager()

    def test_reinforce_positive(self, manager):
        edge = {"edge_alpha": 1.0, "edge_beta": 1.0, "reinforcement_count": 0}
        updated = manager.reinforce(edge, positive=True)
        assert updated["edge_alpha"] == 2.0
        assert updated["edge_beta"] == 1.0
        assert updated["edge_confidence"] == pytest.approx(2.0 / 3.0, abs=1e-4)
        assert updated["reinforcement_count"] == 1

    def test_reinforce_negative(self, manager):
        edge = {"edge_alpha": 1.0, "edge_beta": 1.0, "reinforcement_count": 0}
        updated = manager.reinforce(edge, positive=False)
        assert updated["edge_alpha"] == 1.0
        assert updated["edge_beta"] == 2.0
        assert updated["edge_confidence"] == pytest.approx(1.0 / 3.0, abs=1e-4)

    def test_confidence_converges(self, manager):
        edge = {"edge_alpha": 1.0, "edge_beta": 1.0}
        for _ in range(100):
            edge = manager.reinforce(edge, positive=True)
        # After 100 positive reinforcements: alpha=101, beta=1
        assert edge["edge_confidence"] > 0.99

    def test_decay_shifts_toward_prior(self, manager):
        edge = {"edge_alpha": 10.0, "edge_beta": 2.0, "edge_type": "INSTANTIATES"}
        original_conf = 10.0 / 12.0
        decayed = manager.decay(edge, hours_elapsed=730 * 24)  # 2 years
        assert decayed["edge_confidence"] < original_conf
        assert decayed["edge_alpha"] < 10.0

    def test_decay_zero_hours(self, manager):
        edge = {"edge_alpha": 5.0, "edge_beta": 3.0}
        result = manager.decay(edge, hours_elapsed=0)
        assert result["edge_alpha"] == 5.0

    def test_propagate_through_path(self, manager):
        edges = [
            {"edge_confidence": 0.9},
            {"edge_confidence": 0.8},
            {"edge_confidence": 0.7},
        ]
        conf = manager.propagate_through(edges)
        assert conf == pytest.approx(0.9 * 0.8 * 0.7, abs=1e-6)

    def test_propagate_empty_path(self, manager):
        assert manager.propagate_through([]) == 0.0

    def test_get_edge_confidence(self, manager):
        edge = {"edge_alpha": 3.0, "edge_beta": 1.0}
        assert manager.get_edge_confidence(edge) == pytest.approx(0.75)

    def test_get_edge_uncertainty(self, manager):
        # Few observations = high uncertainty
        edge_few = {"edge_alpha": 1.0, "edge_beta": 1.0}
        edge_many = {"edge_alpha": 50.0, "edge_beta": 50.0}
        assert manager.get_edge_uncertainty(edge_few) > manager.get_edge_uncertainty(edge_many)

    def test_edge_decay_profiles(self):
        assert "GROUNDS" in EDGE_DECAY_PROFILES
        assert EDGE_DECAY_PROFILES["GROUNDS"] > EDGE_DECAY_PROFILES["CONFLICTS_WITH"]


# ===========================================================================
# PredictiveDecayEngine
# ===========================================================================


class TestPredictiveDecayEngine:
    @pytest.fixture
    def engine(self):
        return PredictiveDecayEngine()

    def test_axiom_never_decays(self, engine):
        node = {"id": "AX-001", "immutable": True}
        pred = engine.predict_staleness(node)
        assert pred.current_freshness == 1.0
        assert pred.days_until_stale == float("inf")

    def test_fresh_node_high_freshness(self, engine):
        now = datetime.now(timezone.utc)
        node = {
            "id": "CR-001",
            "created_at": now.isoformat(),
            "technologies": ["flask"],
            "domains": ["security"],
        }
        freshness = engine.compute_freshness(node, now)
        assert freshness > 0.95

    def test_old_node_low_freshness(self, engine):
        old = datetime.now(timezone.utc) - timedelta(days=365 * 3)
        node = {"id": "CR-002", "created_at": old.isoformat()}
        freshness = engine.compute_freshness(node)
        assert freshness < 0.5

    def test_predict_staleness_future_date(self, engine):
        now = datetime.now(timezone.utc)
        node = {"id": "CR-003", "created_at": now.isoformat()}
        pred = engine.predict_staleness(node, now)
        assert pred.days_until_stale > 0
        assert pred.estimated_stale_date is not None
        assert pred.estimated_stale_date > now

    def test_at_risk_nodes(self, engine):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=500)
        nodes = [
            {"id": "CR-010", "created_at": old.isoformat()},
            {"id": "CR-011", "created_at": now.isoformat()},
            {"id": "AX-001", "immutable": True},
        ]
        at_risk = engine.get_at_risk_nodes(nodes, horizon_days=30, now=now)
        # Old node should be at risk or already stale, axiom never, fresh node not
        risk_ids = {p.node_id for p in at_risk}
        assert "AX-001" not in risk_ids

    def test_reinforce_boosts_freshness(self, engine):
        old = datetime.now(timezone.utc) - timedelta(days=200)
        node_base = {"id": "CR-020", "created_at": old.isoformat(), "reinforcement_count": 0}
        node_reinforced = {"id": "CR-020", "created_at": old.isoformat(), "reinforcement_count": 5}
        f_base = engine.compute_freshness(node_base)
        f_reinforced = engine.compute_freshness(node_reinforced)
        assert f_reinforced > f_base

    def test_refresh_node(self, engine):
        node = {"id": "CR-030", "reinforcement_count": 0}
        refreshed = engine.refresh_node(node)
        assert refreshed["reinforcement_count"] == 1
        assert "updated_at" in refreshed

    def test_classify_security_vuln(self, engine):
        node = {
            "id": "CR-SEC-001",
            "severity": "critical",
            "domains": ["security"],
        }
        assert engine.classify_knowledge_type(node) == "security_vuln"

    def test_decay_profiles_exist(self):
        assert "framework_version" in DECAY_PROFILES
        assert "axiom" in DECAY_PROFILES
        assert DECAY_PROFILES["axiom"]["volatility"] == 0.0


# ===========================================================================
# ContradictionTensor + ContradictionManager
# ===========================================================================


class TestContradictionTensor:
    def test_make_id_deterministic(self):
        id1 = ContradictionTensor.make_id("A", "B")
        id2 = ContradictionTensor.make_id("B", "A")
        assert id1 == id2  # Order doesn't matter
        assert id1.startswith("CT-")

    def test_to_dict(self):
        ct = ContradictionTensor(
            id="CT-abc",
            node_a_id="A",
            node_b_id="B",
            conflict_factor=0.75,
        )
        d = ct.to_dict()
        assert d["id"] == "CT-abc"
        assert d["conflict_factor"] == 0.75
        assert d["is_resolved"] is False


class TestContradictionManager:
    @pytest.fixture
    def manager(self):
        return ContradictionManager()

    def test_detect_no_conflict(self, manager):
        node_a = {"id": "A", "ep_b": 0.8, "ep_d": 0.0, "ep_u": 0.2, "ep_a": 0.5}
        node_b = {"id": "B", "ep_b": 0.7, "ep_d": 0.0, "ep_u": 0.3, "ep_a": 0.5}
        result = manager.detect(node_a, node_b)
        assert result is None  # Both believe, no conflict

    def test_detect_high_conflict(self, manager):
        node_a = {"id": "A", "ep_b": 0.9, "ep_d": 0.05, "ep_u": 0.05, "ep_a": 0.5}
        node_b = {"id": "B", "ep_b": 0.05, "ep_d": 0.9, "ep_u": 0.05, "ep_a": 0.5}
        result = manager.detect(node_a, node_b)
        assert result is not None
        assert result.conflict_factor > 0.7

    def test_detect_without_epistemic(self, manager):
        node_a = {"id": "A"}
        node_b = {"id": "B"}
        assert manager.detect(node_a, node_b) is None

    def test_resolve_auto_cbf(self, manager):
        ct = ContradictionTensor(
            id="CT-test",
            node_a_id="A",
            node_b_id="B",
            conflict_factor=0.2,
            opinion_a={"b": 0.6, "d": 0.1, "u": 0.3, "a": 0.5},
            opinion_b={"b": 0.5, "d": 0.2, "u": 0.3, "a": 0.5},
        )
        result = manager.resolve(ct, strategy="auto")
        assert result["strategy"] == "cbf"
        assert ct.resolution is not None

    def test_resolve_auto_murphy(self, manager):
        ct = ContradictionTensor(
            id="CT-test2",
            node_a_id="A",
            node_b_id="B",
            conflict_factor=0.5,
            opinion_a={"b": 0.7, "d": 0.1, "u": 0.2, "a": 0.5},
            opinion_b={"b": 0.1, "d": 0.7, "u": 0.2, "a": 0.5},
        )
        result = manager.resolve(ct, strategy="auto")
        assert result["strategy"] == "murphy"

    def test_resolve_auto_demotion(self, manager):
        ct = ContradictionTensor(
            id="CT-test3",
            node_a_id="A",
            node_b_id="B",
            conflict_factor=0.85,
            opinion_a={"b": 0.9, "d": 0.05, "u": 0.05, "a": 0.5},
            opinion_b={"b": 0.05, "d": 0.9, "u": 0.05, "a": 0.5},
        )
        result = manager.resolve(ct, strategy="auto")
        assert result["strategy"] == "demotion"

    def test_resolve_scope_split(self, manager):
        ct = ContradictionTensor(
            id="CT-test4",
            node_a_id="A",
            node_b_id="B",
            conflict_factor=0.6,
            opinion_a={"b": 0.7, "d": 0.1, "u": 0.2, "a": 0.5},
            opinion_b={"b": 0.1, "d": 0.7, "u": 0.2, "a": 0.5},
        )
        result = manager.resolve(ct, strategy="scope_split")
        assert result["resolved_opinion"] is None
        assert "scope" in result["resolution"].lower()

    def test_get_unresolved(self, manager):
        node_a = {"id": "X", "ep_b": 0.9, "ep_d": 0.05, "ep_u": 0.05, "ep_a": 0.5}
        node_b = {"id": "Y", "ep_b": 0.05, "ep_d": 0.9, "ep_u": 0.05, "ep_a": 0.5}
        manager.detect(node_a, node_b)
        assert manager.unresolved_count == 1
        assert len(manager.get_unresolved()) == 1

    def test_get_for_node(self, manager):
        node_a = {"id": "M", "ep_b": 0.9, "ep_d": 0.05, "ep_u": 0.05, "ep_a": 0.5}
        node_b = {"id": "N", "ep_b": 0.05, "ep_d": 0.9, "ep_u": 0.05, "ep_a": 0.5}
        manager.detect(node_a, node_b)
        assert len(manager.get_for_node("M")) == 1
        assert len(manager.get_for_node("Z")) == 0

    def test_add_evidence(self, manager):
        node_a = {"id": "P", "ep_b": 0.9, "ep_d": 0.05, "ep_u": 0.05, "ep_a": 0.5}
        node_b = {"id": "Q", "ep_b": 0.05, "ep_d": 0.9, "ep_u": 0.05, "ep_a": 0.5}
        ct = manager.detect(node_a, node_b)
        assert ct is not None
        assert manager.add_evidence(ct.id, "P", "evidence-1")
        assert "evidence-1" in ct.evidence_for_a


# ===========================================================================
# DSTEvidenceCombiner
# ===========================================================================


class TestDSTEvidenceCombiner:
    @pytest.fixture
    def combiner(self):
        return DSTEvidenceCombiner()

    def test_single_opinion(self, combiner):
        op = OpinionTuple(b=0.7, d=0.1, u=0.2, a=0.5)
        result = combiner.combine([op])
        assert result.b == op.b

    def test_empty_opinions(self, combiner):
        result = combiner.combine([])
        assert result.u > 0.99  # Vacuous

    def test_low_conflict_uses_cbf(self, combiner):
        ops = [
            OpinionTuple(b=0.7, d=0.05, u=0.25, a=0.5),
            OpinionTuple(b=0.6, d=0.1, u=0.3, a=0.5),
        ]
        strategy = combiner.get_strategy(ops)
        assert strategy == "cbf"

    def test_high_conflict_uses_conservative_envelope(self, combiner):
        ops = [
            OpinionTuple(b=0.9, d=0.05, u=0.05, a=0.5),
            OpinionTuple(b=0.05, d=0.9, u=0.05, a=0.5),
        ]
        strategy = combiner.get_strategy(ops)
        assert strategy == "conservative_envelope"

    def test_combine_reduces_uncertainty(self, combiner):
        ops = [
            OpinionTuple(b=0.6, d=0.05, u=0.35, a=0.5),
            OpinionTuple(b=0.5, d=0.1, u=0.4, a=0.5),
        ]
        result = combiner.combine(ops)
        # CBF reduces uncertainty
        assert result.u < min(op.u for op in ops)

    def test_combine_with_source_trust(self, combiner):
        evidence = [
            {
                "opinion": {"b": 0.8, "d": 0.05, "u": 0.15, "a": 0.5},
                "source_type": "official_docs",
            },
            {
                "opinion": {"b": 0.3, "d": 0.4, "u": 0.3, "a": 0.5},
                "source_type": "stackoverflow",
            },
        ]
        result = combiner.combine_with_source_trust(evidence)
        # Official docs (trust=0.90) should outweigh SO (trust=0.60)
        assert result.b > 0.4

    def test_conservative_envelope_is_conservative(self, combiner):
        ops = [
            OpinionTuple(b=0.9, d=0.05, u=0.05, a=0.5),
            OpinionTuple(b=0.3, d=0.1, u=0.6, a=0.5),
        ]
        result = combiner._conservative_envelope(ops)
        # Conservative envelope takes min belief
        assert result.b <= 0.3 + 0.01


# ===========================================================================
# BM25Index
# ===========================================================================


class TestBM25Index:
    @pytest.fixture
    def index(self):
        idx = BM25Index()
        nodes = [
            {"id": "R1", "text": "Flask CORS security configuration", "technologies": ["flask"]},
            {"id": "R2", "text": "React component rendering patterns", "technologies": ["react"]},
            {"id": "R3", "text": "Python exception handling best practices", "technologies": ["python"]},
            {"id": "R4", "text": "Flask API rate limiting security", "technologies": ["flask"]},
        ]
        idx.index(nodes)
        return idx

    def test_index_size(self, index):
        assert index.size == 4

    def test_score_relevant(self, index):
        scores = index.score("Flask security")
        assert "R1" in scores
        assert "R4" in scores
        assert scores["R1"] > 0
        assert scores["R4"] > 0

    def test_score_irrelevant(self, index):
        scores = index.score("kubernetes deployment")
        # No nodes mention kubernetes
        assert not scores or all(v < 0.5 for v in scores.values())

    def test_flask_ranked_higher(self, index):
        scores = index.score("Flask CORS")
        assert "R1" in scores
        # R1 should rank highest (exact match on "Flask CORS")
        if "R2" in scores:
            assert scores["R1"] >= scores["R2"]

    def test_empty_query(self, index):
        scores = index.score("")
        assert scores == {}

    def test_empty_index(self):
        idx = BM25Index()
        idx.index([])
        assert idx.size == 0
        assert idx.score("anything") == {}


# ===========================================================================
# Personalized PageRank
# ===========================================================================


class TestPPR:
    def test_basic_ppr(self):
        adj = {
            "A": ["B", "C"],
            "B": ["A", "D"],
            "C": ["A"],
            "D": ["B"],
        }
        scores = personalized_pagerank(adj, seed_nodes=["A"])
        assert scores["A"] > scores["D"]  # A is seed, should have highest score

    def test_empty_graph(self):
        assert personalized_pagerank({}, ["A"]) == {}

    def test_empty_seeds(self):
        assert personalized_pagerank({"A": ["B"]}, []) == {}

    def test_disconnected_node(self):
        adj = {"A": ["B"], "B": ["A"]}
        scores = personalized_pagerank(adj, ["A"])
        # C is not in the graph but could be in edges
        assert "A" in scores
        assert "B" in scores

    def test_scores_sum_approximately_one(self):
        adj = {"A": ["B"], "B": ["A", "C"], "C": ["B"]}
        scores = personalized_pagerank(adj, ["A"])
        total = sum(scores.values())
        assert abs(total - 1.0) < 0.1

    def test_build_adjacency(self):
        edges = [
            {"from_id": "A", "to_id": "B"},
            {"from_id": "B", "to_id": "C"},
        ]
        adj = build_adjacency_from_edges(edges)
        assert "B" in adj["A"]
        assert "A" in adj["B"]  # Undirected
        assert "C" in adj["B"]
