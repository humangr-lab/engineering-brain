"""Multi-signal relevance scorer for the Engineering Knowledge Brain.

Ranks knowledge nodes using 6 base weighted signals + 1 optional vector signal:
1. Technology match (0.28) — does the knowledge apply to the same tech?
2. Domain match (0.18) — is the knowledge in the same domain?
3. Severity (0.18) — how critical is this knowledge?
4. Reinforcement count (0.13) — how many times has this been confirmed?
5. Recency (0.13) — how recently was this knowledge relevant?
6. Confidence (0.10) — is this knowledge validated against authoritative sources?
7. Vector similarity (optional) — cosine similarity when vector adapter available.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import UTC, datetime
from typing import Any

from engineering_brain.core.config import BrainConfig

logger = logging.getLogger(__name__)

# Scoring constants
_REINFORCEMENT_CAP = 20.0  # Reinforcement count at which score saturates to 1.0
_GENERAL_DOMAIN_SCORE = 0.3  # Partial credit for general/untagged knowledge

# Lazy-loaded at module level (not per-call) to avoid import overhead in the scoring hot path
_get_decay_engine = None
_OpinionTuple = None


def _ensure_epistemic_imports() -> bool:
    """Lazy-load epistemic imports once at module level."""
    global _get_decay_engine, _OpinionTuple
    if _get_decay_engine is not None:
        return True
    try:
        from engineering_brain.epistemic.opinion import OpinionTuple
        from engineering_brain.epistemic.temporal import get_decay_engine

        _get_decay_engine = get_decay_engine
        _OpinionTuple = OpinionTuple
        return True
    except ImportError:
        return False


_SEVERITY_SCORES: dict[str, float] = {
    "critical": 1.0,
    "high": 0.8,
    "medium": 0.5,
    "low": 0.3,
}


def score_knowledge(
    node: dict[str, Any],
    query_technologies: list[str],
    query_domains: list[str],
    config: BrainConfig | None = None,
    calibrator: Any = None,
) -> float:
    """Score a knowledge node against a query context.

    Returns a float between 0.0 and 1.0.
    """
    cfg = config or BrainConfig()

    # 0. Soft-deleted nodes are invisible — zero-loss deprecation
    if node.get("deprecated"):
        return 0.0

    # 1. Technology match (hierarchy-aware via TagRegistry)
    node_techs = _get_list(node, "technologies") or _get_list(node, "languages")
    if query_technologies and node_techs:
        tech_overlap = _hierarchy_overlap_count(query_technologies, node_techs)
        tech_score = min(tech_overlap / max(len(query_technologies), 1), 1.0)
    elif not node_techs:
        tech_score = 0.5  # Technology-agnostic knowledge gets partial credit
    else:
        tech_score = 0.0

    # 2. Domain match (hierarchy-aware via TagRegistry)
    node_domains = _get_list(node, "domains") or [node.get("domain", "general")]
    if query_domains and node_domains:
        domain_overlap = _hierarchy_overlap_count(query_domains, node_domains)
        domain_score = min(domain_overlap / max(len(query_domains), 1), 1.0)
    elif not node_domains or node_domains == ["general"]:
        domain_score = _GENERAL_DOMAIN_SCORE
    else:
        domain_score = 0.0

    # 3. Severity
    severity = node.get("severity", "medium")
    severity_score = _SEVERITY_SCORES.get(severity, 0.5) if isinstance(severity, str) else 0.5

    # 4. Reinforcement count
    reinforcement = int(node.get("reinforcement_count", 0))
    reinforcement_score = min(reinforcement / _REINFORCEMENT_CAP, 1.0)

    # 5. Recency (with Hawkes decay if epistemic timestamps present)
    recency_score = _compute_recency(node)
    if (
        node.get("event_timestamps")
        and node.get("ep_b") is not None
        and _ensure_epistemic_imports()
    ):
        try:
            layer = _infer_layer(node)
            engine = _get_decay_engine(layer)
            op = _OpinionTuple(
                b=float(node["ep_b"]),
                d=float(node.get("ep_d", 0.0)),
                u=float(node.get("ep_u", 0.5)),
                a=float(node.get("ep_a", 0.5)),
            )
            now_ts = int(time.time())
            last_decay = int(node.get("last_decay_at", 0))
            decayed = engine.apply_decay(op, now_ts, last_decay, node["event_timestamps"])
            recency_score = max(recency_score, decayed.projected_probability)
        except Exception as exc:
            logger.debug("Hawkes decay computation failed (non-blocking): %s", exc)

    # 6. Confidence (from validation status or epistemic opinion)
    confidence_score = _compute_confidence(node)

    # 7. Epistemic scoring (if ep_* fields present)
    ep_b = node.get("ep_b")
    if ep_b is not None:
        ep_u = float(node.get("ep_u", 0.5))
        ep_a = float(node.get("ep_a", 0.5))
        projected = float(ep_b) + ep_a * ep_u
        uncertainty_penalty = ep_u * 0.3
        epistemic_score = max(0.0, projected - uncertainty_penalty)
        # Blend epistemic into confidence slot (epistemic supersedes heuristic)
        confidence_score = epistemic_score

    # 7b. Apply calibration if available
    if calibrator is not None:
        try:
            confidence_score = calibrator.calibrated_confidence(confidence_score)
        except Exception as exc:
            logger.debug("Confidence calibration failed (non-blocking): %s", exc)

    # 8. EigenTrust propagated score (if available)
    eigentrust_score = float(node.get("eigentrust_score", 0.5))

    # 9. Prediction accuracy modifier (rewards rules whose predictions come true)
    pred_tested = int(node.get("prediction_tested_count", 0))
    if pred_tested >= 3:
        pred_correct = int(node.get("prediction_success_count", 0))
        pred_accuracy = pred_correct / pred_tested
        if pred_accuracy > 0.8:
            confidence_score = min(confidence_score * 1.15, 1.0)
        elif pred_accuracy < 0.4:
            confidence_score *= 0.85

    # Weighted sum — normalize so weights always sum to 1.0
    _eigentrust_weight = 0.05
    w_sum = (
        cfg.weight_tech_match
        + cfg.weight_domain_match
        + cfg.weight_severity
        + cfg.weight_reinforcement
        + cfg.weight_recency
        + cfg.weight_confidence
        + _eigentrust_weight
    )
    total = (
        tech_score * cfg.weight_tech_match
        + domain_score * cfg.weight_domain_match
        + severity_score * cfg.weight_severity
        + reinforcement_score * cfg.weight_reinforcement
        + recency_score * cfg.weight_recency
        + confidence_score * cfg.weight_confidence
        + eigentrust_score * _eigentrust_weight
    ) / w_sum

    # 10. Vector similarity signal (7th scoring dimension, if available)
    vector_score = float(node.get("_vector_score", 0.0))
    if vector_score > 0:
        vec_weight = cfg.vector_score_weight  # default 0.15
        # Blend: reduce existing score proportionally to make room for vector signal
        total = total * (1.0 - vec_weight) + vector_score * vec_weight

    return min(max(total, 0.0), 1.0)


def rank_results(
    nodes: list[dict[str, Any]],
    query_technologies: list[str],
    query_domains: list[str],
    top_k: int = 10,
    config: BrainConfig | None = None,
    calibrator: Any = None,
    weight_optimizer: Any = None,
) -> list[dict[str, Any]]:
    """Score and rank a list of knowledge nodes, returning top-K.

    Optionally accepts a calibrator (ConfidenceCalibrator) and/or
    weight_optimizer (AdaptiveWeightOptimizer) for adaptive scoring.
    When weight_optimizer is provided, its adaptive weights replace the
    static defaults in the config for this ranking pass.
    """
    cfg = config

    # Apply adaptive weights from Thompson Sampling optimizer (Gap 4)
    if weight_optimizer:
        try:
            from dataclasses import replace as _replace

            adaptive = weight_optimizer.get_weights()
            base = cfg or BrainConfig()
            cfg = _replace(
                base,
                weight_tech_match=adaptive.get("tech_match", base.weight_tech_match),
                weight_domain_match=adaptive.get("domain_match", base.weight_domain_match),
                weight_severity=adaptive.get("severity", base.weight_severity),
                weight_reinforcement=adaptive.get("reinforcement", base.weight_reinforcement),
                weight_recency=adaptive.get("recency", base.weight_recency),
                weight_confidence=adaptive.get("confidence", base.weight_confidence),
            )
        except Exception as exc:
            logger.debug("Adaptive weight application failed (non-blocking): %s", exc)

    scored: list[tuple[float, dict[str, Any]]] = []
    for node in nodes:
        s = score_knowledge(node, query_technologies, query_domains, cfg, calibrator)
        node_with_score = {**node, "_relevance_score": s}
        scored.append((s, node_with_score))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [node for _, node in scored[:top_k]]


_VALIDATION_CONFIDENCE: dict[str, float] = {
    "human_verified": 1.0,
    "cross_checked": 0.7,
    "unvalidated": 0.3,
}


def _compute_confidence(node: dict[str, Any]) -> float:
    """Compute confidence score from validation_status.

    Validated nodes score higher; unvalidated nodes get 0.3.
    If the node has an explicit confidence field AND is validated,
    use the higher of the two.
    """
    status = str(node.get("validation_status", "unvalidated")).lower()
    base = _VALIDATION_CONFIDENCE.get(status, 0.3)
    explicit = node.get("confidence")
    if explicit is not None:
        try:
            return max(base, min(float(explicit), 1.0))
        except (ValueError, TypeError):
            pass
    return base


def _compute_recency(node: dict[str, Any]) -> float:
    """Compute recency score using smooth exponential decay.

    Uses half-life of 90 days: score = exp(-age * ln(2) / 90).
    Floor at 0.05 to avoid fully zeroing ancient-but-valid knowledge.
    """
    timestamp_str = node.get("last_violation") or node.get("timestamp") or node.get("created_at")
    if not timestamp_str:
        return 0.3  # No timestamp = moderate recency

    try:
        if isinstance(timestamp_str, datetime):
            ts = timestamp_str
        elif isinstance(timestamp_str, (int, float)):
            ts = datetime.fromtimestamp(timestamp_str, tz=UTC)
        else:
            ts = datetime.fromisoformat(str(timestamp_str).replace("Z", "+00:00"))
        age_days = max((datetime.now(UTC) - ts).days, 0)
        half_life = 90.0
        decay_rate = math.log(2) / half_life
        return max(math.exp(-decay_rate * age_days), 0.05)
    except (ValueError, TypeError, OSError):
        return 0.3


def _get_list(node: dict[str, Any], key: str) -> list[str]:
    """Safely get a list field from a node dict."""
    val = node.get(key)
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val:
        return [val]
    return []


def _hierarchy_overlap_count(query_tags: list[str], node_tags: list[str]) -> int:
    """Count hierarchy-aware overlap between query and node tag lists.

    Uses the global TagRegistry for ancestor/descendant matching.
    Falls back to exact matching if registry is empty or unavailable.
    """
    try:
        from engineering_brain.core.taxonomy import get_registry

        registry = get_registry()
        if registry.size > 0:
            return registry.overlap_count(query_tags, node_tags)
    except Exception as exc:
        logger.debug("TagRegistry overlap_count failed: %s", exc)
    # Fallback: exact match
    sq = {t.lower() for t in query_tags}
    sn = {t.lower() for t in node_tags}
    return len(sq & sn)


def _infer_layer(node: dict[str, Any]) -> str:
    """Infer cortical layer from node ID prefix."""
    nid = str(node.get("id", ""))
    if nid.startswith("AX-"):
        return "L0"
    if nid.startswith("P-"):
        return "L1"
    if nid.startswith("PAT-") or nid.startswith("CPAT-"):
        return "L2"
    return "L3"
