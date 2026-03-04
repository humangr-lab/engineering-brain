"""Tests for source_trust — mapping sources to OpinionTuples."""

from __future__ import annotations

import pytest

from engineering_brain.epistemic.source_trust import (
    SOURCE_TRUST_MAP,
    source_to_opinion,
)

# --- SOURCE_TRUST_MAP ---


class TestSourceTrustMap:
    def test_all_values_in_range(self):
        for key, val in SOURCE_TRUST_MAP.items():
            assert 0.0 < val <= 1.0, f"{key} out of range: {val}"

    def test_known_keys_present(self):
        expected = {
            "official_docs",
            "security_cve",
            "rfc_standard",
            "stackoverflow",
            "mdn",
            "github_advisory",
            "owasp",
            "package_registry",
            "human_curated",
        }
        assert expected == set(SOURCE_TRUST_MAP.keys())

    def test_security_highest_trust(self):
        assert SOURCE_TRUST_MAP["security_cve"] >= 0.95
        assert SOURCE_TRUST_MAP["rfc_standard"] >= 0.95

    def test_stackoverflow_lower(self):
        assert SOURCE_TRUST_MAP["stackoverflow"] < SOURCE_TRUST_MAP["official_docs"]


# --- source_to_opinion with dicts ---


class TestSourceToOpinionDict:
    def test_official_docs(self):
        source = {"source_type": "official_docs", "verified": False}
        o = source_to_opinion(source)
        assert o.b == pytest.approx(0.90)
        assert o.d == pytest.approx(0.0)
        assert abs(o.b + o.d + o.u - 1.0) < 1e-9

    def test_official_docs_verified(self):
        source = {"source_type": "official_docs", "verified": True}
        o = source_to_opinion(source)
        assert o.b == pytest.approx(0.95)  # 0.90 + 0.05

    def test_stackoverflow_no_votes(self):
        source = {"source_type": "stackoverflow", "vote_count": 0}
        o = source_to_opinion(source)
        # sigmoid(0) = 0.5, base * sigmoid = 0.60 * 0.5 = 0.30
        # max(base, 0.30) = max(0.60, 0.30) = 0.60 (floor at base trust)
        assert o.b == pytest.approx(0.60, abs=0.01)

    def test_stackoverflow_high_votes(self):
        source = {"source_type": "stackoverflow", "vote_count": 100}
        o = source_to_opinion(source)
        # sigmoid(100/20) = sigmoid(5) ≈ 0.993, trust ≈ 0.596
        assert o.b > 0.55

    def test_stackoverflow_accepted(self):
        source = {
            "source_type": "stackoverflow",
            "vote_count": 50,
            "is_accepted_answer": True,
        }
        o = source_to_opinion(source)
        # Base + 0.15 bonus
        assert o.b > 0.60

    def test_stackoverflow_accepted_capped(self):
        source = {
            "source_type": "stackoverflow",
            "vote_count": 1000,
            "is_accepted_answer": True,
        }
        o = source_to_opinion(source)
        assert o.b <= 0.95  # cap

    def test_cve_with_cvss(self):
        source = {"source_type": "security_cve", "cvss_score": 9.8}
        o = source_to_opinion(source)
        expected_trust = 0.95 * (9.8 / 10.0)
        assert o.b == pytest.approx(expected_trust, abs=0.01)

    def test_cve_low_cvss(self):
        source = {"source_type": "security_cve", "cvss_score": 2.0}
        o = source_to_opinion(source)
        expected_trust = 0.95 * 0.2
        assert o.b == pytest.approx(expected_trust, abs=0.01)

    def test_cve_without_cvss_uses_base(self):
        source = {"source_type": "security_cve"}
        o = source_to_opinion(source)
        assert o.b == pytest.approx(SOURCE_TRUST_MAP["security_cve"])

    def test_unknown_source_type(self):
        source = {"source_type": "unknown_blog"}
        o = source_to_opinion(source)
        assert o.b == pytest.approx(0.50)  # default

    def test_verified_bonus(self):
        source = {"source_type": "package_registry", "verified": True}
        o = source_to_opinion(source)
        assert o.b == pytest.approx(0.75)  # 0.70 + 0.05

    def test_verified_bonus_capped(self):
        source = {"source_type": "security_cve", "verified": True}
        o = source_to_opinion(source)
        assert o.b <= 0.99

    def test_output_is_valid_opinion(self):
        """Every output must satisfy b+d+u=1 invariant."""
        test_sources = [
            {"source_type": "official_docs"},
            {"source_type": "stackoverflow", "vote_count": 42},
            {"source_type": "security_cve", "cvss_score": 7.5},
            {"source_type": "mdn", "verified": True},
            {"source_type": "unknown"},
        ]
        for src in test_sources:
            o = source_to_opinion(src)
            assert abs(o.b + o.d + o.u - 1.0) < 1e-9
            assert 0.0 <= o.b <= 1.0
            assert 0.0 <= o.d <= 1.0
            assert 0.0 <= o.u <= 1.0

    def test_empty_dict(self):
        o = source_to_opinion({})
        assert abs(o.b + o.d + o.u - 1.0) < 1e-9


# --- source_to_opinion with objects ---


class TestSourceToOpinionObject:
    def test_object_with_attributes(self):
        class FakeSource:
            source_type = "owasp"
            verified = False
            vote_count = None
            is_accepted_answer = False
            cvss_score = None

        o = source_to_opinion(FakeSource())
        assert o.b == pytest.approx(0.90)

    def test_object_with_enum_source_type(self):
        class FakeEnum:
            value = "mdn"

        class FakeSource:
            source_type = FakeEnum()
            verified = True
            vote_count = None
            is_accepted_answer = False
            cvss_score = None

        o = source_to_opinion(FakeSource())
        assert o.b == pytest.approx(0.90)  # 0.85 + 0.05
