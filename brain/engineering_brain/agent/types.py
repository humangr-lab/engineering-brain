"""Pydantic models for the Engineering Brain Agent System.

Defines the full type hierarchy: queries, evidence, claims, worker results,
and composed knowledge. All models are immutable and serializable.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# =============================================================================
# Enums
# =============================================================================


class QueryIntent(StrEnum):
    """What the user wants from their query."""

    DECISION = "decision"
    ANALYSIS = "analysis"
    INVESTIGATION = "investigation"
    EXPLANATION = "explanation"
    SYNTHESIS = "synthesis"


class QueryComplexity(StrEnum):
    """Assessed complexity for routing decisions."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class ConfidenceLevel(StrEnum):
    """Confidence in a knowledge claim."""

    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    CONTESTED = "contested"


# =============================================================================
# Input
# =============================================================================


class AgentQuery(BaseModel):
    """Input query for the agent system."""

    question: str = Field(..., min_length=1, description="The question to reason about")
    intent: QueryIntent = Field(
        default=QueryIntent.ANALYSIS,
        description="What kind of answer is expected",
    )
    domain_hints: list[str] = Field(
        default_factory=list,
        description="Domain hints (e.g. 'security', 'performance')",
    )
    technology_hints: list[str] = Field(
        default_factory=list,
        description="Technology hints (e.g. 'flask', 'kafka')",
    )
    context: str = Field(
        default="",
        description="Additional context for the query",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Constraints the answer must satisfy",
    )
    max_depth: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Maximum reasoning depth (1=shallow, 5=exhaustive)",
    )


# =============================================================================
# Evidence & Claims
# =============================================================================


class EvidenceItem(BaseModel):
    """A piece of evidence from the brain's knowledge graph."""

    node_id: str
    node_type: str = ""
    layer: str = ""
    content: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    epistemic_status: str = "E1"
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)


class KnowledgeClaim(BaseModel):
    """A single knowledge claim produced by a worker."""

    claim: str
    confidence: ConfidenceLevel = ConfidenceLevel.MODERATE
    evidence: list[EvidenceItem] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    reasoning: str = ""


# =============================================================================
# Worker Output
# =============================================================================


class WorkerResult(BaseModel):
    """Output from a single domain worker."""

    worker_id: str
    domain: str
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    contradictions_found: list[str] = Field(default_factory=list)
    nodes_consulted: int = 0
    tokens_used: int = 0


# =============================================================================
# Composed Output
# =============================================================================


class ComposedKnowledge(BaseModel):
    """Final composed knowledge from the orchestrator."""

    query: str
    summary: str = ""
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    worker_results: list[WorkerResult] = Field(default_factory=list)
    overall_confidence: ConfidenceLevel = ConfidenceLevel.MODERATE
    contradictions: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    fast_path: bool = False
    tokens_used: int = 0

    def format_markdown(self) -> str:
        """Format as markdown for MCP tool output."""
        lines = [
            "## Composed Knowledge",
            f"**Query**: {self.query}",
            f"**Confidence**: {self.overall_confidence.value.upper()}",
            f"**Fast path**: {'yes' if self.fast_path else 'no'}",
            f"**Tokens**: {self.tokens_used}",
            "",
        ]

        if self.summary:
            lines.extend(["### Summary", self.summary, ""])

        if self.claims:
            lines.append("### Claims")
            for i, claim in enumerate(self.claims, 1):
                lines.append(f"{i}. [{claim.confidence.value.upper()}] {claim.claim}")
                if claim.evidence:
                    for ev in claim.evidence:
                        lines.append(f"   - Evidence: {ev.node_id} ({ev.layer})")
                if claim.contradictions:
                    for c in claim.contradictions:
                        lines.append(f"   - Contradiction: {c}")
            lines.append("")

        if self.contradictions:
            lines.append("### Contradictions")
            for c in self.contradictions:
                lines.append(f"- {c}")
            lines.append("")

        if self.gaps:
            lines.append("### Knowledge Gaps")
            for g in self.gaps:
                lines.append(f"- {g}")
            lines.append("")

        if self.worker_results:
            lines.append("### Workers")
            for wr in self.worker_results:
                lines.append(
                    f"- **{wr.worker_id}** ({wr.domain}): "
                    f"{len(wr.claims)} claims, {wr.nodes_consulted} nodes, "
                    f"{wr.tokens_used} tokens"
                )

        return "\n".join(lines)
