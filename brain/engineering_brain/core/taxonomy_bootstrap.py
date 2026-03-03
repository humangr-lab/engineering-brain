"""Bootstrap the TagRegistry from TAXONOMY.yaml and seed node data.

Converts the static tree in TAXONOMY.yaml into a live Faceted DAG
with polyhierarchy. Also auto-discovers tags from seed node data
(technologies/domains fields).

Usage in brain.seed():
    from engineering_brain.core.taxonomy_bootstrap import bootstrap_registry
    registry = bootstrap_registry(seeds_dir, all_nodes)
    set_registry(registry)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from engineering_brain.core.taxonomy import (
    DOMAIN_ROOTS,
    FACET_PREFIXES,
    Tag,
    TagRegistry,
)

logger = logging.getLogger(__name__)

# SKOS metadata keys — these are tag properties, NOT child tags.
_SKOS_KEYS = {"exact_match", "broad_match", "narrow_match", "related_match"}


# =====================================================================
# TAXONOMY.yaml tree → DAG Tags
# =====================================================================

def _walk_tree(
    tree: dict[str, Any],
    facet: str,
    parent_id: str | None,
    tags: list[Tag],
    prefix_parts: list[str] | None = None,
) -> None:
    """Recursively walk a nested dict tree and create Tag objects.

    Each key becomes a Tag with its parent set to the enclosing key.
    SKOS metadata keys (exact_match, broad_match, narrow_match,
    related_match) are parsed as Tag properties, not child tags.
    """
    if prefix_parts is None:
        prefix_parts = []

    for key, subtree in tree.items():
        if key is None or key in _SKOS_KEYS:
            continue
        tag_id = key.lower()
        current_parts = prefix_parts + [tag_id]

        parents = [parent_id] if parent_id else []
        display = key.replace("_", " ").title()

        # Extract SKOS alignment fields from subtree if present
        skos_kwargs: dict[str, list[str]] = {}
        if isinstance(subtree, dict):
            for sk in _SKOS_KEYS:
                val = subtree.get(sk)
                if isinstance(val, list):
                    skos_kwargs[sk] = val

        tag = Tag(
            id=tag_id,
            facet=facet,
            display_name=display,
            parents=parents,
            **skos_kwargs,
        )
        tags.append(tag)

        # Recurse into children (SKOS keys are skipped by the guard above)
        if isinstance(subtree, dict) and subtree:
            _walk_tree(subtree, facet, tag_id, tags, current_parts)


def _parse_domains_section(domains: dict[str, Any]) -> list[Tag]:
    """Parse the 'domains' top-level section of TAXONOMY.yaml."""
    tags: list[Tag] = []
    _walk_tree(domains, "domain", None, tags)
    return tags


def _parse_technologies_section(technologies: dict[str, Any]) -> list[Tag]:
    """Parse the 'technologies' top-level section of TAXONOMY.yaml.

    The first level under 'technologies' is the category (language, database, etc.)
    which maps to a facet via FACET_PREFIXES. Children get that facet.
    """
    tags: list[Tag] = []
    for category, subtree in technologies.items():
        facet = FACET_PREFIXES.get(category.lower(), "platform")
        if not isinstance(subtree, dict):
            continue

        # The category itself becomes a root tag
        cat_id = category.lower()
        tags.append(Tag(
            id=cat_id,
            facet=facet,
            display_name=category.replace("_", " ").title(),
            parents=[],
        ))

        _walk_tree(subtree, facet, cat_id, tags)

    return tags


def load_taxonomy_yaml(seeds_dir: str) -> list[Tag]:
    """Load TAXONOMY.yaml and convert both sections to Tag objects."""
    taxonomy_path = os.path.join(seeds_dir, "TAXONOMY.yaml")
    if not os.path.isfile(taxonomy_path):
        logger.warning("TAXONOMY.yaml not found at %s", taxonomy_path)
        return []

    with open(taxonomy_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    tags: list[Tag] = []

    domains = data.get("domains")
    if isinstance(domains, dict):
        tags.extend(_parse_domains_section(domains))

    technologies = data.get("technologies")
    if isinstance(technologies, dict):
        tags.extend(_parse_technologies_section(technologies))

    return tags


# =====================================================================
# Auto-discover tags from seed nodes
# =====================================================================

def _extract_tag_from_dotted_path(
    path: str,
    registry: TagRegistry,
) -> list[Tag]:
    """Extract Tag objects from a dotted path like 'framework.python.fastapi'.

    Creates tags for segments not already in the registry,
    with parent-child relationships based on position in the path.
    """
    parts = path.lower().strip().split(".")
    if not parts:
        return []

    tags: list[Tag] = []
    first = parts[0]

    # Determine facet from first segment
    facet = FACET_PREFIXES.get(first)
    if facet:
        # Skip the category prefix (e.g., "language", "framework")
        segments = parts[1:]
        # Ensure the category root exists
        if not registry.get(first):
            tags.append(Tag(id=first, facet=facet, parents=[]))
    elif first in DOMAIN_ROOTS:
        facet = "domain"
        segments = parts  # keep the root as part of the chain
    else:
        # Try to resolve first segment
        resolved = registry.resolve(first)
        if resolved:
            facet = resolved.facet
        else:
            facet = "unknown"
        segments = parts

    # Build chain: each segment's parent is the previous segment
    prev_id: str | None = None
    for seg in segments:
        if not seg:
            continue
        existing = registry.get(seg)
        if not existing:
            parents = [prev_id] if prev_id else []
            tags.append(Tag(
                id=seg,
                facet=facet,
                parents=parents,
            ))
        elif prev_id and prev_id not in existing.parents:
            # Add parent link (polyhierarchy)
            existing.parents.append(prev_id)
        prev_id = seg

    return tags


def discover_tags_from_nodes(
    nodes: list[dict[str, Any]],
    registry: TagRegistry,
) -> list[Tag]:
    """Auto-discover and create Tag objects from seed node data.

    Inspects each node's technologies and domains fields, creates
    tags for any segments not already in the registry.
    """
    new_tags: list[Tag] = []
    seen_paths: set[str] = set()

    for node in nodes:
        # Process technologies/languages
        for tech in (node.get("technologies") or node.get("languages") or []):
            path = str(tech).lower().strip()
            if path and path not in seen_paths:
                seen_paths.add(path)
                new_tags.extend(_extract_tag_from_dotted_path(path, registry))

        # Process domains
        for domain in (node.get("domains") or []):
            path = str(domain).lower().strip()
            if path and path not in seen_paths:
                seen_paths.add(path)
                new_tags.extend(_extract_tag_from_dotted_path(path, registry))

    return new_tags


# =====================================================================
# Known polyhierarchy links (cross-facet parents)
# =====================================================================

# These add polyhierarchy edges that the tree structure can't express.
# Format: (child_id, additional_parent_id)
POLYHIERARCHY_LINKS: list[tuple[str, str]] = [
    # Frameworks belong to both their language and their paradigm
    ("flask", "microframework"),
    ("flask", "wsgi"),
    ("django", "fullstack_framework"),
    ("django", "wsgi"),
    ("fastapi", "asgi"),
    ("fastapi", "microframework"),
    ("express", "microframework"),
    ("nestjs", "fullstack_framework"),
    ("spring_boot", "fullstack_framework"),
    ("rails", "fullstack_framework"),
    # Cross-concern: ORM frameworks
    ("sqlalchemy", "python"),
    ("sqlalchemy", "sql"),
    # Testing tools belong to their language
    ("pytest", "python"),
    ("jest", "javascript"),
    # Observability tools
    ("prometheus", "metrics"),
    ("grafana", "dashboards"),
    ("jaeger", "tracing"),
    # Database tools
    ("pgbouncer", "connection_pooling"),
    ("redis", "caching"),
    ("redis", "message_broker"),
]

# Aliases for common variations
KNOWN_ALIASES: dict[str, list[str]] = {
    "python": ["py", "python3", "cpython"],
    "javascript": ["js", "ecmascript", "es6", "es2015"],
    "typescript": ["ts"],
    "golang": ["go"],
    "postgresql": ["postgres", "pg", "psql"],
    "mongodb": ["mongo"],
    "kubernetes": ["k8s", "kube"],
    "elasticsearch": ["es", "elastic"],
    "redis": ["redis-server"],
    "docker": ["container", "dockerfile"],
    "fastapi": ["fast-api"],
    "flask": ["flask-app"],
    "django": ["django-app"],
    "react": ["reactjs", "react.js"],
    "vue": ["vuejs", "vue.js"],
    "angular": ["angularjs"],
    "nodejs": ["node", "node.js"],
    "rust": ["rustlang"],
    "graphql": ["gql"],
    "grpc": ["g-rpc"],
    "rabbitmq": ["rmq", "rabbit"],
    "apache_kafka": ["kafka"],
    "celery": ["celery-worker"],
    "sqlalchemy": ["sa", "sqla"],
    "pytest": ["py.test"],
    "cors": ["cross-origin"],
}

# Extra paradigm/concept tags not in TAXONOMY.yaml
CONCEPT_TAGS: list[Tag] = [
    Tag(id="microframework", facet="pattern", parents=[]),
    Tag(id="fullstack_framework", facet="pattern", parents=[]),
    Tag(id="wsgi", facet="concern", parents=["web"]),
    Tag(id="asgi", facet="concern", parents=["web"]),
    Tag(id="web", facet="concern", parents=[]),
    Tag(id="sql", facet="concern", parents=["databases"]),
    Tag(id="caching", facet="concern", parents=["performance"]),
    Tag(id="message_broker", facet="concern", parents=["messaging"]),
    Tag(id="connection_pooling", facet="concern", parents=["databases"]),
    Tag(id="metrics", facet="concern", parents=["observability"]),
    Tag(id="dashboards", facet="concern", parents=["observability"]),
    Tag(id="tracing", facet="concern", parents=["observability"]),
    # Knowledge enrichment v2 — cognitive + product concern tags
    Tag(id="meta_cognition", facet="concern", parents=["reasoning"]),
    Tag(id="decision_making", facet="concern", parents=["reasoning"]),
    Tag(id="diagnosis", facet="concern", parents=["testing"]),
    Tag(id="migration", facet="concern", parents=["databases"]),
    Tag(id="consistency", facet="concern", parents=["databases"]),
    Tag(id="estimation", facet="concern", parents=["culture"]),
    Tag(id="communication", facet="concern", parents=["culture"]),
    Tag(id="domain_specific", facet="concern", parents=[]),
    Tag(id="failure", facet="concern", parents=["antipattern"]),
    Tag(id="cautionary", facet="concern", parents=["antipattern"]),
]


# =====================================================================
# Main bootstrap function
# =====================================================================

def bootstrap_registry(
    seeds_dir: str,
    nodes: list[dict[str, Any]] | None = None,
) -> TagRegistry:
    """Build a fully populated TagRegistry from TAXONOMY.yaml + seed nodes.

    Steps:
    1. Load TAXONOMY.yaml tree → Tag objects
    2. Register concept tags and known aliases
    3. Register all tags in the registry
    4. Discover additional tags from seed node data
    5. Apply polyhierarchy links
    6. Precompute ancestor/descendant closure

    Args:
        seeds_dir: Path to the seeds directory containing TAXONOMY.yaml
        nodes: Optional list of all knowledge nodes for tag discovery

    Returns:
        A fully built TagRegistry ready for use
    """
    registry = TagRegistry()

    # 1. Load TAXONOMY.yaml
    yaml_tags = load_taxonomy_yaml(seeds_dir)
    logger.info("Loaded %d tags from TAXONOMY.yaml", len(yaml_tags))

    # 2. Add concept tags first (these provide cross-facet parents)
    registry.register_batch(CONCEPT_TAGS)

    # 3. Register TAXONOMY.yaml tags
    registry.register_batch(yaml_tags)

    # 4. Register known aliases
    for tag_id, aliases in KNOWN_ALIASES.items():
        tag = registry.get(tag_id)
        if tag:
            for alias in aliases:
                if alias.lower() not in tag.aliases:
                    tag.aliases.append(alias.lower())
                    registry._alias_index[alias.lower()] = tag.id
        else:
            # Create stub tag with aliases
            registry.register(Tag(
                id=tag_id,
                facet="unknown",
                aliases=aliases,
            ))

    # 5. Discover tags from seed node data
    if nodes:
        node_tags = discover_tags_from_nodes(nodes, registry)
        if node_tags:
            registry.register_batch(node_tags)
            logger.info("Discovered %d additional tags from %d nodes", len(node_tags), len(nodes))

    # 6. Apply polyhierarchy links
    applied = 0
    for child_id, parent_id in POLYHIERARCHY_LINKS:
        child = registry.get(child_id)
        parent = registry.get(parent_id)
        if child and parent and parent_id not in child.parents:
            child.parents.append(parent_id)
            applied += 1
    if applied:
        logger.info("Applied %d polyhierarchy links", applied)

    # 7. Precompute closure
    registry.ensure_closure()

    stats = registry.stats()
    logger.info(
        "TagRegistry bootstrapped: %d tags, %d aliases, %d facets, max depth %d",
        stats["total_tags"],
        stats["aliases"],
        len(stats["facets"]),
        stats["max_ancestor_depth"],
    )

    return registry
