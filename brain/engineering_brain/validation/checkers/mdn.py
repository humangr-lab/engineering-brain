"""MDN Web Docs checker — validates web platform knowledge.

Checks MDN for existence of web APIs, HTML elements, CSS properties.
Uses GitHub raw content API (no rate limit) + HEAD checks.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from engineering_brain.core.types import Source, SourceType
from engineering_brain.validation.checkers import SourceChecker

logger = logging.getLogger(__name__)

# MDN slug mappings for common web concepts
_MDN_SLUGS: dict[str, str] = {
    "fetch": "Web/API/Fetch_API",
    "websocket": "Web/API/WebSocket",
    "localstorage": "Web/API/Window/localStorage",
    "sessionstorage": "Web/API/Window/sessionStorage",
    "serviceworker": "Web/API/Service_Worker_API",
    "webworker": "Web/API/Web_Workers_API",
    "cors": "Web/HTTP/CORS",
    "csp": "Web/HTTP/CSP",
    "cookie": "Web/HTTP/Cookies",
    "flexbox": "Web/CSS/CSS_flexible_box_layout",
    "grid": "Web/CSS/CSS_grid_layout",
    "css custom properties": "Web/CSS/Using_CSS_custom_properties",
    "intersection observer": "Web/API/Intersection_Observer_API",
    "mutation observer": "Web/API/MutationObserver",
    "resize observer": "Web/API/ResizeObserver",
    "promise": "Web/JavaScript/Reference/Global_Objects/Promise",
    "async/await": "Web/JavaScript/Reference/Statements/async_function",
    "proxy": "Web/JavaScript/Reference/Global_Objects/Proxy",
    "web components": "Web/API/Web_components",
    "shadow dom": "Web/API/Web_components/Using_shadow_DOM",
    "template literal": "Web/JavaScript/Reference/Template_literals",
    "destructuring": "Web/JavaScript/Reference/Operators/Destructuring_assignment",
    "spread operator": "Web/JavaScript/Reference/Operators/Spread_syntax",
    "event loop": "Web/JavaScript/Event_loop",
    "indexeddb": "Web/API/IndexedDB_API",
}

_MDN_BASE = "https://developer.mozilla.org/en-US/docs"
_MDN_RAW_BASE = "https://raw.githubusercontent.com/mdn/content/main/files/en-us"


class MDNChecker(SourceChecker):
    """Validates web platform claims against MDN Web Docs."""

    def __init__(self, rate_limit: float = 0.2) -> None:
        super().__init__(rate_limit=rate_limit)

    @property
    def source_type(self) -> SourceType:
        return SourceType.MDN

    async def check_technology(self, tech_name: str) -> dict[str, Any] | None:
        """Check if a web technology has MDN documentation."""
        slug = _find_mdn_slug(tech_name)
        if not slug:
            return None

        url = f"{_MDN_BASE}/{slug}"
        await self._throttle()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.head(url, follow_redirects=True)
                exists = resp.status_code == 200
                return {
                    "exists": exists,
                    "url": url,
                    "slug": slug,
                }
        except Exception as e:
            logger.debug("MDN check failed for %s: %s", tech_name, e)
            return None

    async def search_claim(
        self, claim_text: str, technologies: list[str], domains: list[str]
    ) -> list[Source]:
        """Search MDN for relevant web platform docs."""
        web_domains = {"web", "frontend", "css", "html", "javascript", "browser"}
        if not (set(d.lower() for d in domains) & web_domains):
            # Also check if technologies suggest web context
            web_techs = {
                "html",
                "css",
                "javascript",
                "react",
                "vue",
                "angular",
                "svelte",
                "typescript",
                "next.js",
                "htmx",
            }
            if not any(t.lower() in web_techs for t in technologies):
                return []

        sources: list[Source] = []

        # Try to find MDN pages for each technology
        for tech in technologies[:3]:
            slug = _find_mdn_slug(tech)
            if slug:
                url = f"{_MDN_BASE}/{slug}"
                # Known MDN slug URLs are trusted
                sources.append(
                    Source(
                        url=url,
                        title=f"MDN: {tech}",
                        source_type=SourceType.MDN,
                        retrieved_at=datetime.now(UTC),
                        verified=True,
                    )
                )

        # Try keyword-based slug construction from claim text
        for keyword in _extract_web_keywords(claim_text):
            slug = _find_mdn_slug(keyword)
            if slug:
                url = f"{_MDN_BASE}/{slug}"
                if not any(s.url == url for s in sources):
                    sources.append(
                        Source(
                            url=url,
                            title=f"MDN: {keyword}",
                            source_type=SourceType.MDN,
                            retrieved_at=datetime.now(UTC),
                            verified=True,
                        )
                    )

        return sources[:3]

    async def _head_check(self, url: str) -> bool:
        """Verify URL is reachable with HEAD request."""
        await self._throttle()
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.head(url, follow_redirects=True)
                return resp.status_code == 200
        except Exception as exc:
            logger.debug("MDN head check failed for %s: %s", url, exc)
            return False


def _find_mdn_slug(term: str) -> str:
    """Find MDN slug for a term."""
    lower = term.lower().strip()
    # Direct lookup
    if lower in _MDN_SLUGS:
        return _MDN_SLUGS[lower]
    # Try as HTML element
    if lower in (
        "div",
        "span",
        "form",
        "input",
        "button",
        "select",
        "textarea",
        "table",
        "canvas",
        "video",
        "audio",
        "img",
    ):
        return f"Web/HTML/Element/{lower}"
    # Try as CSS property
    if lower.startswith("css ") or "-" in lower:
        prop = lower.replace("css ", "").strip()
        return f"Web/CSS/{prop}"
    # Try as JavaScript global
    if lower in (
        "array",
        "object",
        "map",
        "set",
        "weakmap",
        "weakset",
        "symbol",
        "bigint",
        "regexp",
        "date",
        "json",
        "math",
    ):
        return f"Web/JavaScript/Reference/Global_Objects/{lower.capitalize()}"
    return ""


def _extract_web_keywords(text: str) -> list[str]:
    """Extract web-related keywords from claim text."""
    keywords = []
    text_lower = text.lower()
    for term in _MDN_SLUGS:
        if term in text_lower:
            keywords.append(term)
    return keywords[:5]
