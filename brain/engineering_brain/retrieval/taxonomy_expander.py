"""Taxonomy Auto-Expansion — TaxoExpan-style positioning of unknown tags (Tier 2).

When a new seed brings tags unknown to the registry, this module:
1. Tries alias resolution first (cheapest)
2. Embeds the unknown tag and finds nearest neighbors in Qdrant
3. Infers parents from neighbors via majority voting
4. Creates a provisional Tag with inferred parents
5. Registers it in the DAG

Also supports polyhierarchy link suggestion by scanning all tags
for high-similarity pairs that aren't yet connected.

MacBook-friendly: processes in small batches with pauses between.
Feature-flagged: BRAIN_AUTO_EXPAND_ENABLED (default: False).
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any

from engineering_brain.core.taxonomy import Tag, TagRegistry

logger = logging.getLogger(__name__)


class TaxonomyExpander:
    """Auto-positions unknown tags in the DAG via embedding similarity."""

    def __init__(
        self,
        registry: TagRegistry,
        tag_index: Any,  # TagEmbeddingIndex (avoid circular import)
    ) -> None:
        self._registry = registry
        self._index = tag_index

    # -----------------------------------------------------------------
    # Expand unknown tags
    # -----------------------------------------------------------------

    def expand_unknown(
        self,
        tag_text: str,
        facet_hint: str = "",
        context: str = "",
    ) -> Tag | None:
        """Position an unknown tag in the DAG automatically.

        Steps:
        1. Try alias resolution → existing tag
        2. Embed tag_text → find 5 nearest neighbors
        3. Vote on parents from neighbors
        4. Create Tag with inferred parents, marked provisional
        5. Register in registry

        Args:
            tag_text: The unknown tag text (e.g., "svelte", "htmx")
            facet_hint: Optional facet hint (e.g., "framework")
            context: Optional context text for better embedding

        Returns:
            The resolved or newly created Tag, or None if nothing could be done.
        """
        tag_id = tag_text.lower().strip().replace(" ", "_").replace("-", "_")
        if not tag_id:
            return None

        # Step 1: Try alias resolution first (cheapest)
        existing = self._registry.resolve(tag_text)
        if existing:
            return existing

        # Step 2: Semantic search for nearest neighbors
        if not self._index or not self._index.is_indexed:
            # No embedding index available — create orphan tag
            return self._create_orphan(tag_id, tag_text, facet_hint)

        query = f"{context} {tag_text}" if context else tag_text
        neighbors = self._index.semantic_search(
            query,
            facet=facet_hint or None,
            top_k=5,
        )

        if not neighbors:
            # Semantic search returned nothing — try without facet filter
            neighbors = self._index.semantic_search(query, top_k=5)

        if not neighbors:
            return self._create_orphan(tag_id, tag_text, facet_hint)

        # Step 3: Vote on facet from neighbors
        facet = facet_hint or self._vote_facet(neighbors)

        # Step 4: Vote on parents from neighbors
        parents = self._vote_parents(neighbors)

        # Step 5: Create and register the tag
        tag = Tag(
            id=tag_id,
            facet=facet,
            display_name=tag_text.replace("_", " ").title(),
            parents=parents,
            description=f"Auto-expanded via semantic similarity to {', '.join(n.id for n in neighbors[:3])}",
            weight=0.5,  # Lower weight for provisional tags
        )
        self._registry.register(tag)
        self._registry.ensure_closure()

        logger.info(
            "Auto-expanded tag '%s' (facet=%s, parents=%s) from %d neighbors",
            tag_id,
            facet,
            parents,
            len(neighbors),
        )
        return tag

    # -----------------------------------------------------------------
    # Polyhierarchy link suggestion
    # -----------------------------------------------------------------

    def suggest_polyhierarchy_links(
        self,
        min_similarity: float = 0.75,
        batch_size: int = 10,
    ) -> list[tuple[str, str, float]]:
        """Scan all tags, suggest new parent links based on embedding similarity.

        Returns [(child_id, suggested_parent_id, similarity_score), ...]
        Processes in batches of `batch_size` to avoid CPU spikes.
        """
        if not self._index or not self._index.is_indexed:
            return []

        all_tags = self._registry.all_tags()
        suggestions: list[tuple[str, str, float]] = []

        for i in range(0, len(all_tags), batch_size):
            batch = all_tags[i : i + batch_size]

            for tag in batch:
                similar = self._index.find_similar_tags(tag.id, top_k=5)
                ancestors = self._registry.ancestors(tag.id)

                for sim_id, score in similar:
                    if score < min_similarity:
                        continue
                    # Skip if already an ancestor or descendant
                    if sim_id in ancestors:
                        continue
                    if sim_id in self._registry.descendants(tag.id):
                        continue
                    # Skip same-id
                    if sim_id == tag.id:
                        continue

                    sim_tag = self._registry.get(sim_id)
                    if not sim_tag:
                        continue

                    # Suggest deeper tag as child, shallower as parent
                    tag_depth = len(ancestors)
                    sim_depth = len(self._registry.ancestors(sim_id))

                    if sim_depth < tag_depth:
                        suggestions.append((tag.id, sim_id, score))
                    elif tag_depth < sim_depth:
                        suggestions.append((sim_id, tag.id, score))
                    # Equal depth — skip (ambiguous direction)

            # MacBook-friendly pause between batches
            if i + batch_size < len(all_tags):
                time.sleep(0.1)

        # Deduplicate
        seen: set[tuple[str, str]] = set()
        unique: list[tuple[str, str, float]] = []
        for child, parent, score in suggestions:
            key = (child, parent)
            if key not in seen:
                seen.add(key)
                unique.append((child, parent, score))

        logger.info("Polyhierarchy suggestion scan: %d unique suggestions", len(unique))
        return unique

    def apply_suggestions(
        self,
        suggestions: list[tuple[str, str, float]],
        min_confidence: float = 0.8,
    ) -> int:
        """Apply approved suggestions as new polyhierarchy links.

        Only applies suggestions with score >= min_confidence.
        Returns the number of links applied.
        """
        applied = 0

        for child_id, parent_id, score in suggestions:
            if score < min_confidence:
                continue

            child_tag = self._registry.get(child_id)
            parent_tag = self._registry.get(parent_id)
            if not child_tag or not parent_tag:
                continue

            # Don't create cycles
            if child_id in self._registry.ancestors(parent_id):
                continue

            if parent_id not in child_tag.parents:
                child_tag.parents.append(parent_id)
                applied += 1

        if applied > 0:
            self._registry.ensure_closure()
            logger.info("Applied %d polyhierarchy links", applied)

        return applied

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _vote_facet(self, neighbors: list[Tag]) -> str:
        """Vote on facet from neighbor tags (majority wins)."""
        counter: Counter[str] = Counter()
        for tag in neighbors:
            counter[tag.facet] += 1
        if counter:
            return counter.most_common(1)[0][0]
        return "library"  # Safe default

    def _vote_parents(self, neighbors: list[Tag]) -> list[str]:
        """Vote on parents from neighbor tags.

        Collects all parents from neighbors, returns top 2 by frequency.
        """
        counter: Counter[str] = Counter()
        for tag in neighbors:
            for pid in tag.parents:
                counter[pid] += 1

        if not counter:
            return []

        # Top 2 parents by frequency (at least 2 votes for first, 1 for second)
        top = counter.most_common(3)
        parents = []
        for pid, count in top:
            if not parents and count >= 1 or count >= 2:
                parents.append(pid)
            if len(parents) >= 2:
                break

        return parents

    def _create_orphan(self, tag_id: str, tag_text: str, facet_hint: str) -> Tag:
        """Create an orphan tag (no parents) when embedding is unavailable."""
        tag = Tag(
            id=tag_id,
            facet=facet_hint or "library",
            display_name=tag_text.replace("_", " ").title(),
            description="Auto-discovered (no embedding available for parent inference)",
            weight=0.3,  # Even lower weight for orphans
        )
        self._registry.register(tag)
        logger.debug("Created orphan tag '%s'", tag_id)
        return tag


# -----------------------------------------------------------------
# Module-level singleton
# -----------------------------------------------------------------

_global_expander: TaxonomyExpander | None = None


def get_expander() -> TaxonomyExpander | None:
    """Get the global TaxonomyExpander singleton."""
    return _global_expander


def set_expander(expander: TaxonomyExpander | None) -> None:
    """Set the global TaxonomyExpander singleton."""
    global _global_expander
    _global_expander = expander
