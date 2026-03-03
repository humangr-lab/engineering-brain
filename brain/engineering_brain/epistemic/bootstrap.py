"""Bootstrap epistemic opinions for all Engineering Brain nodes.

Reads the validation cache (4,110+ real source references) and
computes initial OpinionTuples via CBF fusion of layer priors + sources.
Optionally runs contradiction detection, trust propagation, and gap analysis.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engineering_brain.epistemic.layer_opinions import bootstrap_opinion
from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.provenance import ProvenanceChain, ProvenanceRecord

logger = logging.getLogger(__name__)

# Node ID prefix → cortical layer mapping
_PREFIX_TO_LAYER: dict[str, str] = {
    "AX-": "L0",
    "P-": "L1",
    "PAT-": "L2",
    "CR-": "L3",
}


def _node_layer(node_id: str) -> str:
    """Infer cortical layer from node ID prefix."""
    for prefix, layer in _PREFIX_TO_LAYER.items():
        if node_id.startswith(prefix):
            return layer
    return "L3"  # default for unknown


def _load_validation_cache(cache_path: str | Path) -> dict[str, Any]:
    """Load the validation cache JSON file."""
    path = Path(cache_path)
    if not path.exists():
        logger.warning("Validation cache not found: %s", path)
        return {}

    cache_file = path / "validation_cache.json" if path.is_dir() else path
    if not cache_file.exists():
        logger.warning("Validation cache file not found: %s", cache_file)
        return {}

    with open(cache_file) as f:
        return json.load(f)


def bootstrap_all_nodes(
    graph_adapter: Any,
    cache_path: str | Path,
    enable_contradiction_detection: bool = False,
    enable_trust_propagation: bool = False,
    enable_gap_analysis: bool = False,
) -> dict[str, Any]:
    """Bootstrap epistemic opinions for all nodes in the graph.

    For each node:
    1. Determine cortical layer from ID prefix
    2. Get layer prior (L0=near-dogmatic, L5=vacuous)
    3. Look up sources from validation cache
    4. CBF-fuse prior with source opinions
    5. Write ep_b, ep_d, ep_u, ep_a to the node
    6. Update confidence = projected_probability (backward compat)
    7. Record provenance for auditability

    Optionally runs post-bootstrap analysis:
    - Contradiction detection (Dempster K for CONFLICTS_WITH edges)
    - Trust propagation (EigenTrust over graph topology)
    - Gap analysis (what the brain doesn't know)

    Returns:
        Stats dict: {bootstrapped, skipped, total_sources_used, ...}
    """
    cache = _load_validation_cache(cache_path)
    all_nodes = graph_adapter.get_all_nodes()

    bootstrapped = 0
    skipped = 0
    total_sources = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for node in all_nodes:
        node_id = node.get("id", "")
        if not node_id:
            skipped += 1
            continue

        layer = _node_layer(node_id)

        # Look up sources from validation cache
        cache_key = f"v1:{node_id}"
        cache_entry = cache.get(cache_key, {})
        sources = cache_entry.get("sources", [])
        total_sources += len(sources)

        # Compute opinion via CBF fusion
        opinion = bootstrap_opinion(layer, sources)

        # Build provenance record
        prov_inputs: list[dict[str, Any]] = [{"source": "layer_prior", "layer": layer}]
        for s in sources[:5]:
            prov_inputs.append({"source": s.get("source_type", "unknown"), "url": s.get("url", "")})
        prov_record = ProvenanceRecord(
            operation="bootstrap",
            timestamp=now_iso,
            inputs=tuple(prov_inputs),
            output={"b": opinion.b, "d": opinion.d, "u": opinion.u, "a": opinion.a},
            reason=f"bootstrapped from {layer} prior + {len(sources)} sources",
        )

        # Get existing provenance or start fresh
        existing_prov = node.get("provenance", [])
        if not isinstance(existing_prov, list):
            existing_prov = []
        chain = ProvenanceChain.from_list(existing_prov)
        chain.add(prov_record)

        # Determine node label for graph adapter
        label = _node_label(node_id)

        # Write back to graph
        graph_adapter.add_node(
            label,
            node_id,
            {
                **node,
                "ep_b": opinion.b,
                "ep_d": opinion.d,
                "ep_u": opinion.u,
                "ep_a": opinion.a,
                "confidence": opinion.projected_probability,
                "provenance": chain.to_list(),
            },
        )
        bootstrapped += 1

    logger.info(
        "Bootstrapped %d nodes (%d skipped, %d total sources)",
        bootstrapped, skipped, total_sources,
    )

    result: dict[str, Any] = {
        "bootstrapped": bootstrapped,
        "skipped": skipped,
        "total_sources_used": total_sources,
    }

    # Post-bootstrap: contradiction detection
    if enable_contradiction_detection:
        try:
            from engineering_brain.epistemic.contradiction import ContradictionDetector
            detector = ContradictionDetector(graph_adapter)
            reports = detector.detect_all()
            result["contradiction_reports"] = len(reports)
            logger.info("Contradiction detection: %d reports", len(reports))
        except Exception as e:
            logger.warning("Contradiction detection failed: %s", e)
            result["contradiction_reports"] = 0

    # Post-bootstrap: trust propagation
    if enable_trust_propagation:
        try:
            from engineering_brain.epistemic.trust_propagation import EigenTrustEngine
            engine = EigenTrustEngine()
            scores = engine.compute(graph_adapter)
            # Store scores on nodes
            for nid, score in scores.items():
                n = graph_adapter.get_node(nid)
                if n is not None:
                    graph_adapter.add_node(
                        _node_label(nid), nid,
                        {**n, "eigentrust_score": score},
                    )
            result["trust_scores"] = len(scores)
            logger.info("Trust propagation: %d nodes scored", len(scores))
        except Exception as e:
            logger.warning("Trust propagation failed: %s", e)
            result["trust_scores"] = 0

    # Post-bootstrap: gap analysis
    if enable_gap_analysis:
        try:
            from engineering_brain.epistemic.gap_analysis import GapAnalyzer
            analyzer = GapAnalyzer(graph_adapter)
            gaps = analyzer.analyze()
            result["gaps"] = len(gaps)
            logger.info("Gap analysis: %d gaps found", len(gaps))
        except Exception as e:
            logger.warning("Gap analysis failed: %s", e)
            result["gaps"] = 0

    return result


def _node_label(node_id: str) -> str:
    """Infer graph label from node ID prefix."""
    if node_id.startswith("AX-"):
        return "Axiom"
    if node_id.startswith("P-"):
        return "Principle"
    if node_id.startswith("PAT-"):
        return "Pattern"
    if node_id.startswith("CR-"):
        return "Rule"
    if node_id.startswith("tech:"):
        return "Technology"
    if node_id.startswith("domain:"):
        return "Domain"
    return "Rule"
