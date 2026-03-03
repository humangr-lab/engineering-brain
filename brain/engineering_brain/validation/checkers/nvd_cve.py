"""NIST NVD checker — security claim validation via CVE database.

Only used for rules with security domain. Checks if there are
real CVEs backing the security advice.

Rate limit: 5 req/30s without key, 10 req/s with key.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from engineering_brain.core.types import Source, SourceType
from engineering_brain.validation.checkers import SourceChecker

logger = logging.getLogger(__name__)


class NVDChecker(SourceChecker):
    """Cross-references security claims against NIST NVD."""

    def __init__(self, api_key: str = "", rate_limit: float = 0.15):
        super().__init__(rate_limit=rate_limit)
        self._api_key = api_key
        self._base_url = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    @property
    def source_type(self) -> SourceType:
        return SourceType.SECURITY_CVE

    async def check_technology(self, tech_name: str) -> dict[str, Any] | None:
        """NVD doesn't do technology existence checks."""
        return None

    async def search_claim(self, claim_text: str, technologies: list[str], domains: list[str]) -> list[Source]:
        """Search NVD for CVEs related to the security claim."""
        if "security" not in domains and "auth" not in " ".join(domains):
            return []

        keyword = _extract_vuln_keyword(claim_text, technologies)
        if not keyword:
            return []

        await self._throttle()
        try:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["apiKey"] = self._api_key

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    self._base_url,
                    params={"keywordSearch": keyword, "resultsPerPage": 5},
                    headers=headers,
                )
                data = resp.json()

            sources: list[Source] = []
            for vuln in data.get("vulnerabilities", [])[:3]:
                cve = vuln.get("cve", {})
                cve_id = cve.get("id", "")
                descriptions = cve.get("descriptions", [])
                desc = next((d["value"] for d in descriptions if d.get("lang") == "en"), "")

                # Extract CVSS score
                metrics = cve.get("metrics", {})
                cvss_score = None
                for version in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                    metric_list = metrics.get(version, [])
                    if metric_list:
                        cvss_data = metric_list[0].get("cvssData", {})
                        cvss_score = cvss_data.get("baseScore")
                        break

                sources.append(Source(
                    url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                    title=f"{cve_id}: {desc[:100]}",
                    source_type=SourceType.SECURITY_CVE,
                    retrieved_at=datetime.now(timezone.utc),
                    cvss_score=cvss_score,
                    verified=True,
                ))

            return sources

        except Exception as e:
            logger.debug("NVD search failed for '%s': %s", keyword, e)
            return []


def _extract_vuln_keyword(claim_text: str, technologies: list[str]) -> str:
    """Extract a search keyword from a security claim."""
    # Combine primary technology with key security terms
    tech = technologies[0] if technologies else ""
    text_lower = claim_text.lower()

    vuln_terms = []
    for term in ("cors", "xss", "injection", "traversal", "auth", "csrf",
                 "ssrf", "deserialization", "overflow", "race condition",
                 "privilege", "bypass", "arbitrary", "remote code"):
        if term in text_lower:
            vuln_terms.append(term)

    if vuln_terms:
        return f"{tech} {vuln_terms[0]}".strip()
    return tech
