"""Schema definitions for the Engineering Knowledge Brain.

Defines the 6 cortical layers, node types, edge types, and partitioning strategy
for industrial-scale knowledge graph operations.
"""

from __future__ import annotations

from enum import StrEnum


class Layer(StrEnum):
    """6 cortical layers of the knowledge brain, from deepest to surface."""

    L0_AXIOMS = "L0"  # Immutable truths — permanent
    L1_PRINCIPLES = "L1"  # Stable wisdom — decades
    L2_PATTERNS = "L2"  # Established practices — years
    L3_RULES = "L3"  # Learned constraints — months to years
    L4_EVIDENCE = "L4"  # Concrete instances — months
    L5_CONTEXT = "L5"  # Ephemeral session state — minutes to hours

    @property
    def stability(self) -> float:
        """Higher = more stable (0.0 ephemeral → 1.0 permanent)."""
        return {
            "L0": 1.0,
            "L1": 0.9,
            "L2": 0.7,
            "L3": 0.5,
            "L4": 0.3,
            "L5": 0.1,
        }[self.value]

    @property
    def max_ttl_days(self) -> int | None:
        """Maximum time-to-live in days. None = permanent."""
        return {
            "L0": None,
            "L1": None,
            "L2": None,
            "L3": 365,
            "L4": 90,
            "L5": 1,
        }[self.value]


class NodeType(StrEnum):
    """All node types in the knowledge graph."""

    # Layer nodes
    AXIOM = "Axiom"
    PRINCIPLE = "Principle"
    PATTERN = "Pattern"
    RULE = "Rule"
    FINDING = "Finding"
    CODE_EXAMPLE = "CodeExample"
    TEST_RESULT = "TestResult"
    TASK = "Task"

    # Taxonomy nodes
    TECHNOLOGY = "Technology"
    FILE_TYPE = "FileType"
    DOMAIN = "Domain"
    HUMAN_LAYER = "HumanLayer"
    # Source attribution
    SOURCE = "Source"
    VALIDATION_RUN = "ValidationRun"

    @property
    def layer(self) -> Layer | None:
        """Which cortical layer this node type belongs to."""
        return _NODE_LAYER_MAP.get(self)


class EdgeType(StrEnum):
    """All relationship types in the knowledge graph (32 total)."""

    # Hierarchical (layer-to-layer)
    GROUNDS = "GROUNDS"  # Axiom → Principle
    INFORMS = "INFORMS"  # Principle → Pattern
    INSTANTIATES = "INSTANTIATES"  # Pattern → Rule
    EVIDENCED_BY = "EVIDENCED_BY"  # Rule → Finding
    DEMONSTRATED_BY = "DEMONSTRATED_BY"  # Rule → CodeExample

    # Cross-layer (semantic)
    APPLIES_TO = "APPLIES_TO"  # Rule/Pattern → Technology/FileType
    IN_DOMAIN = "IN_DOMAIN"  # Rule/Pattern → Domain
    USED_IN = "USED_IN"  # Pattern → Technology
    CAUGHT_BY = "CAUGHT_BY"  # Finding → HumanLayer
    VIOLATED = "VIOLATED"  # Finding → Rule
    # Evolution (learning)
    SUPERSEDES = "SUPERSEDES"  # Rule → Rule (newer version)
    CONFLICTS_WITH = "CONFLICTS_WITH"  # Rule ↔ Rule (contradiction)
    VARIANT_OF = "VARIANT_OF"  # Pattern → Pattern (family)
    REINFORCES = "REINFORCES"  # Evidence → Rule
    WEAKENS = "WEAKENS"  # Evidence → Rule

    # Causal
    CAUSED_BY = "CAUSED_BY"  # Finding → Finding
    PREVENTS = "PREVENTS"  # Rule → Pattern (anti-pattern)

    # Context
    REQUIRES = "REQUIRES"  # Task → Technology
    PRODUCES = "PRODUCES"  # Task → FileType
    SUBDOMAIN_OF = "SUBDOMAIN_OF"  # Domain → Domain

    # Source attribution
    CITES = "CITES"  # Knowledge → Source
    SOURCED_FROM = "SOURCED_FROM"  # Rule → Source (creation link)
    VALIDATED_BY = "VALIDATED_BY"  # Knowledge → ValidationRun

    # Reasoning edges (used by pack_manager, reasoning_engine)
    RELATES_TO = "RELATES_TO"  # Generic relationship
    STRENGTHENS = "STRENGTHENS"  # Evidence strengthens knowledge
    PREREQUISITE = "PREREQUISITE"  # Knowledge depends on prior knowledge
    DEEPENS = "DEEPENS"  # Knowledge deepens understanding
    ALTERNATIVE = "ALTERNATIVE"  # Alternative approach
    TRIGGERS = "TRIGGERS"  # Event triggers consequence
    COMPLEMENTS = "COMPLEMENTS"  # Knowledge complements another
    VALIDATES = "VALIDATES"  # Knowledge validates another


# --- Partitioning & Sharding ---

# Domains used for graph sharding
SHARD_DOMAINS: list[str] = [
    "security",
    "testing",
    "architecture",
    "ui",
    "api",
    "database",
    "performance",
    "devops",
    "general",
]

# Qdrant collection names per layer
VECTOR_COLLECTIONS: dict[str, str] = {
    "L0": "brain_axioms",
    "L1": "brain_principles",
    "L2": "brain_patterns",
    "L3": "brain_rules",
    "L4": "brain_evidence",
}

# Redis cache key prefixes
CACHE_KEY_PREFIX = "brain"

# Graph database name for engineering brain
BRAIN_GRAPH_DB = "engineering_brain"


def shard_key(domain: str, layer: Layer) -> str:
    """Compute shard key for partitioning: domain:layer."""
    d = domain.lower().strip()
    if d not in SHARD_DOMAINS:
        d = "general"
    return f"{d}:{layer.value}"


def collection_for_layer(layer: Layer) -> str | None:
    """Get Qdrant collection name for a given layer."""
    return VECTOR_COLLECTIONS.get(layer.value)


def cache_key(domain: str, technology: str, file_type: str) -> str:
    """Build Redis cache key for a query context."""
    parts = [CACHE_KEY_PREFIX, domain, technology, file_type]
    return ":".join(p.lower().strip() for p in parts if p)


# --- Internal maps ---

_NODE_LAYER_MAP: dict[NodeType, Layer | None] = {
    NodeType.AXIOM: Layer.L0_AXIOMS,
    NodeType.PRINCIPLE: Layer.L1_PRINCIPLES,
    NodeType.PATTERN: Layer.L2_PATTERNS,
    NodeType.RULE: Layer.L3_RULES,
    NodeType.FINDING: Layer.L4_EVIDENCE,
    NodeType.CODE_EXAMPLE: Layer.L4_EVIDENCE,
    NodeType.TEST_RESULT: Layer.L4_EVIDENCE,
    NodeType.TASK: Layer.L5_CONTEXT,
    # Taxonomy & metadata nodes (no cortical layer — return None)
    NodeType.TECHNOLOGY: None,
    NodeType.FILE_TYPE: None,
    NodeType.DOMAIN: None,
    NodeType.HUMAN_LAYER: None,
    NodeType.SOURCE: None,
    NodeType.VALIDATION_RUN: None,
}
