"""Agent guardrails — obligation derivation and applicability checking.

Derives RFC 2119 obligation levels (MUST, SHOULD, MAY, MUST NOT, SHOULD NOT)
from existing node metadata and checks applicability against query context.

Pure heuristic — zero LLM tokens. Designed for the assembly pipeline:
  filter_candidates() → annotate_guardrails() → assemble(strategy)

Two mechanisms:
1. Obligation derivation: maps severity + validation + epistemic status → obligation level.
2. Applicability checking: compares when_applies/when_not_applies against ExtractedContext.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# =============================================================================
# Enums
# =============================================================================


class ObligationLevel(StrEnum):
    """RFC 2119 obligation levels for agent-facing knowledge."""

    MUST = "MUST"
    MUST_NOT = "MUST NOT"
    SHOULD = "SHOULD"
    SHOULD_NOT = "SHOULD NOT"
    MAY = "MAY"


# =============================================================================
# Prohibition detection
# =============================================================================

_PROHIBITION_RE = re.compile(
    r"\b(never|do\s+not|don't|must\s+not|should\s+not|avoid|prohibit|forbid|not\s+allowed)\b",
    re.IGNORECASE,
)

# Fields that express directives (scanned for prohibition patterns)
_DIRECTIVE_FIELDS = ("text", "name", "statement")

# Fields that express rationale (NOT scanned — "avoid" in WHY ≠ prohibition)
# why, how_to_do_right, how_to_apply, intent — deliberately excluded


def _has_prohibition(node: dict[str, Any]) -> bool:
    """Check if the node's directive text contains prohibition language."""
    for key in _DIRECTIVE_FIELDS:
        val = node.get(key, "")
        if val and _PROHIBITION_RE.search(str(val)):
            return True
    return False


# =============================================================================
# Obligation derivation
# =============================================================================

_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}
_VALIDATION_RANK = {"human_verified": 2, "cross_checked": 1, "unvalidated": 0}


def _epistemic_level(node: dict[str, Any]) -> int:
    """Extract numeric epistemic level (0-5) from epistemic_status field."""
    status = str(node.get("epistemic_status", ""))
    if len(status) >= 2 and status[0].upper() == "E" and status[1].isdigit():
        return int(status[1])
    return 0


def _positive_obligation(
    sev_rank: int,
    val_rank: int,
    ep_level: int,
) -> ObligationLevel:
    """Derive positive obligation from the metadata matrix.

    Score combines severity (0-3), validation (0-2), epistemic (0-3 capped).
    Score range: 0 (low/unvalidated/E0) to 8 (critical/human_verified/E3+).

    Thresholds:
      score >= 7 → MUST
      score >= 4 → SHOULD
      score <  4 → MAY
    """
    score = sev_rank + val_rank + min(ep_level, 3)
    if score >= 7:
        return ObligationLevel.MUST
    if score >= 4:
        return ObligationLevel.SHOULD
    return ObligationLevel.MAY


def derive_obligation(node: dict[str, Any]) -> ObligationLevel:
    """Derive an RFC 2119 obligation level from node metadata.

    Decision tree (ordered by precedence):
    1. deprecated → MUST_NOT
    2. prohibition text + critical/high → MUST_NOT
    3. prohibition text + medium/low → SHOULD_NOT
    4. high uncertainty (ep_u > 0.7) → MAY (capped)
    5. Positive obligation from severity × validation × epistemic matrix
    6. reinforcement_count >= 10 promotes MAY → SHOULD
    7. ep_b >= 0.8 promotes one tier (MAY → SHOULD, SHOULD → MUST)
    """
    # 1. Deprecated
    if node.get("deprecated"):
        return ObligationLevel.MUST_NOT

    severity = str(node.get("severity", "medium")).lower()
    sev_rank = _SEVERITY_RANK.get(severity, 1)

    # 2-3. Prohibition detection
    if _has_prohibition(node):
        if sev_rank >= 2:  # critical or high
            return ObligationLevel.MUST_NOT
        return ObligationLevel.SHOULD_NOT

    # 4. High uncertainty cap
    ep_u = node.get("ep_u")
    if ep_u is not None and float(ep_u) > 0.7:
        return ObligationLevel.MAY

    # 5. Positive obligation from matrix
    validation = str(node.get("validation_status", "unvalidated")).lower()
    val_rank = _VALIDATION_RANK.get(validation, 0)
    ep_level = _epistemic_level(node)
    obligation = _positive_obligation(sev_rank, val_rank, ep_level)

    # 6. Reinforcement boost
    reinforcement = int(node.get("reinforcement_count", 0))
    if obligation == ObligationLevel.MAY and reinforcement >= 10:
        obligation = ObligationLevel.SHOULD

    # 7. Belief mass boost
    ep_b = node.get("ep_b")
    if ep_b is not None and float(ep_b) >= 0.8:
        if obligation == ObligationLevel.MAY:
            obligation = ObligationLevel.SHOULD
        elif obligation == ObligationLevel.SHOULD:
            obligation = ObligationLevel.MUST

    return obligation


# =============================================================================
# Applicability checking
# =============================================================================


@dataclass(frozen=True)
class ApplicabilityResult:
    """Result of checking a node's applicability to the current query context."""

    applicable: bool
    confidence: float
    reason: str
    excluded_by: str = ""


def _tokenize(text: str) -> set[str]:
    """Extract lowercase keyword tokens (≥2 chars) from free-form text."""
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 2}


def check_applicability(
    node: dict[str, Any],
    ctx: Any,
) -> ApplicabilityResult:
    """Check if a node applies to the current query context.

    Uses keyword overlap between the node's applicability fields
    and the context's technologies + domains. Never hard-drops —
    returns ``applicable=False`` as metadata for the assembler.

    Parameters
    ----------
    node:
        Knowledge node dict.
    ctx:
        ExtractedContext with technologies, domains, raw_text.
    """
    layer = node.get("_layer", "")

    # L0 (Axioms) and L4 (Findings) — always applicable
    if layer in ("L0", "L4"):
        return ApplicabilityResult(applicable=True, confidence=1.0, reason="universal")

    # Build context keywords
    ctx_techs = {t.lower() for t in (getattr(ctx, "technologies", None) or [])}
    ctx_domains = {d.lower() for d in (getattr(ctx, "domains", None) or [])}
    ctx_keywords = ctx_techs | ctx_domains
    raw_text = str(getattr(ctx, "raw_text", "")).lower()
    if raw_text:
        ctx_keywords |= _tokenize(raw_text)

    # Get applicability fields (L2 uses when_to_use/when_not_to_use)
    when_applies = str(node.get("when_applies") or node.get("when_to_use") or "")
    when_not = str(node.get("when_not_applies") or node.get("when_not_to_use") or "")

    # 1. Check exclusions first
    if when_not:
        not_tokens = _tokenize(when_not)
        for kw in ctx_keywords:
            if kw in not_tokens:
                return ApplicabilityResult(
                    applicable=False,
                    confidence=0.8,
                    reason="excluded by when_not_applies",
                    excluded_by=kw,
                )

    # 2. Check positive applicability
    if not when_applies:
        # No constraint stated — assume generally applicable
        return ApplicabilityResult(applicable=True, confidence=0.5, reason="no constraint")

    applies_tokens = _tokenize(when_applies)
    if not applies_tokens:
        return ApplicabilityResult(applicable=True, confidence=0.5, reason="no constraint")

    matched = applies_tokens & ctx_keywords
    confidence = len(matched) / len(applies_tokens) if applies_tokens else 0.5

    if matched:
        return ApplicabilityResult(
            applicable=True,
            confidence=min(confidence + 0.3, 1.0),
            reason=f"matches: {', '.join(sorted(matched)[:3])}",
        )

    # 3. Technology cross-check (node's own tech tags)
    node_techs = set()
    tech_field = node.get("technologies")
    if isinstance(tech_field, dict):
        for vals in tech_field.values():
            if isinstance(vals, list):
                node_techs.update(v.lower() for v in vals)
    elif isinstance(tech_field, list):
        node_techs.update(t.lower() for t in tech_field)

    if node_techs and ctx_techs:
        tech_overlap = node_techs & ctx_techs
        if tech_overlap:
            return ApplicabilityResult(
                applicable=True,
                confidence=0.6,
                reason=f"tech match: {', '.join(sorted(tech_overlap)[:3])}",
            )

    # No match found — conservatively keep (might still be relevant by domain)
    return ApplicabilityResult(
        applicable=True,
        confidence=0.3,
        reason="no direct match, conservatively included",
    )


# =============================================================================
# Batch annotation
# =============================================================================


@dataclass
class GuardrailSummary:
    """Summary statistics from guardrail annotation."""

    total_nodes: int = 0
    must_count: int = 0
    must_not_count: int = 0
    should_count: int = 0
    should_not_count: int = 0
    may_count: int = 0
    inapplicable_count: int = 0
    inapplicable_ids: list[str] = field(default_factory=list)


_OBLIGATION_COUNTER_MAP = {
    ObligationLevel.MUST: "must_count",
    ObligationLevel.MUST_NOT: "must_not_count",
    ObligationLevel.SHOULD: "should_count",
    ObligationLevel.SHOULD_NOT: "should_not_count",
    ObligationLevel.MAY: "may_count",
}


def annotate_guardrails(
    candidates: list[dict[str, Any]],
    ctx: Any,
) -> tuple[list[dict[str, Any]], GuardrailSummary]:
    """Annotate candidates with obligation levels and applicability.

    Adds ``_obligation`` (str) and ``_applicability`` (dict) keys to each
    node dict. Non-destructive — existing keys are preserved.

    Parameters
    ----------
    candidates:
        Filtered candidate nodes from the assembly pipeline.
    ctx:
        ExtractedContext with technologies, domains, raw_text.

    Returns
    -------
    (annotated_candidates, summary) — same list mutated in place + stats.
    """
    summary = GuardrailSummary(total_nodes=len(candidates))

    for node in candidates:
        # Derive obligation
        obligation = derive_obligation(node)
        node["_obligation"] = obligation.value

        # Check applicability
        applicability = check_applicability(node, ctx)
        node["_applicability"] = {
            "applicable": applicability.applicable,
            "confidence": applicability.confidence,
            "reason": applicability.reason,
            "excluded_by": applicability.excluded_by,
        }

        # Update counters
        counter = _OBLIGATION_COUNTER_MAP.get(obligation)
        if counter:
            setattr(summary, counter, getattr(summary, counter) + 1)

        if not applicability.applicable:
            summary.inapplicable_count += 1
            nid = node.get("id", "")
            if nid:
                summary.inapplicable_ids.append(nid)

    return candidates, summary
