"""Ontology alignment for the Engineering Knowledge Brain.

Aligns taxonomy tags with external ontologies via SKOS mappings
(exactMatch, broadMatch, narrowMatch, relatedMatch). Uses embedding
similarity to propose alignments, which can be confirmed manually or
via LLM review.

Reference: SKOS (W3C 2009), Ontology Matching (Euzenat & Shvaiko 2013).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from engineering_brain.core.taxonomy import Tag, TagRegistry

logger = logging.getLogger(__name__)


# Known ontology prefixes for URI expansion
ONTOLOGY_PREFIXES: dict[str, str] = {
    "wd": "https://www.wikidata.org/wiki/",
    "dbr": "https://dbpedia.org/resource/",
    "schema": "https://schema.org/",
    "owl": "http://www.w3.org/2002/07/owl#",
}

# Valid SKOS match types
MATCH_TYPES = {"exact_match", "broad_match", "narrow_match", "related_match"}


class OntologyAligner:
    """Align taxonomy tags with external ontologies via SKOS mappings.

    Supports:
    - Manual alignment via apply_alignment()
    - Batch import from SKOS YAML/JSON files
    - Export of all mappings
    - Alignment statistics
    """

    def __init__(
        self,
        registry: TagRegistry,
        embedder: Any = None,
    ) -> None:
        self._registry = registry
        self._embedder = embedder

    def align_tag(
        self,
        tag_id: str,
        candidates: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Propose SKOS alignments for a tag.

        If candidates provided, score each against the tag's text.
        Returns {match_type: [uri, ...]} proposals.

        Each candidate: {"uri": "wd:Q28865", "label": "Python", "match_type": "exact_match"}
        """
        tag = self._registry.get(tag_id)
        if not tag:
            return {"error": f"Tag '{tag_id}' not found"}

        if candidates:
            return self._score_candidates(tag, candidates)

        # Without candidates, just return current mappings
        return self._current_mappings(tag)

    def align_all(self, batch_size: int = 10) -> dict[str, Any]:
        """Report alignment coverage for all tags."""
        all_tags = self._registry.all_tags()
        aligned = 0
        unaligned = 0

        for tag in all_tags:
            if tag.exact_match or tag.broad_match or tag.narrow_match or tag.related_match:
                aligned += 1
            else:
                unaligned += 1

        return {
            "total_tags": len(all_tags),
            "aligned": aligned,
            "unaligned": unaligned,
            "coverage": aligned / max(len(all_tags), 1),
        }

    def apply_alignment(
        self,
        tag_id: str,
        match_type: str,
        uri: str,
    ) -> bool:
        """Apply a confirmed alignment to a tag.

        Args:
            tag_id: The tag to align.
            match_type: One of exact_match, broad_match, narrow_match, related_match.
            uri: The external ontology URI (e.g., "wd:Q28865").

        Returns True if applied successfully.
        """
        if match_type not in MATCH_TYPES:
            logger.warning("Invalid match type: %s (valid: %s)", match_type, MATCH_TYPES)
            return False

        tag = self._registry.get(tag_id)
        if not tag:
            logger.warning("Tag not found: %s", tag_id)
            return False

        # Expand prefix if needed
        expanded = self._expand_uri(uri)

        # Add to the appropriate list (avoid duplicates)
        match_list = getattr(tag, match_type)
        if expanded not in match_list:
            match_list.append(expanded)
            logger.info("Applied %s alignment: %s → %s", match_type, tag_id, expanded)
            return True

        return False

    def remove_alignment(
        self,
        tag_id: str,
        match_type: str,
        uri: str,
    ) -> bool:
        """Remove an alignment from a tag."""
        if match_type not in MATCH_TYPES:
            return False

        tag = self._registry.get(tag_id)
        if not tag:
            return False

        expanded = self._expand_uri(uri)
        match_list = getattr(tag, match_type)
        if expanded in match_list:
            match_list.remove(expanded)
            return True
        # Also try unexpanded
        if uri in match_list:
            match_list.remove(uri)
            return True

        return False

    def import_skos_file(self, filepath: str) -> int:
        """Import SKOS alignments from a YAML or JSON file.

        Expected format:
        ```yaml
        alignments:
          - tag_id: python
            exact_match: ["wd:Q28865", "dbr:Python_(programming_language)"]
            broad_match: ["schema:ComputerLanguage"]
          - tag_id: flask
            exact_match: ["wd:Q28927463"]
        ```

        Returns count of alignments applied.
        """
        path = Path(filepath)
        if not path.exists():
            logger.warning("SKOS file not found: %s", filepath)
            return 0

        try:
            content = path.read_text(encoding="utf-8")
            if path.suffix in (".yaml", ".yml"):
                import yaml
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)
        except Exception as e:
            logger.error("Failed to parse SKOS file %s: %s", filepath, e)
            return 0

        count = 0
        alignments = data.get("alignments", [])
        for entry in alignments:
            tag_id = entry.get("tag_id", "")
            if not tag_id:
                continue
            for match_type in MATCH_TYPES:
                uris = entry.get(match_type, [])
                if isinstance(uris, str):
                    uris = [uris]
                for uri in uris:
                    if self.apply_alignment(tag_id, match_type, uri):
                        count += 1

        logger.info("Imported %d alignments from %s", count, filepath)
        return count

    def export_skos(self) -> dict[str, Any]:
        """Export all SKOS mappings as a dictionary.

        Returns:
            {"alignments": [{tag_id, exact_match, broad_match, ...}, ...]}
        """
        alignments: list[dict[str, Any]] = []

        for tag in self._registry.all_tags():
            entry: dict[str, Any] = {"tag_id": tag.id}
            has_mapping = False
            for match_type in MATCH_TYPES:
                uris = getattr(tag, match_type)
                if uris:
                    entry[match_type] = list(uris)
                    has_mapping = True
            if has_mapping:
                alignments.append(entry)

        return {"alignments": alignments}

    def stats(self) -> dict[str, Any]:
        """Alignment coverage statistics."""
        coverage = self.align_all()
        # Count by match type
        type_counts: dict[str, int] = {mt: 0 for mt in MATCH_TYPES}
        for tag in self._registry.all_tags():
            for mt in MATCH_TYPES:
                type_counts[mt] += len(getattr(tag, mt))

        coverage["match_type_counts"] = type_counts
        coverage["total_mappings"] = sum(type_counts.values())
        return coverage

    def _score_candidates(
        self,
        tag: Tag,
        candidates: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Score candidate alignments using embedding similarity."""
        if not self._embedder:
            # Without embedder, just return candidates as-is
            return {"candidates": candidates, "method": "no_scoring"}

        try:
            tag_text = tag.display_name or tag.id
            tag_vec = self._embedder.embed_text(tag_text)
            if not tag_vec:
                return {"candidates": candidates, "method": "embed_failed"}
        except Exception:
            return {"candidates": candidates, "method": "embed_failed"}

        scored: list[dict[str, Any]] = []
        for cand in candidates:
            label = cand.get("label", "")
            if not label:
                continue
            try:
                cand_vec = self._embedder.embed_text(label)
                if cand_vec:
                    sim = self._cosine(tag_vec, cand_vec)
                    scored.append({**cand, "similarity": round(sim, 4)})
            except Exception:
                scored.append({**cand, "similarity": 0.0})

        scored.sort(key=lambda c: c.get("similarity", 0), reverse=True)
        return {"candidates": scored, "method": "embedding_similarity"}

    @staticmethod
    def _current_mappings(tag: Tag) -> dict[str, Any]:
        """Get current SKOS mappings for a tag."""
        return {
            "tag_id": tag.id,
            "exact_match": list(tag.exact_match),
            "broad_match": list(tag.broad_match),
            "narrow_match": list(tag.narrow_match),
            "related_match": list(tag.related_match),
        }

    @staticmethod
    def _expand_uri(uri: str) -> str:
        """Expand a prefixed URI (e.g., 'wd:Q28865' → full URL)."""
        for prefix, base_url in ONTOLOGY_PREFIXES.items():
            if uri.startswith(f"{prefix}:"):
                return base_url + uri[len(prefix) + 1:]
        return uri

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)
