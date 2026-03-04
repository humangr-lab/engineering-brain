"""Embedding manager for the Engineering Knowledge Brain.

Computes and stores vector embeddings for all brain nodes, enabling:
- Hybrid retrieval (graph + vector search)
- Embedding-based clustering (cosine > Jaccard)
- Semantic query expansion

Graceful degradation: every method returns [] on failure, never blocks.
Uses FastEmbed or VoyageAI as embedding provider.
"""

from __future__ import annotations

import logging
import math
import threading
from typing import Any

from engineering_brain.adapters.base import VectorAdapter
from engineering_brain.core.config import BrainConfig

logger = logging.getLogger(__name__)

# Max seconds to wait for a single embed call before giving up
_EMBED_TIMEOUT = int(__import__("os").getenv("BRAIN_EMBED_TIMEOUT", "30"))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Pure Python, no deps."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class BrainEmbedder:
    """Computes and manages embeddings for brain nodes."""

    def __init__(self, vector: VectorAdapter, config: BrainConfig | None = None) -> None:
        self._vector = vector
        self._config = config or BrainConfig()
        self._provider: Any = None  # Lazy init
        self._provider_attempted = False

    def _get_provider(self) -> Any:
        """Lazy-load embedding provider (graceful degradation)."""
        if self._provider is not None:
            return self._provider
        if self._provider_attempted:
            return None
        self._provider_attempted = True
        try:
            from fastembed import TextEmbedding

            self._provider = TextEmbedding()
            return self._provider
        except ImportError:
            pass
        try:
            import voyageai

            self._provider = voyageai.Client()
            return self._provider
        except ImportError:
            logger.info(
                "No embedding provider available — embedding disabled. "
                "Install fastembed or voyageai for embedding support."
            )
            return None
        except Exception as e:
            logger.debug("Embedding provider unavailable: %s", e)
            return None

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string. Returns [] on failure."""
        provider = self._get_provider()
        if not provider:
            return []
        try:
            result = provider.embed(text)
            # fastembed.TextEmbedding.embed() returns a generator of ndarray
            if hasattr(result, "__next__"):
                result = next(result)
            return [float(x) for x in result] if result is not None else []
        except Exception as e:
            logger.debug("Embedding failed: %s", e)
            return []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Returns [] on failure."""
        provider = self._get_provider()
        if not provider:
            return []
        try:
            if hasattr(provider, "embed_batch"):
                result = provider.embed_batch(texts)
            else:
                result = provider.embed(texts)
            # fastembed returns a generator of ndarray — materialise
            if hasattr(result, "__next__"):
                return [[float(x) for x in vec] for vec in result]
            return [[float(x) for x in vec] for vec in result]
        except Exception as e:
            logger.debug("Batch embedding failed: %s", e)
            return []

    def node_to_text(self, node: dict[str, Any]) -> str:
        """Build embedding text from node fields.

        Field priority per node type:
        - Rule: text + why + how_to_do_right
        - Pattern: name + intent + when_to_use
        - Principle: name + why + how_to_apply
        - Axiom: statement
        - Finding: description + resolution
        """
        parts: list[str] = []

        # Primary text (pick first non-empty)
        for f in ("text", "name", "statement", "description"):
            val = node.get(f, "")
            if val:
                parts.append(str(val))
                break

        # Secondary context
        for f in ("why", "intent"):
            val = node.get(f, "")
            if val:
                parts.append(str(val))

        # Actionable guidance
        for f in ("how_to_do_right", "how_to_apply", "resolution"):
            val = node.get(f, "")
            if val:
                parts.append(str(val))

        return ". ".join(parts)[:500]

    def embed_and_store(self, node: dict[str, Any], collection: str) -> bool:
        """Embed a node and store in vector adapter."""
        if self._provider_attempted and self._provider is None:
            return False  # Provider already failed — don't retry
        text = self.node_to_text(node)
        if not text:
            return False
        vec = self.embed_text(text)
        if not vec:
            return False
        node_id = node.get("id", "")
        if not node_id:
            return False
        metadata = {
            "layer": node.get("_layer", ""),
            "technologies": node.get("technologies", []),
            "domains": node.get("domains", []),
            "confidence": float(node.get("confidence", 0.5)),
        }
        return self._vector.upsert(collection, node_id, text, vec, metadata)

    def embed_all_nodes(
        self,
        graph: Any,
        batch_size: int | None = None,
    ) -> dict[str, int]:
        """Batch-embed all nodes in graph. Returns {embedded, skipped, failed}.

        Groups nodes by layer for correct vector collection routing.
        Fast-exits if no embedding provider is available (prevents memory
        blowup from loading sentence-transformers model in test environments).
        """
        # Fast exit: check provider BEFORE loading all nodes
        provider = self._get_provider()
        if not provider:
            logger.debug("No embedding provider available — skipping bulk embed")
            return {"embedded": 0, "skipped": 0, "failed": 0}

        from engineering_brain.core.schema import VECTOR_COLLECTIONS

        bs = batch_size or self._config.embedding_batch_size
        stats = {"embedded": 0, "skipped": 0, "failed": 0}

        # ID prefix → layer key mapping
        prefix_to_layer = {
            "AX-": "L1",  # Axioms stored with principles (small count)
            "P-": "L1",
            "PAT-": "L2",
            "CPAT-": "L2",
            "CR-": "L3",
            "F-": "L4",
        }

        all_nodes = graph.get_all_nodes()
        # Group by collection
        by_collection: dict[str, list[dict[str, Any]]] = {}

        for node in all_nodes:
            nid = node.get("id", "")
            if not nid or node.get("deprecated"):
                stats["skipped"] += 1
                continue

            # Determine layer
            layer_key = None
            for prefix, lk in prefix_to_layer.items():
                if nid.startswith(prefix):
                    layer_key = lk
                    break
            if not layer_key:
                stats["skipped"] += 1
                continue

            collection = VECTOR_COLLECTIONS.get(layer_key)
            if not collection:
                stats["skipped"] += 1
                continue

            by_collection.setdefault(collection, []).append(node)

        # Batch embed per collection
        for collection, nodes in by_collection.items():
            self._vector.ensure_collection(
                collection,
                self._config.embedding_dimension,
            )

            for i in range(0, len(nodes), bs):
                batch = nodes[i : i + bs]
                texts = [self.node_to_text(n) for n in batch]
                vectors = self.embed_batch(texts)

                if not vectors or len(vectors) != len(batch):
                    # Fallback to one-by-one
                    for node in batch:
                        if self.embed_and_store(node, collection):
                            stats["embedded"] += 1
                        else:
                            stats["failed"] += 1
                    continue

                for node, text, vec in zip(batch, texts, vectors, strict=False):
                    nid = node.get("id", "")
                    if not vec or not nid:
                        stats["failed"] += 1
                        continue
                    metadata = {
                        "layer": node.get("_layer", ""),
                        "technologies": node.get("technologies", []),
                        "domains": node.get("domains", []),
                        "confidence": float(node.get("confidence", 0.5)),
                    }
                    if self._vector.upsert(collection, nid, text, vec, metadata):
                        stats["embedded"] += 1
                    else:
                        stats["failed"] += 1

        return stats


# ── Singleton access ──────────────────────────────────────────────

_embedder: BrainEmbedder | None = None
_embedder_lock = threading.Lock()


def get_embedder(
    vector: VectorAdapter | None = None,
    config: BrainConfig | None = None,
) -> BrainEmbedder | None:
    """Get/create singleton embedder. Thread-safe. Returns None if embedding disabled."""
    global _embedder
    cfg = config or BrainConfig()
    if not cfg.embedding_enabled:
        return None
    if _embedder is not None:
        return _embedder
    with _embedder_lock:
        if _embedder is not None:
            return _embedder
        if vector is None:
            from engineering_brain.adapters.memory import MemoryVectorAdapter

            vector = MemoryVectorAdapter()
        _embedder = BrainEmbedder(vector, cfg)
    return _embedder


def reset_embedder() -> None:
    """Reset singleton and release native resources (for testing).

    Explicitly deletes the fastembed/onnxruntime provider to prevent
    'FATAL: exception not rethrown' crashes during Python shutdown on 3.12.
    """
    global _embedder
    if _embedder is not None:
        _embedder._provider = None
        _embedder._provider_attempted = False
    _embedder = None
