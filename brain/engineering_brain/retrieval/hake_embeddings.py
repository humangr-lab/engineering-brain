"""HAKE — Hierarchy-Aware Knowledge Embedding for taxonomy tags (Tier 3).

Encodes tags as polar coordinates that CODIFY the DAG hierarchy:
- **Modulus** = hierarchy level (root=1.0, leaf → small modulus)
- **Phase** = lateral position within level (siblings have similar phases)

Combined with semantic embedding for a hybrid representation that captures
both meaning AND structure.

Reference: Zhang et al., "Learning Hierarchy-Aware Knowledge Graph Embeddings
for Link Prediction" (AAAI 2020).

MacBook-friendly: pure math (sin/cos), no API calls needed for hierarchy encoding.
Feature-flagged: BRAIN_HAKE_ENABLED (default: False).
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

from engineering_brain.core.taxonomy import Tag, TagRegistry

logger = logging.getLogger(__name__)


class HAKEEncoder:
    """Hierarchy-Aware Knowledge Embedding (HAKE) for taxonomy tags.

    Encodes tags as polar coordinates:
    - modulus = hierarchy level (deeper = smaller modulus)
    - phase = position within level (siblings have similar phases)

    Combined with semantic embedding for hybrid representation.
    """

    def __init__(self, registry: TagRegistry, base_dim: int = 1024) -> None:
        self._registry = registry
        self._base_dim = base_dim
        self._max_depth = self._compute_max_depth()

    # -----------------------------------------------------------------
    # Encoding
    # -----------------------------------------------------------------

    def encode_tag(self, tag_id: str, semantic_vec: list[float]) -> list[float]:
        """Combine semantic embedding with hierarchy encoding.

        Output: [semantic_vec..., modulus, phase_sin, phase_cos, depth_norm]
        Total dim: base_dim + 4
        """
        tag = self._registry.get(tag_id)
        if not tag:
            # Unknown tag: append zeros
            return semantic_vec + [0.0, 0.0, 0.0, 0.0]

        depth = len(self._registry.ancestors(tag_id))
        modulus = self._compute_modulus(depth)
        phase = self._compute_phase(tag)
        depth_norm = depth / max(self._max_depth, 1)

        return semantic_vec + [modulus, math.sin(phase), math.cos(phase), depth_norm]

    def hierarchy_distance(self, vec_a: list[float], vec_b: list[float]) -> float:
        """Compute hierarchy-aware distance between two HAKE vectors.

        Considers both semantic similarity and hierarchical distance.
        Semantic part uses cosine similarity, hierarchy part uses polar distance.
        """
        if len(vec_a) < 4 or len(vec_b) < 4:
            return float("inf")

        # Semantic part: cosine similarity on base_dim dimensions
        sem_a = vec_a[:-4]
        sem_b = vec_b[:-4]
        semantic_sim = self._cosine_similarity(sem_a, sem_b)

        # Hierarchy part: modulus difference + phase distance
        mod_a, sin_a, cos_a, depth_a = vec_a[-4:]
        mod_b, sin_b, cos_b, depth_b = vec_b[-4:]

        modulus_dist = abs(mod_a - mod_b)
        phase_dist = math.sqrt((sin_a - sin_b) ** 2 + (cos_a - cos_b) ** 2)

        # Combined distance: lower = more similar
        # Semantic similarity is [0, 1], convert to distance
        semantic_dist = 1.0 - max(0.0, semantic_sim)

        return 0.5 * semantic_dist + 0.3 * modulus_dist + 0.2 * phase_dist

    def encode_all(
        self,
        embedder: Any,  # BrainEmbedder
        batch_size: int = 10,
    ) -> dict[str, int]:
        """Encode all tags with HAKE vectors. Small batches for MacBook.

        Returns {encoded, skipped, failed}.
        """
        if not embedder:
            return {"encoded": 0, "skipped": 0, "failed": 0}

        all_tags = self._registry.all_tags()
        if not all_tags:
            return {"encoded": 0, "skipped": 0, "failed": 0}

        encoded = 0
        skipped = 0
        failed = 0
        self._hake_vectors: dict[str, list[float]] = {}

        from engineering_brain.retrieval.tag_embeddings import _tag_to_text

        for i in range(0, len(all_tags), batch_size):
            batch = all_tags[i:i + batch_size]
            texts = [_tag_to_text(tag, self._registry) for tag in batch]

            try:
                vectors = embedder.embed_batch(texts)
            except Exception as e:
                logger.debug("HAKE batch embed failed: %s", e)
                failed += len(batch)
                continue

            for tag, vec in zip(batch, vectors):
                if not vec:
                    skipped += 1
                    continue
                try:
                    hake_vec = self.encode_tag(tag.id, vec)
                    self._hake_vectors[tag.id] = hake_vec
                    encoded += 1
                except Exception:
                    failed += 1

            # MacBook-friendly pause
            if i + batch_size < len(all_tags):
                time.sleep(0.05)

        logger.info(
            "HAKE encoding: %d encoded, %d skipped, %d failed",
            encoded, skipped, failed,
        )
        return {"encoded": encoded, "skipped": skipped, "failed": failed}

    def get_hake_vector(self, tag_id: str) -> list[float] | None:
        """Get the HAKE vector for a tag (after encode_all)."""
        return getattr(self, "_hake_vectors", {}).get(tag_id)

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _compute_max_depth(self) -> int:
        """Compute maximum depth in the DAG."""
        max_d = 0
        for tag in self._registry.all_tags():
            d = len(self._registry.ancestors(tag.id))
            if d > max_d:
                max_d = d
        return max_d

    def _compute_modulus(self, depth: int) -> float:
        """Map depth to modulus: root=1.0, deeper levels decay exponentially."""
        if self._max_depth == 0:
            return 1.0
        return math.exp(-depth / max(self._max_depth, 1))

    def _compute_phase(self, tag: Tag) -> float:
        """Compute phase angle for a tag based on its sibling position.

        Tags with the same parent get equally-spaced phases in [0, 2*pi).
        """
        if not tag.parents:
            # Root-level tags: hash-based phase
            h = hash(tag.id) % 1000
            return (h / 1000.0) * 2.0 * math.pi

        # Get siblings (other children of first parent)
        first_parent = tag.parents[0]
        parent_tag = self._registry.get(first_parent)
        if not parent_tag:
            return 0.0

        siblings = sorted(parent_tag.children)
        if not siblings:
            return 0.0

        try:
            idx = siblings.index(tag.id)
        except ValueError:
            idx = 0

        n = len(siblings)
        return (idx / n) * 2.0 * math.pi

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return dot / (norm_a * norm_b)
