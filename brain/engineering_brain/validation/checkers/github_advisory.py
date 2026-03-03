"""GitHub Advisory Database checker — security vulnerability validation.

Queries GitHub's security advisory API for known vulnerabilities
in referenced technologies. Requires GITHUB_TOKEN for rate limits.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from engineering_brain.core.types import Source, SourceType
from engineering_brain.validation.checkers import SourceChecker

logger = logging.getLogger(__name__)

# Map brain tech names → GitHub ecosystem
_ECOSYSTEM_MAP: dict[str, str] = {
    "Flask": "pip", "FastAPI": "pip", "Django": "pip",
    "Pydantic": "pip", "SQLAlchemy": "pip",
    "Flask-SocketIO": "pip", "Flask-CORS": "pip",
    "React": "npm", "Vue": "npm", "Angular": "npm",
    "Express": "npm", "Next.js": "npm", "Socket.IO": "npm",
    "Svelte": "npm", "Nuxt": "npm",
}


class GitHubAdvisoryChecker(SourceChecker):
    """Validates security claims against GitHub Security Advisories."""

    def __init__(self, token: str = "", rate_limit: float = 0.3):
        super().__init__(rate_limit=rate_limit)
        self._token = token

    @property
    def source_type(self) -> SourceType:
        return SourceType.GITHUB_ADVISORY

    def is_available(self) -> bool:
        return bool(self._token)

    async def check_technology(self, tech_name: str) -> dict[str, Any] | None:
        """Not used for technology existence checks."""
        return None

    async def search_claim(self, claim_text: str, technologies: list[str], domains: list[str]) -> list[Source]:
        """Search GitHub Advisories for security issues."""
        if "security" not in domains:
            return []
        if not self._token:
            return []

        # Find ecosystem for this technology
        ecosystem = None
        for tech in technologies:
            ecosystem = _ECOSYSTEM_MAP.get(tech)
            if ecosystem:
                break

        keyword = technologies[0] if technologies else ""
        if not keyword:
            return []

        await self._throttle()
        try:
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            params: dict[str, Any] = {"per_page": 5}
            if ecosystem:
                params["ecosystem"] = ecosystem
            params["keyword"] = keyword.lower()

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.github.com/advisories",
                    params=params,
                    headers=headers,
                )
                if resp.status_code != 200:
                    logger.debug("GitHub Advisory API returned %d", resp.status_code)
                    return []
                data = resp.json()

            sources: list[Source] = []
            for advisory in (data if isinstance(data, list) else [])[:3]:
                ghsa_id = advisory.get("ghsa_id", "")
                summary = advisory.get("summary", "")
                severity = advisory.get("severity", "")
                html_url = advisory.get("html_url", "")

                # Extract CVSS
                cvss = advisory.get("cvss", {})
                cvss_score = cvss.get("score") if cvss else None

                sources.append(Source(
                    url=html_url,
                    title=f"GHSA {ghsa_id}: {summary[:80]} [{severity}]",
                    source_type=SourceType.GITHUB_ADVISORY,
                    retrieved_at=datetime.now(timezone.utc),
                    cvss_score=cvss_score,
                    verified=True,
                ))

            return sources

        except Exception as e:
            logger.debug("GitHub Advisory search failed: %s", e)
            return []
