"""Disk-based JSON cache for validation results.

Avoids re-querying APIs for nodes that were recently validated.
Default TTL: 30 days. Cache location: ~/.engineering_brain/validation_cache.json
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ValidationCache:
    """Simple disk-backed JSON cache with TTL."""

    def __init__(self, cache_dir: str = "", ttl_days: int = 30):
        self._ttl_seconds = ttl_days * 86400
        if not cache_dir:
            cache_dir = os.path.join(os.path.expanduser("~"), ".engineering_brain")
        self._cache_dir = Path(cache_dir)
        self._cache_file = self._cache_dir / "validation_cache.json"
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load cache from disk."""
        if self._cache_file.exists():
            try:
                with open(self._cache_file) as f:
                    self._data = json.load(f)
                logger.info("Validation cache loaded: %d entries", len(self._data))
            except Exception as e:
                logger.warning("Cache load failed: %s", e)
                self._data = {}

    def save(self) -> None:
        """Persist cache to disk."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._cache_file, "w") as f:
                json.dump(self._data, f, indent=2, default=str)
        except Exception as e:
            logger.warning("Cache save failed: %s", e)

    def get(self, key: str) -> dict[str, Any] | None:
        """Get cached entry if not expired."""
        entry = self._data.get(key)
        if entry is None:
            return None
        cached_at = entry.get("_cached_at", 0)
        if time.time() - cached_at > self._ttl_seconds:
            del self._data[key]
            return None
        return entry

    def put(self, key: str, value: dict[str, Any]) -> None:
        """Store entry with current timestamp. Auto-saves every 10 writes."""
        value["_cached_at"] = time.time()
        self._data[key] = value
        self._writes_since_save = getattr(self, "_writes_since_save", 0) + 1
        if self._writes_since_save >= 10:
            self.save()
            self._writes_since_save = 0

    def clear(self) -> None:
        """Clear all cached entries."""
        self._data.clear()

    def stats(self) -> dict[str, int]:
        """Cache statistics."""
        now = time.time()
        expired = sum(1 for v in self._data.values() if now - v.get("_cached_at", 0) > self._ttl_seconds)
        return {
            "total": len(self._data),
            "valid": len(self._data) - expired,
            "expired": expired,
        }
