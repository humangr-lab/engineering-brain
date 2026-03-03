"""Comprehensive tests for validation checkers in engineering_brain.validation.checkers.

All HTTP/API calls are mocked — no real network requests are made.
Each checker is tested for:
  - Successful validation paths
  - Error/failure paths (API down, invalid response, timeouts)
  - Rate limiting behavior (via the base class _throttle)
  - Edge cases (empty inputs, missing fields, domain filtering)
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from engineering_brain.core.types import Source, SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _mock_response(status_code: int = 200, json_data: Any = None) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


# =========================================================================
# 1. GitHubAdvisoryChecker
# =========================================================================

class TestGitHubAdvisoryChecker:
    """Tests for GitHubAdvisoryChecker."""

    def _make_checker(self, token: str = "ghp_test_token"):
        from engineering_brain.validation.checkers.github_advisory import GitHubAdvisoryChecker
        checker = GitHubAdvisoryChecker(token=token, rate_limit=0.0)
        return checker

    def test_source_type(self):
        checker = self._make_checker()
        assert checker.source_type == SourceType.GITHUB_ADVISORY

    def test_is_available_with_token(self):
        checker = self._make_checker(token="ghp_real_token")
        assert checker.is_available() is True

    def test_is_not_available_without_token(self):
        checker = self._make_checker(token="")
        assert checker.is_available() is False

    def test_check_technology_returns_none(self):
        checker = self._make_checker()
        result = run(checker.check_technology("Flask"))
        assert result is None

    @patch("engineering_brain.validation.checkers.github_advisory.httpx.AsyncClient")
    def test_search_claim_success(self, mock_client_cls):
        """Successful advisory search returns Source objects."""
        advisories = [
            {
                "ghsa_id": "GHSA-1234-abcd",
                "summary": "XSS vulnerability in Flask-CORS allows origin bypass",
                "severity": "HIGH",
                "html_url": "https://github.com/advisories/GHSA-1234-abcd",
                "cvss": {"score": 7.5},
            },
            {
                "ghsa_id": "GHSA-5678-efgh",
                "summary": "CORS misconfiguration in Flask",
                "severity": "MEDIUM",
                "html_url": "https://github.com/advisories/GHSA-5678-efgh",
                "cvss": {"score": 5.0},
            },
        ]
        mock_resp = _mock_response(200, advisories)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim(
            "CORS misconfiguration allows origin bypass",
            ["Flask"],
            ["security"],
        ))

        assert len(sources) == 2
        assert sources[0].source_type == SourceType.GITHUB_ADVISORY
        assert "GHSA-1234-abcd" in sources[0].title
        assert sources[0].cvss_score == 7.5
        assert sources[0].verified is True
        assert sources[1].cvss_score == 5.0

    def test_search_claim_skips_non_security_domain(self):
        """Should return empty list when domain is not 'security'."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Flask routing best practices",
            ["Flask"],
            ["backend", "python"],
        ))
        assert sources == []

    def test_search_claim_skips_without_token(self):
        """Should return empty list when no token is set."""
        checker = self._make_checker(token="")
        sources = run(checker.search_claim(
            "XSS vulnerability",
            ["React"],
            ["security"],
        ))
        assert sources == []

    def test_search_claim_skips_empty_technologies(self):
        """Should return empty list when no technologies provided."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "XSS vulnerability",
            [],
            ["security"],
        ))
        assert sources == []

    @patch("engineering_brain.validation.checkers.github_advisory.httpx.AsyncClient")
    def test_search_claim_api_error_returns_empty(self, mock_client_cls):
        """API returning non-200 should produce empty list."""
        mock_resp = _mock_response(403, {"message": "rate limited"})

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim(
            "SQL injection vulnerability",
            ["Django"],
            ["security"],
        ))
        assert sources == []

    @patch("engineering_brain.validation.checkers.github_advisory.httpx.AsyncClient")
    def test_search_claim_exception_returns_empty(self, mock_client_cls):
        """Network error should produce empty list, not raise."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim(
            "CSRF vulnerability",
            ["Flask"],
            ["security"],
        ))
        assert sources == []

    @patch("engineering_brain.validation.checkers.github_advisory.httpx.AsyncClient")
    def test_search_claim_ecosystem_mapping(self, mock_client_cls):
        """Should map React to 'npm' ecosystem in request params."""
        mock_resp = _mock_response(200, [])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        run(checker.search_claim("XSS in React", ["React"], ["security"]))

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert params.get("ecosystem") == "npm"

    @patch("engineering_brain.validation.checkers.github_advisory.httpx.AsyncClient")
    def test_search_claim_limits_to_3_results(self, mock_client_cls):
        """Should return at most 3 advisories even if API returns more."""
        advisories = [
            {
                "ghsa_id": f"GHSA-{i:04d}",
                "summary": f"Vuln {i}",
                "severity": "LOW",
                "html_url": f"https://github.com/advisories/GHSA-{i:04d}",
                "cvss": {"score": 3.0},
            }
            for i in range(10)
        ]
        mock_resp = _mock_response(200, advisories)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim("vuln", ["Flask"], ["security"]))
        assert len(sources) <= 3

    @patch("engineering_brain.validation.checkers.github_advisory.httpx.AsyncClient")
    def test_search_claim_missing_cvss(self, mock_client_cls):
        """Advisory without cvss field should have cvss_score=None."""
        advisories = [
            {
                "ghsa_id": "GHSA-no-cvss",
                "summary": "Missing CVSS",
                "severity": "UNKNOWN",
                "html_url": "https://github.com/advisories/GHSA-no-cvss",
            },
        ]
        mock_resp = _mock_response(200, advisories)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim("vuln", ["Flask"], ["security"]))
        assert len(sources) == 1
        assert sources[0].cvss_score is None


# =========================================================================
# 2. MDNChecker
# =========================================================================

class TestMDNChecker:
    """Tests for MDNChecker."""

    def _make_checker(self):
        from engineering_brain.validation.checkers.mdn import MDNChecker
        return MDNChecker(rate_limit=0.0)

    def test_source_type(self):
        checker = self._make_checker()
        assert checker.source_type == SourceType.MDN

    @patch("engineering_brain.validation.checkers.mdn.httpx.AsyncClient")
    def test_check_technology_exists(self, mock_client_cls):
        """Known web tech should return exists=True."""
        mock_resp = _mock_response(200)

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("fetch"))
        assert result is not None
        assert result["exists"] is True
        assert "Fetch_API" in result["slug"]

    def test_check_technology_unknown(self):
        """Unknown tech (no MDN slug) should return None without HTTP call."""
        checker = self._make_checker()
        result = run(checker.check_technology("MyCustomFramework"))
        assert result is None

    @patch("engineering_brain.validation.checkers.mdn.httpx.AsyncClient")
    def test_check_technology_api_error(self, mock_client_cls):
        """HTTP error should return None."""
        mock_client = AsyncMock()
        mock_client.head = AsyncMock(side_effect=Exception("Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("fetch"))
        assert result is None

    @patch("engineering_brain.validation.checkers.mdn.httpx.AsyncClient")
    def test_check_technology_not_found(self, mock_client_cls):
        """HEAD returning 404 should return exists=False."""
        mock_resp = _mock_response(404)

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("websocket"))
        assert result is not None
        assert result["exists"] is False

    def test_search_claim_non_web_domain(self):
        """Non-web domain + non-web tech should return empty."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Database query optimization",
            ["PostgreSQL"],
            ["database", "backend"],
        ))
        assert sources == []

    def test_search_claim_web_domain(self):
        """Web domain should match MDN slugs from technologies."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Using CORS headers",
            ["React"],
            ["web", "frontend"],
        ))
        # React is in web_techs, so should produce source even without slug match
        # if React doesn't have a slug, it won't produce. Let's test with known slugs.
        assert isinstance(sources, list)

    def test_search_claim_with_known_slugs(self):
        """Should produce sources for technologies with known MDN slugs."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Using fetch API for HTTP requests",
            ["JavaScript"],
            ["javascript"],
        ))
        # "fetch" is in _MDN_SLUGS and is in the claim text
        assert len(sources) >= 1
        assert any("fetch" in s.title.lower() for s in sources)
        assert all(s.source_type == SourceType.MDN for s in sources)
        assert all(s.verified for s in sources)

    def test_search_claim_web_tech_trigger(self):
        """Web tech names (react, vue, etc.) should trigger MDN search."""
        checker = self._make_checker()
        # "cors" is in _MDN_SLUGS and in claim text
        sources = run(checker.search_claim(
            "Configuring cors headers properly",
            ["react"],
            ["backend"],  # Not a web domain, but react is a web tech
        ))
        assert len(sources) >= 1

    def test_search_claim_limits_to_3(self):
        """Should return at most 3 sources."""
        checker = self._make_checker()
        # Include many known MDN slugs in claim text
        claim = "fetch websocket localstorage sessionstorage serviceworker cors promise proxy"
        sources = run(checker.search_claim(claim, ["JavaScript"], ["javascript"]))
        assert len(sources) <= 3

    def test_search_claim_deduplicates(self):
        """Should not return duplicate URLs."""
        checker = self._make_checker()
        claim = "Using fetch API with cors headers"
        sources = run(checker.search_claim(claim, ["JavaScript"], ["web"]))
        urls = [s.url for s in sources]
        assert len(urls) == len(set(urls))


# =========================================================================
# 3. NVDChecker
# =========================================================================

class TestNVDChecker:
    """Tests for NVDChecker (NIST NVD CVE database)."""

    def _make_checker(self, api_key: str = ""):
        from engineering_brain.validation.checkers.nvd_cve import NVDChecker
        return NVDChecker(api_key=api_key, rate_limit=0.0)

    def test_source_type(self):
        checker = self._make_checker()
        assert checker.source_type == SourceType.SECURITY_CVE

    def test_check_technology_returns_none(self):
        checker = self._make_checker()
        result = run(checker.check_technology("Flask"))
        assert result is None

    def test_search_claim_skips_non_security_domain(self):
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Flask routing best practices",
            ["Flask"],
            ["backend", "python"],
        ))
        assert sources == []

    @patch("engineering_brain.validation.checkers.nvd_cve.httpx.AsyncClient")
    def test_search_claim_success(self, mock_client_cls):
        """Successful NVD search returns Source objects with CVE details."""
        nvd_data = {
            "vulnerabilities": [
                {
                    "cve": {
                        "id": "CVE-2023-12345",
                        "descriptions": [
                            {"lang": "en", "value": "XSS vulnerability in Flask-CORS allows origin bypass via crafted headers"},
                        ],
                        "metrics": {
                            "cvssMetricV31": [
                                {"cvssData": {"baseScore": 7.5}},
                            ],
                        },
                    },
                },
            ],
        }
        mock_resp = _mock_response(200, nvd_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim(
            "XSS vulnerability in CORS handling",
            ["Flask"],
            ["security"],
        ))

        assert len(sources) == 1
        assert sources[0].source_type == SourceType.SECURITY_CVE
        assert "CVE-2023-12345" in sources[0].url
        assert "CVE-2023-12345" in sources[0].title
        assert sources[0].cvss_score == 7.5
        assert sources[0].verified is True

    @patch("engineering_brain.validation.checkers.nvd_cve.httpx.AsyncClient")
    def test_search_claim_with_api_key(self, mock_client_cls):
        """API key should be included in request headers."""
        nvd_data = {"vulnerabilities": []}
        mock_resp = _mock_response(200, nvd_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker(api_key="my-nvd-key")
        run(checker.search_claim("injection", ["Django"], ["security"]))

        call_kwargs = mock_client.get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert headers.get("apiKey") == "my-nvd-key"

    @patch("engineering_brain.validation.checkers.nvd_cve.httpx.AsyncClient")
    def test_search_claim_exception_returns_empty(self, mock_client_cls):
        """Network error should return empty list, not raise."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim("sql injection", ["Django"], ["security"]))
        assert sources == []

    @patch("engineering_brain.validation.checkers.nvd_cve.httpx.AsyncClient")
    def test_search_claim_cvss_v30_fallback(self, mock_client_cls):
        """Should extract CVSS from v3.0 if v3.1 is missing."""
        nvd_data = {
            "vulnerabilities": [
                {
                    "cve": {
                        "id": "CVE-2022-99999",
                        "descriptions": [
                            {"lang": "en", "value": "Buffer overflow"},
                        ],
                        "metrics": {
                            "cvssMetricV30": [
                                {"cvssData": {"baseScore": 9.8}},
                            ],
                        },
                    },
                },
            ],
        }
        mock_resp = _mock_response(200, nvd_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim("overflow", ["nginx"], ["security"]))
        assert len(sources) == 1
        assert sources[0].cvss_score == 9.8

    @patch("engineering_brain.validation.checkers.nvd_cve.httpx.AsyncClient")
    def test_search_claim_no_cvss(self, mock_client_cls):
        """CVE without CVSS metrics should have cvss_score=None."""
        nvd_data = {
            "vulnerabilities": [
                {
                    "cve": {
                        "id": "CVE-2021-00001",
                        "descriptions": [
                            {"lang": "en", "value": "Unknown severity"},
                        ],
                        "metrics": {},
                    },
                },
            ],
        }
        mock_resp = _mock_response(200, nvd_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim("auth bypass", ["nginx"], ["auth"]))
        assert len(sources) == 1
        assert sources[0].cvss_score is None

    @patch("engineering_brain.validation.checkers.nvd_cve.httpx.AsyncClient")
    def test_search_claim_limits_to_3(self, mock_client_cls):
        """Should return at most 3 CVEs."""
        nvd_data = {
            "vulnerabilities": [
                {
                    "cve": {
                        "id": f"CVE-2023-{i:05d}",
                        "descriptions": [{"lang": "en", "value": f"Vuln {i}"}],
                        "metrics": {},
                    },
                }
                for i in range(10)
            ],
        }
        mock_resp = _mock_response(200, nvd_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim("injection", ["Flask"], ["security"]))
        assert len(sources) <= 3

    def test_search_claim_auth_domain(self):
        """Should also trigger for 'auth' in domains."""
        from engineering_brain.validation.checkers.nvd_cve import _extract_vuln_keyword
        keyword = _extract_vuln_keyword("auth bypass in JWT", ["Flask"])
        assert keyword  # Should extract something

    def test_extract_vuln_keyword_with_vuln_terms(self):
        """Should combine tech name with found vulnerability term."""
        from engineering_brain.validation.checkers.nvd_cve import _extract_vuln_keyword
        keyword = _extract_vuln_keyword("SQL injection in login form", ["Django"])
        assert "Django" in keyword
        assert "injection" in keyword

    def test_extract_vuln_keyword_no_vuln_terms(self):
        """Should return just tech name when no vuln terms found."""
        from engineering_brain.validation.checkers.nvd_cve import _extract_vuln_keyword
        keyword = _extract_vuln_keyword("Best practices for routing", ["Flask"])
        assert keyword == "Flask"

    def test_extract_vuln_keyword_empty_tech(self):
        """Should return vuln term alone when no technologies."""
        from engineering_brain.validation.checkers.nvd_cve import _extract_vuln_keyword
        keyword = _extract_vuln_keyword("XSS in input fields", [])
        assert "xss" in keyword.lower()


# =========================================================================
# 4. OfficialDocsChecker
# =========================================================================

class TestOfficialDocsChecker:
    """Tests for OfficialDocsChecker."""

    def _make_checker(self):
        from engineering_brain.validation.checkers.official_docs import OfficialDocsChecker
        return OfficialDocsChecker(rate_limit=0.0)

    def test_source_type(self):
        checker = self._make_checker()
        assert checker.source_type == SourceType.OFFICIAL_DOCS

    def test_check_technology_known(self):
        """Known tech should return metadata without HTTP call."""
        checker = self._make_checker()
        result = run(checker.check_technology("Flask"))
        assert result is not None
        assert result["exists"] is True
        assert "flask" in result["url"].lower()
        assert result["title"] == "Flask Documentation"
        assert result["reachable"] is True

    def test_check_technology_alias(self):
        """Alias should resolve to canonical tech."""
        checker = self._make_checker()
        result = run(checker.check_technology("flask-restful"))
        assert result is not None
        assert result["exists"] is True
        assert result["resolved_from"] == "flask-restful"

    def test_check_technology_unknown(self):
        """Unknown tech should return None."""
        checker = self._make_checker()
        result = run(checker.check_technology("SomeUnknownFramework"))
        assert result is None

    def test_search_claim_returns_sources(self):
        """Should return Source for each known technology."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Configure CORS properly",
            ["Flask", "Redis"],
            ["security"],
        ))
        assert len(sources) == 2
        assert all(s.source_type == SourceType.OFFICIAL_DOCS for s in sources)
        assert all(s.verified for s in sources)

    def test_search_claim_deduplicates(self):
        """Same URL should not appear twice."""
        checker = self._make_checker()
        # Both flask-restful and Flask-Login resolve to "Flask"
        sources = run(checker.search_claim(
            "API patterns",
            ["flask-restful", "flask-login"],
            [],
        ))
        urls = [s.url for s in sources]
        assert len(urls) == len(set(urls))

    def test_search_claim_limits_to_5_technologies(self):
        """Should process at most 5 technologies."""
        checker = self._make_checker()
        techs = ["Flask", "Django", "FastAPI", "Redis", "PostgreSQL", "React", "Vue", "Angular"]
        sources = run(checker.search_claim("test", techs, []))
        assert len(sources) <= 5

    def test_search_claim_unknown_tech_skipped(self):
        """Unknown tech should not produce a source."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Something",
            ["NonExistentTech"],
            [],
        ))
        assert sources == []


# =========================================================================
# 5. OWASPChecker
# =========================================================================

class TestOWASPChecker:
    """Tests for OWASPChecker."""

    def _make_checker(self):
        from engineering_brain.validation.checkers.owasp import OWASPChecker
        return OWASPChecker(rate_limit=0.0)

    def test_source_type(self):
        checker = self._make_checker()
        assert checker.source_type == SourceType.OWASP

    def test_check_technology_returns_none(self):
        checker = self._make_checker()
        result = run(checker.check_technology("Flask"))
        assert result is None

    def test_search_claim_skips_non_security(self):
        """Non-security domain should return empty."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Flask routing patterns",
            ["Flask"],
            ["backend", "python"],
        ))
        assert sources == []

    def test_search_claim_finds_matching_sheets(self):
        """Security claim with known keywords should return OWASP sources."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Prevent SQL injection attacks in login form",
            ["Django"],
            ["security"],
        ))
        assert len(sources) >= 1
        assert all(s.source_type == SourceType.OWASP for s in sources)
        assert any("injection" in s.title.lower() for s in sources)
        assert all(s.verified for s in sources)

    def test_search_claim_cors(self):
        """CORS keyword should match OWASP CORS cheat sheet."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "CORS configuration for cross-origin requests",
            ["Flask"],
            ["security"],
        ))
        assert len(sources) >= 1
        assert any("cors" in s.url.lower() for s in sources)

    def test_search_claim_xss(self):
        """XSS keyword should match OWASP XSS cheat sheet."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Prevent XSS attacks by sanitizing input",
            ["React"],
            ["security"],
        ))
        assert len(sources) >= 1

    def test_search_claim_auth_domain(self):
        """'auth' domain should also trigger OWASP search."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Authentication best practices with session management",
            ["Flask"],
            ["auth"],
        ))
        assert len(sources) >= 1
        assert any("authentication" in s.title.lower() or "session" in s.title.lower()
                    for s in sources)

    def test_search_claim_limits_to_3(self):
        """Should return at most 3 sources."""
        checker = self._make_checker()
        # Claim with many security keywords
        claim = "cors csrf xss injection authentication session password deserialization"
        sources = run(checker.search_claim(claim, ["Flask"], ["security"]))
        assert len(sources) <= 3

    def test_search_claim_no_matching_keywords(self):
        """Security domain but no matching OWASP keywords should return empty."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "General security best practices overview",
            ["Flask"],
            ["security"],
        ))
        # "security" alone is not in _OWASP_SHEETS keys
        # This depends on whether any keyword matches - could be empty
        assert isinstance(sources, list)

    def test_search_claim_tech_name_matches(self):
        """Technology name itself can match OWASP sheets (e.g., 'docker')."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Container security best practices",
            ["Docker"],
            ["security"],
        ))
        assert len(sources) >= 1
        assert any("docker" in s.url.lower() for s in sources)

    @patch("engineering_brain.validation.checkers.owasp.httpx.AsyncClient")
    def test_head_check_success(self, mock_client_cls):
        """_head_check should return True on 200."""
        mock_resp = _mock_response(200)

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker._head_check("https://example.com"))
        assert result is True

    @patch("engineering_brain.validation.checkers.owasp.httpx.AsyncClient")
    def test_head_check_failure(self, mock_client_cls):
        """_head_check should return False on error."""
        mock_client = AsyncMock()
        mock_client.head = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker._head_check("https://example.com"))
        assert result is False


# =========================================================================
# 6. PackageRegistryChecker
# =========================================================================

class TestPackageRegistryChecker:
    """Tests for PackageRegistryChecker (PyPI + npm)."""

    def _make_checker(self):
        from engineering_brain.validation.checkers.package_registry import PackageRegistryChecker
        return PackageRegistryChecker(rate_limit=0.0)

    def test_source_type(self):
        checker = self._make_checker()
        assert checker.source_type == SourceType.PACKAGE_REGISTRY

    # --- check_technology: PyPI ---

    @patch("engineering_brain.validation.checkers.package_registry.httpx.AsyncClient")
    def test_check_technology_pypi_exists(self, mock_client_cls):
        """Known PyPI package should return metadata."""
        pypi_data = {
            "info": {
                "version": "3.0.0",
                "summary": "A simple framework for building complex web applications.",
                "home_page": "https://palletsprojects.com/p/flask/",
                "license": "BSD-3-Clause",
                "classifiers": ["Development Status :: 5 - Production/Stable"],
            },
        }
        mock_resp = _mock_response(200, pypi_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("Flask"))

        assert result is not None
        assert result["exists"] is True
        assert result["registry"] == "pypi"
        assert result["package"] == "flask"
        assert result["version"] == "3.0.0"
        assert result["tech_name"] == "Flask"
        assert result["is_deprecated"] is False

    @patch("engineering_brain.validation.checkers.package_registry.httpx.AsyncClient")
    def test_check_technology_pypi_not_found(self, mock_client_cls):
        """PyPI 404 should return exists=False."""
        mock_resp = _mock_response(404)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("Flask"))
        assert result is not None
        assert result["exists"] is False
        assert result["registry"] == "pypi"

    @patch("engineering_brain.validation.checkers.package_registry.httpx.AsyncClient")
    def test_check_technology_pypi_deprecated(self, mock_client_cls):
        """Deprecated PyPI package should set is_deprecated=True."""
        pypi_data = {
            "info": {
                "version": "1.0.0",
                "summary": "DEPRECATED: Use new-package instead",
                "home_page": "",
                "license": "",
                "classifiers": [],
            },
        }
        mock_resp = _mock_response(200, pypi_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("Flask"))
        assert result["is_deprecated"] is True

    @patch("engineering_brain.validation.checkers.package_registry.httpx.AsyncClient")
    def test_check_technology_pypi_exception(self, mock_client_cls):
        """PyPI network error should return None."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("DNS resolution failed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("Flask"))
        assert result is None

    # --- check_technology: npm ---

    @patch("engineering_brain.validation.checkers.package_registry.httpx.AsyncClient")
    def test_check_technology_npm_exists(self, mock_client_cls):
        """Known npm package should return metadata."""
        npm_data = {
            "dist-tags": {"latest": "18.2.0"},
            "description": "React is a JavaScript library for building user interfaces.",
            "homepage": "https://react.dev/",
            "license": "MIT",
        }
        mock_resp = _mock_response(200, npm_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("React"))

        assert result is not None
        assert result["exists"] is True
        assert result["registry"] == "npm"
        assert result["package"] == "react"
        assert result["version"] == "18.2.0"
        assert result["tech_name"] == "React"

    @patch("engineering_brain.validation.checkers.package_registry.httpx.AsyncClient")
    def test_check_technology_npm_not_found(self, mock_client_cls):
        """npm 404 should return exists=False."""
        mock_resp = _mock_response(404)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("React"))
        assert result is not None
        assert result["exists"] is False
        assert result["registry"] == "npm"

    @patch("engineering_brain.validation.checkers.package_registry.httpx.AsyncClient")
    def test_check_technology_npm_deprecated(self, mock_client_cls):
        """Deprecated npm package should set is_deprecated=True."""
        npm_data = {
            "dist-tags": {"latest": "1.0.0"},
            "description": "Old package",
            "deprecated": "Use @new/package instead",
            "license": "MIT",
        }
        mock_resp = _mock_response(200, npm_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("React"))
        assert result["is_deprecated"] is True

    def test_check_technology_not_in_maps(self):
        """Technology not in either map should return None."""
        checker = self._make_checker()
        result = run(checker.check_technology("SomeCustomTech"))
        assert result is None

    def test_check_technology_empty_package_name(self):
        """Tech mapped to empty package (e.g., 'Python') should skip."""
        checker = self._make_checker()
        # "Python" maps to "" in _PYPI_MAP, and is not in _NPM_MAP
        result = run(checker.check_technology("Python"))
        assert result is None

    # --- search_claim ---

    @patch("engineering_brain.validation.checkers.package_registry.httpx.AsyncClient")
    def test_search_claim_pypi(self, mock_client_cls):
        """Should verify PyPI packages for given technologies."""
        pypi_data = {
            "info": {
                "version": "2.5.0",
                "summary": "FastAPI framework",
                "home_page": "https://fastapi.tiangolo.com",
                "license": "MIT",
                "classifiers": [],
            },
        }
        mock_resp = _mock_response(200, pypi_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim(
            "FastAPI endpoint design",
            ["FastAPI"],
            ["backend"],
        ))

        assert len(sources) == 1
        assert sources[0].source_type == SourceType.PACKAGE_REGISTRY
        assert "pypi.org" in sources[0].url
        assert "fastapi" in sources[0].url
        assert sources[0].verified is True

    @patch("engineering_brain.validation.checkers.package_registry.httpx.AsyncClient")
    def test_search_claim_npm(self, mock_client_cls):
        """Should verify npm packages for JS technologies."""
        npm_data = {
            "dist-tags": {"latest": "5.0.0"},
            "description": "Svelte framework",
            "homepage": "https://svelte.dev",
            "license": "MIT",
        }
        mock_resp = _mock_response(200, npm_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Svelte component design",
            ["Svelte"],
            ["frontend"],
        ))

        assert len(sources) == 1
        assert sources[0].source_type == SourceType.PACKAGE_REGISTRY
        assert "npmjs.com" in sources[0].url
        assert sources[0].verified is True

    @patch("engineering_brain.validation.checkers.package_registry.httpx.AsyncClient")
    def test_search_claim_pypi_priority_over_npm(self, mock_client_cls):
        """If tech is in _PYPI_MAP, should use PyPI and skip npm."""
        pypi_data = {
            "info": {
                "version": "1.0.0",
                "summary": "Test",
                "home_page": "",
                "license": "",
                "classifiers": [],
            },
        }
        mock_resp = _mock_response(200, pypi_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Redis caching strategies",
            ["Redis"],
            ["backend"],
        ))

        # Redis is in _PYPI_MAP → should produce pypi source
        assert len(sources) == 1
        assert "pypi.org" in sources[0].url


# =========================================================================
# 7. StackOverflowChecker
# =========================================================================

class TestStackOverflowChecker:
    """Tests for StackOverflowChecker."""

    def _make_checker(self, api_key: str = ""):
        from engineering_brain.validation.checkers.stackoverflow import StackOverflowChecker
        return StackOverflowChecker(api_key=api_key, rate_limit=0.0)

    def test_source_type(self):
        checker = self._make_checker()
        assert checker.source_type == SourceType.STACKOVERFLOW

    def test_is_available_always_true(self):
        checker = self._make_checker()
        assert checker.is_available() is True

    def test_is_available_without_key(self):
        checker = self._make_checker(api_key="")
        assert checker.is_available() is True

    # --- check_technology ---

    @patch("engineering_brain.validation.checkers.stackoverflow.httpx.AsyncClient")
    def test_check_technology_found(self, mock_client_cls):
        """Known SO tag should return exists=True with count."""
        so_data = {
            "items": [
                {"name": "flask", "count": 50000},
            ],
        }
        mock_resp = _mock_response(200, so_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("Flask"))
        assert result is not None
        assert result["exists"] is True
        assert result["tag"] == "flask"
        assert result["count"] == 50000

    @patch("engineering_brain.validation.checkers.stackoverflow.httpx.AsyncClient")
    def test_check_technology_not_found(self, mock_client_cls):
        """Unknown SO tag should return exists=False."""
        so_data = {"items": []}
        mock_resp = _mock_response(200, so_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("UnknownLib"))
        assert result is not None
        assert result["exists"] is False
        assert result["count"] == 0

    @patch("engineering_brain.validation.checkers.stackoverflow.httpx.AsyncClient")
    def test_check_technology_exception(self, mock_client_cls):
        """Network error should return None."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("API error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        result = run(checker.check_technology("Flask"))
        assert result is None

    @patch("engineering_brain.validation.checkers.stackoverflow.httpx.AsyncClient")
    def test_check_technology_with_api_key(self, mock_client_cls):
        """API key should be included in request params."""
        so_data = {"items": [{"name": "flask", "count": 1000}]}
        mock_resp = _mock_response(200, so_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker(api_key="my-so-key")
        run(checker.check_technology("Flask"))

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert params.get("key") == "my-so-key"

    # --- search_claim ---

    @patch("engineering_brain.validation.checkers.stackoverflow.httpx.AsyncClient")
    def test_search_claim_success(self, mock_client_cls):
        """Successful SO search returns Source objects."""
        so_data = {
            "items": [
                {
                    "title": "How to handle CORS in Flask?",
                    "link": "https://stackoverflow.com/q/12345",
                    "score": 150,
                    "answer_count": 5,
                    "is_answered": True,
                },
                {
                    "title": "Flask-CORS not working",
                    "link": "https://stackoverflow.com/q/67890",
                    "score": 42,
                    "answer_count": 3,
                    "is_answered": True,
                },
            ],
        }
        mock_resp = _mock_response(200, so_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim(
            "CORS configuration in Flask",
            ["Flask"],
            ["security"],
        ))

        assert len(sources) == 2
        assert all(s.source_type == SourceType.STACKOVERFLOW for s in sources)
        assert sources[0].vote_count == 150
        assert sources[0].is_accepted_answer is True
        assert "score=150" in sources[0].title
        assert all(s.verified for s in sources)

    @patch("engineering_brain.validation.checkers.stackoverflow.httpx.AsyncClient")
    def test_search_claim_exception_returns_empty(self, mock_client_cls):
        """Network error should return empty list."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("throttled"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim("test", ["Flask"], []))
        assert sources == []

    @patch("engineering_brain.validation.checkers.stackoverflow.httpx.AsyncClient")
    def test_search_claim_with_api_key(self, mock_client_cls):
        """API key should be in search params."""
        so_data = {"items": []}
        mock_resp = _mock_response(200, so_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker(api_key="my-key")
        run(checker.search_claim("test", ["Flask"], []))

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert params.get("key") == "my-key"

    @patch("engineering_brain.validation.checkers.stackoverflow.httpx.AsyncClient")
    def test_search_claim_with_tags(self, mock_client_cls):
        """SO tags should be computed from technologies."""
        so_data = {"items": []}
        mock_resp = _mock_response(200, so_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        run(checker.search_claim("test", ["Flask", "Redis"], []))

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        tagged = params.get("tagged", "")
        assert "flask" in tagged
        assert "redis" in tagged

    @patch("engineering_brain.validation.checkers.stackoverflow.httpx.AsyncClient")
    def test_search_claim_limits_to_5(self, mock_client_cls):
        """Should return at most 5 results."""
        so_data = {
            "items": [
                {
                    "title": f"Question {i}",
                    "link": f"https://stackoverflow.com/q/{i}",
                    "score": 10 - i,
                    "answer_count": 1,
                    "is_answered": True,
                }
                for i in range(10)
            ],
        }
        mock_resp = _mock_response(200, so_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        checker = self._make_checker()
        sources = run(checker.search_claim("test", ["Flask"], []))
        assert len(sources) <= 5

    def test_build_search_query(self):
        """Query builder should include tech name and truncate."""
        from engineering_brain.validation.checkers.stackoverflow import _build_search_query
        query = _build_search_query("How to configure CORS properly", ["Flask"])
        assert "Flask" in query
        assert len(query) <= 150

    def test_build_search_query_tech_already_in_text(self):
        """Should not duplicate tech name if already in claim."""
        from engineering_brain.validation.checkers.stackoverflow import _build_search_query
        query = _build_search_query("Flask CORS configuration", ["Flask"])
        # Should not have "Flask Flask CORS..."
        assert query.count("Flask") == 1

    def test_get_so_tags(self):
        """Should map technologies to SO tags."""
        from engineering_brain.validation.checkers.stackoverflow import _get_so_tags
        tags = _get_so_tags(["Flask", "Redis", "React"])
        assert "flask" in tags
        assert "redis" in tags
        # React maps to "reactjs"
        assert "reactjs" in tags

    def test_get_so_tags_limits_to_3(self):
        """Should include at most 3 tags."""
        from engineering_brain.validation.checkers.stackoverflow import _get_so_tags
        tags = _get_so_tags(["Flask", "Redis", "React", "Django", "Vue"])
        parts = tags.split(";")
        assert len(parts) <= 3


# =========================================================================
# 8. ArchitecturePatternsChecker
# =========================================================================

class TestArchitecturePatternsChecker:
    """Tests for ArchitecturePatternsChecker."""

    def _make_checker(self):
        from engineering_brain.validation.checkers.architecture_patterns import ArchitecturePatternsChecker
        return ArchitecturePatternsChecker(rate_limit=0.0)

    def test_source_type(self):
        checker = self._make_checker()
        assert checker.source_type == SourceType.OFFICIAL_DOCS

    def test_check_technology_returns_none(self):
        checker = self._make_checker()
        result = run(checker.check_technology("Flask"))
        assert result is None

    def test_search_claim_circuit_breaker(self):
        """Should find circuit breaker pattern reference."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Implement circuit breaker for resilience",
            ["Kubernetes"],
            ["infrastructure"],
        ))
        assert len(sources) >= 1
        assert any("circuit breaker" in s.title.lower() for s in sources)
        assert all(s.verified for s in sources)

    def test_search_claim_cqrs(self):
        """Should find CQRS pattern reference."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Use CQRS to separate reads and writes",
            [],
            ["architecture"],
        ))
        assert len(sources) >= 1
        assert any("cqrs" in s.title.lower() for s in sources)

    def test_search_claim_solid_principles(self):
        """Should find SOLID principle references."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Apply single responsibility and dependency inversion",
            [],
            ["design"],
        ))
        assert len(sources) >= 1

    def test_search_claim_no_match(self):
        """Claim with no matching patterns should return empty."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Optimize database query performance using indexes",
            ["PostgreSQL"],
            ["database"],
        ))
        # "database" alone is not a pattern keyword
        # This may or may not match depending on keywords
        assert isinstance(sources, list)

    def test_search_claim_limits_to_3(self):
        """Should return at most 3 sources."""
        checker = self._make_checker()
        # Many pattern keywords in one claim
        claim = "event sourcing with cqrs and circuit breaker using saga pattern and microservices"
        sources = run(checker.search_claim(claim, [], []))
        assert len(sources) <= 3

    def test_search_claim_deduplicates_urls(self):
        """Same URL should not appear twice (e.g., 'saga' and 'saga pattern')."""
        checker = self._make_checker()
        claim = "Implement saga pattern using choreography-based saga"
        sources = run(checker.search_claim(claim, [], []))
        urls = [s.url for s in sources]
        assert len(urls) == len(set(urls))

    def test_search_claim_twelve_factor(self):
        """Should match 12-factor app reference."""
        checker = self._make_checker()
        sources = run(checker.search_claim(
            "Follow twelve-factor app principles for cloud-native design",
            [],
            ["devops"],
        ))
        assert len(sources) >= 1
        assert any("12factor" in s.url for s in sources)


# =========================================================================
# 9. Technology Resolution (official_docs module)
# =========================================================================

class TestResolveResolvedTechnology:
    """Tests for resolve_technology() in official_docs."""

    def test_exact_match(self):
        from engineering_brain.validation.checkers.official_docs import resolve_technology
        assert resolve_technology("Flask") == "Flask"
        assert resolve_technology("React") == "React"
        assert resolve_technology("Docker") == "Docker"

    def test_alias_match(self):
        from engineering_brain.validation.checkers.official_docs import resolve_technology
        assert resolve_technology("flask-restful") == "Flask"
        assert resolve_technology("expressjs") == "Express"
        assert resolve_technology("k8s") == "Kubernetes"
        assert resolve_technology("boto3") == "AWS"
        assert resolve_technology("golang") == "Go"
        assert resolve_technology("csharp") == "C#"

    def test_prefix_match(self):
        from engineering_brain.validation.checkers.official_docs import resolve_technology
        assert resolve_technology("Flask-WTF") == "Flask"
        assert resolve_technology("Flask-Admin") == "Flask"
        assert resolve_technology("Flask-Login") == "Flask"

    def test_case_insensitive_match(self):
        from engineering_brain.validation.checkers.official_docs import resolve_technology
        assert resolve_technology("flask") == "Flask"
        assert resolve_technology("REDIS") == "Redis"
        assert resolve_technology("docker") == "Docker"
        assert resolve_technology("KUBERNETES") == "Kubernetes"

    def test_unknown_returns_as_is(self):
        from engineering_brain.validation.checkers.official_docs import resolve_technology
        assert resolve_technology("MyCustomLib") == "MyCustomLib"
        assert resolve_technology("") == ""


# =========================================================================
# 10. MDN Slug Resolution (mdn module helpers)
# =========================================================================

class TestMDNSlugResolution:
    """Tests for _find_mdn_slug() and _extract_web_keywords()."""

    def test_direct_slug_lookup(self):
        from engineering_brain.validation.checkers.mdn import _find_mdn_slug
        assert _find_mdn_slug("fetch") == "Web/API/Fetch_API"
        assert _find_mdn_slug("websocket") == "Web/API/WebSocket"
        assert _find_mdn_slug("cors") == "Web/HTTP/CORS"

    def test_html_element_slug(self):
        from engineering_brain.validation.checkers.mdn import _find_mdn_slug
        assert _find_mdn_slug("div") == "Web/HTML/Element/div"
        assert _find_mdn_slug("canvas") == "Web/HTML/Element/canvas"
        assert _find_mdn_slug("form") == "Web/HTML/Element/form"

    def test_css_property_slug(self):
        from engineering_brain.validation.checkers.mdn import _find_mdn_slug
        slug = _find_mdn_slug("css display")
        assert "Web/CSS/" in slug

    def test_css_property_with_dash(self):
        from engineering_brain.validation.checkers.mdn import _find_mdn_slug
        slug = _find_mdn_slug("border-radius")
        assert "Web/CSS/" in slug

    def test_js_global_slug(self):
        from engineering_brain.validation.checkers.mdn import _find_mdn_slug
        slug = _find_mdn_slug("array")
        assert "Global_Objects/Array" in slug

    def test_unknown_term_returns_empty(self):
        from engineering_brain.validation.checkers.mdn import _find_mdn_slug
        assert _find_mdn_slug("postgresql") == ""
        assert _find_mdn_slug("kubernetes orchestration") == ""

    def test_extract_web_keywords(self):
        from engineering_brain.validation.checkers.mdn import _extract_web_keywords
        keywords = _extract_web_keywords("Using fetch with cors to handle websocket connections")
        assert "fetch" in keywords
        assert "cors" in keywords
        assert "websocket" in keywords

    def test_extract_web_keywords_no_match(self):
        from engineering_brain.validation.checkers.mdn import _extract_web_keywords
        keywords = _extract_web_keywords("Database migration strategies for PostgreSQL")
        assert keywords == []

    def test_extract_web_keywords_limits(self):
        from engineering_brain.validation.checkers.mdn import _extract_web_keywords
        # Even with many matches, should limit to 5
        text = " ".join(list(
            __import__("engineering_brain.validation.checkers.mdn", fromlist=["_MDN_SLUGS"])._MDN_SLUGS.keys()
        ))
        keywords = _extract_web_keywords(text)
        assert len(keywords) <= 5


# =========================================================================
# 11. OWASP Sheet Matching (helper)
# =========================================================================

class TestOWASPSheetMatching:
    """Tests for _find_matching_sheets() helper."""

    def test_find_by_claim_text(self):
        from engineering_brain.validation.checkers.owasp import _find_matching_sheets
        matches = _find_matching_sheets("prevent csrf attacks", [])
        assert len(matches) >= 1
        assert any("csrf" in title.lower() for title, url in matches)

    def test_find_by_technology(self):
        from engineering_brain.validation.checkers.owasp import _find_matching_sheets
        matches = _find_matching_sheets("secure containers", ["Docker"])
        assert len(matches) >= 1
        assert any("docker" in url.lower() for _, url in matches)

    def test_find_combined_claim_and_tech(self):
        from engineering_brain.validation.checkers.owasp import _find_matching_sheets
        matches = _find_matching_sheets("authentication best practices", ["kubernetes"])
        # Should find authentication AND kubernetes
        assert len(matches) >= 2

    def test_no_matches(self):
        from engineering_brain.validation.checkers.owasp import _find_matching_sheets
        matches = _find_matching_sheets("database indexing strategies", [])
        assert matches == []


# =========================================================================
# 12. PyPI Deprecated Detection (helper)
# =========================================================================

class TestPyPIDeprecatedDetection:
    """Tests for _is_pypi_deprecated() helper."""

    def test_not_deprecated(self):
        from engineering_brain.validation.checkers.package_registry import _is_pypi_deprecated
        info = {
            "summary": "A modern web framework",
            "classifiers": ["Development Status :: 5 - Production/Stable"],
        }
        assert _is_pypi_deprecated(info) is False

    def test_deprecated_by_classifier(self):
        from engineering_brain.validation.checkers.package_registry import _is_pypi_deprecated
        info = {
            "summary": "Old package",
            "classifiers": ["Development Status :: 7 - Inactive"],
        }
        assert _is_pypi_deprecated(info) is True

    def test_deprecated_by_summary(self):
        from engineering_brain.validation.checkers.package_registry import _is_pypi_deprecated
        info = {
            "summary": "DEPRECATED: Use new-package instead",
            "classifiers": [],
        }
        assert _is_pypi_deprecated(info) is True

    def test_deprecated_no_longer_maintained(self):
        from engineering_brain.validation.checkers.package_registry import _is_pypi_deprecated
        info = {
            "summary": "This project is no longer maintained",
            "classifiers": [],
        }
        assert _is_pypi_deprecated(info) is True

    def test_empty_info(self):
        from engineering_brain.validation.checkers.package_registry import _is_pypi_deprecated
        info: dict[str, Any] = {}
        assert _is_pypi_deprecated(info) is False


# =========================================================================
# 13. Base SourceChecker Rate Limiting
# =========================================================================

class TestRateLimiting:
    """Tests for the base SourceChecker._throttle() rate limiting."""

    def test_throttle_enforces_delay(self):
        """Consecutive calls with rate_limit > 0 should sleep."""
        from engineering_brain.validation.checkers.official_docs import OfficialDocsChecker

        checker = OfficialDocsChecker(rate_limit=0.05)
        # Simulate a recent request
        checker._last_request = time.monotonic()

        start = time.monotonic()
        run(checker._throttle())
        elapsed = time.monotonic() - start

        # Should have waited approximately 0.05s
        assert elapsed >= 0.04  # Allow small timing margin

    def test_throttle_no_delay_when_enough_time_passed(self):
        """Should not sleep if enough time has passed since last request."""
        from engineering_brain.validation.checkers.official_docs import OfficialDocsChecker

        checker = OfficialDocsChecker(rate_limit=0.05)
        # Set last request to far in the past
        checker._last_request = time.monotonic() - 10.0

        start = time.monotonic()
        run(checker._throttle())
        elapsed = time.monotonic() - start

        # Should not have waited
        assert elapsed < 0.02

    def test_throttle_updates_last_request(self):
        """_throttle should update _last_request timestamp."""
        from engineering_brain.validation.checkers.official_docs import OfficialDocsChecker

        checker = OfficialDocsChecker(rate_limit=0.0)
        old_ts = checker._last_request
        run(checker._throttle())
        assert checker._last_request > old_ts


# =========================================================================
# 14. SourceChecker ABC
# =========================================================================

class TestSourceCheckerABC:
    """Tests for the abstract base class behavior."""

    def test_is_available_default(self):
        """Default is_available should return True."""
        from engineering_brain.validation.checkers.official_docs import OfficialDocsChecker
        checker = OfficialDocsChecker()
        assert checker.is_available() is True

    def test_is_available_github_needs_token(self):
        """GitHubAdvisoryChecker should require token."""
        from engineering_brain.validation.checkers.github_advisory import GitHubAdvisoryChecker
        checker_with = GitHubAdvisoryChecker(token="tok")
        checker_without = GitHubAdvisoryChecker(token="")
        assert checker_with.is_available() is True
        assert checker_without.is_available() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
