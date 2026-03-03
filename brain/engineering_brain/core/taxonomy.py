"""Faceted Taxonomy DAG — SOTA knowledge classification.

Replaces static dotted-path tree (TAXONOMY.yaml) with a live, in-memory
Directed Acyclic Graph where:
- Each tag is a first-class entity with facet, multiple parents, children
- Tags support polyhierarchy (flask → python_web AND wsgi_framework)
- Ancestor/descendant sets are precomputed for O(1) hierarchy checks
- Old dotted-path format auto-decomposes via decompose_dotted_path()

Architecture layers (this module = Layer 1 + Layer 2):
  Layer 1: Faceted DAG (Tag Registry) — in-memory, µs lookups
  Layer 2: Ancestor Index (precomputed closure) — O(1) hierarchy checks

Performance: match() costs O(Q*N) set lookups where Q≈3, N≈5 → ~15 lookups.
For 100K nodes: <10ms total. Registry RAM: ~1MB/10K tags.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =====================================================================
# Tag — first-class entity in the taxonomy DAG
# =====================================================================

@dataclass
class Tag:
    """A single concept in the taxonomy DAG."""

    id: str
    facet: str
    display_name: str = ""
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    weight: float = 1.0
    # SKOS alignment fields (external ontology mappings)
    exact_match: list[str] = field(default_factory=list)    # skos:exactMatch URIs
    broad_match: list[str] = field(default_factory=list)    # skos:broadMatch URIs
    narrow_match: list[str] = field(default_factory=list)   # skos:narrowMatch URIs
    related_match: list[str] = field(default_factory=list)  # skos:relatedMatch URIs

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.id


# =====================================================================
# Facet definitions
# =====================================================================

# Known facets with their prefixes in dotted paths.
# Used by decompose_dotted_path() to classify path segments.
FACET_PREFIXES: dict[str, str] = {
    "language": "lang",
    "framework": "framework",
    "library": "library",
    "database": "platform",
    "messaging": "platform",
    "cloud": "platform",
    "infrastructure": "platform",
    "security_tool": "platform",
    "networking": "platform",
    "observability": "platform",
    "ci_cd": "platform",
}

DOMAIN_ROOTS: set[str] = {
    "reliability", "performance", "security", "observability", "operations",
    "architecture", "deployment", "code_quality", "testing", "databases",
    "messaging", "mathematics", "culture", "data_engineering", "compliance",
    "blockchain", "mobile", "ai_ml", "api", "ui", "devops",
    # Knowledge enrichment v2 — cognitive + product domains
    "reasoning", "sacada", "integration", "fintech", "realtime",
    "antipattern", "fact_checking", "prediction_markets", "gamification",
    # Knowledge enrichment v3 — agent orchestration + data engineering
    "agent_orchestration",
}

# Weights for facet-based scoring
FACET_WEIGHTS: dict[str, float] = {
    "lang": 0.25,
    "framework": 0.20,
    "library": 0.10,
    "domain": 0.25,
    "concern": 0.10,
    "pattern": 0.05,
    "platform": 0.05,
}


# =====================================================================
# TagRegistry — live in-memory DAG with precomputed closure
# =====================================================================

class TagRegistry:
    """Live in-memory faceted DAG of all tags.

    Auto-built from seed data at brain.seed() time. Provides O(1) ancestor/
    descendant lookups via precomputed transitive closure.
    """

    def __init__(self) -> None:
        self._tags: dict[str, Tag] = {}
        self._facet_index: dict[str, set[str]] = {}
        self._alias_index: dict[str, str] = {}
        self._ancestors: dict[str, frozenset[str]] = {}
        self._descendants: dict[str, frozenset[str]] = {}
        self._closure_dirty: bool = True

    # -----------------------------------------------------------------
    # Registration
    # -----------------------------------------------------------------

    def register(self, tag: Tag) -> None:
        """Add a tag to the registry. Marks closure as dirty."""
        tag_id = tag.id.lower()
        tag.id = tag_id
        tag.parents = [p.lower() for p in tag.parents]

        existing = self._tags.get(tag_id)
        if existing:
            # Merge parents (polyhierarchy: accumulate all parents)
            merged_parents = list(dict.fromkeys(existing.parents + tag.parents))
            existing.parents = merged_parents
            if tag.aliases:
                existing.aliases = list(set(existing.aliases + tag.aliases))
            if tag.description and not existing.description:
                existing.description = tag.description
        else:
            self._tags[tag_id] = tag
            self._facet_index.setdefault(tag.facet, set()).add(tag_id)

        # Register aliases
        for alias in tag.aliases:
            self._alias_index[alias.lower()] = tag_id
        # Also register the display_name as alias
        if tag.display_name:
            self._alias_index[tag.display_name.lower()] = tag_id

        self._closure_dirty = True

    def register_batch(self, tags: list[Tag]) -> None:
        """Register multiple tags, then rebuild closure once."""
        for tag in tags:
            tag_id = tag.id.lower()
            tag.id = tag_id
            tag.parents = [p.lower() for p in tag.parents]

            existing = self._tags.get(tag_id)
            if existing:
                merged_parents = list(dict.fromkeys(existing.parents + tag.parents))
                existing.parents = merged_parents
                if tag.aliases:
                    existing.aliases = list(set(existing.aliases + tag.aliases))
            else:
                self._tags[tag_id] = tag
                self._facet_index.setdefault(tag.facet, set()).add(tag_id)

            for alias in tag.aliases:
                self._alias_index[alias.lower()] = tag_id
            if tag.display_name:
                self._alias_index[tag.display_name.lower()] = tag_id

        self._closure_dirty = True

    # -----------------------------------------------------------------
    # Lookup
    # -----------------------------------------------------------------

    def get(self, tag_id: str) -> Tag | None:
        """Get a tag by ID (case-insensitive)."""
        return self._tags.get(tag_id.lower())

    def resolve(self, text: str) -> Tag | None:
        """Resolve a string to a Tag via ID or alias lookup."""
        key = text.lower().strip()
        # Direct ID
        tag = self._tags.get(key)
        if tag:
            return tag
        # Alias
        canonical_id = self._alias_index.get(key)
        if canonical_id:
            return self._tags.get(canonical_id)
        # Underscore/hyphen variants
        for variant in (key.replace("-", "_"), key.replace("_", "-"), key.replace(" ", "_")):
            tag = self._tags.get(variant)
            if tag:
                return tag
            canonical_id = self._alias_index.get(variant)
            if canonical_id:
                return self._tags.get(canonical_id)
        return None

    def tags_by_facet(self, facet: str) -> list[Tag]:
        """Get all tags in a given facet."""
        ids = self._facet_index.get(facet, set())
        return [self._tags[tid] for tid in ids if tid in self._tags]

    def all_tags(self) -> list[Tag]:
        """Get all registered tags."""
        return list(self._tags.values())

    @property
    def size(self) -> int:
        return len(self._tags)

    # -----------------------------------------------------------------
    # Precomputed transitive closure (Layer 2)
    # -----------------------------------------------------------------

    def ensure_closure(self) -> None:
        """Rebuild ancestor/descendant sets if dirty."""
        if not self._closure_dirty:
            return
        self._precompute_closure()
        self._closure_dirty = False

    def _precompute_closure(self) -> None:
        """BFS from every tag to compute ancestor/descendant sets.

        Also links parent→child edges (children are computed from parents).
        """
        # Build children from parent edges
        for tag in self._tags.values():
            tag.children = []
        for tag in self._tags.values():
            for parent_id in tag.parents:
                parent = self._tags.get(parent_id)
                if parent and tag.id not in parent.children:
                    parent.children.append(tag.id)

        # Ancestors: BFS upward from each tag
        ancestors: dict[str, set[str]] = {}
        for tag_id in self._tags:
            anc: set[str] = set()
            queue = deque(self._tags[tag_id].parents)
            while queue:
                pid = queue.popleft()
                if pid not in anc and pid in self._tags:
                    anc.add(pid)
                    queue.extend(self._tags[pid].parents)
            ancestors[tag_id] = anc
        self._ancestors = {k: frozenset(v) for k, v in ancestors.items()}

        # Descendants: invert the ancestor relation
        desc: dict[str, set[str]] = {tid: set() for tid in self._tags}
        for tag_id, ancs in self._ancestors.items():
            for anc_id in ancs:
                if anc_id in desc:
                    desc[anc_id].add(tag_id)
        self._descendants = {k: frozenset(v) for k, v in desc.items()}

    def ancestors(self, tag_id: str) -> frozenset[str]:
        """All ancestors of a tag (precomputed, O(1) lookup)."""
        self.ensure_closure()
        return self._ancestors.get(tag_id.lower(), frozenset())

    def descendants(self, tag_id: str) -> frozenset[str]:
        """All descendants of a tag (precomputed, O(1) lookup)."""
        self.ensure_closure()
        return self._descendants.get(tag_id.lower(), frozenset())

    def is_ancestor_of(self, ancestor_id: str, descendant_id: str) -> bool:
        """Check if ancestor_id is an ancestor of descendant_id. O(1)."""
        self.ensure_closure()
        a = ancestor_id.lower()
        d = descendant_id.lower()
        return a in self._ancestors.get(d, frozenset())

    # -----------------------------------------------------------------
    # Matching — facet-aware, hierarchy-aware
    # -----------------------------------------------------------------

    def tag_matches(self, query_tag: str, node_tag: str) -> bool:
        """Check if a single query tag matches a single node tag.

        Match means: exact, or query is ancestor of node, or node is ancestor of query.
        """
        self.ensure_closure()
        qt = query_tag.lower()
        nt = node_tag.lower()

        if qt == nt:
            return True

        # Resolve aliases
        qt_resolved = self._alias_index.get(qt, qt)
        nt_resolved = self._alias_index.get(nt, nt)
        if qt_resolved == nt_resolved:
            return True

        # Hierarchy: qt is ancestor of nt (broad query matches specific node)
        qt_desc = self._descendants.get(qt_resolved, frozenset())
        if nt_resolved in qt_desc:
            return True

        # Hierarchy: nt is ancestor of qt (specific query matches broad node)
        nt_desc = self._descendants.get(nt_resolved, frozenset())
        if qt_resolved in nt_desc:
            return True

        return False

    def match(
        self,
        query_tags: dict[str, list[str]],
        node_tags: dict[str, list[str]],
    ) -> bool:
        """Facet-aware matching. Returns True if query matches node on ANY facet.

        Both dicts are {facet: [tag_ids]}. Uses precomputed ancestor index
        for O(1) hierarchy checks per pair.
        """
        self.ensure_closure()
        for facet, qtags in query_tags.items():
            ntags = node_tags.get(facet, [])
            if not ntags:
                continue
            for qt in qtags:
                for nt in ntags:
                    if self.tag_matches(qt, nt):
                        return True
        return False

    def match_flat(
        self,
        query_tags: list[str],
        node_tags: list[str],
    ) -> bool:
        """Flat (non-faceted) matching — any query tag matches any node tag.

        Used for backward compatibility with old code that doesn't use facets.
        Resolves each tag to its canonical form and checks hierarchy.
        """
        self.ensure_closure()
        for qt in query_tags:
            for nt in node_tags:
                if self.tag_matches(qt, nt):
                    return True
        return False

    def overlap_score(
        self,
        query_tags: dict[str, list[str]],
        node_tags: dict[str, list[str]],
    ) -> float:
        """Facet-weighted overlap score between query and node tags.

        Returns 0.0-1.0. Each matching facet contributes its weight.
        Within a facet, score = matched_query_tags / total_query_tags.
        """
        self.ensure_closure()
        total_weight = 0.0
        weighted_score = 0.0

        for facet, weight in FACET_WEIGHTS.items():
            qtags = query_tags.get(facet, [])
            ntags = node_tags.get(facet, [])
            if not qtags:
                continue
            total_weight += weight
            if not ntags:
                continue
            matched = 0
            for qt in qtags:
                for nt in ntags:
                    if self.tag_matches(qt, nt):
                        matched += 1
                        break
            weighted_score += weight * (matched / len(qtags))

        if total_weight == 0:
            return 0.0
        return weighted_score / total_weight

    def overlap_count(
        self,
        query_tags: list[str],
        node_tags: list[str],
    ) -> int:
        """Count how many query tags match any node tag (flat, non-faceted).

        Each query tag counted at most once. Used by scorer.py.
        """
        self.ensure_closure()
        count = 0
        for qt in query_tags:
            for nt in node_tags:
                if self.tag_matches(qt, nt):
                    count += 1
                    break
        return count

    # -----------------------------------------------------------------
    # Dotted path decomposition (backward compatibility)
    # -----------------------------------------------------------------

    def decompose_dotted_path(self, path: str) -> dict[str, list[str]]:
        """Convert a dotted path to faceted tags.

        'language.python.web.flask' → {lang: [python], framework: [flask]}
        'security.authentication.oauth' → {domain: [security], concern: [authentication, oauth]}

        Strategy:
        1. Check if full path is a known tag → use its facet
        2. Check the first segment for facet prefix (language → lang)
        3. Resolve each segment individually via the registry
        4. Fallback: treat first segment as domain if it's a known domain root
        """
        path_lower = path.lower().strip()

        # 1. Full path is a known tag?
        tag = self.resolve(path_lower)
        if tag:
            return {tag.facet: [tag.id]}

        parts = path_lower.split(".")
        if len(parts) == 1:
            # Single segment: try to resolve, or classify as domain
            tag = self.resolve(parts[0])
            if tag:
                return {tag.facet: [tag.id]}
            if parts[0] in DOMAIN_ROOTS:
                return {"domain": [parts[0]]}
            return {"unknown": [parts[0]]}

        result: dict[str, list[str]] = {}

        # 2. First segment → facet prefix?
        facet_prefix = FACET_PREFIXES.get(parts[0])
        if facet_prefix:
            # e.g., "language.python.web.flask" → facet = "lang"
            # Resolve each subsequent segment
            for segment in parts[1:]:
                resolved = self.resolve(segment)
                if resolved:
                    result.setdefault(resolved.facet, []).append(resolved.id)
                else:
                    # Not in registry yet — assign to the prefix facet
                    result.setdefault(facet_prefix, []).append(segment)
        elif parts[0] in DOMAIN_ROOTS:
            # Domain path: "security.authentication.oauth"
            result.setdefault("domain", []).append(parts[0])
            for segment in parts[1:]:
                resolved = self.resolve(segment)
                if resolved:
                    result.setdefault(resolved.facet, []).append(resolved.id)
                else:
                    result.setdefault("concern", []).append(segment)
        else:
            # Unknown prefix — resolve each segment individually
            for segment in parts:
                resolved = self.resolve(segment)
                if resolved:
                    result.setdefault(resolved.facet, []).append(resolved.id)
                else:
                    result.setdefault("unknown", []).append(segment)

        return result if result else {"unknown": [path_lower]}

    # -----------------------------------------------------------------
    # Node tag normalization (backward compat with old seed format)
    # -----------------------------------------------------------------

    def normalize_node_tags(self, node: dict[str, Any]) -> dict[str, list[str]]:
        """Convert a node's technologies/domains to faceted tags.

        Supports both old format (technologies/domains lists) and new format
        (tags dict). Returns {facet: [tag_ids]}.
        """
        # New format: tags dict already present
        if "tags" in node and isinstance(node["tags"], dict):
            return {
                facet: ([v] if isinstance(v, str) else v)
                for facet, v in node["tags"].items()
            }

        result: dict[str, list[str]] = {}

        # Convert technologies/languages → faceted tags
        for t in (node.get("technologies") or node.get("languages") or []):
            decomposed = self.decompose_dotted_path(str(t))
            for facet, ids in decomposed.items():
                result.setdefault(facet, []).extend(ids)

        # Convert domains → faceted tags
        for d in (node.get("domains") or []):
            decomposed = self.decompose_dotted_path(str(d))
            for facet, ids in decomposed.items():
                result.setdefault(facet, []).extend(ids)

        # Deduplicate per facet
        return {facet: list(dict.fromkeys(ids)) for facet, ids in result.items()}

    # -----------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return registry statistics."""
        self.ensure_closure()
        facet_counts = {f: len(ids) for f, ids in self._facet_index.items()}
        max_depth = 0
        for tag_id in self._tags:
            depth = len(self._ancestors.get(tag_id, frozenset()))
            if depth > max_depth:
                max_depth = depth
        return {
            "total_tags": len(self._tags),
            "facets": facet_counts,
            "aliases": len(self._alias_index),
            "max_ancestor_depth": max_depth,
        }


# =====================================================================
# Module-level singleton (populated by brain.seed())
# =====================================================================

_global_registry: TagRegistry | None = None


def get_registry() -> TagRegistry:
    """Get the global TagRegistry singleton. Creates empty if not initialized."""
    global _global_registry
    if _global_registry is None:
        _global_registry = TagRegistry()
    return _global_registry


def set_registry(registry: TagRegistry) -> None:
    """Set the global TagRegistry singleton (called from brain.seed())."""
    global _global_registry
    _global_registry = registry
