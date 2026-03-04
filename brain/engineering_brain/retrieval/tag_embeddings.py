"""Tag Embedding Index — semantic matching for taxonomy tags (Layer 3).

Embeds every tag in the TagRegistry into Qdrant, enabling:
- Fuzzy matching: "web security" → finds cors, xss, csrf tags
- Semantic fallback: when exact+ancestor match fails
- Similar tag discovery: for auto-expansion (Tier 2)

MacBook-friendly: processes in small batches (default 20) with no CPU spikes.
Graceful degradation: returns empty results if embedder unavailable.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from engineering_brain.core.taxonomy import Tag, TagRegistry

logger = logging.getLogger(__name__)

COLLECTION = "brain_tags"


class TagEmbeddingIndex:
    """Tag embeddings in Qdrant for semantic matching."""

    def __init__(
        self,
        embedder: Any,  # BrainEmbedder (avoid circular import)
        registry: TagRegistry,
    ) -> None:
        self._embedder = embedder
        self._registry = registry
        self._indexed = False

    # -----------------------------------------------------------------
    # Indexing
    # -----------------------------------------------------------------

    def index_all(self, batch_size: int = 20) -> dict[str, int]:
        """Embed all tags and store in Qdrant.

        Processes in small batches to avoid CPU/RAM spikes.
        Returns {indexed, skipped, failed}.
        """
        if not self._embedder:
            return {"indexed": 0, "skipped": 0, "failed": 0}

        all_tags = self._registry.all_tags()
        if not all_tags:
            return {"indexed": 0, "skipped": 0, "failed": 0}

        # Ensure collection exists
        try:
            vector = self._embedder._vector
            if vector:
                dim = self._embedder._config.embedding_dimension
                vector.ensure_collection(COLLECTION, dim)
        except Exception as e:
            logger.debug("Could not ensure tag collection: %s", e)
            return {"indexed": 0, "skipped": 0, "failed": 0}

        indexed = 0
        skipped = 0
        failed = 0

        # Process in batches
        for i in range(0, len(all_tags), batch_size):
            batch = all_tags[i : i + batch_size]
            texts = [_tag_to_text(tag, self._registry) for tag in batch]
            try:
                vectors = self._embedder.embed_batch(texts)
            except Exception as e:
                logger.debug("Batch embed failed: %s", e)
                failed += len(batch)
                continue

            for tag, text, vec in zip(batch, texts, vectors, strict=False):
                if not vec:
                    skipped += 1
                    continue
                try:
                    metadata = {
                        "facet": tag.facet,
                        "parents": tag.parents[:5],
                        "depth": len(self._registry.ancestors(tag.id)),
                        "weight": tag.weight,
                    }
                    vector.upsert(COLLECTION, tag.id, text, vec, metadata)
                    indexed += 1
                except Exception as exc:
                    logger.debug("Failed to index tag %s: %s", tag.id, exc)
                    failed += 1

            # Brief pause between batches to be MacBook-friendly
            if i + batch_size < len(all_tags):
                time.sleep(0.05)

        self._indexed = indexed > 0
        logger.info(
            "Tag embedding index: %d indexed, %d skipped, %d failed",
            indexed,
            skipped,
            failed,
        )
        return {"indexed": indexed, "skipped": skipped, "failed": failed}

    # -----------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------

    def semantic_search(
        self,
        query: str,
        facet: str | None = None,
        top_k: int = 5,
    ) -> list[Tag]:
        """Find tags semantically similar to query text.

        Args:
            query: Natural language query
            facet: Optional facet filter (e.g., "lang", "framework")
            top_k: Number of results

        Returns:
            List of matching Tag objects, ordered by similarity.
        """
        if not self._embedder or not self._indexed:
            return []

        query_vec = self._embedder.embed_text(query)
        if not query_vec:
            return []

        try:
            filters = {"facet": facet} if facet else None
            results = self._embedder._vector.search(
                COLLECTION,
                query_vec,
                top_k=top_k,
                filters=filters,
                score_threshold=0.3,
            )
        except Exception as e:
            logger.debug("Tag semantic search failed: %s", e)
            return []

        tags: list[Tag] = []
        for r in results:
            tag = self._registry.get(r["id"])
            if tag:
                tags.append(tag)
        return tags

    def find_similar_tags(
        self,
        tag_id: str,
        top_k: int = 5,
    ) -> list[tuple[str, float]]:
        """Find tags most similar to a given tag.

        Returns [(tag_id, similarity_score), ...] excluding the query tag itself.
        Used by Tier 2 auto-expansion to suggest polyhierarchy links.
        """
        if not self._embedder or not self._indexed:
            return []

        tag = self._registry.get(tag_id)
        if not tag:
            return []

        text = _tag_to_text(tag, self._registry)
        vec = self._embedder.embed_text(text)
        if not vec:
            return []

        try:
            results = self._embedder._vector.search(
                COLLECTION,
                vec,
                top_k=top_k + 1,
                score_threshold=0.3,
            )
        except Exception as exc:
            logger.debug("Tag embedding search failed: %s", exc)
            return []

        return [(r["id"], r["score"]) for r in results if r["id"] != tag_id][:top_k]

    @property
    def is_indexed(self) -> bool:
        return self._indexed


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------


def _tag_to_text(tag: Tag, registry: TagRegistry) -> str:
    """Build rich text representation of a tag for embedding.

    Includes facet, display name, parent names, and description.
    """
    parts = [f"{tag.facet}: {tag.display_name}"]

    # Include parent names for hierarchy context
    parent_names = []
    for pid in tag.parents[:3]:
        parent = registry.get(pid)
        if parent:
            parent_names.append(parent.display_name)
    if parent_names:
        parts.append(f"Parents: {', '.join(parent_names)}")

    if tag.description:
        parts.append(tag.description)

    if tag.aliases:
        parts.append(f"Also known as: {', '.join(tag.aliases[:3])}")

    return ". ".join(parts)


# -----------------------------------------------------------------
# Module-level singleton
# -----------------------------------------------------------------

_global_index: TagEmbeddingIndex | None = None


def get_tag_index() -> TagEmbeddingIndex | None:
    """Get the global TagEmbeddingIndex singleton."""
    return _global_index


def set_tag_index(index: TagEmbeddingIndex | None) -> None:
    """Set the global TagEmbeddingIndex singleton."""
    global _global_index
    _global_index = index
