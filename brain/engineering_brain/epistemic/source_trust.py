"""Source trust mapping — converts Source objects to OpinionTuples.

Each SourceType has a base trust weight. Special handling for:
- StackOverflow: trust scales with vote_count via sigmoid
- CVE: trust scales with cvss_score
- All: verified flag adds +0.05 bonus (capped at 0.99)
"""

from __future__ import annotations

import math
from typing import Any

from engineering_brain.epistemic.opinion import OpinionTuple


def _sigmoid(x: float) -> float:
    if x > 500:
        return 1.0
    if x < -500:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


_MAX_TRUST = 0.95  # Trust ceiling — even the best source isn't 100% certain
_ACCEPTED_ANSWER_BONUS = 0.15  # StackOverflow accepted answer trust boost
_CVSS_TRUST_SCALAR = 0.95  # CVSS score → trust multiplier (cvss/10 * scalar)

# Base trust weights by source type (ordered by authority)
SOURCE_TRUST_MAP: dict[str, float] = {
    "official_docs": 0.90,
    "security_cve": 0.95,
    "rfc_standard": 0.95,
    "stackoverflow": 0.60,
    "mdn": 0.85,
    "github_advisory": 0.90,
    "owasp": 0.90,
    "package_registry": 0.70,
    "human_curated": 0.85,
}


def source_to_opinion(source: Any, polarity: str = "positive") -> OpinionTuple:
    """Convert a Source object (or dict) to an OpinionTuple.

    Source existence = positive evidence for the claim.
    Trust level determines how much belief mass to assign.
    """
    # Handle both Source objects and dicts
    if isinstance(source, dict):
        source_type = source.get("source_type", "")
        vote_count = source.get("vote_count")
        is_accepted = source.get("is_accepted_answer", False)
        cvss_score = source.get("cvss_score")
        verified = source.get("verified", False)
    else:
        source_type = getattr(source, "source_type", "")
        vote_count = getattr(source, "vote_count", None)
        is_accepted = getattr(source, "is_accepted_answer", False)
        cvss_score = getattr(source, "cvss_score", None)
        verified = getattr(source, "verified", False)

    # Handle enum values
    st = source_type.value if hasattr(source_type, "value") else str(source_type)

    # Compute trust based on source type
    if st == "stackoverflow":
        votes = int(vote_count) if vote_count is not None else 0
        base = SOURCE_TRUST_MAP.get("stackoverflow", 0.60)
        trust = max(base, base * _sigmoid(votes / 20.0))
        if is_accepted:
            trust = min(_MAX_TRUST, trust + _ACCEPTED_ANSWER_BONUS)
    elif st == "security_cve" and cvss_score is not None:
        trust = _CVSS_TRUST_SCALAR * (float(cvss_score) / 10.0)
    else:
        trust = SOURCE_TRUST_MAP.get(st, 0.50)

    # Verified bonus
    if verified:
        trust = min(0.99, trust + 0.05)

    # Clamp
    trust = max(0.01, min(0.99, trust))

    if polarity == "negative":
        return OpinionTuple(b=0.0, d=trust, u=1.0 - trust, a=0.5)
    return OpinionTuple(b=trust, d=0.0, u=1.0 - trust, a=0.5)
