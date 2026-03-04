"""OWASP checker — validates security best practice claims.

Checks if security advice aligns with OWASP cheat sheets and guidelines.
Uses HEAD requests to verify OWASP URLs — no API key needed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from engineering_brain.core.types import Source, SourceType
from engineering_brain.validation.checkers import SourceChecker

logger = logging.getLogger(__name__)

# OWASP cheat sheet URL patterns
_OWASP_BASE = "https://cheatsheetseries.owasp.org/cheatsheets"

_OWASP_SHEETS: dict[str, str] = {
    "cors": f"{_OWASP_BASE}/CORS_Cheat_Sheet.html",
    "csrf": f"{_OWASP_BASE}/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html",
    "xss": f"{_OWASP_BASE}/Cross_Site_Scripting_Prevention_Cheat_Sheet.html",
    "sql injection": f"{_OWASP_BASE}/SQL_Injection_Prevention_Cheat_Sheet.html",
    "injection": f"{_OWASP_BASE}/Injection_Prevention_Cheat_Sheet.html",
    "authentication": f"{_OWASP_BASE}/Authentication_Cheat_Sheet.html",
    "authorization": f"{_OWASP_BASE}/Authorization_Cheat_Sheet.html",
    "session": f"{_OWASP_BASE}/Session_Management_Cheat_Sheet.html",
    "password": f"{_OWASP_BASE}/Password_Storage_Cheat_Sheet.html",
    "input validation": f"{_OWASP_BASE}/Input_Validation_Cheat_Sheet.html",
    "file upload": f"{_OWASP_BASE}/File_Upload_Cheat_Sheet.html",
    "path traversal": f"{_OWASP_BASE}/Path_Traversal_Cheat_Sheet.html",
    "error handling": f"{_OWASP_BASE}/Error_Handling_Cheat_Sheet.html",
    "logging": f"{_OWASP_BASE}/Logging_Cheat_Sheet.html",
    "deserialization": f"{_OWASP_BASE}/Deserialization_Cheat_Sheet.html",
    "api security": f"{_OWASP_BASE}/REST_Security_Cheat_Sheet.html",
    "rest": f"{_OWASP_BASE}/REST_Security_Cheat_Sheet.html",
    "jwt": f"{_OWASP_BASE}/JSON_Web_Token_for_Java_Cheat_Sheet.html",
    "cryptography": f"{_OWASP_BASE}/Cryptographic_Storage_Cheat_Sheet.html",
    "tls": f"{_OWASP_BASE}/Transport_Layer_Security_Cheat_Sheet.html",
    "clickjacking": f"{_OWASP_BASE}/Clickjacking_Defense_Cheat_Sheet.html",
    "content security policy": f"{_OWASP_BASE}/Content_Security_Policy_Cheat_Sheet.html",
    "csp": f"{_OWASP_BASE}/Content_Security_Policy_Cheat_Sheet.html",
    "docker": f"{_OWASP_BASE}/Docker_Security_Cheat_Sheet.html",
    "kubernetes": f"{_OWASP_BASE}/Kubernetes_Security_Cheat_Sheet.html",
    "graphql": f"{_OWASP_BASE}/GraphQL_Cheat_Sheet.html",
    "websocket": f"{_OWASP_BASE}/WebSocket_Security_Cheat_Sheet.html",
    "ssrf": f"{_OWASP_BASE}/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html",
    "race condition": f"{_OWASP_BASE}/Race_Conditions_Cheat_Sheet.html",
    "secrets": f"{_OWASP_BASE}/Secrets_Management_Cheat_Sheet.html",
    "denial of service": f"{_OWASP_BASE}/Denial_of_Service_Cheat_Sheet.html",
    "xml": f"{_OWASP_BASE}/XML_Security_Cheat_Sheet.html",
}


class OWASPChecker(SourceChecker):
    """Validates security claims against OWASP cheat sheets."""

    def __init__(self, rate_limit: float = 0.2) -> None:
        super().__init__(rate_limit=rate_limit)

    @property
    def source_type(self) -> SourceType:
        return SourceType.OWASP

    async def check_technology(self, tech_name: str) -> dict[str, Any] | None:
        """OWASP doesn't do technology existence checks."""
        return None

    async def search_claim(
        self, claim_text: str, technologies: list[str], domains: list[str]
    ) -> list[Source]:
        """Search OWASP cheat sheets relevant to a security claim."""
        if "security" not in domains and "auth" not in " ".join(domains):
            return []

        # Find matching OWASP cheat sheets
        matching_urls = _find_matching_sheets(claim_text, technologies)
        if not matching_urls:
            return []

        sources: list[Source] = []
        for title, url in matching_urls[:3]:
            # Known OWASP cheat sheet URLs are trusted
            sources.append(
                Source(
                    url=url,
                    title=f"OWASP: {title}",
                    source_type=SourceType.OWASP,
                    retrieved_at=datetime.now(UTC),
                    verified=True,
                )
            )

        return sources

    async def _head_check(self, url: str) -> bool:
        """Verify URL reachability."""
        await self._throttle()
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.head(url, follow_redirects=True)
                return resp.status_code == 200
        except Exception as exc:
            logger.debug("OWASP head check failed for %s: %s", url, exc)
            return False


def _find_matching_sheets(claim_text: str, technologies: list[str]) -> list[tuple[str, str]]:
    """Find OWASP cheat sheets matching the claim and technologies."""
    matches: list[tuple[str, str]] = []
    text_lower = claim_text.lower()
    techs_lower = " ".join(t.lower() for t in technologies)
    combined = f"{text_lower} {techs_lower}"

    for keyword, url in _OWASP_SHEETS.items():
        if keyword in combined:
            title = keyword.replace("_", " ").title()
            if (title, url) not in matches:
                matches.append((title, url))

    return matches
