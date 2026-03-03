"""Redis cache adapter for the Engineering Knowledge Brain (L2 cache tier).

Provides distributed caching across processes using Redis.
Falls back to no-op on connection failure — never blocks the brain.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from engineering_brain.adapters.base import CacheAdapter
from engineering_brain.core.config import BrainConfig

logger = logging.getLogger(__name__)

_redis_client = None


def _get_redis(config: BrainConfig | None = None):
    """Lazy-load Redis connection."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        cfg = config or BrainConfig()
        _redis_client = redis.Redis(
            host=cfg.redis_host,
            port=cfg.redis_port,
            db=cfg.redis_db,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        _redis_client.ping()
        return _redis_client
    except ImportError:
        logger.warning("redis package not installed — L2 cache disabled")
        return None
    except Exception as e:
        logger.warning("Redis connection failed (L2 cache disabled): %s", e)
        _redis_client = None
        return None


class RedisCacheAdapter(CacheAdapter):
    """Redis L2 cache with TTL and prefix-based invalidation."""

    def __init__(self, config: BrainConfig | None = None) -> None:
        self._config = config or BrainConfig()
        self._default_ttl = self._config.redis_cache_ttl
        self._prefix = "brain:"
        self._hits = 0
        self._misses = 0

    def _client(self):
        return _get_redis(self._config)

    def _key(self, key: str) -> str:
        if key.startswith(self._prefix):
            return key
        return f"{self._prefix}{key}"

    def get(self, key: str) -> Any | None:
        client = self._client()
        if client is None:
            self._misses += 1
            return None
        try:
            raw = client.get(self._key(key))
            if raw is None:
                self._misses += 1
                return None
            self._hits += 1
            return json.loads(raw)
        except Exception as e:
            logger.debug("Redis get failed: %s", e)
            self._misses += 1
            return None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        client = self._client()
        if client is None:
            return False
        try:
            ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
            serialized = json.dumps(value, default=str)
            client.setex(self._key(key), ttl, serialized)
            return True
        except Exception as e:
            logger.debug("Redis set failed: %s", e)
            return False

    def delete(self, key: str) -> bool:
        client = self._client()
        if client is None:
            return False
        try:
            return bool(client.delete(self._key(key)))
        except Exception as e:
            logger.debug("Redis delete failed: %s", e)
            return False

    def invalidate_prefix(self, prefix: str) -> int:
        client = self._client()
        if client is None:
            return 0
        try:
            full_prefix = self._key(prefix)
            keys = list(client.scan_iter(match=f"{full_prefix}*", count=100))
            if keys:
                return client.delete(*keys)
            return 0
        except Exception as e:
            logger.debug("Redis invalidate_prefix failed: %s", e)
            return 0

    def stats(self) -> dict[str, Any]:
        client = self._client()
        total = self._hits + self._misses
        base = {
            "hit_count": self._hits,
            "miss_count": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "available": client is not None,
        }
        if client is not None:
            try:
                keys = list(client.scan_iter(match=f"{self._prefix}*", count=1000))
                base["size"] = len(keys)
            except Exception:
                base["size"] = -1
        else:
            base["size"] = 0
        return base

    def is_available(self) -> bool:
        client = self._client()
        if client is None:
            return False
        try:
            return client.ping()
        except Exception:
            return False
