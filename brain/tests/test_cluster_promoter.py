"""Tests for the cluster-based additive crystallization module."""

from __future__ import annotations

import hashlib

import pytest

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.core.brain import Brain
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import NodeType
from engineering_brain.learning.cluster_promoter import (
    ClusterPromoter,
    _extract_terms,
    _jaccard,
    _text_term_overlap,
)

# ---------------------------------------------------------------------------
# Helper to create rules
# ---------------------------------------------------------------------------


def _make_rule(
    graph: MemoryGraphAdapter,
    rule_id: str,
    text: str,
    why: str = "why",
    technologies: list[str] | None = None,
    domains: list[str] | None = None,
    reinforcement_count: int = 10,
    confidence: float = 0.7,
    **extra,
) -> dict:
    data = {
        "id": rule_id,
        "text": text,
        "why": why,
        "how_to_do_right": "",
        "severity": "medium",
        "technologies": technologies or [],
        "domains": domains or [],
        "reinforcement_count": reinforcement_count,
        "confidence": confidence,
        **extra,
    }
    graph.add_node(NodeType.RULE.value, rule_id, data)
    return data


def _config(**overrides) -> BrainConfig:
    defaults = {
        "crystallize_enabled": True,
        "crystallize_min_similarity": 0.35,
        "crystallize_min_cluster_size": 3,
        "crystallize_min_reinforcements": 5,
        "crystallize_min_confidence": 0.5,
    }
    defaults.update(overrides)
    cfg = BrainConfig()
    for k, v in defaults.items():
        setattr(cfg, k, v)
    return cfg


# ---------------------------------------------------------------------------
# Unit tests for similarity helpers
# ---------------------------------------------------------------------------


class TestSimilarityHelpers:
    def test_jaccard_identical(self):
        assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_jaccard_disjoint(self):
        assert _jaccard({"a"}, {"b"}) == 0.0

    def test_jaccard_partial(self):
        assert _jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)

    def test_jaccard_empty(self):
        assert _jaccard(set(), set()) == 0.0

    def test_extract_terms(self):
        terms = _extract_terms("Always validate user input before processing")
        assert "validate" in terms
        assert "input" in terms
        assert "processing" in terms
        # Stop words excluded
        assert "always" not in terms
        assert "before" not in terms

    def test_text_term_overlap_identical(self):
        assert _text_term_overlap("validate CORS origins", "validate CORS origins") == 1.0

    def test_text_term_overlap_disjoint(self):
        assert _text_term_overlap("flask server", "react component") == 0.0

    def test_text_term_overlap_partial(self):
        overlap = _text_term_overlap(
            "validate CORS allowed origins in Flask",
            "validate CORS configuration for security",
        )
        assert overlap > 0.0


# ---------------------------------------------------------------------------
# Cluster crystallization tests
# ---------------------------------------------------------------------------


class TestClusterPromoter:
    def test_basic_cluster_creation(self):
        """3 rules with same tech + overlapping text → 1 pattern."""
        graph = MemoryGraphAdapter()
        cfg = _config()
        for i in range(3):
            _make_rule(
                graph,
                f"CR-CORS-{i:03d}",
                text=f"Validate CORS origins configuration rule {i}",
                why="CORS misconfiguration leads to security vulnerabilities",
                technologies=["flask"],
                domains=["security"],
            )

        cp = ClusterPromoter(graph, cfg)
        created = cp.crystallize()
        assert len(created) == 1
        assert created[0].startswith("CPAT-")

        # Verify pattern exists in graph
        pattern = graph.get_node(created[0])
        assert pattern is not None
        assert pattern["category"] == "crystallized"
        assert pattern["_cluster_size"] == 3

    def test_idempotent_crystallization(self):
        """Running crystallize() twice produces same result."""
        graph = MemoryGraphAdapter()
        cfg = _config()
        for i in range(3):
            _make_rule(
                graph,
                f"CR-DUP-{i:03d}",
                text=f"Duplicate detection test rule {i}",
                why="Testing idempotency of clustering",
                technologies=["python"],
                domains=["testing"],
            )

        cp = ClusterPromoter(graph, cfg)
        first_run = cp.crystallize()
        second_run = cp.crystallize()
        assert first_run == second_run
        # Only one pattern in graph
        patterns = graph.query(label=NodeType.PATTERN.value, limit=100)
        cpat_patterns = [p for p in patterns if p.get("id", "").startswith("CPAT-")]
        assert len(cpat_patterns) == 1

    def test_minimum_cluster_size(self):
        """Only 2 rules → no cluster (min_cluster_size=3)."""
        graph = MemoryGraphAdapter()
        cfg = _config()
        for i in range(2):
            _make_rule(
                graph,
                f"CR-SMALL-{i:03d}",
                text=f"Small cluster rule {i}",
                technologies=["flask"],
                domains=["security"],
            )

        cp = ClusterPromoter(graph, cfg)
        assert cp.crystallize() == []

    def test_disjoint_clusters(self):
        """6 rules: 3 about Flask CORS, 3 about React hooks → 2 patterns."""
        graph = MemoryGraphAdapter()
        cfg = _config()

        # Cluster 1: Flask CORS
        for i in range(3):
            _make_rule(
                graph,
                f"CR-FLASK-{i:03d}",
                text=f"Flask CORS origin validation rule number {i}",
                why="CORS security misconfiguration risk",
                technologies=["flask"],
                domains=["security"],
            )

        # Cluster 2: React hooks
        for i in range(3):
            _make_rule(
                graph,
                f"CR-REACT-{i:03d}",
                text=f"React hooks state management pattern {i}",
                why="React state consistency and performance",
                technologies=["react"],
                domains=["ui"],
            )

        cp = ClusterPromoter(graph, cfg)
        created = cp.crystallize()
        assert len(created) == 2

        # Verify both are CPAT patterns
        for pid in created:
            assert pid.startswith("CPAT-")
            pattern = graph.get_node(pid)
            assert pattern["_cluster_size"] == 3

    def test_ineligible_rules_excluded(self):
        """Rules below thresholds are not clustered."""
        graph = MemoryGraphAdapter()
        cfg = _config()

        # Low reinforcement rules
        for i in range(3):
            _make_rule(
                graph,
                f"CR-LOW-{i:03d}",
                text=f"Low reinforcement rule {i}",
                technologies=["flask"],
                domains=["security"],
                reinforcement_count=1,  # Below min_reinforcements=5
                confidence=0.3,  # Below min_confidence=0.5
            )

        cp = ClusterPromoter(graph, cfg)
        assert cp.crystallize() == []

    def test_deterministic_pattern_id(self):
        """Pattern ID is deterministic from sorted member rule IDs."""
        graph = MemoryGraphAdapter()
        cfg = _config()

        rule_ids = ["CR-A-001", "CR-A-002", "CR-A-003"]
        for rid in rule_ids:
            _make_rule(
                graph,
                rid,
                text="Identical text for deterministic test",
                technologies=["python"],
                domains=["general"],
            )

        # Compute expected ID
        fingerprint = "|".join(sorted(rule_ids))
        expected_hash = hashlib.sha256(fingerprint.encode()).hexdigest()[:10]
        expected_id = f"CPAT-{expected_hash}"

        cp = ClusterPromoter(graph, cfg)
        created = cp.crystallize()
        assert len(created) == 1
        assert created[0] == expected_id

    def test_shared_technologies(self):
        """Pattern's languages = technologies shared by >50% of members."""
        graph = MemoryGraphAdapter()
        cfg = _config()

        _make_rule(
            graph,
            "CR-T-001",
            text="Path validation security check rule",
            technologies=["flask", "python"],
            domains=["security"],
        )
        _make_rule(
            graph,
            "CR-T-002",
            text="Path validation security vulnerability check",
            technologies=["flask", "python"],
            domains=["security"],
        )
        _make_rule(
            graph,
            "CR-T-003",
            text="Path validation security access control",
            technologies=["flask"],
            domains=["security"],
        )

        cp = ClusterPromoter(graph, cfg)
        created = cp.crystallize()
        assert len(created) == 1

        pattern = graph.get_node(created[0])
        # flask appears in all 3, python in 2/3 (>50%)
        assert "flask" in pattern["languages"]

    def test_original_rules_preserved(self):
        """After crystallization, all original rules still exist unchanged."""
        graph = MemoryGraphAdapter()
        cfg = _config()

        originals = {}
        for i in range(3):
            rid = f"CR-PRES-{i:03d}"
            data = _make_rule(
                graph,
                rid,
                text=f"Preservation test rule {i}",
                technologies=["python"],
                domains=["testing"],
            )
            originals[rid] = data.copy()

        rules_before = graph.count(NodeType.RULE.value)
        cp = ClusterPromoter(graph, cfg)
        cp.crystallize()
        rules_after = graph.count(NodeType.RULE.value)

        # Rule count unchanged
        assert rules_before == rules_after

        # Each rule's data unchanged
        for rid, original in originals.items():
            current = graph.get_node(rid)
            assert current["text"] == original["text"]
            assert current["technologies"] == original["technologies"]
            assert current["reinforcement_count"] == original["reinforcement_count"]

    def test_epistemic_aggregation(self):
        """Cluster pattern gets aggregated epistemic opinion."""
        graph = MemoryGraphAdapter()
        cfg = _config()

        for i in range(3):
            _make_rule(
                graph,
                f"CR-EP-{i:03d}",
                text=f"Epistemic aggregation test rule {i}",
                technologies=["python"],
                domains=["testing"],
                ep_b=0.7,
                ep_d=0.05,
                ep_u=0.25,
                ep_a=0.5,
            )

        cp = ClusterPromoter(graph, cfg)
        created = cp.crystallize()
        assert len(created) == 1

        pattern = graph.get_node(created[0])
        assert pattern.get("ep_b") is not None
        assert pattern["ep_b"] > 0
        assert pattern["ep_d"] >= 0
        assert pattern["ep_u"] > 0
        # b + d + u ≈ 1
        total = pattern["ep_b"] + pattern["ep_d"] + pattern["ep_u"]
        assert abs(total - 1.0) < 0.01

    def test_backward_compat_promote_api(self):
        """brain.promote() runs both single-rule and cluster promotion."""
        brain = Brain()
        cfg = brain._config
        cfg.crystallize_enabled = True
        cfg.crystallize_min_reinforcements = 5
        cfg.crystallize_min_confidence = 0.5
        cfg.crystallize_min_cluster_size = 3

        # Add 3 similar rules eligible for cluster promotion
        for i in range(3):
            brain.add_rule(
                text=f"Test backward compat rule {i}",
                why="Backward compatibility testing",
                how="Test properly",
                technologies=["python"],
                domains=["testing"],
                id=f"CR-BC-{i:03d}",
                reinforcement_count=10,
                confidence=0.7,
            )

        promoted = brain.promote()
        cpat_ids = [p for p in promoted if p.startswith("CPAT-")]
        assert len(cpat_ids) >= 1

    def test_empty_graph(self):
        """No rules in graph → empty result, no errors."""
        graph = MemoryGraphAdapter()
        cfg = _config()
        cp = ClusterPromoter(graph, cfg)
        assert cp.crystallize() == []

    def test_similarity_threshold_respected(self):
        """Rules with low overlap are not clustered together."""
        graph = MemoryGraphAdapter()
        cfg = _config(crystallize_min_similarity=0.8)  # Very high threshold

        # Three rules with different technologies and text
        _make_rule(
            graph,
            "CR-DIV-001",
            text="Flask CORS security",
            technologies=["flask"],
            domains=["security"],
        )
        _make_rule(
            graph,
            "CR-DIV-002",
            text="React hooks lifecycle",
            technologies=["react"],
            domains=["ui"],
        )
        _make_rule(
            graph,
            "CR-DIV-003",
            text="Docker compose networking",
            technologies=["docker"],
            domains=["devops"],
        )

        cp = ClusterPromoter(graph, cfg)
        assert cp.crystallize() == []

    def test_coexistence_with_single_rule_promotion(self):
        """A rule can have both PAT- and CPAT- patterns."""
        brain = Brain()
        cfg = brain._config
        cfg.crystallize_enabled = True
        cfg.crystallize_min_reinforcements = 5
        cfg.crystallize_min_confidence = 0.5
        cfg.crystallize_min_cluster_size = 3
        cfg.promote_l3_to_l2_threshold = 10

        # Add 3 rules: one meets single-rule threshold too
        brain.add_rule(
            text="High reinforcement CORS validation rule",
            why="Security vulnerability prevention",
            how="Validate origins",
            technologies=["flask"],
            domains=["security"],
            id="CR-COEX-001",
            reinforcement_count=25,
            confidence=0.9,
        )
        brain.add_rule(
            text="CORS validation security check rule",
            why="Security vulnerability prevention",
            how="Check origins",
            technologies=["flask"],
            domains=["security"],
            id="CR-COEX-002",
            reinforcement_count=10,
            confidence=0.7,
        )
        brain.add_rule(
            text="CORS security validation enforcement rule",
            why="Security vulnerability prevention",
            how="Enforce origins",
            technologies=["flask"],
            domains=["security"],
            id="CR-COEX-003",
            reinforcement_count=10,
            confidence=0.7,
        )

        promoted = brain.promote()
        # Should have both PAT- (from single-rule) and CPAT- (from cluster)
        pat_ids = [p for p in promoted if p.startswith("PAT-")]
        cpat_ids = [p for p in promoted if p.startswith("CPAT-")]
        assert len(pat_ids) >= 1
        assert len(cpat_ids) >= 1

    def test_pattern_fields_populated(self):
        """Verify all expected fields are populated on crystallized pattern."""
        graph = MemoryGraphAdapter()
        cfg = _config()

        for i in range(3):
            _make_rule(
                graph,
                f"CR-FLD-{i:03d}",
                text=f"Field population test rule number {i}",
                why="Testing field extraction",
                technologies=["flask"],
                domains=["security"],
                confidence=0.7 + i * 0.05,
            )

        cp = ClusterPromoter(graph, cfg)
        created = cp.crystallize()
        assert len(created) == 1

        pattern = graph.get_node(created[0])
        assert pattern["id"].startswith("CPAT-")
        assert pattern["category"] == "crystallized"
        assert pattern["name"]  # Non-empty
        assert pattern["intent"]  # Non-empty (from why merge)
        assert isinstance(pattern["languages"], list)
        assert isinstance(pattern["_crystallized_from"], list)
        assert len(pattern["_crystallized_from"]) == 3
        assert pattern["_cluster_size"] == 3
        assert 0 < pattern["_crystallization_confidence"] <= 1.0

    def test_brain_crystallize_convenience(self):
        """brain.crystallize() works as standalone method."""
        brain = Brain()
        brain._config.crystallize_enabled = True
        brain._config.crystallize_min_reinforcements = 5
        brain._config.crystallize_min_cluster_size = 3

        for i in range(3):
            brain.add_rule(
                text=f"Convenience test rule {i}",
                why="Testing convenience API",
                how="Do it",
                technologies=["python"],
                domains=["testing"],
                id=f"CR-CONV-{i:03d}",
                reinforcement_count=10,
                confidence=0.7,
            )

        created = brain.crystallize()
        assert len(created) >= 1
        assert all(c.startswith("CPAT-") for c in created)

    def test_crystallize_disabled(self):
        """No patterns created when crystallize_enabled=False."""
        brain = Brain()
        brain._config.crystallize_enabled = False

        for i in range(3):
            brain.add_rule(
                text=f"Disabled test rule {i}",
                why="Testing disabled flag",
                how="Don't",
                technologies=["python"],
                id=f"CR-DIS-{i:03d}",
                reinforcement_count=10,
                confidence=0.7,
            )

        assert brain.crystallize() == []

    def test_deprecated_rules_excluded(self):
        """Deprecated (soft-deleted) rules are NOT included in clustering."""
        graph = MemoryGraphAdapter()
        cfg = _config()

        # 3 eligible rules + 1 deprecated
        for i in range(3):
            _make_rule(
                graph,
                f"CR-DEP-{i:03d}",
                text=f"Deprecated exclusion test rule {i}",
                technologies=["flask"],
                domains=["security"],
            )
        _make_rule(
            graph,
            "CR-DEP-003",
            text="Deprecated exclusion test rule 3",
            technologies=["flask"],
            domains=["security"],
            deprecated=True,
        )

        cp = ClusterPromoter(graph, cfg)
        created = cp.crystallize()
        # Should cluster only the 3 non-deprecated rules
        assert len(created) == 1
        pattern = graph.get_node(created[0])
        assert pattern["_cluster_size"] == 3
        assert "CR-DEP-003" not in pattern["_crystallized_from"]


# ---------------------------------------------------------------------------
# LLM Cluster Promoter
# ---------------------------------------------------------------------------

import os
from unittest import mock


class TestLLMClusterPromoter:
    """Tests for LLM-enhanced cluster promotion functions."""

    def test_synthesize_name_flag_off(self) -> None:
        """LLM name synthesis skipped when flag is off."""
        graph = MemoryGraphAdapter()
        cfg = BrainConfig()
        cp = ClusterPromoter(graph, cfg)
        cluster = [{"text": "rule 1"}, {"text": "rule 2"}]

        with mock.patch.dict(os.environ, {}, clear=True):
            result = cp._llm_synthesize_name(cluster)
            assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_synthesize_name_success(self, mock_flag, mock_llm) -> None:
        """Returns pattern name when LLM succeeds."""
        mock_llm.return_value = "Secure Input Validation Pattern"
        graph = MemoryGraphAdapter()
        cfg = BrainConfig()
        cp = ClusterPromoter(graph, cfg)
        cluster = [{"text": "validate all inputs"}, {"text": "sanitize user data"}]

        result = cp._llm_synthesize_name(cluster)
        assert result == "Secure Input Validation Pattern"

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_synthesize_name_too_many_words(self, mock_flag, mock_llm) -> None:
        """Returns None when LLM generates name with > 10 words."""
        mock_llm.return_value = "This Name Has Way Too Many Words To Be A Good Pattern Name Ever"
        graph = MemoryGraphAdapter()
        cfg = BrainConfig()
        cp = ClusterPromoter(graph, cfg)

        result = cp._llm_synthesize_name([{"text": "r1"}, {"text": "r2"}])
        assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_synthesize_name_failure(self, mock_flag, mock_llm) -> None:
        """Returns None when LLM call fails."""
        mock_llm.return_value = None
        graph = MemoryGraphAdapter()
        cfg = BrainConfig()
        cp = ClusterPromoter(graph, cfg)

        result = cp._llm_synthesize_name([{"text": "r1"}])
        assert result is None

    def test_synthesize_intent_flag_off(self) -> None:
        """LLM intent synthesis skipped when flag is off."""
        graph = MemoryGraphAdapter()
        cfg = BrainConfig()
        cp = ClusterPromoter(graph, cfg)
        cluster = [{"text": "rule 1"}]

        with mock.patch.dict(os.environ, {}, clear=True):
            result = cp._llm_synthesize_intent(cluster)
            assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_synthesize_intent_success(self, mock_flag, mock_llm) -> None:
        """Returns intent sentence when LLM succeeds."""
        mock_llm.return_value = "Ensure all user inputs are validated before processing."
        graph = MemoryGraphAdapter()
        cfg = BrainConfig()
        cp = ClusterPromoter(graph, cfg)

        result = cp._llm_synthesize_intent([{"text": "r1"}, {"text": "r2"}])
        assert result is not None
        assert "validated" in result.lower()

    def test_merge_field_flag_off(self) -> None:
        """LLM merge field skipped when flag is off."""
        graph = MemoryGraphAdapter()
        cfg = BrainConfig()
        cp = ClusterPromoter(graph, cfg)
        cluster = [{"why": "reason 1"}, {"why": "reason 2"}]

        with mock.patch.dict(os.environ, {}, clear=True):
            result = cp._llm_merge_field(cluster, "why", "shared intent")
            assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_merge_field_success(self, mock_flag, mock_llm) -> None:
        """Returns merged field text when LLM succeeds."""
        mock_llm.return_value = (
            "Prevent security vulnerabilities through systematic input validation."
        )
        graph = MemoryGraphAdapter()
        cfg = BrainConfig()
        cp = ClusterPromoter(graph, cfg)
        cluster = [{"why": "prevent XSS"}, {"why": "prevent SQL injection"}]

        result = cp._llm_merge_field(cluster, "why", "shared intent")
        assert result is not None
        assert len(result) <= 400

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_merge_field_too_long(self, mock_flag, mock_llm) -> None:
        """Returns None when LLM response exceeds 400 chars."""
        mock_llm.return_value = "x" * 500
        graph = MemoryGraphAdapter()
        cfg = BrainConfig()
        cp = ClusterPromoter(graph, cfg)

        result = cp._llm_merge_field([{"why": "r1"}], "why")
        assert result is None

    @mock.patch("engineering_brain.llm_helpers.brain_llm_call")
    @mock.patch("engineering_brain.llm_helpers.is_llm_enabled", return_value=True)
    def test_merge_field_failure(self, mock_flag, mock_llm) -> None:
        """Returns None when LLM call fails."""
        mock_llm.return_value = None
        graph = MemoryGraphAdapter()
        cfg = BrainConfig()
        cp = ClusterPromoter(graph, cfg)

        result = cp._llm_merge_field([{"why": "r1"}], "why")
        assert result is None
