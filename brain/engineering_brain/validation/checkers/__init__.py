"""Source checkers for knowledge validation.

Each checker queries one external API to find evidence supporting or
contradicting a knowledge claim.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from engineering_brain.core.types import Source, SourceType

logger = logging.getLogger(__name__)


class SourceChecker(ABC):
    """Abstract base for all source checkers."""

    def __init__(self, rate_limit: float = 1.0):
        self._rate_limit = rate_limit  # seconds between requests
        self._last_request: float = 0.0

    async def _throttle(self) -> None:
        """Enforce rate limit."""
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self._rate_limit:
            await asyncio.sleep(self._rate_limit - elapsed)
        self._last_request = time.monotonic()

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """Which source this checker queries."""

    @abstractmethod
    async def check_technology(self, tech_name: str) -> dict[str, Any] | None:
        """Check if a technology exists. Returns metadata dict or None."""

    @abstractmethod
    async def search_claim(self, claim_text: str, technologies: list[str], domains: list[str]) -> list[Source]:
        """Search for evidence related to a claim. Returns Source list."""

    def is_available(self) -> bool:
        """Check if this checker can be used (API key present, etc.)."""
        return True
