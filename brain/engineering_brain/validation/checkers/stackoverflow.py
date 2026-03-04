"""StackOverflow checker — community knowledge validation.

Searches SO for questions/answers related to a knowledge claim.
Uses vote counts and accepted answers as confidence proxy.

Rate limit: 300/day without key, 10,000/day with key.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from engineering_brain.core.types import Source, SourceType
from engineering_brain.validation.checkers import SourceChecker

logger = logging.getLogger(__name__)

# SO tag mapping — brain technology name → SO tag
_SO_TAGS: dict[str, str] = {
    "Flask": "flask",
    "FastAPI": "fastapi",
    "Django": "django",
    "React": "reactjs",
    "Vue": "vue.js",
    "Angular": "angular",
    "TypeScript": "typescript",
    "JavaScript": "javascript",
    "Python": "python",
    "Node.js": "node.js",
    "Kubernetes": "kubernetes",
    "Docker": "docker",
    "PostgreSQL": "postgresql",
    "MongoDB": "mongodb",
    "Redis": "redis",
    "GraphQL": "graphql",
    "CORS": "cors",
    "WebSocket": "websocket",
    "Flask-SocketIO": "flask-socketio",
    "Socket.IO": "socket.io",
    "Svelte": "svelte",
    "Next.js": "next.js",
    "Express": "express",
    "NestJS": "nestjs",
    "Tailwind CSS": "tailwind-css",
    "CSS": "css",
    "HTML": "html",
    "REST": "rest",
    "Rust": "rust",
    "Go": "go",
    "Java": "java",
    "Spring Boot": "spring-boot",
    "Ruby on Rails": "ruby-on-rails",
    "AWS": "amazon-web-services",
    "GCP": "google-cloud-platform",
    "Azure": "azure",
    "Terraform": "terraform",
    "Helm": "kubernetes-helm",
}


class StackOverflowChecker(SourceChecker):
    """Validates claims against StackOverflow community knowledge."""

    def __init__(self, api_key: str = "", rate_limit: float = 0.5) -> None:
        super().__init__(rate_limit=rate_limit)
        self._api_key = api_key
        self._base_url = "https://api.stackexchange.com/2.3"

    @property
    def source_type(self) -> SourceType:
        return SourceType.STACKOVERFLOW

    def is_available(self) -> bool:
        return True  # Works without key, just slower

    async def check_technology(self, tech_name: str) -> dict[str, Any] | None:
        """Check if a technology has an active SO tag."""
        tag = _SO_TAGS.get(tech_name, tech_name.lower().replace(" ", "-"))
        await self._throttle()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                params: dict[str, Any] = {
                    "site": "stackoverflow",
                    "inname": tag,
                    "pagesize": 1,
                }
                if self._api_key:
                    params["key"] = self._api_key
                resp = await client.get(f"{self._base_url}/tags", params=params)
                data = resp.json()
                items = data.get("items", [])
                if items:
                    return {
                        "exists": True,
                        "tag": items[0].get("name", tag),
                        "count": items[0].get("count", 0),
                    }
                return {"exists": False, "tag": tag, "count": 0}
        except Exception as e:
            logger.debug("SO tag check failed for %s: %s", tech_name, e)
            return None

    async def search_claim(
        self, claim_text: str, technologies: list[str], domains: list[str]
    ) -> list[Source]:
        """Search SO for questions related to a claim."""
        query = _build_search_query(claim_text, technologies)
        tags = _get_so_tags(technologies)

        await self._throttle()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                params: dict[str, Any] = {
                    "order": "desc",
                    "sort": "votes",
                    "q": query,
                    "site": "stackoverflow",
                    "pagesize": 5,
                    "filter": "!nNPvSNVZJS",
                }
                if tags:
                    params["tagged"] = tags
                if self._api_key:
                    params["key"] = self._api_key

                resp = await client.get(f"{self._base_url}/search/advanced", params=params)
                data = resp.json()

            sources: list[Source] = []
            for item in data.get("items", [])[:5]:
                score = item.get("score", 0)
                item.get("answer_count", 0)
                title = item.get("title", "")
                link = item.get("link", "")
                is_answered = item.get("is_answered", False)

                sources.append(
                    Source(
                        url=link,
                        title=f"SO: {title} (score={score})",
                        source_type=SourceType.STACKOVERFLOW,
                        retrieved_at=datetime.now(UTC),
                        vote_count=score,
                        is_accepted_answer=is_answered,
                        verified=True,
                    )
                )

            return sources

        except Exception as e:
            logger.debug("SO search failed: %s", e)
            return []


def _build_search_query(claim_text: str, technologies: list[str]) -> str:
    """Extract key terms from claim for SO search."""
    # Remove common filler words, keep technical terms
    text = claim_text[:200]
    # Remove code examples
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r'"[^"]*"', "", text)
    # Keep first meaningful sentence
    sentences = text.split(".")
    query = sentences[0].strip() if sentences else text
    # Add primary technology if not already in query
    if technologies:
        primary = technologies[0]
        if primary.lower() not in query.lower():
            query = f"{primary} {query}"
    return query[:150]


def _get_so_tags(technologies: list[str]) -> str:
    """Convert technology list to SO tag string."""
    tags = []
    for tech in technologies[:3]:
        tag = _SO_TAGS.get(tech, tech.lower().replace(" ", "-").replace(".", ""))
        if tag:
            tags.append(tag)
    return ";".join(tags)
