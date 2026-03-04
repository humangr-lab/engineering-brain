"""Tier 5 validation tests — checkers, orchestrator, rate limiting, offline mode."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest

# =========================================================================
# I-01: OfficialDocsChecker tests
# =========================================================================


class TestOfficialDocsChecker:
    def test_direct_tech_match(self):
        from engineering_brain.validation.checkers.official_docs import OfficialDocsChecker

        checker = OfficialDocsChecker()
        result = asyncio.run(checker.check_technology("Flask"))
        assert result is not None
        assert result["exists"] is True
        assert "flask" in result["url"].lower()

    def test_unknown_tech_returns_none(self):
        from engineering_brain.validation.checkers.official_docs import OfficialDocsChecker

        checker = OfficialDocsChecker()
        result = asyncio.run(checker.check_technology("NonExistentTech12345"))
        assert result is None

    def test_search_claim_returns_sources(self):
        from engineering_brain.validation.checkers.official_docs import OfficialDocsChecker

        checker = OfficialDocsChecker()
        sources = asyncio.run(
            checker.search_claim("CORS configuration", ["Flask", "Redis"], ["security"])
        )
        assert len(sources) >= 2
        assert all(s.verified for s in sources)

    def test_search_claim_deduplicates_urls(self):
        from engineering_brain.validation.checkers.official_docs import OfficialDocsChecker

        checker = OfficialDocsChecker()
        # Flask-SocketIO and Flask should not produce duplicate Flask URL
        sources = asyncio.run(checker.search_claim("WebSocket", ["Flask", "Flask-SocketIO"], []))
        urls = [s.url for s in sources]
        assert len(urls) == len(set(urls)), "Duplicate URLs in sources"


# =========================================================================
# I-02: Technology alias resolution tests
# =========================================================================


class TestTechAliasResolution:
    def test_resolve_exact_match(self):
        from engineering_brain.validation.checkers.official_docs import resolve_technology

        assert resolve_technology("Flask") == "Flask"
        assert resolve_technology("Redis") == "Redis"

    def test_resolve_alias(self):
        from engineering_brain.validation.checkers.official_docs import resolve_technology

        assert resolve_technology("flask-restful") == "Flask"
        assert resolve_technology("expressjs") == "Express"
        assert resolve_technology("k8s") == "Kubernetes"
        assert resolve_technology("boto3") == "AWS"

    def test_resolve_prefix_match(self):
        from engineering_brain.validation.checkers.official_docs import resolve_technology

        # "Flask-Foo" should resolve to "Flask"
        assert resolve_technology("Flask-WTF") == "Flask"
        assert resolve_technology("Flask-Admin") == "Flask"

    def test_resolve_case_insensitive(self):
        from engineering_brain.validation.checkers.official_docs import resolve_technology

        assert resolve_technology("flask") == "Flask"
        assert resolve_technology("REDIS") == "Redis"
        assert resolve_technology("docker") == "Docker"

    def test_resolve_unknown_returns_as_is(self):
        from engineering_brain.validation.checkers.official_docs import resolve_technology

        assert resolve_technology("MyCustomLib") == "MyCustomLib"


# =========================================================================
# I-03: Rate limiter tests
# =========================================================================


class TestTokenBucketRateLimiter:
    def test_basic_acquire(self):
        from engineering_brain.validation.orchestrator import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(rate=10.0, burst=5)

        # Should acquire 5 tokens without blocking
        async def _run():
            for _ in range(5):
                await limiter.acquire()

        asyncio.run(_run())

    def test_burst_limit(self):
        import time

        from engineering_brain.validation.orchestrator import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(rate=100.0, burst=2)

        async def _run():
            for _ in range(3):
                await limiter.acquire()

        start = time.monotonic()
        asyncio.run(_run())
        elapsed = time.monotonic() - start
        # 3 acquires with burst=2 should take minimal time at rate=100/s
        assert elapsed < 1.0

    def test_get_rate_limiter_returns_same_instance(self):
        from engineering_brain.validation.orchestrator import _get_rate_limiter

        limiter1 = _get_rate_limiter("pypi")
        limiter2 = _get_rate_limiter("pypi")
        assert limiter1 is limiter2


# =========================================================================
# I-05: Offline mode tests
# =========================================================================


class TestOfflineMode:
    def test_offline_env_var(self):
        from engineering_brain.validation.orchestrator import _is_offline_mode

        old = os.environ.get("BRAIN_VALIDATION_OFFLINE")
        try:
            os.environ["BRAIN_VALIDATION_OFFLINE"] = "true"
            assert _is_offline_mode() is True
            os.environ["BRAIN_VALIDATION_OFFLINE"] = "false"
            assert _is_offline_mode() is False
            os.environ["BRAIN_VALIDATION_OFFLINE"] = "1"
            assert _is_offline_mode() is True
            os.environ["BRAIN_VALIDATION_OFFLINE"] = ""
            assert _is_offline_mode() is False
        finally:
            if old is not None:
                os.environ["BRAIN_VALIDATION_OFFLINE"] = old
            else:
                os.environ.pop("BRAIN_VALIDATION_OFFLINE", None)


# =========================================================================
# Integration: ValidationReport
# =========================================================================


class TestValidationReport:
    def test_report_summary(self):
        from engineering_brain.validation.orchestrator import ValidationReport

        report = ValidationReport()
        report.total_nodes = 100
        report.validated = 80
        report.cache_hits = 20
        report.api_calls = 15
        summary = report.summary()
        assert "100" in summary
        assert "80" in summary
        assert "15" in summary

    def test_report_by_checker(self):
        from engineering_brain.validation.orchestrator import ValidationReport

        report = ValidationReport()
        report.by_checker["OfficialDocsChecker"] = 50
        report.by_checker["NVDChecker"] = 10
        summary = report.summary()
        assert "OfficialDocsChecker" in summary
        assert "NVDChecker" in summary


# =========================================================================
# I-04: ObservationLog.record_feedback test
# =========================================================================


class TestObservationLogFeedback:
    def test_record_feedback(self):
        import tempfile

        from engineering_brain.observation.log import ObservationLog

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            log = ObservationLog(path)
            log.record_feedback(rule_id="CR-TEST-001", reason="too vague", context="Flask CORS")
            observations = log.read_all()
            assert len(observations) == 1
            obs = observations[0]
            assert "CR-TEST-001" in obs.rule_ids
            assert obs.outcome == "negative"
            assert obs.metadata.get("source") == "agent_feedback"
            assert obs.metadata.get("reason") == "too vague"
        finally:
            os.unlink(path)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
