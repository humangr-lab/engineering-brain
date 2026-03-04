"""Qdrant vector adapter for the Engineering Knowledge Brain.

Provides semantic search across knowledge layers using vector embeddings.
Requires the `qdrant-client` package.

Graceful degradation:
- _get_client() returns None if qdrant-client is not installed
- All methods return empty results / False on unavailable client
- Use BRAIN_ADAPTER=memory for fully standalone operation (no Qdrant needed)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from engineering_brain.adapters.base import VectorAdapter
from engineering_brain.core.config import BrainConfig

logger = logging.getLogger(__name__)

_qdrant_client = None


def _get_client(config: BrainConfig | None = None) -> Any:
    """Lazy-load and return the Qdrant client singleton."""
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client
    try:
        from qdrant_client import QdrantClient

        host = config.qdrant_host if config else "localhost"
        port = config.qdrant_port if config else 6333
        _qdrant_client = QdrantClient(host=host, port=port)
        return _qdrant_client
    except ImportError:
        logger.info("qdrant-client package not installed — Qdrant adapter disabled")
        return None
    except Exception as e:
        logger.warning("Qdrant connection failed: %s", e)
        return None


def _stable_uuid(doc_id: str) -> str:
    """Convert a string doc_id to a deterministic UUID string for Qdrant point IDs."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id))


class QdrantVectorAdapter(VectorAdapter):
    """Qdrant vector adapter for semantic search."""

    def __init__(self, config: BrainConfig | None = None) -> None:
        self._config = config
        self._prefix = config.qdrant_collection_prefix if config else "brain_"
        self._dimension = config.embedding_dimension if config else 1024

    def _client(self) -> Any:
        return _get_client(self._config)

    def _full_collection_name(self, collection: str) -> str:
        """Prefix collection name for namespacing."""
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
            from qdrant_client.models import PointStruct

            full_name = self._full_collection_name(collection)
            self.ensure_collection(collection, len(vector))
            payload = {"text": text, **(metadata or {})}
            point = PointStruct(
                id=_stable_uuid(doc_id),
                vector=vector,
                payload={"doc_id": doc_id, **payload},
            )
            client.upsert(collection_name=full_name, points=[point])
            return True
        except Exception as e:
            logger.error("Qdrant upsert failed: %s", e)
            return False

    def batch_upsert(self, collection: str, documents: list[dict[str, Any]]) -> int:
        client = self._client()
        if client is None:
            return 0
        try:
            from qdrant_client.models import PointStruct

            full_name = self._full_collection_name(collection)
            if documents:
                self.ensure_collection(collection, len(documents[0].get("vector", [])))
            points = []
            for doc in documents:
                doc_id = doc["id"]
                payload = {
                    "doc_id": doc_id,
                    "text": doc.get("text", ""),
                    **(doc.get("metadata", {})),
                }
                points.append(
                    PointStruct(
                        id=_stable_uuid(doc_id),
                        vector=doc["vector"],
                        payload=payload,
                    )
                )
            if points:
                client.upsert(collection_name=full_name, points=points)
            return len(points)
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
            results = client.search(
                collection_name=full_name,
                query_vector=query_vector,
                limit=top_k,
                score_threshold=score_threshold if score_threshold > 0 else None,
            )
            return [
                {
                    "id": r.payload.get("doc_id", str(r.id)),
                    "score": r.score,
                    "text": r.payload.get("text", ""),
                    "metadata": {k: v for k, v in r.payload.items() if k not in ("doc_id", "text")},
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
            from qdrant_client.models import PointIdsList

            full_name = self._full_collection_name(collection)
            client.delete(
                collection_name=full_name,
                points_selector=PointIdsList(points=[_stable_uuid(doc_id)]),
            )
            return True
        except Exception as e:
            logger.error("Qdrant delete failed: %s", e)
            return False

    def ensure_collection(self, collection: str, dimension: int) -> bool:
        client = self._client()
        if client is None:
            return False
        try:
            from qdrant_client.models import Distance, VectorParams

            full_name = self._full_collection_name(collection)
            if not client.collection_exists(full_name):
                client.create_collection(
                    collection_name=full_name,
                    vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
                )
                self._configure_collection(full_name)
                return True
            else:
                # Validate dimension match on existing collection
                try:
                    info = client.get_collection(full_name)
                    existing_dim = info.config.params.vectors.size
                    if existing_dim and existing_dim != dimension:
                        logger.warning(
                            "Brain dimension mismatch for '%s': existing=%d, required=%d. Recreating.",
                            full_name,
                            existing_dim,
                            dimension,
                        )
                        client.delete_collection(full_name)
                        client.create_collection(
                            collection_name=full_name,
                            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
                        )
                        self._configure_collection(full_name)
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
            from qdrant_client.models import PayloadSchemaType

            for field_name in ("layer", "domain", "technologies"):
                try:
                    client.create_payload_index(
                        collection_name=full_name,
                        field_name=field_name,
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
                except Exception as exc:
                    logger.debug(
                        "Qdrant payload index creation skipped for field %s: %s", field_name, exc
                    )
        except ImportError:
            pass  # qdrant_client models not available
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
            info = client.get_collection(full_name)
            return info.points_count or 0
        except Exception as e:
            logger.error("Qdrant count failed: %s", e)
            return 0

    def health_check(self) -> bool:
        """Verify Qdrant connection with a lightweight operation."""
        try:
            client = self._client()
            if client is None:
                return False
            client.get_collections()
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
