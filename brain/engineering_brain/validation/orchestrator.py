"""Validation orchestrator — async batch engine for knowledge cross-checking.

Uses a "technology-first" approach to minimize API calls:
1. Run zero-cost checkers (official_docs, mdn, owasp) instantly for all nodes
2. Batch API-calling checkers by unique technology (PyPI/npm once per tech)
3. Batch NVD/GHSA calls by unique security claim keyword
4. Distribute results from tech-level checks to all nodes sharing that tech

This reduces API calls from ~7000 to ~200 for 1,608 nodes.

Usage:
    report = await validate_all(brain)
    report = await validate_node(brain, "CR-SEC-CORS-001")
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from engineering_brain.core.config import BrainConfig, get_brain_config
from engineering_brain.core.types import Source, ValidationStatus
from engineering_brain.validation.cache import ValidationCache
from engineering_brain.validation.checkers import SourceChecker
from engineering_brain.validation.checkers.architecture_patterns import ArchitecturePatternsChecker
from engineering_brain.validation.checkers.github_advisory import GitHubAdvisoryChecker
from engineering_brain.validation.checkers.mdn import MDNChecker
from engineering_brain.validation.checkers.nvd_cve import NVDChecker
from engineering_brain.validation.checkers.official_docs import (
    OfficialDocsChecker,
    resolve_technology,
)
from engineering_brain.validation.checkers.owasp import OWASPChecker
from engineering_brain.validation.checkers.package_registry import PackageRegistryChecker
from engineering_brain.validation.checkers.stackoverflow import StackOverflowChecker
from engineering_brain.validation.router import ValidationRouter

logger = logging.getLogger(__name__)


def _is_offline_mode() -> bool:
    """I-05: Offline mode — only run zero-cost checkers."""
    return os.getenv("BRAIN_VALIDATION_OFFLINE", "").lower() in ("true", "1", "yes")


class ValidationReport:
    """Results from a validation run."""

    def __init__(self) -> None:
        self.total_nodes: int = 0
        self.validated: int = 0
        self.cache_hits: int = 0
        self.api_calls: int = 0
        self.errors: int = 0
        self.by_status: dict[str, int] = {
            "human_verified": 0,
            "cross_checked": 0,
            "unvalidated": 0,
        }
        self.by_checker: dict[str, int] = {}
        self.elapsed_seconds: float = 0.0
        self.node_results: list[dict[str, Any]] = []

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            "Validation Report",
            f"  Total nodes:     {self.total_nodes}",
            f"  Validated:       {self.validated}",
            f"  Cache hits:      {self.cache_hits}",
            f"  API calls:       {self.api_calls}",
            f"  Errors:          {self.errors}",
            f"  Elapsed:         {self.elapsed_seconds:.1f}s",
            "  By status:",
            f"    human_verified:  {self.by_status['human_verified']}",
            f"    cross_checked:   {self.by_status['cross_checked']}",
            f"    unvalidated:     {self.by_status['unvalidated']}",
        ]
        if self.by_checker:
            lines.append("  By checker:")
            for name, count in sorted(self.by_checker.items()):
                lines.append(f"    {name}: {count} sources found")
        return "\n".join(lines)


class TokenBucketRateLimiter:
    """I-03: Per-API token bucket rate limiter.

    Limits API calls to max `rate` calls per second.
    Thread-safe via asyncio.Lock.
    """

    def __init__(self, rate: float = 1.0, burst: int = 5) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


# Shared rate limiters per API (I-03)
_rate_limiters: dict[str, TokenBucketRateLimiter] = {}


def _get_rate_limiter(api: str) -> TokenBucketRateLimiter:
    """Get or create rate limiter for an API."""
    if api not in _rate_limiters:
        defaults = {
            "pypi": TokenBucketRateLimiter(rate=1.0, burst=5),
            "npm": TokenBucketRateLimiter(rate=1.0, burst=5),
            "nvd": TokenBucketRateLimiter(rate=0.15, burst=2),
            "stackoverflow": TokenBucketRateLimiter(rate=0.5, burst=3),
            "github": TokenBucketRateLimiter(rate=1.0, burst=5),
        }
        _rate_limiters[api] = defaults.get(api, TokenBucketRateLimiter())
    return _rate_limiters[api]


def _build_checkers(config: BrainConfig) -> dict[str, SourceChecker]:
    """Initialize all available checkers."""
    checkers: dict[str, SourceChecker] = {}
    checkers["official_docs"] = OfficialDocsChecker(rate_limit=0.2)
    checkers["mdn"] = MDNChecker(rate_limit=0.2)
    checkers["owasp"] = OWASPChecker(rate_limit=0.2)
    checkers["architecture_patterns"] = ArchitecturePatternsChecker(rate_limit=0.0)
    checkers["package_registry"] = PackageRegistryChecker(rate_limit=0.1)
    checkers["stackoverflow"] = StackOverflowChecker(
        api_key=config.so_api_key,
        rate_limit=config.validation_rate_so,
    )
    checkers["nvd_cve"] = NVDChecker(
        api_key=config.nvd_api_key,
        rate_limit=config.validation_rate_nvd,
    )
    if config.github_token:
        checkers["github_advisory"] = GitHubAdvisoryChecker(
            token=config.github_token,
            rate_limit=0.3,
        )
    return checkers


async def validate_all(
    brain: Any,
    config: BrainConfig | None = None,
    force_refresh: bool = False,
    dry_run: bool = False,
    max_concurrency: int = 20,
    layer_filter: str = "",
    progress_callback: Any = None,
) -> ValidationReport:
    """Validate all knowledge nodes using technology-first batching.

    Phase 1: Zero-cost checkers (instant, no API calls)
    Phase 2: Batch API calls by unique technology
    Phase 3: Batch NVD calls by unique security keyword
    """
    cfg = config or get_brain_config()
    report = ValidationReport()
    t0 = time.monotonic()

    # Load knowledge nodes (filter out tech/domain helper nodes)
    all_nodes = brain._graph.get_all_nodes()
    knowledge_nodes = [
        n for n in all_nodes if n.get("id", "").startswith(("AX-", "P-", "PAT-", "CR-"))
    ]
    if layer_filter:
        knowledge_nodes = [n for n in knowledge_nodes if _node_layer(n) == layer_filter.upper()]
    report.total_nodes = len(knowledge_nodes)
    logger.info("Validating %d knowledge nodes", len(knowledge_nodes))

    checkers = _build_checkers(cfg)
    cache = ValidationCache(
        cache_dir=cfg.validation_cache_dir, ttl_days=cfg.validation_cache_ttl_days
    )

    if dry_run:
        router = ValidationRouter(checkers)
        for node in knowledge_nodes:
            node_checkers = router.route(node)
            report.node_results.append(
                {
                    "id": node.get("id", "?"),
                    "layer": _node_layer(node),
                    "checkers": [type(c).__name__ for c in node_checkers],
                }
            )
            if _node_layer(node) == "L0":
                report.by_status["human_verified"] += 1
            elif node_checkers:
                report.by_status["unvalidated"] += 1
            else:
                report.by_status["unvalidated"] += 1
        report.elapsed_seconds = time.monotonic() - t0
        return report

    # =====================================================================
    # Phase 0: Auto-mark L0 axioms + check cache
    # =====================================================================
    nodes_needing_validation: list[dict[str, Any]] = []
    for node in knowledge_nodes:
        node_id = node.get("id", "")
        if _node_layer(node) == "L0":
            brain._graph.update_node(
                node_id, {"validation_status": ValidationStatus.HUMAN_VERIFIED.value}
            )
            report.by_status["human_verified"] += 1
            report.validated += 1
            continue

        if not force_refresh:
            cached = cache.get(f"v1:{node_id}")
            if cached:
                _apply_cached(node_id, cached, brain)
                status = cached.get("validation_status", "unvalidated")
                report.by_status[status] = report.by_status.get(status, 0) + 1
                report.cache_hits += 1
                report.validated += 1
                continue

        nodes_needing_validation.append(node)

    total_to_validate = len(nodes_needing_validation)
    logger.info(
        "Phase 0 done: %d axioms marked, %d cache hits, %d need validation",
        report.by_status["human_verified"],
        report.cache_hits,
        total_to_validate,
    )

    if not nodes_needing_validation:
        report.elapsed_seconds = time.monotonic() - t0
        return report

    # =====================================================================
    # Phase 1: Zero-cost checkers (pure lookup, no HTTP calls)
    # Run official_docs, mdn, owasp for every node — instant
    # =====================================================================
    offline = _is_offline_mode()
    if offline:
        logger.info("Offline mode: skipping API-dependent checkers (Phase 2+3)")

    zero_cost_checkers = {
        "official_docs": checkers["official_docs"],
        "mdn": checkers["mdn"],
        "owasp": checkers["owasp"],
        "architecture_patterns": checkers["architecture_patterns"],
    }
    # Pre-compute sources per node from zero-cost checkers
    node_sources: dict[str, list[Source]] = defaultdict(list)

    for node in nodes_needing_validation:
        node_id = node.get("id", "")
        # I-02: Resolve technology aliases for better matching
        techs = [resolve_technology(t) for t in node.get("technologies", [])]
        domains = node.get("domains", [])
        claim = node.get("text", node.get("name", ""))

        for checker in zero_cost_checkers.values():
            try:
                sources = await checker.search_claim(claim, techs, domains)
                node_sources[node_id].extend(sources)
                report.by_checker[type(checker).__name__] = report.by_checker.get(
                    type(checker).__name__, 0
                ) + len(sources)
            except Exception as exc:
                logger.debug(
                    "Zero-cost checker %s failed for node %s: %s",
                    type(checker).__name__,
                    node_id,
                    exc,
                )

    completed = 0
    if progress_callback:
        progress_callback(0, total_to_validate)

    # =====================================================================
    # Phase 2: Batch PyPI/npm calls by unique technology name
    # Instead of 1266 calls, we make ~130 (one per unique tech)
    # I-05: Skip entirely in offline mode
    # =====================================================================
    if not offline:
        pkg_checker = checkers["package_registry"]
        tech_to_nodes: dict[str, list[str]] = defaultdict(list)

        for node in nodes_needing_validation:
            node_id = node.get("id", "")
            # I-02: Resolve aliases for package registry lookup
            for tech in node.get("technologies", []):
                tech_to_nodes[resolve_technology(tech)].append(node_id)

        unique_techs = list(tech_to_nodes.keys())
        logger.info("Phase 2: %d unique technologies to check on PyPI/npm", len(unique_techs))

        tech_sources: dict[str, list[Source]] = {}
        sem = asyncio.Semaphore(5)

        async def _check_tech(tech: str) -> None:
            async with sem:
                try:
                    sources = await pkg_checker.search_claim("", [tech], [])
                    tech_sources[tech] = sources
                    report.api_calls += 1
                    report.by_checker["PackageRegistryChecker"] = report.by_checker.get(
                        "PackageRegistryChecker", 0
                    ) + len(sources)
                except Exception as e:
                    logger.debug("PyPI/npm check failed for %s: %s", tech, e)
                    report.errors += 1
                    tech_sources[tech] = []

        await asyncio.gather(*[_check_tech(t) for t in unique_techs], return_exceptions=True)

        for tech, node_ids in tech_to_nodes.items():
            for nid in node_ids:
                node_sources[nid].extend(tech_sources.get(tech, []))

    # =====================================================================
    # Phase 3: Batch NVD/GHSA calls for security-domain nodes
    # Only call NVD once per unique (tech, vuln_keyword) pair
    # I-05: Skip entirely in offline mode
    # =====================================================================
    nvd_checker = checkers["nvd_cve"]
    ghsa_checker = checkers.get("github_advisory")
    security_nodes = [
        n
        for n in nodes_needing_validation
        if "security" in [d.lower() for d in n.get("domains", [])]
    ]

    if security_nodes and not offline:
        # Deduplicate by first technology
        seen_keywords: set[str] = set()
        nvd_tasks: list[tuple[str, str, list[str]]] = []

        for node in security_nodes:
            techs = node.get("technologies", [])
            primary_tech = techs[0] if techs else ""
            claim = node.get("text", node.get("name", ""))
            keyword = _extract_security_keyword(claim, primary_tech)
            if keyword and keyword not in seen_keywords:
                seen_keywords.add(keyword)
                nvd_tasks.append((keyword, primary_tech, [node.get("id", "")]))

        logger.info("Phase 3: %d unique security keywords for NVD", len(nvd_tasks))

        keyword_sources: dict[str, list[Source]] = {}

        async def _check_nvd(keyword: str, tech: str) -> None:
            async with sem:
                all_s: list[Source] = []
                try:
                    s = await nvd_checker.search_claim(
                        keyword, [tech] if tech else [], ["security"]
                    )
                    all_s.extend(s)
                    report.api_calls += 1
                    report.by_checker["NVDChecker"] = report.by_checker.get("NVDChecker", 0) + len(
                        s
                    )
                except Exception as e:
                    logger.debug("NVD check failed for %s: %s", keyword, e)
                    report.errors += 1
                if ghsa_checker:
                    try:
                        s = await ghsa_checker.search_claim(
                            keyword, [tech] if tech else [], ["security"]
                        )
                        all_s.extend(s)
                        report.api_calls += 1
                        report.by_checker["GitHubAdvisoryChecker"] = report.by_checker.get(
                            "GitHubAdvisoryChecker", 0
                        ) + len(s)
                    except Exception as exc:
                        logger.warning("GHSA checker failed for keyword %s: %s", keyword, exc)
                        report.errors += 1
                keyword_sources[keyword] = all_s

        await asyncio.gather(*[_check_nvd(kw, t) for kw, t, _ in nvd_tasks], return_exceptions=True)

        # Distribute security sources to matching nodes
        for node in security_nodes:
            nid = node.get("id", "")
            techs = node.get("technologies", [])
            primary_tech = techs[0] if techs else ""
            claim = node.get("text", node.get("name", ""))
            keyword = _extract_security_keyword(claim, primary_tech)
            if keyword and keyword in keyword_sources:
                node_sources[nid].extend(keyword_sources[keyword])

    # =====================================================================
    # Phase 4: Apply results to all nodes
    # =====================================================================
    for node in nodes_needing_validation:
        node_id = node.get("id", "")
        sources = node_sources.get(node_id, [])

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_sources: list[Source] = []
        for s in sources:
            if s.url not in seen_urls:
                seen_urls.add(s.url)
                unique_sources.append(s)

        verified_count = sum(1 for s in unique_sources if s.verified)
        if verified_count >= 1:
            status = ValidationStatus.CROSS_CHECKED
        else:
            status = ValidationStatus.UNVALIDATED

        source_dicts = [s.model_dump(mode="json") for s in unique_sources[:5]]
        brain._graph.update_node(
            node_id,
            {
                "validation_status": status.value,
                "sources": source_dicts,
            },
        )

        cache.put(
            f"v1:{node_id}",
            {
                "validation_status": status.value,
                "sources": source_dicts,
                "checked_at": datetime.now(UTC).isoformat(),
            },
        )

        report.by_status[status.value] = report.by_status.get(status.value, 0) + 1
        report.validated += 1
        completed += 1
        if progress_callback:
            progress_callback(completed, total_to_validate)

    cache.save()
    report.elapsed_seconds = time.monotonic() - t0
    logger.info("Validation complete: %s", report.summary())
    return report


async def validate_node(
    brain: Any,
    node_id: str,
    config: BrainConfig | None = None,
    force_refresh: bool = True,
) -> dict[str, Any]:
    """Validate a single knowledge node (uses all checkers, not batched)."""
    cfg = config or get_brain_config()
    node = brain._graph.get_node(node_id)
    if not node:
        return {"error": f"Node {node_id} not found"}

    checkers = _build_checkers(cfg)
    router = ValidationRouter(checkers)
    node_checkers = router.route(node)

    if not node_checkers and _node_layer(node) == "L0":
        return {
            "id": node_id,
            "validation_status": "human_verified",
            "sources": [],
            "note": "L0 axioms are auto-verified",
        }

    technologies = node.get("technologies", [])
    domains = node.get("domains", [])
    claim_text = node.get("text", node.get("name", node.get("statement", "")))

    all_sources: list[Source] = []
    checker_details: list[dict[str, Any]] = []

    for checker in node_checkers:
        checker_name = type(checker).__name__
        try:
            sources = await checker.search_claim(claim_text, technologies, domains)
            all_sources.extend(sources)
            checker_details.append(
                {
                    "checker": checker_name,
                    "sources_found": len(sources),
                    "urls": [s.url for s in sources],
                }
            )
        except Exception as e:
            checker_details.append({"checker": checker_name, "error": str(e)})

    verified_sources = [s for s in all_sources if s.verified]
    status = ValidationStatus.CROSS_CHECKED if verified_sources else ValidationStatus.UNVALIDATED

    source_dicts = [s.model_dump(mode="json") for s in all_sources[:5]]
    brain._graph.update_node(
        node_id,
        {
            "validation_status": status.value,
            "sources": source_dicts,
        },
    )

    return {
        "id": node_id,
        "claim": claim_text[:100],
        "validation_status": status.value,
        "sources": source_dicts,
        "checkers": checker_details,
    }


def _apply_cached(node_id: str, cached: dict[str, Any], brain: Any) -> None:
    """Apply cached validation result."""
    brain._graph.update_node(
        node_id,
        {
            "validation_status": cached.get("validation_status", "unvalidated"),
            "sources": cached.get("sources", []),
        },
    )


def _extract_security_keyword(claim: str, tech: str) -> str:
    """Extract unique keyword for NVD search from a security claim."""
    text_lower = claim.lower()
    for term in (
        "cors",
        "xss",
        "injection",
        "traversal",
        "auth",
        "csrf",
        "ssrf",
        "deserialization",
        "overflow",
        "race condition",
        "privilege",
        "bypass",
        "arbitrary",
        "remote code",
        "websocket",
    ):
        if term in text_lower:
            return f"{tech} {term}".strip()
    return tech


def _node_layer(node: dict[str, Any]) -> str:
    """Determine layer from node data."""
    node_id = node.get("id", "")
    if node_id.startswith("AX-"):
        return "L0"
    if node_id.startswith("P-"):
        return "L1"
    if node_id.startswith("PAT-"):
        return "L2"
    if node_id.startswith("CR-"):
        return "L3"
    # Fallback to field-based detection
    if "statement" in node and node.get("immutable"):
        return "L0"
    if "how_to_apply" in node and "mental_model" in node:
        return "L1"
    if "intent" in node or "when_to_use" in node:
        return "L2"
    return "L3"
