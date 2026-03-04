"""Async batch embedding pipeline for the Engineering Knowledge Brain.

Provides async batch embedding with:
- Configurable concurrency (default 5)
- Rate limiting per API provider
- Circuit breaker on repeated failures
- Graceful degradation (never blocks brain operations)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Circuit breaker states
_CB_CLOSED = "closed"
_CB_OPEN = "open"
_CB_HALF_OPEN = "half_open"


class CircuitBreaker:
    """Simple circuit breaker for API calls."""

    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 60.0) -> None:
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._state = _CB_CLOSED
        self._last_failure_time = 0.0

    @property
    def is_open(self) -> bool:
        if self._state == _CB_OPEN:
            if time.time() - self._last_failure_time > self._reset_timeout:
                self._state = _CB_HALF_OPEN
                return False
            return True
        return False

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = _CB_CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self._failure_threshold:
            self._state = _CB_OPEN


class AsyncEmbeddingPipeline:
    """Async batch embedding with rate limiting and circuit breaker."""

    def __init__(
        self,
        max_concurrency: int = 5,
        rate_limit_per_second: float = 10.0,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._max_concurrency = max_concurrency
        self._rate_limit = rate_limit_per_second
        self._min_interval = 1.0 / rate_limit_per_second if rate_limit_per_second > 0 else 0
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._semaphore: asyncio.Semaphore | None = None
        self._last_call_time = 0.0
        self._rate_lock = asyncio.Lock()
        self._embedder = None

    def _get_embedder(self) -> Any:
        """Lazy-load the embedding provider."""
        if self._embedder is not None:
            return self._embedder
        try:
            from pipeline_autonomo.embedding_provider import get_embedding_provider

            self._embedder = get_embedding_provider()
            return self._embedder
        except ImportError:
            logger.info(
                "pipeline_autonomo not installed — async embedding disabled. "
                "Install fastembed or voyageai for standalone embedding support."
            )
            return None
        except Exception as e:
            logger.warning("Embedding provider unavailable: %s", e)
            return None

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 50,
    ) -> list[list[float] | None]:
        """Embed a batch of texts asynchronously.

        Returns list of embeddings (None for failed items).
        """
        if not texts:
            return []

        embedder = self._get_embedder()
        if embedder is None:
            return [None] * len(texts)

        if self._circuit_breaker.is_open:
            logger.warning("Circuit breaker OPEN — skipping embedding batch")
            return [None] * len(texts)

        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrency)

        results: list[list[float] | None] = [None] * len(texts)
        tasks: list[asyncio.Task[None]] = []

        for batch_start in range(0, len(texts), batch_size):
            batch_end = min(batch_start + batch_size, len(texts))
            batch_texts = texts[batch_start:batch_end]
            task = asyncio.create_task(
                self._embed_sub_batch(
                    embedder,
                    batch_texts,
                    results,
                    batch_start,
                )
            )
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def _embed_sub_batch(
        self,
        embedder: Any,
        texts: list[str],
        results: list[list[float] | None],
        offset: int,
    ) -> None:
        """Embed a sub-batch with rate limiting and circuit breaker."""
        if self._semaphore is None:
            return
        async with self._semaphore:
            # Rate limiting (synchronized to avoid race on _last_call_time)
            async with self._rate_lock:
                now = time.time()
                elapsed = now - self._last_call_time
                if elapsed < self._min_interval:
                    await asyncio.sleep(self._min_interval - elapsed)
                self._last_call_time = time.time()

            try:
                # Run synchronous embedding in executor to not block event loop
                loop = asyncio.get_event_loop()
                embeddings = await loop.run_in_executor(
                    None,
                    embedder.embed_batch,
                    texts,
                )
                self._circuit_breaker.record_success()
                for i, emb in enumerate(embeddings):
                    results[offset + i] = emb
            except Exception as e:
                self._circuit_breaker.record_failure()
                logger.warning("Async embedding batch failed: %s", e)

    async def embed_nodes(
        self,
        nodes: list[dict[str, Any]],
        text_key: str = "text",
        batch_size: int = 50,
    ) -> dict[str, list[float]]:
        """Embed a list of knowledge nodes.

        Returns dict of {node_id: embedding} for successfully embedded nodes.
        """
        texts: list[str] = []
        ids: list[str] = []
        for node in nodes:
            nid = node.get("id", "")
            text = node.get(text_key) or node.get("name") or node.get("statement", "")
            why = node.get("why", "")
            combined = f"{text} {why}".strip()
            if nid and combined:
                texts.append(combined)
                ids.append(nid)

        embeddings = await self.embed_batch(texts, batch_size=batch_size)

        result: dict[str, list[float]] = {}
        for nid, emb in zip(ids, embeddings, strict=False):
            if emb is not None:
                result[nid] = emb

        return result


def get_async_embedding_pipeline(
    max_concurrency: int = 5,
    rate_limit: float = 10.0,
) -> AsyncEmbeddingPipeline:
    """Get a configured async embedding pipeline instance."""
    return AsyncEmbeddingPipeline(
        max_concurrency=max_concurrency,
        rate_limit_per_second=rate_limit,
    )
