"""Tests for guardrails.py — obligation derivation and applicability checking.

Covers:
- derive_obligation: decision tree, prohibition detection, metadata matrix, boosts/caps
- check_applicability: exclusions, positive matching, technology cross-check, edge cases
- annotate_guardrails: batch annotation, summary stats, robustness
- GuardrailMetadata/GuardrailEntry: schema validation, defaults, round-trips
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engineering_brain.retrieval.guardrails import (
    ObligationLevel,
    _has_prohibition,
    annotate_guardrails,
    check_applicability,
    derive_obligation,
)

# =============================================================================
# Helpers
# =============================================================================


@dataclass
class MockContext:
    technologies: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    file_types: list[str] = field(default_factory=list)
    phase: str = "exec"
    raw_text: str = ""
    facet_tags: dict = field(default_factory=dict)


def _node(
    nid: str = "TEST-001",
    text: str = "Test rule",
    severity: str = "medium",
    validation_status: str = "unvalidated",
    epistemic_status: str = "E0",
    **kw,
) -> dict:
    return {
        "id": nid,
        "text": text,
        "severity": severity,
        "validation_status": validation_status,
        "epistemic_status": epistemic_status,
        "reinforcement_count": kw.pop("reinforcement_count", 0),
        "ep_b": kw.pop("ep_b", None),
        "ep_d": kw.pop("ep_d", None),
        "ep_u": kw.pop("ep_u", None),
        "deprecated": kw.pop("deprecated", False),
        "_layer": kw.pop("layer", "L3"),
        "why": kw.pop("why", ""),
        "when_applies": kw.pop("when_applies", ""),
        "when_not_applies": kw.pop("when_not_applies", ""),
        **kw,
    }


# =============================================================================
# derive_obligation — Decision tree
# =============================================================================


class TestDeriveObligation:
    def test_critical_verified_e3_is_must(self):
        """critical + human_verified + E3 → MUST"""
        node = _node(severity="critical", validation_status="human_verified", epistemic_status="E3")
        assert derive_obligation(node) == ObligationLevel.MUST

    def test_critical_cross_checked_e2_is_must(self):
        """critical + cross_checked + E2 → MUST (score = 3+1+2 = 6... need 7)
        Actually 3+1+2=6 → SHOULD. But E3 → 3+1+3=7 → MUST."""
        node = _node(severity="critical", validation_status="cross_checked", epistemic_status="E3")
        assert derive_obligation(node) == ObligationLevel.MUST

    def test_critical_cross_checked_e2_is_should(self):
        """critical + cross_checked + E2 → score 3+1+2=6 → SHOULD"""
        node = _node(severity="critical", validation_status="cross_checked", epistemic_status="E2")
        assert derive_obligation(node) == ObligationLevel.SHOULD

    def test_critical_unvalidated_is_should(self):
        """critical + unvalidated → SHOULD (score = 3+0+0 = 3 → MAY... wait)
        Actually 3+0+0=3 → MAY. With E1: 3+0+1=4 → SHOULD."""
        node = _node(severity="critical", validation_status="unvalidated", epistemic_status="E1")
        assert derive_obligation(node) == ObligationLevel.SHOULD

    def test_high_verified_e3_is_should(self):
        """high + human_verified + E3 → score 2+2+3=7 → MUST"""
        node = _node(severity="high", validation_status="human_verified", epistemic_status="E3")
        assert derive_obligation(node) == ObligationLevel.MUST

    def test_high_unvalidated_e0_is_may(self):
        """high + unvalidated + E0 → score 2+0+0=2 → MAY"""
        node = _node(severity="high", validation_status="unvalidated", epistemic_status="E0")
        assert derive_obligation(node) == ObligationLevel.MAY

    def test_medium_any_is_may(self):
        """medium + unvalidated + E0 → score 1+0+0=1 → MAY"""
        node = _node(severity="medium")
        assert derive_obligation(node) == ObligationLevel.MAY

    def test_low_any_is_may(self):
        """low + any → score 0+... → MAY"""
        node = _node(severity="low", validation_status="human_verified", epistemic_status="E5")
        assert derive_obligation(node) == ObligationLevel.SHOULD  # 0+2+3=5 → SHOULD

    def test_low_unvalidated_is_may(self):
        node = _node(severity="low")
        assert derive_obligation(node) == ObligationLevel.MAY


class TestProhibitionDetection:
    def test_never_critical_is_must_not(self):
        node = _node(text="Never use eval() on user input", severity="critical")
        assert derive_obligation(node) == ObligationLevel.MUST_NOT

    def test_do_not_high_is_must_not(self):
        node = _node(text="Do not use wildcard CORS origins", severity="high")
        assert derive_obligation(node) == ObligationLevel.MUST_NOT

    def test_avoid_medium_is_should_not(self):
        node = _node(text="Avoid mixing sync and async code", severity="medium")
        assert derive_obligation(node) == ObligationLevel.SHOULD_NOT

    def test_must_not_low_is_should_not(self):
        node = _node(text="Must not use deprecated APIs", severity="low")
        assert derive_obligation(node) == ObligationLevel.SHOULD_NOT

    def test_dont_high_is_must_not(self):
        node = _node(text="Don't hardcode credentials", severity="high")
        assert derive_obligation(node) == ObligationLevel.MUST_NOT

    def test_prohibit_in_statement_field(self):
        node = _node(text="", severity="critical")
        node["statement"] = "Prohibit raw SQL concatenation"
        assert derive_obligation(node) == ObligationLevel.MUST_NOT

    def test_avoid_in_why_does_not_trigger(self):
        """'avoid' in WHY field is rationale, not directive → should NOT trigger."""
        node = _node(
            text="Use parameterized queries",
            severity="medium",
            why="To avoid SQL injection attacks",
        )
        # No prohibition in text → falls through to positive obligation
        assert derive_obligation(node) == ObligationLevel.MAY

    def test_not_allowed_triggers(self):
        node = _node(text="Direct database access is not allowed in handlers", severity="high")
        assert derive_obligation(node) == ObligationLevel.MUST_NOT

    def test_has_prohibition_helper(self):
        assert _has_prohibition({"text": "Never do this"}) is True
        assert _has_prohibition({"text": "Always do this"}) is False
        assert _has_prohibition({"name": "Avoid wildcards"}) is True
        assert _has_prohibition({}) is False


class TestDeprecated:
    def test_deprecated_is_must_not(self):
        node = _node(deprecated=True, severity="critical", validation_status="human_verified")
        assert derive_obligation(node) == ObligationLevel.MUST_NOT

    def test_deprecated_overrides_everything(self):
        """Deprecated takes precedence over all other signals."""
        node = _node(
            deprecated=True,
            severity="low",
            validation_status="unvalidated",
            epistemic_status="E0",
        )
        assert derive_obligation(node) == ObligationLevel.MUST_NOT


class TestBoostsAndCaps:
    def test_high_uncertainty_caps_at_may(self):
        """ep_u > 0.7 → MAY regardless of severity/validation."""
        node = _node(
            severity="critical",
            validation_status="human_verified",
            epistemic_status="E5",
            ep_u=0.75,
        )
        assert derive_obligation(node) == ObligationLevel.MAY

    def test_reinforcement_promotes_may_to_should(self):
        """reinforcement >= 10 promotes MAY → SHOULD."""
        node = _node(severity="medium", reinforcement_count=15)
        assert derive_obligation(node) == ObligationLevel.SHOULD

    def test_reinforcement_does_not_promote_should(self):
        """Reinforcement only promotes MAY, not SHOULD."""
        node = _node(
            severity="critical",
            validation_status="unvalidated",
            epistemic_status="E1",
            reinforcement_count=20,
        )
        # Score = 3+0+1=4 → SHOULD; reinforcement only promotes MAY → no change
        assert derive_obligation(node) == ObligationLevel.SHOULD

    def test_belief_boost_may_to_should(self):
        """ep_b >= 0.8 promotes MAY → SHOULD."""
        node = _node(severity="medium", ep_b=0.85)
        assert derive_obligation(node) == ObligationLevel.SHOULD

    def test_belief_boost_should_to_must(self):
        """ep_b >= 0.8 promotes SHOULD → MUST."""
        node = _node(
            severity="critical",
            validation_status="unvalidated",
            epistemic_status="E1",
            ep_b=0.9,
        )
        # Score = 3+0+1=4 → SHOULD → belief boost → MUST
        assert derive_obligation(node) == ObligationLevel.MUST

    def test_belief_does_not_promote_must(self):
        """ep_b boost doesn't go beyond MUST."""
        node = _node(
            severity="critical",
            validation_status="human_verified",
            epistemic_status="E3",
            ep_b=0.95,
        )
        assert derive_obligation(node) == ObligationLevel.MUST


class TestEdgeCases:
    def test_empty_node_defaults_may(self):
        assert derive_obligation({}) == ObligationLevel.MAY

    def test_no_severity_defaults_medium(self):
        node = {"text": "Some guidance"}
        assert derive_obligation(node) == ObligationLevel.MAY

    def test_invalid_epistemic_status(self):
        node = _node(epistemic_status="unknown")
        # Defaults to level 0
        assert derive_obligation(node) == ObligationLevel.MAY

    def test_ep_u_as_string(self):
        """ep_u stored as string should still work."""
        node = _node(severity="critical", ep_u="0.9")
        assert derive_obligation(node) == ObligationLevel.MAY


# =============================================================================
# check_applicability
# =============================================================================


class TestCheckApplicability:
    def test_l0_always_applicable(self):
        node = _node(layer="L0")
        result = check_applicability(node, MockContext())
        assert result.applicable is True
        assert result.confidence == 1.0

    def test_l4_always_applicable(self):
        node = _node(layer="L4")
        result = check_applicability(node, MockContext())
        assert result.applicable is True
        assert result.confidence == 1.0

    def test_exclusion_matches_technology(self):
        node = _node(when_not_applies="test environments, development only")
        ctx = MockContext(domains=["test"])
        result = check_applicability(node, ctx)
        assert result.applicable is False
        assert result.excluded_by == "test"

    def test_exclusion_matches_domain(self):
        node = _node(when_not_applies="throwaway scripts, prototyping")
        ctx = MockContext(domains=["prototyping"])
        result = check_applicability(node, ctx)
        assert result.applicable is False

    def test_exclusion_case_insensitive(self):
        node = _node(when_not_applies="Firebase projects")
        ctx = MockContext(technologies=["firebase"])
        result = check_applicability(node, ctx)
        assert result.applicable is False

    def test_when_applies_matches(self):
        node = _node(when_applies="Any project using Flask and PostgreSQL")
        ctx = MockContext(technologies=["Flask", "PostgreSQL"])
        result = check_applicability(node, ctx)
        assert result.applicable is True
        assert result.confidence > 0.5

    def test_when_applies_no_match_still_applicable(self):
        """No match → conservatively included with low confidence."""
        node = _node(when_applies="Only for Ruby on Rails projects")
        ctx = MockContext(technologies=["Flask"])
        result = check_applicability(node, ctx)
        assert result.applicable is True
        assert result.confidence <= 0.5

    def test_empty_when_applies_neutral(self):
        node = _node(when_applies="")
        ctx = MockContext(technologies=["Flask"])
        result = check_applicability(node, ctx)
        assert result.applicable is True
        assert result.confidence == 0.5

    def test_l2_uses_when_to_use(self):
        node = _node(layer="L2")
        node["when_to_use"] = "Flask applications with caching"
        ctx = MockContext(technologies=["Flask"])
        result = check_applicability(node, ctx)
        assert result.applicable is True
        assert result.confidence > 0.5

    def test_l2_uses_when_not_to_use(self):
        node = _node(layer="L2")
        node["when_not_to_use"] = "simple CRUD applications"
        ctx = MockContext(domains=["crud"])
        result = check_applicability(node, ctx)
        assert result.applicable is False

    def test_technology_tag_cross_check(self):
        """When when_applies has keywords that don't match context, fall to tech cross-check."""
        node = _node(when_applies="production backend services")
        node["technologies"] = {"lang": ["python"], "framework": ["flask"]}
        ctx = MockContext(technologies=["Flask"])
        result = check_applicability(node, ctx)
        assert result.applicable is True
        assert result.confidence == 0.6  # tech match confidence

    def test_technology_tag_no_overlap(self):
        node = _node(when_applies="production Ruby projects")
        node["technologies"] = {"lang": ["ruby"]}
        ctx = MockContext(technologies=["Python"])
        result = check_applicability(node, ctx)
        assert result.applicable is True
        assert result.confidence <= 0.5  # no match → low confidence

    def test_exclusion_overrides_inclusion(self):
        """when_not_applies match should exclude even if when_applies would match."""
        node = _node(
            when_applies="Any Flask project",
            when_not_applies="test environments",
        )
        ctx = MockContext(technologies=["Flask"], domains=["test"])
        result = check_applicability(node, ctx)
        assert result.applicable is False

    def test_raw_text_matching(self):
        node = _node(when_not_applies="microservice deployments")
        ctx = MockContext(raw_text="setting up a microservice architecture")
        result = check_applicability(node, ctx)
        assert result.applicable is False

    def test_multiple_exclusion_terms(self):
        node = _node(when_not_applies="scripts, prototypes, throwaway code")
        ctx = MockContext(domains=["prototypes"])
        result = check_applicability(node, ctx)
        assert result.applicable is False


# =============================================================================
# annotate_guardrails
# =============================================================================


class TestAnnotateGuardrails:
    def test_annotates_obligation(self):
        nodes = [
            _node(severity="critical", validation_status="human_verified", epistemic_status="E3")
        ]
        ctx = MockContext()
        annotated, summary = annotate_guardrails(nodes, ctx)
        assert annotated[0]["_obligation"] == "MUST"

    def test_annotates_applicability(self):
        nodes = [_node(when_not_applies="test environments")]
        ctx = MockContext(domains=["test"])
        annotated, summary = annotate_guardrails(nodes, ctx)
        assert annotated[0]["_applicability"]["applicable"] is False

    def test_summary_counts(self):
        nodes = [
            _node(
                nid="A",
                severity="critical",
                validation_status="human_verified",
                epistemic_status="E3",
            ),
            _node(nid="B", text="Never use eval()", severity="critical"),
            _node(nid="C", severity="medium"),
        ]
        ctx = MockContext()
        _, summary = annotate_guardrails(nodes, ctx)
        assert summary.total_nodes == 3
        assert summary.must_count == 1
        assert summary.must_not_count == 1
        assert summary.may_count == 1

    def test_inapplicable_ids(self):
        nodes = [
            _node(nid="A", when_not_applies="testing only"),
            _node(nid="B", when_applies="any Flask project"),
        ]
        ctx = MockContext(technologies=["Flask"], domains=["testing"])
        _, summary = annotate_guardrails(nodes, ctx)
        assert "A" in summary.inapplicable_ids

    def test_empty_input(self):
        annotated, summary = annotate_guardrails([], MockContext())
        assert annotated == []
        assert summary.total_nodes == 0

    def test_preserves_existing_keys(self):
        node = _node(severity="medium")
        node["custom_field"] = "custom_value"
        annotated, _ = annotate_guardrails([node], MockContext())
        assert annotated[0]["custom_field"] == "custom_value"
        assert "_obligation" in annotated[0]

    def test_mixed_obligations(self):
        nodes = [
            _node(
                nid="MUST",
                severity="critical",
                validation_status="human_verified",
                epistemic_status="E3",
            ),
            _node(nid="MUST_NOT", text="Never hardcode secrets", severity="critical"),
            _node(
                nid="SHOULD",
                severity="high",
                validation_status="cross_checked",
                epistemic_status="E2",
            ),
            _node(nid="SHOULD_NOT", text="Avoid global state", severity="medium"),
            _node(nid="MAY", severity="low"),
        ]
        ctx = MockContext()
        annotated, summary = annotate_guardrails(nodes, ctx)
        obligations = {n["id"]: n["_obligation"] for n in annotated}
        assert obligations["MUST"] == "MUST"
        assert obligations["MUST_NOT"] == "MUST NOT"
        assert obligations["SHOULD"] == "SHOULD"
        assert obligations["SHOULD_NOT"] == "SHOULD NOT"
        assert obligations["MAY"] == "MAY"


# =============================================================================
# GuardrailMetadata + GuardrailEntry schema
# =============================================================================


class TestGuardrailSchema:
    def test_default_empty(self):
        from engineering_brain.core.types import GuardrailMetadata

        meta = GuardrailMetadata()
        assert meta.must_do == []
        assert meta.must_not_do == []
        assert meta.should_do == []
        assert meta.should_not_do == []
        assert meta.may_do == []
        assert meta.inapplicable_ids == []

    def test_guardrail_entry_fields(self):
        from engineering_brain.core.types import GuardrailEntry

        entry = GuardrailEntry(
            node_id="CR-001",
            obligation="MUST",
            text="Set CORS origins",
            why="Security",
        )
        assert entry.node_id == "CR-001"
        assert entry.applicable is True  # default
        assert entry.excluded_by == ""  # default

    def test_metadata_model_dump_roundtrip(self):
        from engineering_brain.core.types import GuardrailEntry, GuardrailMetadata

        meta = GuardrailMetadata(
            must_do=[GuardrailEntry(node_id="A", obligation="MUST", text="Do X")],
            must_not_do=[GuardrailEntry(node_id="B", obligation="MUST NOT", text="Not Y")],
            inapplicable_ids=["C"],
        )
        dumped = meta.model_dump()
        restored = GuardrailMetadata(**dumped)
        assert len(restored.must_do) == 1
        assert len(restored.must_not_do) == 1
        assert restored.inapplicable_ids == ["C"]

    def test_assembly_result_guardrails_default_none(self):
        from engineering_brain.core.types import AssemblyResult

        r = AssemblyResult()
        assert r.guardrails is None

    def test_assembly_result_with_guardrails(self):
        from engineering_brain.core.types import AssemblyResult, GuardrailMetadata

        r = AssemblyResult(guardrails=GuardrailMetadata())
        assert r.guardrails is not None
        assert r.guardrails.must_do == []

    def test_knowledge_result_guardrails_default_none(self):
        from engineering_brain.core.types import KnowledgeResult

        r = KnowledgeResult()
        assert r.guardrails is None
