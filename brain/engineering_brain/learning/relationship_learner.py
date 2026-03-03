"""Relationship Learner — discover missing DAG edges via co-occurrence (Tier 3).

Tracks how tags co-occur across knowledge nodes. Tags that frequently
appear together but aren't connected in the DAG are candidates for
new relationships.

Also updates Tag.weight based on observed importance.

MacBook-friendly: processes in batches with dict counters (no GPU needed).
Feature-flagged: BRAIN_RELATIONSHIP_LEARNING (default: False).
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any

from engineering_brain.core.taxonomy import Tag, TagRegistry

logger = logging.getLogger(__name__)


class RelationshipLearner:
    """Learn edge weights and discover missing relationships.

    Tracks co-occurrence of tags across knowledge nodes.
    Suggests new relationships based on frequency + semantic similarity.
    """

    def __init__(self, registry: TagRegistry) -> None:
        self._registry = registry
        self._cooccurrence: Counter[tuple[str, str]] = Counter()
        self._tag_frequency: Counter[str] = Counter()
        self._nodes_observed = 0

    # -----------------------------------------------------------------
    # Observation
    # -----------------------------------------------------------------

    def observe_node(self, node: dict[str, Any]) -> None:
        """Track tag co-occurrences in a knowledge node.

        Extracts tags from node's technologies and domains fields,
        then records pairwise co-occurrence counts.
        """
        tags = self._extract_tags_from_node(node)
        if len(tags) < 2:
            return

        self._nodes_observed += 1

        # Update tag frequencies
        for t in tags:
            self._tag_frequency[t] += 1

        # Update pairwise co-occurrence
        sorted_tags = sorted(tags)
        for i, a in enumerate(sorted_tags):
            for b in sorted_tags[i + 1:]:
                self._cooccurrence[(a, b)] += 1

    def observe_batch(
        self,
        nodes: list[dict[str, Any]],
        batch_size: int = 50,
    ) -> None:
        """Track co-occurrences from a batch of nodes. Incremental.

        Processes in batches with brief pauses to be MacBook-friendly.
        """
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i + batch_size]
            for node in batch:
                self.observe_node(node)

            # MacBook-friendly pause
            if i + batch_size < len(nodes):
                time.sleep(0.05)

        logger.info(
            "Observed %d nodes, %d unique co-occurrences tracked",
            self._nodes_observed, len(self._cooccurrence),
        )

    # -----------------------------------------------------------------
    # Suggestion
    # -----------------------------------------------------------------

    def suggest_relationships(
        self,
        min_cooccurrence: int = 3,
    ) -> list[dict[str, Any]]:
        """Suggest new relationships based on co-occurrence patterns.

        Returns [{child, parent, cooccurrence, confidence}, ...]
        Only suggests pairs that aren't already connected in the DAG.
        """
        suggestions: list[dict[str, Any]] = []

        for (tag_a, tag_b), count in self._cooccurrence.most_common():
            if count < min_cooccurrence:
                break

            # Skip if already connected (ancestor/descendant)
            ancestors_a = self._registry.ancestors(tag_a)
            ancestors_b = self._registry.ancestors(tag_b)

            if tag_b in ancestors_a or tag_a in ancestors_b:
                continue
            if tag_a in self._registry.descendants(tag_b):
                continue

            # Compute confidence: co-occurrence / min(freq_a, freq_b)
            freq_a = self._tag_frequency.get(tag_a, 1)
            freq_b = self._tag_frequency.get(tag_b, 1)
            confidence = count / min(freq_a, freq_b)

            # Determine direction: deeper tag is child
            depth_a = len(ancestors_a)
            depth_b = len(ancestors_b)

            if depth_a >= depth_b:
                child, parent = tag_a, tag_b
            else:
                child, parent = tag_b, tag_a

            suggestions.append({
                "child": child,
                "parent": parent,
                "cooccurrence": count,
                "confidence": min(confidence, 1.0),
            })

        logger.info("Relationship suggestions: %d candidates", len(suggestions))
        return suggestions

    # -----------------------------------------------------------------
    # Weight update
    # -----------------------------------------------------------------

    def update_weights(self) -> int:
        """Update Tag.weight based on learned co-occurrence.

        Tags that co-occur frequently with many others get higher weight.
        Uses normalized frequency as weight signal.
        Returns number of tags updated.
        """
        if not self._tag_frequency:
            return 0

        max_freq = max(self._tag_frequency.values())
        if max_freq == 0:
            return 0

        updated = 0
        for tag_id, freq in self._tag_frequency.items():
            tag = self._registry.get(tag_id)
            if not tag:
                continue

            # Normalize frequency to [0.3, 1.0] range
            normalized = 0.3 + 0.7 * (freq / max_freq)
            # Blend with existing weight (80% existing, 20% learned)
            new_weight = 0.8 * tag.weight + 0.2 * normalized
            tag.weight = round(new_weight, 4)
            updated += 1

        logger.info("Updated weights for %d tags", updated)
        return updated

    # -----------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------

    @property
    def stats(self) -> dict[str, int]:
        """Return observation statistics."""
        return {
            "nodes_observed": self._nodes_observed,
            "unique_cooccurrences": len(self._cooccurrence),
            "unique_tags_seen": len(self._tag_frequency),
        }

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _extract_tags_from_node(self, node: dict[str, Any]) -> list[str]:
        """Extract tag IDs from a node's technologies and domains."""
        tags: list[str] = []

        # Handle both old format (list of strings) and new format (dict)
        techs = node.get("technologies", [])
        domains = node.get("domains", [])

        if isinstance(techs, dict):
            for facet_tags in techs.values():
                if isinstance(facet_tags, list):
                    tags.extend(t.lower() for t in facet_tags)
                elif isinstance(facet_tags, str):
                    tags.append(facet_tags.lower())
        elif isinstance(techs, list):
            for t in techs:
                # Dotted path: take last segment
                segments = str(t).lower().split(".")
                tags.extend(segments)

        if isinstance(domains, dict):
            for facet_tags in domains.values():
                if isinstance(facet_tags, list):
                    tags.extend(d.lower() for d in facet_tags)
                elif isinstance(facet_tags, str):
                    tags.append(facet_tags.lower())
        elif isinstance(domains, list):
            for d in domains:
                segments = str(d).lower().split(".")
                tags.extend(segments)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for t in tags:
            if t and t not in seen:
                seen.add(t)
                unique.append(t)

        return unique
