"""Consolidated Brain singleton factory with thread safety and background embedding.

All callers that need a Brain instance MUST go through get_brain().
This ensures:
  1. Exactly ONE Brain per process (no duplicate ~10MB graphs)
  2. Thread-safe initialization (double-check locking)
  3. Background embedding launched once after seed completes
  4. FastEmbed ONNX model warmed up as side effect of background embed
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_brain: Any = None
_brain_lock = threading.Lock()
_embed_ready = threading.Event()
_embed_thread: threading.Thread | None = None


def get_brain(
    *,
    background_embed: bool = True,
    adapter: str | None = None,
) -> Any:
    """Get or create the process-wide Brain singleton.

    Thread-safe via double-check locking. On first call:
      1. Creates Brain(adapter=adapter)
      2. Calls brain.seed(skip_bulk_embed=True) for fast startup (~7s)
      3. If background_embed=True, spawns daemon thread for embed_all_nodes

    Args:
        background_embed: If True, launch background embedding after seed.
        adapter: Storage adapter override. None = config default (memory).

    Returns:
        Seeded Brain instance.
    """
    global _brain
    if _brain is not None:
        return _brain
    with _brain_lock:
        if _brain is not None:
            return _brain
        try:
            from engineering_brain.core.brain import Brain

            _brain = Brain(adapter=adapter)
            _brain.seed(skip_bulk_embed=True)
            logger.info(
                "[BrainFactory] Brain initialized (%d nodes)",
                _brain.stats().get("total", 0),
            )
            # Wire task_knowledge with the same singleton
            try:
                from engineering_brain.retrieval.task_knowledge import init_task_knowledge

                init_task_knowledge(_brain)
            except Exception:
                pass
            # Launch background embedding
            if background_embed and not os.getenv("BRAIN_SKIP_BACKGROUND_EMBED"):
                _start_background_embed()
        except Exception as exc:
            logger.error("[BrainFactory] Brain init failed: %s", exc)
            raise
    return _brain


def is_embed_ready() -> bool:
    """Check if background embedding has completed (non-blocking)."""
    return _embed_ready.is_set()


def wait_for_embed(timeout: float | None = None) -> bool:
    """Block until background embedding completes or timeout.

    Returns True if embed finished, False on timeout.
    """
    return _embed_ready.wait(timeout=timeout)


def _start_background_embed() -> None:
    """Spawn a daemon thread to embed all nodes + tags.

    Solves: vector index populated, ONNX model warmed up, tag embeddings built.
    """
    global _embed_thread
    if _embed_thread is not None:
        return

    def _embed_worker() -> None:
        try:
            brain = _brain
            if brain is None or brain._embedder is None:
                return
            embedder = brain._embedder
            graph = brain._graph

            # Phase 1: embed_all_nodes (also loads ONNX model on first call)
            stats = embedder.embed_all_nodes(graph)
            logger.info(
                "[BrainFactory] Background embed: %d embedded, %d skipped, %d failed",
                stats.get("embedded", 0),
                stats.get("skipped", 0),
                stats.get("failed", 0),
            )

            # Phase 2: Tag embeddings
            try:
                from engineering_brain.core.taxonomy import get_registry
                from engineering_brain.retrieval.tag_embeddings import (
                    TagEmbeddingIndex,
                    get_tag_index,
                    set_tag_index,
                )

                registry = get_registry()
                if registry and not get_tag_index():
                    tag_index = TagEmbeddingIndex(embedder, registry)
                    tag_stats = tag_index.index_all(batch_size=20)
                    set_tag_index(tag_index)
                    logger.info(
                        "[BrainFactory] Background tag embed: %d indexed",
                        tag_stats.get("indexed", 0),
                    )
            except Exception as e:
                logger.debug("[BrainFactory] Tag embed failed (non-blocking): %s", e)

            # Phase 3: Cross-layer inference (Gap 1)
            if brain._config.cross_layer_inference_enabled and brain._cross_layer_inferrer is None:
                try:
                    from engineering_brain.learning.cross_layer_inferrer import (
                        CrossLayerEdgeInferrer,
                    )

                    inferrer = CrossLayerEdgeInferrer(graph, embedder, brain._config)
                    brain._cross_layer_inferrer = inferrer
                    inferred = inferrer.infer_edges(batch_size=20)
                    count = 0
                    for edge in inferred:
                        if not graph.has_edge(edge.source_id, edge.target_id):
                            graph.add_edge(edge.source_id, edge.target_id, edge.edge_type.value)
                            count += 1
                    if count:
                        logger.info("[BrainFactory] Inferred %d cross-layer edges", count)
                except Exception as e:
                    logger.debug("[BrainFactory] Cross-layer inference failed: %s", e)

        except Exception as e:
            logger.warning("[BrainFactory] Background embed failed (non-blocking): %s", e)
        finally:
            _embed_ready.set()

    _embed_thread = threading.Thread(target=_embed_worker, daemon=True, name="brain-bg-embed")
    _embed_thread.start()
    logger.debug("[BrainFactory] Background embedding thread started")


def reset_brain() -> None:
    """Reset singleton (for testing only)."""
    global _brain, _embed_thread
    with _brain_lock:
        _brain = None
        _embed_ready.clear()
        _embed_thread = None
