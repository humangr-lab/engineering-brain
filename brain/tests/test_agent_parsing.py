"""Tests for engineering_brain.agent.parsing — shared LLM response parsing."""

from __future__ import annotations

from engineering_brain.agent.parsing import (
    parse_claims,
    parse_confidence,
    parse_evidence_item,
)
from engineering_brain.agent.types import ConfidenceLevel, EvidenceItem


class TestParseConfidence:
    def test_lowercase(self):
        assert parse_confidence("high") == ConfidenceLevel.HIGH

    def test_uppercase(self):
        assert parse_confidence("HIGH") == ConfidenceLevel.HIGH

    def test_title_case(self):
        assert parse_confidence("Moderate") == ConfidenceLevel.MODERATE

    def test_whitespace(self):
        assert parse_confidence("  low  ") == ConfidenceLevel.LOW

    def test_contested(self):
        assert parse_confidence("CONTESTED") == ConfidenceLevel.CONTESTED

    def test_invalid_returns_default(self):
        assert parse_confidence("banana") == ConfidenceLevel.MODERATE

    def test_custom_default(self):
        assert parse_confidence("banana", ConfidenceLevel.LOW) == ConfidenceLevel.LOW

    def test_non_string(self):
        assert parse_confidence(42) == ConfidenceLevel.MODERATE

    def test_none(self):
        assert parse_confidence(None) == ConfidenceLevel.MODERATE


class TestParseEvidenceItem:
    def test_dict_with_node_id(self):
        item = parse_evidence_item({"node_id": "CR-001", "relevance": "direct"})
        assert isinstance(item, EvidenceItem)
        assert item.node_id == "CR-001"
        assert item.content == "direct"

    def test_dict_empty(self):
        item = parse_evidence_item({})
        assert isinstance(item, EvidenceItem)
        assert item.node_id == ""

    def test_string(self):
        item = parse_evidence_item("CR-002")
        assert isinstance(item, EvidenceItem)
        assert item.node_id == "CR-002"

    def test_int_returns_none(self):
        assert parse_evidence_item(42) is None

    def test_none_returns_none(self):
        assert parse_evidence_item(None) is None

    def test_list_returns_none(self):
        assert parse_evidence_item([1, 2]) is None


class TestParseClaims:
    def test_typical_response(self):
        raw = [
            {
                "claim": "Always validate input",
                "confidence": "high",
                "evidence": [
                    {"node_id": "CR-001", "relevance": "direct"},
                    "CR-002",
                ],
                "contradictions": ["Some say no"],
                "reasoning": "Brain evidence",
            },
        ]
        claims = parse_claims(raw)
        assert len(claims) == 1
        assert claims[0].claim == "Always validate input"
        assert claims[0].confidence == ConfidenceLevel.HIGH
        assert len(claims[0].evidence) == 2
        assert claims[0].evidence[0].node_id == "CR-001"
        assert claims[0].evidence[1].node_id == "CR-002"
        assert claims[0].contradictions == ["Some say no"]
        assert claims[0].reasoning == "Brain evidence"

    def test_empty_list(self):
        assert parse_claims([]) == []

    def test_non_list_returns_empty(self):
        assert parse_claims("not a list") == []
        assert parse_claims(None) == []
        assert parse_claims(42) == []

    def test_skips_non_dict_entries(self):
        raw = ["not a dict", {"claim": "valid", "confidence": "low"}]
        claims = parse_claims(raw)
        assert len(claims) == 1
        assert claims[0].claim == "valid"

    def test_missing_fields_use_defaults(self):
        raw = [{"claim": "bare claim"}]
        claims = parse_claims(raw)
        assert len(claims) == 1
        assert claims[0].confidence == ConfidenceLevel.MODERATE
        assert claims[0].evidence == []
        assert claims[0].contradictions == []
        assert claims[0].reasoning == ""

    def test_coerces_non_string_contradictions(self):
        raw = [{"claim": "c", "contradictions": [{"a": "b"}, 42]}]
        claims = parse_claims(raw)
        assert all(isinstance(c, str) for c in claims[0].contradictions)

    def test_invalid_confidence_defaults(self):
        raw = [{"claim": "c", "confidence": "INVALID"}]
        claims = parse_claims(raw)
        assert claims[0].confidence == ConfidenceLevel.MODERATE

    def test_evidence_filters_none(self):
        raw = [{"claim": "c", "evidence": [42, None, "CR-001"]}]
        claims = parse_claims(raw)
        assert len(claims[0].evidence) == 1
        assert claims[0].evidence[0].node_id == "CR-001"
