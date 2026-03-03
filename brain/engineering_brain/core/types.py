"""Pydantic models for all node and edge types in the Engineering Knowledge Brain.

Every knowledge node carries WHY (understanding) and HOW (actionable guidance),
not just WHAT (rule text). This is the core design principle — teach agents to
think, not memorize.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

import logging
import warnings

from pydantic import BaseModel, Field, field_validator, model_validator

_logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _warn_empty_sources(model_name: str, node_id: str) -> None:
    """Emit a deprecation warning for knowledge nodes without sources.

    This is a soft enforcement: warns now, will become a hard error
    once all seeds have been backfilled with proper sources.
    """
    warnings.warn(
        f"{model_name}(id={node_id!r}) has no sources — "
        "at least one authoritative source will be required in a future version",
        stacklevel=4,
    )


# =============================================================================
# Source Attribution & Validation
# =============================================================================

class EpistemicStatus(str, Enum):
    """Epistemic maturity level for knowledge nodes (E0-E5 ladder).

    Classifies how well-established a piece of knowledge is:
    - E0: Unverified rumor from a single source
    - E1: Hypothesis with some supporting evidence
    - E2: Empirically observed in multiple contexts
    - E3: Tested and validated through automated checks
    - E4: Formally proven or exhaustively verified
    - E5: Foundational axiom (self-evident truth)

    Each level has minimum requirements for sources, belief mass,
    and maximum tolerated uncertainty.
    """

    E0_RUMOR = "E0"
    E1_HYPOTHESIS = "E1"
    E2_OBSERVATION = "E2"
    E3_TESTED = "E3"
    E4_PROVEN = "E4"
    E5_AXIOM = "E5"

    @property
    def min_sources(self) -> int:
        """Minimum number of independent sources required."""
        return {
            "E0": 0, "E1": 1, "E2": 2, "E3": 2, "E4": 3, "E5": 0,
        }[self.value]

    @property
    def min_belief(self) -> float:
        """Minimum epistemic belief mass (ep_b) required."""
        return {
            "E0": 0.0, "E1": 0.2, "E2": 0.4, "E3": 0.6, "E4": 0.8, "E5": 0.95,
        }[self.value]

    @property
    def max_uncertainty(self) -> float:
        """Maximum tolerated epistemic uncertainty (ep_u)."""
        return {
            "E0": 1.0, "E1": 0.8, "E2": 0.6, "E3": 0.4, "E4": 0.2, "E5": 0.05,
        }[self.value]

    @property
    def level(self) -> int:
        """Numeric level (0-5) for ordering."""
        return int(self.value[1])


class SourceType(str, Enum):
    """Type of authoritative source, ordered by trust weight."""

    OFFICIAL_DOCS = "official_docs"
    SECURITY_CVE = "security_cve"
    RFC_STANDARD = "rfc_standard"
    STACKOVERFLOW = "stackoverflow"
    MDN = "mdn"
    GITHUB_ADVISORY = "github_advisory"
    OWASP = "owasp"
    PACKAGE_REGISTRY = "package_registry"
    HUMAN_CURATED = "human_curated"


class ValidationStatus(str, Enum):
    """Validation state of a knowledge node."""

    UNVALIDATED = "unvalidated"
    CROSS_CHECKED = "cross_checked"
    HUMAN_VERIFIED = "human_verified"


class Source(BaseModel):
    """Authoritative source reference for a knowledge node."""

    url: str = Field(description="Canonical URL")
    title: str = Field(default="", description="Display title")
    source_type: SourceType = Field(description="Type of authoritative source")
    retrieved_at: datetime | None = Field(default=None, description="When this source was verified")
    vote_count: int | None = Field(default=None, description="StackOverflow votes or GitHub stars")
    is_accepted_answer: bool = Field(default=False, description="StackOverflow accepted answer")
    cvss_score: float | None = Field(default=None, description="CVSS score for CVE sources")
    verified: bool = Field(default=False, description="URL reachability confirmed")


# =============================================================================
# L0 — Axioms (immutable truths)
# =============================================================================

class Axiom(BaseModel):
    """Immutable software truth — the physical laws of engineering."""

    id: str
    statement: str = Field(description="The axiom statement")
    domain: str = Field(default="general", description="Primary domain")
    formal_notation: str | None = Field(default=None, description="Formal/mathematical notation")
    proof_reference: str | None = Field(default=None, description="Reference to proof or standard")
    immutable: bool = Field(default=True, description="Always True for axioms")
    sources: list[Source] = Field(default_factory=list, description="At least one authoritative source REQUIRED — enforced after backfill")
    validation_status: ValidationStatus = Field(default=ValidationStatus.UNVALIDATED)
    ep_b: float | None = Field(default=None, description="Epistemic belief mass")
    ep_d: float | None = Field(default=None, description="Epistemic disbelief mass")
    ep_u: float | None = Field(default=None, description="Epistemic uncertainty mass")
    ep_a: float | None = Field(default=None, description="Epistemic base rate")
    epistemic_status: str = Field(default="E5", description="Epistemic maturity level (E0-E5)")

    @model_validator(mode="after")
    def _check_sources(self) -> "Axiom":
        if not self.sources:
            _warn_empty_sources("Axiom", self.id)
        return self


# =============================================================================
# L1 — Principles (stable wisdom)
# =============================================================================

class Principle(BaseModel):
    """Core engineering principle — the constitution of good engineering."""

    id: str
    name: str = Field(description="Short memorable name")
    why: str = Field(description="WHY this matters — the deeper understanding")
    how_to_apply: str = Field(description="HOW to apply — actionable steps")
    when_applies: str = Field(default="", description="WHEN to apply — contexts/conditions that trigger this principle")
    when_not_applies: str = Field(default="", description="WHEN NOT to apply — contexts where this principle is irrelevant or counterproductive")
    mental_model: str = Field(description="Mental model or analogy for intuitive understanding")
    domains: list[str] = Field(default_factory=list, description="Applicable domains")
    violation_consequence: str = Field(default="", description="What happens when violated")
    teaching_example: str = Field(default="", description="Concrete example that teaches the principle")
    sources: list[Source] = Field(default_factory=list, description="At least one authoritative source REQUIRED — enforced after backfill")
    validation_status: ValidationStatus = Field(default=ValidationStatus.UNVALIDATED)
    ep_b: float | None = Field(default=None, description="Epistemic belief mass")
    ep_d: float | None = Field(default=None, description="Epistemic disbelief mass")
    ep_u: float | None = Field(default=None, description="Epistemic uncertainty mass")
    ep_a: float | None = Field(default=None, description="Epistemic base rate")
    epistemic_status: str = Field(default="E0", description="Epistemic maturity level (E0-E5)")

    @model_validator(mode="after")
    def _check_sources(self) -> "Principle":
        if not self.sources:
            _warn_empty_sources("Principle", self.id)
        return self


# =============================================================================
# L2 — Patterns (established practices)
# =============================================================================

class Pattern(BaseModel):
    """Design pattern — the vocabulary of experienced engineers."""

    id: str
    name: str
    category: str = Field(default="general", description="Pattern category")
    intent: str = Field(description="What problem this pattern solves")
    when_to_use: str = Field(description="Conditions that signal this pattern is needed")
    when_not_to_use: str = Field(default="", description="Anti-conditions")
    languages: list[str] = Field(default_factory=list, description="Applicable languages")
    example_good: str = Field(default="", description="Good implementation example")
    example_bad: str = Field(default="", description="Bad implementation to contrast")
    related_principles: list[str] = Field(default_factory=list, description="L1 principle IDs")
    sources: list[Source] = Field(default_factory=list, description="At least one authoritative source REQUIRED — enforced after backfill")
    validation_status: ValidationStatus = Field(default=ValidationStatus.UNVALIDATED)
    ep_b: float | None = Field(default=None, description="Epistemic belief mass")
    ep_d: float | None = Field(default=None, description="Epistemic disbelief mass")
    ep_u: float | None = Field(default=None, description="Epistemic uncertainty mass")
    ep_a: float | None = Field(default=None, description="Epistemic base rate")
    epistemic_status: str = Field(default="E0", description="Epistemic maturity level (E0-E5)")
    # Soft-delete fields — zero-loss deprecation
    deprecated: bool = Field(default=False, description="Soft-deleted — invisible in queries but preserved in graph")
    deprecated_at: datetime | None = Field(default=None, description="When this node was deprecated")
    deprecation_reason: str = Field(default="", description="stale|low_confidence|superseded")

    @model_validator(mode="after")
    def _check_sources(self) -> "Pattern":
        if not self.sources:
            _warn_empty_sources("Pattern", self.id)
        return self


# =============================================================================
# L3 — Rules (learned from experience) — UPGRADED with WHY + HOW
# =============================================================================

class Rule(BaseModel):
    """Crystallized rule — learned constraint with WHY + HOW.

    Unlike old-style rules that just said 'don't do X', these rules teach:
    - WHY: The deeper reason this matters
    - HOW: The correct way to do it
    - EXAMPLE_GOOD: Working code that demonstrates the right approach
    - EXAMPLE_BAD: Anti-pattern code to recognize and avoid
    """

    id: str
    text: str = Field(description="The rule statement")
    why: str = Field(description="WHY this rule exists — the understanding")
    how_to_do_right: str = Field(description="HOW to do it correctly — actionable steps")
    when_applies: str = Field(default="", description="WHEN this rule applies — specific contexts, technologies, or conditions")
    when_not_applies: str = Field(default="", description="WHEN this rule does NOT apply — exceptions, irrelevant contexts")
    severity: str = Field(default="medium", description="critical|high|medium|low")
    technologies: list[str] = Field(default_factory=list)
    file_types: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    reinforcement_count: int = Field(default=0, description="Times this rule was confirmed")
    observation_count: int = Field(default=0, description="Times this rule was observed in scoring context")
    confidence: float = Field(default=0.5, description="0.0-1.0 confidence score")
    last_violation: datetime | None = Field(default=None)
    example_good: str = Field(default="", description="Good code example")
    example_bad: str = Field(default="", description="Bad code example")
    source_findings: list[str] = Field(default_factory=list, description="Finding IDs that generated this rule")
    sources: list[Source] = Field(default_factory=list, description="At least one authoritative source REQUIRED — enforced after backfill")
    validation_status: ValidationStatus = Field(default=ValidationStatus.UNVALIDATED)
    ep_b: float | None = Field(default=None, description="Epistemic belief mass")
    ep_d: float | None = Field(default=None, description="Epistemic disbelief mass")
    ep_u: float | None = Field(default=None, description="Epistemic uncertainty mass")
    ep_a: float | None = Field(default=None, description="Epistemic base rate")
    epistemic_status: str = Field(default="E0", description="Epistemic maturity level (E0-E5)")
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime | None = Field(default=None, description="Last modification timestamp")
    # Scaling fields
    version: int = Field(default=1, description="Node version for conflict detection")
    shard_id: str | None = Field(default=None, description="Shard assignment for distributed storage")
    etag: str | None = Field(default=None, description="Content hash for optimistic concurrency")
    # Prediction fields — testable IF/THEN knowledge
    prediction_if: str = Field(default="", description="IF condition (testable predicate)")
    prediction_then: str = Field(default="", description="THEN expected outcome")
    prediction_tested_count: int = Field(default=0, description="Times this prediction was tested")
    prediction_success_count: int = Field(default=0, description="Times prediction was confirmed")
    # Soft-delete fields — zero-loss deprecation
    deprecated: bool = Field(default=False, description="Soft-deleted — invisible in queries but preserved in graph")
    deprecated_at: datetime | None = Field(default=None, description="When this node was deprecated")
    deprecation_reason: str = Field(default="", description="stale|low_confidence|superseded")

    @model_validator(mode="after")
    def _check_sources(self) -> "Rule":
        if not self.sources:
            _warn_empty_sources("Rule", self.id)
        return self


# =============================================================================
# L4 — Evidence (concrete instances)
# =============================================================================

class Finding(BaseModel):
    """Concrete finding — specific bug, issue, or observation.

    SBAR extension fields (expected, actual, requirement_id, root_cause,
    category) align with pipeline Finding dataclass for seamless ingestion.
    """

    id: str
    finding_type: str = Field(default="bug", description="bug|security|quality|performance")
    description: str
    severity: str = Field(default="medium")
    file_path: str = Field(default="")
    line: int | None = Field(default=None)
    sprint: str = Field(default="")
    run_id: str = Field(default="")
    resolution: str = Field(default="")
    lesson_learned: str = Field(default="", description="What we learned from this finding")
    timestamp: datetime = Field(default_factory=_now)
    # SBAR extension — structured finding fields
    expected: str = Field(default="", description="SBAR: what was expected")
    actual: str = Field(default="", description="SBAR: what actually happened")
    requirement_id: str = Field(default="", description="RF/INV/EDGE ID this finding relates to")
    root_cause: str = Field(default="", description="Root cause analysis")
    category: str = Field(default="", description="Finding category (e.g., logic_error, missing_validation)")
    confidence: float = Field(default=0.5, description="Confidence in this finding (0.0-1.0)")
    verification: str = Field(default="", description="How this finding was verified")
    # Source attribution — consistent with Axiom, Principle, Pattern, Rule
    sources: list[Source] = Field(default_factory=list, description="At least one authoritative source REQUIRED — enforced after backfill")
    # Soft-delete fields — zero-loss deprecation (consistent with Pattern/Rule)
    deprecated: bool = Field(default=False, description="Soft-deleted — invisible in queries but preserved in graph")
    deprecated_at: datetime | None = Field(default=None, description="When this finding was deprecated")
    deprecation_reason: str = Field(default="", description="stale|low_confidence|superseded|resolved")

    @model_validator(mode="after")
    def _check_sources(self) -> "Finding":
        if not self.sources:
            _warn_empty_sources("Finding", self.id)
        return self


class CodeExample(BaseModel):
    """Concrete code example — good or bad code with explanation."""

    id: str
    language: str = Field(default="python")
    code: str
    quality: str = Field(default="good", description="good|bad|mixed")
    explanation: str = Field(description="Why this code is good/bad")
    file_origin: str = Field(default="", description="Where this code came from")
    pattern_demonstrated: str = Field(default="", description="Pattern ID this demonstrates")


class TestResult(BaseModel):
    """Test execution result — evidence of correctness or failure."""

    id: str
    test_name: str
    status: str = Field(default="passed", description="passed|failed|skipped|error")
    sprint: str = Field(default="")
    assertion_count: int = Field(default=0)
    failure_reason: str = Field(default="")
    timestamp: datetime = Field(default_factory=_now)


# =============================================================================
# L5 — Context (ephemeral)
# =============================================================================

class TaskContext(BaseModel):
    """Ephemeral task context — current session state."""

    id: str
    session_id: str = Field(default="")
    description: str
    technologies: list[str] = Field(default_factory=list)
    file_types: list[str] = Field(default_factory=list)
    phase: str = Field(default="exec", description="init|spec|exec|qa|vote")
    ttl_minutes: int = Field(default=60)


# =============================================================================
# Cross-cutting taxonomy
# =============================================================================

class Technology(BaseModel):
    """Technology node — framework, library, language."""

    id: str
    name: str
    version: str = Field(default="")
    category: str = Field(default="framework", description="framework|library|language|tool")
    ecosystem: str = Field(default="", description="python|javascript|css|general")


class FileType(BaseModel):
    """File type node — extension and associated patterns."""

    id: str
    extension: str
    language: str = Field(default="")
    typical_patterns: list[str] = Field(default_factory=list)


class Domain(BaseModel):
    """Knowledge domain — hierarchical categorization."""

    id: str
    name: str
    parent_domain: str = Field(default="", description="Parent domain ID for hierarchy")
    description: str = Field(default="")


class HumanLayer(BaseModel):
    """Human layer perspective — the lens through which to evaluate."""

    id: str
    name: str
    perspective: str = Field(default="", description="What perspective this layer provides")
    focus_areas: list[str] = Field(default_factory=list)


class Sprint(BaseModel):
    """Sprint node — execution context for findings and test results."""

    id: str
    name: str = Field(default="", description="Sprint name, e.g. 'S00 — Foundation Models'")
    product: str = Field(default="", description="Product this sprint belongs to")
    status: str = Field(default="pending", description="pending|in_progress|completed|failed")
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)


# =============================================================================
# Query & Result types
# =============================================================================

class KnowledgeQuery(BaseModel):
    """Query to the knowledge brain."""

    task_description: str = Field(description="What the agent is trying to do")
    technologies: list[str] = Field(default_factory=list)
    file_type: str = Field(default="")
    phase: str = Field(default="exec")
    domains: list[str] = Field(default_factory=list)
    max_results_per_layer: dict[str, int] | None = Field(default=None)
    budget_chars: int | None = Field(default=None)


class KnowledgeResult(BaseModel):
    """Result from querying the knowledge brain."""

    principles: list[dict[str, Any]] = Field(default_factory=list)
    patterns: list[dict[str, Any]] = Field(default_factory=list)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    formatted_text: str = Field(default="", description="Budget-capped LLM-ready text")
    total_nodes_queried: int = Field(default=0)
    cache_hit: bool = Field(default=False)
    shards_queried: list[str] = Field(default_factory=list)
    query_time_ms: float = Field(default=0.0)


class ConfidenceTier(str, Enum):
    """Epistemic confidence classification for knowledge nodes."""

    VALIDATED = "validated"
    PROBABLE = "probable"
    UNCERTAIN = "uncertain"
    CONTESTED = "contested"


class EnhancedKnowledgeResult(BaseModel):
    """Knowledge result enriched with epistemic context for frontier model consumption."""

    base_result: KnowledgeResult = Field(description="Original query result")
    assessments: list[dict[str, Any]] = Field(default_factory=list, description="Per-node confidence assessment")
    contradictions: list[dict[str, Any]] = Field(default_factory=list, description="In-result contradictions")
    gaps: list[dict[str, Any]] = Field(default_factory=list, description="Query-relevant knowledge gaps")
    metacognitive_summary: str = Field(default="", description="Natural language summary of what brain knows/doesn't know")
    enhanced_text: str = Field(default="", description="Epistemically-annotated LLM-ready text")
    confidence_distribution: dict[str, int] = Field(default_factory=dict, description="Counts per tier")
    overall_confidence: str = Field(default="", description="Dominant confidence tier")
    has_contradictions: bool = Field(default=False)
    has_gaps: bool = Field(default=False)


# =============================================================================
# Edge model (for graph storage)
# =============================================================================

class KnowledgeEdge(BaseModel):
    """Edge between two knowledge nodes."""

    from_id: str
    to_id: str
    edge_type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    weight: float = Field(default=1.0)
    created_at: datetime = Field(default_factory=_now)
    # Bayesian edge weight fields (Beta distribution)
    edge_alpha: float = Field(default=1.0, description="Beta prior successes")
    edge_beta: float = Field(default=1.0, description="Beta prior failures")
    edge_confidence: float = Field(default=0.5, description="Projected mean = alpha / (alpha + beta)")
    last_reinforced: datetime | None = Field(default=None, description="Last reinforcement timestamp")
    reinforcement_count: int = Field(default=0, description="Total reinforcement events")


# =============================================================================
# Seed YAML model
# =============================================================================

class SeedEntry(BaseModel):
    """Single entry in a seed YAML file."""

    id: str
    text: str = Field(default="")
    name: str = Field(default="")
    why: str = Field(default="")
    how_to_do_right: str = Field(default="")
    how_to_apply: str = Field(default="")
    when_applies: str = Field(default="")
    when_not_applies: str = Field(default="")
    mental_model: str = Field(default="")
    severity: str = Field(default="medium")
    technologies: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    @field_validator("technologies", "domains", "languages", mode="before")
    @classmethod
    def _flatten_faceted_dict(cls, v: Any) -> list[str]:
        """Accept both list[str] and dict[str, list[str]] (faceted format).

        Faceted dict is flattened to a list of tag IDs for downstream compat.
        e.g. {lang: [python], framework: [fastapi]} → [python, fastapi]
        """
        if isinstance(v, dict):
            flat: list[str] = []
            for tags in v.values():
                if isinstance(tags, list):
                    flat.extend(str(t) for t in tags)
                elif isinstance(tags, str):
                    flat.append(tags)
            return flat
        if isinstance(v, list):
            return v
        return []
    example_good: str = Field(default="")
    example_bad: str = Field(default="")
    intent: str = Field(default="")
    when_to_use: str = Field(default="")
    when_not_to_use: str = Field(default="")
    category: str = Field(default="general")
    violation_consequence: str = Field(default="")
    teaching_example: str = Field(default="")
    statement: str = Field(default="")
    formal_notation: str | None = Field(default=None)
    related_principles: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list, description="Source dicts — at least one authoritative source REQUIRED — enforced after backfill")

    @field_validator("sources", mode="before")
    @classmethod
    def _coerce_sources(cls, v: Any) -> list[dict[str, Any]]:
        """Accept both list[str] (bare URLs) and list[dict] (full Source objects)."""
        if not isinstance(v, list):
            return []
        result: list[dict[str, Any]] = []
        for item in v:
            if isinstance(item, str):
                result.append({"url": item, "source_type": "official_docs"})
            elif isinstance(item, dict):
                result.append(item)
        return result
    validation_status: str = Field(default="unvalidated", description="unvalidated|cross_checked|human_verified")
    prediction_if: str = Field(default="", description="IF condition for testable prediction")
    prediction_then: str = Field(default="", description="THEN expected outcome")
    deprecated: bool = Field(default=False)
    deprecated_at: datetime | None = Field(default=None)
    deprecation_reason: str = Field(default="")


class SeedFile(BaseModel):
    """Parsed seed YAML file."""

    layer: str = Field(description="L0|L1|L2|L3|L4|L5 or axioms|principles|patterns|rules|evidence")
    technology: str = Field(default="")
    domain: str = Field(default="general")
    knowledge: list[SeedEntry] = Field(default_factory=list)


# =============================================================================
# ERG — Epistemic Reasoning Graph
# =============================================================================

class Pack(BaseModel):
    """Materialized subgraph — a curated set of nodes with reasoning edges."""

    id: str
    description: str = Field(default="")
    node_ids: list[str] = Field(default_factory=list)
    reasoning_edges: list[dict[str, Any]] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    layers_present: list[str] = Field(default_factory=list)
    quality_score: float = Field(default=0.0)
    node_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=_now)


# =============================================================================
# Pack Factory — Template-driven pack creation + MCP export
# =============================================================================

class MCPToolSpec(BaseModel):
    """Tool definition for generated MCP servers."""

    name: str = Field(description="Tool name, e.g. 'check_vulnerability'")
    description: str = Field(default="", description="For LLM consumption")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema")
    handler_type: str = Field(default="query", description="query|filter|lookup|traverse|aggregate|reason|stats")
    handler_config: dict[str, Any] = Field(default_factory=dict, description="Handler-specific params")


class PackTemplate(BaseModel):
    """Recipe for creating packs — template-driven one-liner creation."""

    id: str = Field(description="Template ID, e.g. 'security-review'")
    name: str = Field(default="", description="Human-readable name")
    description: str = Field(default="", description="What this template is for")
    version: str = Field(default="1.0.0")

    # What knowledge to include
    layers: list[str] = Field(default_factory=list, description="Layer filter: ['L1', 'L2', 'L3']")
    technologies: list[str] = Field(default_factory=list, description="Glob patterns: ['flask', 'python*']")
    domains: list[str] = Field(default_factory=list, description="Domain filter: ['security', 'auth*']")
    severities: list[str] = Field(default_factory=list, description="Severity filter: ['critical', 'high']")
    min_confidence: float = Field(default=0.0)
    exclude_deprecated: bool = Field(default=True)

    # How to structure
    required_layers: list[str] = Field(default_factory=lambda: ["L1", "L2", "L3"])
    min_nodes: int = Field(default=5)
    max_nodes: int = Field(default=80)
    min_quality: float = Field(default=0.3)
    prefer_high_severity: bool = Field(default=False)

    # Reasoning
    reasoning_template: str = Field(default="T-LINEAR-DEFAULT")
    default_profile: str | None = Field(default=None)

    # MCP server generation
    mcp_tools: list[MCPToolSpec] = Field(default_factory=list)
    mcp_server_name: str = Field(default="")
    mcp_server_description: str = Field(default="")

    # Composition
    extends: list[str] = Field(default_factory=list, description="Template IDs to inherit from")
    tags: list[str] = Field(default_factory=list, description="Discovery tags")

    # Parameters accepted by brain.pack()
    parameters: dict[str, Any] = Field(default_factory=dict, description="{param_name: default_value}")


class MaterializedPack(BaseModel):
    """Pack with full node data — ready for export as standalone MCP server."""

    # Core (same as Pack)
    id: str
    description: str = Field(default="")
    node_ids: list[str] = Field(default_factory=list)
    reasoning_edges: list[dict[str, Any]] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    layers_present: list[str] = Field(default_factory=list)
    quality_score: float = Field(default=0.0)
    node_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=_now)

    # Full node data (for standalone servers)
    nodes: list[dict[str, Any]] = Field(default_factory=list, description="Complete node dicts")
    edges: list[dict[str, Any]] = Field(default_factory=list, description="Graph edges between pack nodes")

    # Template reference
    template_id: str = Field(default="")
    template_version: str = Field(default="")

    # Lifecycle
    version: int = Field(default=1)
    usage_count: int = Field(default=0)

    # Internal: template ref for serve/export (excluded from serialization)
    _template: Any = None

    def serve(self, port: int | None = None) -> None:
        """Start an in-process MCP server for this pack."""
        from engineering_brain.export.pack_mcp_generator import PackMCPGenerator
        generator = PackMCPGenerator()
        template = self._resolve_template()
        server = generator.generate_server(self, template=template)
        server.serve(port=port)

    def export(self, path: str) -> None:
        """Export as a standalone MCP server directory."""
        from engineering_brain.export.pack_mcp_generator import PackMCPGenerator
        generator = PackMCPGenerator()
        template = self._resolve_template()
        generator.export(self, output_dir=path, template=template)

    def _resolve_template(self) -> Any:
        """Resolve the PackTemplate from the stored ref or registry lookup."""
        if self._template is not None:
            return self._template
        if not self.template_id:
            return None
        try:
            from engineering_brain.retrieval.pack_templates import get_template_registry
            registry = get_template_registry()
            return registry.get(self.template_id)
        except Exception:
            return None

    def save(self, path: str) -> None:
        """Persist pack state to JSON."""
        import json as _json
        from pathlib import Path as _Path
        _Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            _json.dump(self.model_dump(mode="json"), f, indent=2, default=str)

    @classmethod
    def load(cls, path: str) -> "MaterializedPack":
        """Load pack state from JSON."""
        import json as _json
        with open(path) as f:
            return cls(**_json.load(f))

    def record_usage(self, node_ids: list[str] | None = None) -> None:
        """Record a usage event."""
        self.usage_count += 1


class ReasoningStep(BaseModel):
    """Single step in a reasoning template."""

    order: int
    description: str = Field(default="")
    operation: str = Field(default="activate", description="activate|aggregate|score")
    node_filter: dict[str, Any] = Field(default_factory=dict)
    max_nodes: int = Field(default=8)
    edge_to_next: str = Field(default="", description="PREREQUISITE|DEEPENS|ALTERNATIVE|TRIGGERS|COMPLEMENTS|VALIDATES")


class ReasoningTemplate(BaseModel):
    """Recipe for traversing the graph — sequence of steps with node filters."""

    id: str
    name: str = Field(default="")
    applicable_when: dict[str, Any] = Field(default_factory=dict)
    steps: list[ReasoningStep] = Field(default_factory=list)


class BrainProfile(BaseModel):
    """Role-specific reasoning preferences."""

    id: str
    name: str = Field(default="")
    pack_boost: dict[str, float] = Field(default_factory=dict)
    pack_suppress: dict[str, float] = Field(default_factory=dict)
    confidence_threshold: float = Field(default=0.6)
    contradiction_sensitivity: str = Field(default="moderate", description="low|moderate|high|extreme")
    default_template: str | None = Field(default=None)


class ChainResult(BaseModel):
    """Result of executing one reasoning chain."""

    name: str = Field(default="")
    steps: list[dict[str, Any]] = Field(default_factory=list)
    chain_opinion: dict[str, Any] = Field(default_factory=dict)
    confidence_tier: str = Field(default="")
    nodes_activated: int = Field(default=0)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)


class ReasoningResult(BaseModel):
    """Full result from brain.reason() — structured epistemic reasoning."""

    chains: list[ChainResult] = Field(default_factory=list)
    overall_opinion: dict[str, Any] = Field(default_factory=dict)
    confidence_distribution: dict[str, int] = Field(default_factory=dict)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    metacognitive_summary: str = Field(default="")
    formatted_text: str = Field(default="")
    packs_used: list[str] = Field(default_factory=list)
    template_used: str = Field(default="")
    profile_used: str | None = Field(default=None)
    nodes_activated: int = Field(default=0)
    total_nodes_in_packs: int = Field(default=0)
    reasoning_time_ms: float = Field(default=0.0)
