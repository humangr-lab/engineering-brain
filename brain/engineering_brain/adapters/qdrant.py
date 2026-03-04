"""Qdrant vector adapter for the Engineering Knowledge Brain.

Provides semantic search across knowledge layers using vector embeddings.

When used inside the pipeline, reuses the Qdrant singleton from pipeline_autonomo.
When used standalone (open-source install), falls back gracefully:
- _get_client() returns None if pipeline_autonomo is not installed
- All methods return empty results / False on unavailable client
- Use BRAIN_ADAPTER=memory for fully standalone operation (no Qdrant needed)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from engineering_brain.adapters.base import VectorAdapter
from engineering_brain.core.config import BrainConfig

logger = logging.getLogger(__name__)


@dataclass
class _VectorDocument:
    """Lightweight vector document for standalone use (no pipeline dependency)."""

    id: str
    text: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


_qdrant_client = None


def _get_client(config: BrainConfig | None = None) -> Any:
    """Lazy-load and return the Qdrant client singleton."""
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client
    try:
        from pipeline_autonomo.qdrant_client import get_qdrant_client

        _qdrant_client = get_qdrant_client()
        return _qdrant_client
    except ImportError:
        logger.info("pipeline_autonomo not installed — Qdrant adapter disabled (standalone mode)")
        return None
    except Exception as e:
        logger.warning("Qdrant connection failed: %s", e)
        return None


class QdrantVectorAdapter(VectorAdapter):
    """Qdrant adapter using the existing pipeline singleton client."""

    def __init__(self, config: BrainConfig | None = None) -> None:
        self._config = config
        self._prefix = config.qdrant_collection_prefix if config else "brain_"
        self._dimension = config.embedding_dimension if config else 1024

    def _client(self) -> Any:
        return _get_client(self._config)

    def _full_collection_name(self, collection: str) -> str:
        """Prefix collection name to avoid collisions with pipeline collections."""
        if collection.startswith(self._prefix):
            return collection
        return f"{self._prefix}{collection}"

    def upsert(
        self,
        collection: str,
        doc_id: str,
        text: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        client = self._client()
        if client is None:
            return False
        try:
            full_name = self._full_collection_name(collection)
            self.ensure_collection(collection, len(vector))
            try:
                from pipeline_autonomo.qdrant_client import VectorDocument
            except ImportError:
                VectorDocument = _VectorDocument
            doc = VectorDocument(
                id=doc_id,
                text=text,
                vector=vector,
                metadata=metadata or {},
            )
            client.insert_document(full_name, doc)
            return True
        except Exception as e:
            logger.error("Qdrant upsert failed: %s", e)
            return False

    def batch_upsert(self, collection: str, documents: list[dict[str, Any]]) -> int:
        client = self._client()
        if client is None:
            return 0
        try:
            full_name = self._full_collection_name(collection)
            if documents:
                self.ensure_collection(collection, len(documents[0].get("vector", [])))
            try:
                from pipeline_autonomo.qdrant_client import VectorDocument
            except ImportError:
                VectorDocument = _VectorDocument
            docs = []
            for doc in documents:
                docs.append(
                    VectorDocument(
                        id=doc["id"],
                        text=doc.get("text", ""),
                        vector=doc["vector"],
                        metadata=doc.get("metadata", {}),
                    )
                )
            return client.upsert_batch(full_name, docs)
        except Exception as e:
            logger.error("Qdrant batch_upsert failed: %s", e)
            return 0

    def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        client = self._client()
        if client is None:
            return []
        try:
            full_name = self._full_collection_name(collection)
            if not client.collection_exists(full_name):
                return []
            results = client.search_similar(
                collection=full_name,
                query_vector=query_vector,
                top_k=top_k,
                filters=filters,
                score_threshold=score_threshold,
            )
            return [
                {
                    "id": r.id,
                    "score": r.score,
                    "text": r.text,
                    "metadata": r.metadata,
                }
                for r in results
            ]
        except Exception as e:
            logger.error("Qdrant search failed: %s", e)
            return []

    def delete(self, collection: str, doc_id: str) -> bool:
        client = self._client()
        if client is None:
            return False
        try:
            full_name = self._full_collection_name(collection)
            return client.delete_by_id(full_name, doc_id)
        except Exception as e:
            logger.error("Qdrant delete failed: %s", e)
            return False

    def ensure_collection(self, collection: str, dimension: int) -> bool:
        client = self._client()
        if client is None:
            return False
        try:
            full_name = self._full_collection_name(collection)
            if not client.collection_exists(full_name):
                created = client.create_collection(full_name, dimension=dimension)
                if created:
                    self._configure_collection(full_name)
                return created
            else:
                # BUG-1 FIX: Validate dimension match on existing collection
                try:
                    info = client.get_collection_info(full_name)
                    existing_dim = info.get("dimension", 0)
                    if existing_dim and existing_dim != dimension:
                        logger.warning(
                            "Brain dimension mismatch for '%s': existing=%d, required=%d. Recreating.",
                            full_name,
                            existing_dim,
                            dimension,
                        )
                        client.delete_collection(full_name)
                        created = client.create_collection(full_name, dimension=dimension)
                        if created:
                            self._configure_collection(full_name)
                        return created
                except Exception as dim_err:
                    logger.warning("Failed to validate brain dimensions: %s", dim_err)
                    return False
                return True
        except Exception as e:
            logger.error("Qdrant ensure_collection failed: %s", e)
            return False

    def _configure_collection(self, full_name: str) -> None:
        """Apply payload indexes for optimal filtering performance."""
        client = self._client()
        if client is None:
            return
        try:
            raw = getattr(client, "_client", None)
            if raw is None:
                return
            from qdrant_client.models import PayloadSchemaType

            for field in ("layer", "domain", "technologies"):
                try:
                    raw.create_payload_index(
                        collection_name=full_name,
                        field_name=field,
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
                except Exception as exc:
                    logger.debug(
                        "Qdrant payload index creation skipped for field %s: %s", field, exc
                    )
        except ImportError:
            pass  # qdrant_client not available
        except Exception as e:
            logger.debug("Qdrant configure_collection failed (non-blocking): %s", e)

    def count(self, collection: str) -> int:
        client = self._client()
        if client is None:
            return 0
        try:
            full_name = self._full_collection_name(collection)
            if not client.collection_exists(full_name):
                return 0
            return client.count(full_name)
        except Exception as e:
            logger.error("Qdrant count failed: %s", e)
            return 0

    def health_check(self) -> bool:
        """Verify Qdrant connection with a lightweight operation."""
        try:
            client = self._client()
            if client is None:
                return False
            raw = getattr(client, "_client", None)
            if raw:
                raw.get_collections()
            return True
        except Exception as exc:
            logger.debug("Qdrant health check failed: %s", exc)
            return False

    def is_available(self) -> bool:
        try:
            client = self._client()
            return client is not None
        except Exception as exc:
            logger.debug("Qdrant availability check failed: %s", exc)
            return False
