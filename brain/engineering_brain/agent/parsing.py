"""Shared LLM response parsing for claims, evidence, and confidence.

Used by both worker.py and orchestrator.py to avoid duplication.
"""

from __future__ import annotations

from typing import Any

from engineering_brain.agent.types import (
    ConfidenceLevel,
    EvidenceItem,
    KnowledgeClaim,
)


def parse_confidence(
    raw: Any,
    default: ConfidenceLevel = ConfidenceLevel.MODERATE,
) -> ConfidenceLevel:
    """Parse a confidence level string from LLM response.

    Handles case insensitivity and whitespace. Falls back to *default*
    on unrecognised values.
    """
    try:
        return ConfidenceLevel(str(raw).lower().strip())
    except ValueError:
        return default


def parse_evidence_item(raw: Any) -> EvidenceItem | None:
    """Parse a single evidence item (dict or string) from LLM response.

    Returns None for unrecognised types so callers can skip.
    """
    if isinstance(raw, dict):
        return EvidenceItem(
            node_id=raw.get("node_id", ""),
            content=raw.get("relevance", ""),
        )
    if isinstance(raw, str):
        return EvidenceItem(node_id=raw)
    return None


def parse_claims(raw_claims: Any) -> list[KnowledgeClaim]:
    """Parse a list of claim dicts from LLM JSON response.

    Skips non-dict entries, coerces string fields, normalises confidence.
    """
    if not isinstance(raw_claims, list):
        return []

    claims: list[KnowledgeClaim] = []
    for claim_data in raw_claims:
        if not isinstance(claim_data, dict):
            continue

        evidence: list[EvidenceItem] = []
        for ev in claim_data.get("evidence", []):
            item = parse_evidence_item(ev)
            if item is not None:
                evidence.append(item)

        claims.append(
            KnowledgeClaim(
                claim=str(claim_data.get("claim", "")),
                confidence=parse_confidence(claim_data.get("confidence", "moderate")),
                evidence=evidence,
                contradictions=[str(c) for c in claim_data.get("contradictions", [])],
                reasoning=str(claim_data.get("reasoning", "")),
            )
        )

    return claims
