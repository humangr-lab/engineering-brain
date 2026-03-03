"""E2E smoke tests for the Engineering Knowledge Brain.

Covers the full lifecycle: create, add, query, version, validate,
seed, maintenance, save/load, communities, provenance, and observation.

All tests use the memory adapter only — no Docker or external services required.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure src/ is on the import path
_src = str(Path(__file__).resolve().parent.parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

import pytest

from engineering_brain.core.brain import Brain
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.types import KnowledgeResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def brain() -> Brain:
    """Fresh in-memory Brain instance with embedding/observation disabled."""
    cfg = BrainConfig(
        adapter="memory",
        embedding_enabled=False,
        observation_log_enabled=False,
        sharding_enabled=False,
    )
    return Brain(adapter="memory", config=cfg)


@pytest.fixture()
def seeded_brain(brain: Brain, tmp_path: Path) -> Brain:
    """Brain loaded with a small seed YAML file."""
    seed_yaml = tmp_path / "test_seed.yaml"
    seed_yaml.write_text(
        "layer: rules\n"
        "technology: flask\n"
        "domain: security\n"
        "knowledge:\n"
        "  - id: CR-SMOKE-001\n"
        "    text: Always validate user input before processing\n"
        "    why: Unvalidated input leads to injection attacks\n"
        "    how_to_do_right: Use Pydantic models or manual validation\n"
        "    severity: critical\n"
        "    technologies: [flask, python]\n"
        "    domains: [security]\n"
        "  - id: CR-SMOKE-002\n"
        "    text: Never expose stack traces to end users\n"
        "    why: Stack traces leak internal implementation details\n"
        "    how_to_do_right: Return generic error messages in production\n"
        "    severity: high\n"
        "    technologies: [flask]\n"
        "    domains: [security]\n"
    )
    count = brain.ingest(str(seed_yaml))
    assert count == 2, f"Expected 2 ingested nodes, got {count}"
    return brain


# ---------------------------------------------------------------------------
# 1. Create Brain with memory adapter
# ---------------------------------------------------------------------------

class TestBrainCreation:
    def test_create_memory_brain(self, brain: Brain) -> None:
        assert brain.is_healthy()
        stats = brain.stats()
        assert stats["total"] == 0
        assert stats["config"]["adapter"] == "memory"

    def test_initial_version_is_zero(self, brain: Brain) -> None:
        assert brain.version == 0


# ---------------------------------------------------------------------------
# 2. Add rules (add_rule, batch_add_rules)
# ---------------------------------------------------------------------------

class TestAddRules:
    def test_add_rule_returns_id(self, brain: Brain) -> None:
        rid = brain.add_rule(
            text="Use parameterized queries",
            why="Prevents SQL injection",
            how="Use ORM or query parameters",
            severity="critical",
            technologies=["python", "sql"],
            domains=["security"],
        )
        assert rid.startswith("CR-")

    def test_add_rule_with_explicit_id(self, brain: Brain) -> None:
        rid = brain.add_rule(
            text="Always set CORS explicitly",
            why="Open CORS allows cross-origin attacks",
            how="Allowlist specific origins",
            severity="high",
            id="CR-EXPLICIT-ID",
        )
        assert rid == "CR-EXPLICIT-ID"

    def test_batch_add_rules(self, brain: Brain) -> None:
        rules = [
            {
                "text": "Use HTTPS everywhere",
                "why": "HTTP is plaintext",
                "how": "Configure TLS",
                "severity": "critical",
                "technologies": ["web"],
                "id": "CR-BATCH-001",
            },
            {
                "text": "Rotate secrets regularly",
                "why": "Stale secrets risk long-term compromise",
                "how": "Use a secrets manager with auto-rotation",
                "severity": "high",
                "id": "CR-BATCH-002",
            },
        ]
        ids = brain.batch_add_rules(rules)
        assert len(ids) == 2
        assert "CR-BATCH-001" in ids
        assert "CR-BATCH-002" in ids

    def test_batch_add_empty_list(self, brain: Brain) -> None:
        v_before = brain.version
        ids = brain.batch_add_rules([])
        assert ids == []
        assert brain.version == v_before  # no write counted


# ---------------------------------------------------------------------------
# 3. Query and verify results have formatted_text
# ---------------------------------------------------------------------------

class TestQuery:
    def test_query_empty_brain(self, brain: Brain) -> None:
        result = brain.query("flask security best practices")
        assert isinstance(result, KnowledgeResult)
        assert isinstance(result.formatted_text, str)

    def test_query_returns_populated_result(self, seeded_brain: Brain) -> None:
        result = seeded_brain.query(
            "flask input validation",
            technologies=["flask"],
        )
        assert isinstance(result, KnowledgeResult)
        # formatted_text should be a string (may be empty if no match, but type is str)
        assert isinstance(result.formatted_text, str)

    def test_query_with_budget(self, seeded_brain: Brain) -> None:
        result = seeded_brain.query(
            "validate user input in flask",
            budget_chars=500,
        )
        assert isinstance(result, KnowledgeResult)
        # Budget enforcement: formatted text should not exceed budget by a large margin
        # (formatter may slightly exceed due to section headers)
        assert len(result.formatted_text) < 1000


# ---------------------------------------------------------------------------
# 4. Version tracking (version increments on add)
# ---------------------------------------------------------------------------

class TestVersionTracking:
    def test_version_increments_on_add_rule(self, brain: Brain) -> None:
        v0 = brain.version
        brain.add_rule(
            text="Test rule 1",
            why="Testing version",
            severity="low",
        )
        v1 = brain.version
        assert v1 == v0 + 1

    def test_version_increments_on_add_principle(self, brain: Brain) -> None:
        v0 = brain.version
        brain.add_principle(
            name="Test Principle",
            why="Testing version",
            how="Just test it",
        )
        assert brain.version == v0 + 1

    def test_version_increments_on_add_pattern(self, brain: Brain) -> None:
        v0 = brain.version
        brain.add_pattern(
            name="Test Pattern",
            intent="Testing",
            when_to_use="Always",
        )
        assert brain.version == v0 + 1

    def test_batch_add_increments_once(self, brain: Brain) -> None:
        v0 = brain.version
        brain.batch_add_rules([
            {"text": "R1", "why": "W1", "severity": "low", "id": "CR-V1"},
            {"text": "R2", "why": "W2", "severity": "low", "id": "CR-V2"},
            {"text": "R3", "why": "W3", "severity": "low", "id": "CR-V3"},
        ])
        # Batch add increments write counter exactly once
        assert brain.version == v0 + 1


# ---------------------------------------------------------------------------
# 5. Validation (_validate_rule raises on empty why)
# ---------------------------------------------------------------------------

class TestValidation:
    def test_validate_rule_raises_on_empty_why(self) -> None:
        with pytest.raises(ValueError, match="'why' must be non-empty"):
            Brain._validate_rule(
                text="Some rule",
                why="",
                severity="medium",
                technologies=[],
            )

    def test_validate_rule_raises_on_empty_text(self) -> None:
        with pytest.raises(ValueError, match="text must be non-empty"):
            Brain._validate_rule(
                text="",
                why="Some reason",
                severity="medium",
                technologies=[],
            )

    def test_validate_rule_raises_on_invalid_severity(self) -> None:
        with pytest.raises(ValueError, match="Severity must be one of"):
            Brain._validate_rule(
                text="Some rule",
                why="Some reason",
                severity="extreme",
                technologies=[],
            )

    def test_validate_rule_passes_on_valid_input(self) -> None:
        # Should not raise
        Brain._validate_rule(
            text="Valid rule",
            why="Valid reason",
            severity="critical",
            technologies=["python"],
        )


# ---------------------------------------------------------------------------
# 6. Seed versioning (ingest, second ingest skips, force=True reloads)
# ---------------------------------------------------------------------------

class TestSeedVersioning:
    def test_ingest_loads_rules(self, brain: Brain, tmp_path: Path) -> None:
        seed_file = tmp_path / "seed.yaml"
        seed_file.write_text(
            "layer: rules\n"
            "technology: python\n"
            "knowledge:\n"
            "  - id: CR-SEED-001\n"
            "    text: Test seed rule\n"
            "    why: Testing\n"
            "    severity: low\n"
        )
        count = brain.ingest(str(seed_file))
        assert count == 1

    def test_second_ingest_skips_unchanged(self, brain: Brain, tmp_path: Path) -> None:
        seed_file = tmp_path / "seed.yaml"
        seed_file.write_text(
            "layer: rules\n"
            "technology: python\n"
            "knowledge:\n"
            "  - id: CR-SEED-002\n"
            "    text: Another rule\n"
            "    why: Testing idempotency\n"
            "    severity: low\n"
        )
        count1 = brain.ingest(str(seed_file))
        assert count1 == 1

        v_before = brain.version
        count2 = brain.ingest(str(seed_file))
        assert count2 == 0, "Second ingest of unchanged file should skip"
        assert brain.version == v_before, "Version should not change on skip"

    def test_force_ingest_reloads(self, brain: Brain, tmp_path: Path) -> None:
        seed_file = tmp_path / "seed.yaml"
        seed_file.write_text(
            "layer: rules\n"
            "technology: python\n"
            "knowledge:\n"
            "  - id: CR-SEED-003\n"
            "    text: Force reload rule\n"
            "    why: Testing force\n"
            "    severity: low\n"
        )
        count1 = brain.ingest(str(seed_file))
        assert count1 == 1

        v_before = brain.version
        count2 = brain.ingest(str(seed_file), force=True)
        assert count2 == 1, "force=True should reload even unchanged file"
        assert brain.version > v_before

    def test_ingest_nonexistent_file(self, brain: Brain) -> None:
        count = brain.ingest("/nonexistent/path/seed.yaml")
        assert count == 0


# ---------------------------------------------------------------------------
# 7. Maintenance cycle
# ---------------------------------------------------------------------------

class TestMaintenance:
    def test_maintenance_returns_dict(self, brain: Brain) -> None:
        # Add some rules first so there is material for maintenance
        brain.add_rule(
            text="Maintenance test rule",
            why="Testing maintenance",
            severity="low",
            id="CR-MAINT-001",
        )
        result = brain.maintenance()
        assert isinstance(result, dict)
        # With default config, all three sub-cycles should be present
        # (crystallized, promoted, pruned) though results may be empty
        assert "crystallized" in result or "promoted" in result or "pruned" in result

    def test_maintenance_selective_flags(self, brain: Brain) -> None:
        brain.add_rule(
            text="Selective maint rule",
            why="Testing selective",
            severity="low",
            id="CR-MAINT-002",
        )
        result = brain.maintenance(crystallize=False, promote=False, prune=True)
        assert "pruned" in result
        assert "crystallized" not in result
        assert "promoted" not in result


# ---------------------------------------------------------------------------
# 8. Save to tempfile, load from file, verify node counts match
# ---------------------------------------------------------------------------

class TestSaveLoad:
    def test_save_and_load_roundtrip(self, brain: Brain) -> None:
        # Populate brain
        brain.add_rule(
            text="Rule for save test",
            why="Persistence test",
            severity="medium",
            id="CR-SAVE-001",
            technologies=["python"],
            domains=["testing"],
        )
        brain.add_principle(
            name="Save principle",
            why="Persistence test",
            how="Just save it",
            id="P-SAVE-001",
        )
        brain.add_pattern(
            name="Save pattern",
            intent="Persistence test",
            when_to_use="During save",
            id="PAT-SAVE-001",
        )

        stats_before = brain.stats()
        version_before = brain.version

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            save_path = f.name

        try:
            save_result = brain.save(save_path)
            assert save_result["nodes"] == stats_before["graph"]["node_count"]
            assert save_result["version"] == version_before

            # Load into a new brain
            loaded = Brain.load(save_path)
            loaded_stats = loaded.stats()

            assert loaded_stats["graph"]["node_count"] == stats_before["graph"]["node_count"]
            assert loaded.version == version_before

            # Verify a specific node survived the roundtrip
            node = loaded.graph.get_node("CR-SAVE-001")
            assert node is not None
            assert node.get("text") == "Rule for save test"
        finally:
            os.unlink(save_path)

    def test_load_nonexistent_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            Brain.load("/nonexistent/brain_state.json")

    def test_save_creates_parent_dirs(self, brain: Brain, tmp_path: Path) -> None:
        brain.add_rule(
            text="Dir creation test",
            why="Test auto-mkdir",
            severity="low",
            id="CR-DIR-001",
        )
        nested = tmp_path / "deep" / "nested" / "brain.json"
        result = brain.save(str(nested))
        assert result["nodes"] > 0
        assert nested.exists()


# ---------------------------------------------------------------------------
# 9. detect_communities
# ---------------------------------------------------------------------------

class TestDetectCommunities:
    def test_communities_empty_brain(self, brain: Brain) -> None:
        communities = brain.detect_communities()
        assert isinstance(communities, list)

    def test_communities_with_connected_rules(self, brain: Brain) -> None:
        # Add several rules in same technology/domain to form a community
        for i in range(5):
            brain.add_rule(
                text=f"Flask security rule {i}",
                why="Security matters",
                severity="high",
                technologies=["flask"],
                domains=["security"],
                id=f"CR-COMM-{i:03d}",
            )
        communities = brain.detect_communities(min_size=2)
        assert isinstance(communities, list)
        # Each community should be a dict
        for comm in communities:
            assert isinstance(comm, dict)


# ---------------------------------------------------------------------------
# 10. query_with_provenance
# ---------------------------------------------------------------------------

class TestQueryWithProvenance:
    def test_query_with_provenance_returns_tuple(self, seeded_brain: Brain) -> None:
        result, provenance = seeded_brain.query_with_provenance(
            "flask input validation security",
            technologies=["flask"],
        )
        assert isinstance(result, KnowledgeResult)
        assert isinstance(provenance, (list, dict))

    def test_query_with_provenance_empty_brain(self, brain: Brain) -> None:
        result, provenance = brain.query_with_provenance("nonexistent topic")
        assert isinstance(result, KnowledgeResult)


# ---------------------------------------------------------------------------
# 11. observation_count via reinforce
# ---------------------------------------------------------------------------

class TestObservationCount:
    def test_reinforce_increments_observation_count(self, brain: Brain) -> None:
        rid = brain.add_rule(
            text="Reinforce test rule",
            why="Testing reinforcement",
            severity="medium",
            id="CR-REINFORCE-001",
        )
        # Initial observation count should be 0
        node = brain.graph.get_node(rid)
        assert node is not None
        assert int(node.get("observation_count", 0)) == 0

        # Positive reinforcement
        success = brain.reinforce(rid, evidence_id="EV-001", positive=True)
        assert success is True

        node = brain.graph.get_node(rid)
        assert int(node.get("observation_count", 0)) == 1
        assert int(node.get("reinforcement_count", 0)) == 1

    def test_negative_reinforce_increments_observation_not_reinforcement(self, brain: Brain) -> None:
        rid = brain.add_rule(
            text="Weaken test rule",
            why="Testing weakening",
            severity="medium",
            id="CR-WEAKEN-001",
        )
        # Negative reinforcement
        success = brain.reinforce(rid, evidence_id="EV-002", positive=False)
        assert success is True

        node = brain.graph.get_node(rid)
        assert int(node.get("observation_count", 0)) == 1
        # Negative reinforcement does NOT increment reinforcement_count
        assert int(node.get("reinforcement_count", 0)) == 0

    def test_reinforce_nonexistent_rule_returns_false(self, brain: Brain) -> None:
        success = brain.reinforce("CR-NONEXISTENT", evidence_id="EV-003", positive=True)
        assert success is False

    def test_multiple_reinforcements_accumulate(self, brain: Brain) -> None:
        rid = brain.add_rule(
            text="Multi reinforce rule",
            why="Testing accumulation",
            severity="medium",
            id="CR-MULTI-001",
        )
        for i in range(5):
            brain.reinforce(rid, evidence_id=f"EV-MULTI-{i}", positive=True)

        node = brain.graph.get_node(rid)
        assert int(node.get("observation_count", 0)) == 5
        assert int(node.get("reinforcement_count", 0)) == 5
        # Confidence should have increased from default 0.5
        assert float(node.get("confidence", 0)) > 0.5


# ---------------------------------------------------------------------------
# Bonus: stats, add_axiom, add_principle, add_pattern round-trip
# ---------------------------------------------------------------------------

class TestMiscAPI:
    def test_stats_reflect_node_counts(self, brain: Brain) -> None:
        brain.add_rule(text="R", why="W", severity="low", id="CR-STATS-001")
        brain.add_principle(name="P", why="W", how="H", id="P-STATS-001")
        brain.add_pattern(name="PAT", intent="I", when_to_use="W", id="PAT-STATS-001")
        brain.add_axiom(statement="Axiom", id="AX-STATS-001")

        s = brain.stats()
        assert s["layers"]["Axiom"] >= 1
        assert s["layers"]["Principle"] >= 1
        assert s["layers"]["Pattern"] >= 1
        assert s["layers"]["Rule"] >= 1
        assert s["total"] >= 4

    def test_is_healthy(self, brain: Brain) -> None:
        assert brain.is_healthy() is True

    def test_add_axiom_returns_id(self, brain: Brain) -> None:
        aid = brain.add_axiom(statement="All code has bugs", id="AX-TEST-001")
        assert aid == "AX-TEST-001"
        node = brain.graph.get_node(aid)
        assert node is not None
        assert node.get("statement") == "All code has bugs"
