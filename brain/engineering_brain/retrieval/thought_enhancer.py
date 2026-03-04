"""Thought Enhancement Layer — Epistemic Context Injection for Frontier Models.

Takes existing retrieval results and enriches them with:
- Confidence tiers (VALIDATED / PROBABLE / UNCERTAIN / CONTESTED)
- In-result contradiction detection (Dempster K between returned nodes)
- Query-relevant gap identification
- Provenance summaries
- Metacognitive summary (natural language: what brain knows/doesn't know)
- Epistemically-annotated formatted output

The enhanced output gives frontier models qualified knowledge with
uncertainty signals, so they can make categorically better decisions.
"""

from __future__ import annotations

import logging
from typing import Any

from engineering_brain.adapters.base import GraphAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.types import (
    ConfidenceTier,
    EnhancedKnowledgeResult,
    KnowledgeQuery,
    KnowledgeResult,
)
from engineering_brain.epistemic.conflict_resolution import (
    ConflictSeverity,
    classify_conflict,
    dempster_conflict,
)
from engineering_brain.epistemic.opinion import OpinionTuple
from engineering_brain.epistemic.provenance import ProvenanceChain
from engineering_brain.retrieval.context_extractor import ExtractedContext

logger = logging.getLogger(__name__)


class ThoughtEnhancer:
    """Enriches retrieval results with epistemic context for frontier models."""

    def __init__(self, graph: GraphAdapter, config: BrainConfig | None = None) -> None:
        self._graph = graph
        self._config = config or BrainConfig()

    def enhance(
        self,
        query: KnowledgeQuery,
        query_context: ExtractedContext,
        scored_nodes: list[dict[str, Any]],
        base_result: KnowledgeResult,
        budget_chars: int | None = None,
    ) -> EnhancedKnowledgeResult:
        """Enhance retrieval results with epistemic context."""
        # 1. Classify confidence tiers
        assessments = self._classify_confidence_tiers(scored_nodes)

        # 2. Detect in-result contradictions
        contradictions = self._detect_in_result_contradictions(scored_nodes)

        # 3. Mark contradicted nodes as CONTESTED
        contradicted_ids: set[str] = set()
        for c in contradictions:
            contradicted_ids.add(c["node_a_id"])
            contradicted_ids.add(c["node_b_id"])
        for a in assessments:
            if a["node_id"] in contradicted_ids:
                a["tier"] = ConfidenceTier.CONTESTED.value
                a["contradiction_ids"] = [
                    c["node_b_id"] if c["node_a_id"] == a["node_id"] else c["node_a_id"]
                    for c in contradictions
                    if a["node_id"] in (c["node_a_id"], c["node_b_id"])
                ]

        # 4. Identify query-relevant gaps
        gaps = self._identify_query_gaps(query_context, scored_nodes)

        # 5. Extract provenance summaries
        prov_summaries = self._extract_provenance_summaries(scored_nodes)
        for a in assessments:
            a["provenance_summary"] = prov_summaries.get(a["node_id"], "")

        # 6. Compute distribution
        dist: dict[str, int] = {}
        for a in assessments:
            tier = a["tier"]
            dist[tier] = dist.get(tier, 0) + 1

        # 7. Determine overall confidence
        if not assessments:
            overall = ""
        elif dist.get(ConfidenceTier.CONTESTED.value, 0) > len(assessments) * 0.3:
            overall = ConfidenceTier.CONTESTED.value
        elif dist.get(ConfidenceTier.VALIDATED.value, 0) >= len(assessments) * 0.7:
            overall = ConfidenceTier.VALIDATED.value
        elif dist.get(ConfidenceTier.VALIDATED.value, 0) >= len(assessments) * 0.4:
            overall = ConfidenceTier.PROBABLE.value
        else:
            overall = ConfidenceTier.UNCERTAIN.value

        # 8. Compose metacognitive summary
        meta = self._compose_metacognitive_summary(
            assessments,
            contradictions,
            gaps,
            base_result.total_nodes_queried,
        )

        # 9. Format enhanced output
        budget = budget_chars or self._config.enhanced_context_budget_chars
        enhanced_text = self._format_enhanced_output(
            assessments,
            contradictions,
            gaps,
            meta,
            scored_nodes,
            budget,
        )

        return EnhancedKnowledgeResult(
            base_result=base_result,
            assessments=assessments,
            contradictions=contradictions,
            gaps=gaps,
            metacognitive_summary=meta,
            enhanced_text=enhanced_text,
            confidence_distribution=dist,
            overall_confidence=overall,
            has_contradictions=len(contradictions) > 0,
            has_gaps=len(gaps) > 0,
        )

    # =========================================================================
    # Confidence Tier Classification
    # =========================================================================

    def _classify_confidence_tiers(
        self,
        nodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Classify each node into a confidence tier."""
        assessments = []
        for node in nodes:
            node_id = node.get("id", "")
            ep_b = node.get("ep_b")

            if ep_b is not None:
                b = float(ep_b)
                d = float(node.get("ep_d", 0.0))
                u = float(node.get("ep_u", 0.5))
                a = float(node.get("ep_a", 0.5))
                projected = b + a * u
                evidence_strength = 1.0 - u
                eigentrust = float(node.get("eigentrust_score", 0.5))
                validation = str(node.get("validation_status", "unvalidated"))
                tier = self._compute_tier(projected, evidence_strength, eigentrust, validation, d)
            else:
                confidence = float(node.get("confidence", 0.5))
                validation = str(node.get("validation_status", "unvalidated"))
                projected = confidence
                evidence_strength = 0.0
                eigentrust = float(node.get("eigentrust_score", 0.5))
                tier = self._compute_tier_fallback(confidence, validation)

            assessments.append(
                {
                    "node_id": node_id,
                    "tier": tier.value,
                    "projected_probability": round(projected, 3),
                    "evidence_strength": round(evidence_strength, 3),
                    "eigentrust_score": round(eigentrust, 3),
                    "validation_status": validation,
                    "provenance_summary": "",
                    "contradiction_ids": [],
                }
            )
        return assessments

    def _compute_tier(
        self,
        projected: float,
        evidence_strength: float,
        eigentrust: float,
        validation: str,
        disbelief: float,
    ) -> ConfidenceTier:
        """Decision tree for epistemic-aware tier classification."""
        if disbelief > 0.3:
            return ConfidenceTier.CONTESTED
        if (
            validation in ("cross_checked", "human_verified")
            and projected >= 0.7
            and evidence_strength >= 0.5
            and eigentrust >= 0.4
        ):
            return ConfidenceTier.VALIDATED
        if projected >= 0.6 and evidence_strength >= 0.3:
            return ConfidenceTier.PROBABLE
        return ConfidenceTier.UNCERTAIN

    def _compute_tier_fallback(self, confidence: float, validation: str) -> ConfidenceTier:
        """Fallback for nodes without epistemic data."""
        if validation in ("cross_checked", "human_verified") and confidence >= 0.7:
            return ConfidenceTier.VALIDATED
        if confidence >= 0.5:
            return ConfidenceTier.PROBABLE
        return ConfidenceTier.UNCERTAIN

    # =========================================================================
    # In-Result Contradiction Detection
    # =========================================================================

    def _detect_in_result_contradictions(
        self,
        nodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Detect contradictions between nodes in the result set."""
        result_ids = {n.get("id", "") for n in nodes if n.get("id")}
        node_map = {n.get("id", ""): n for n in nodes if n.get("id")}
        contradictions: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()

        for node in nodes:
            node_id = node.get("id", "")
            if not node_id:
                continue

            edges = self._graph.get_edges(node_id=node_id, edge_type="CONFLICTS_WITH")
            for edge in edges:
                other_id = edge["to_id"] if edge["from_id"] == node_id else edge["from_id"]
                if other_id not in result_ids:
                    continue

                pair = tuple(sorted([node_id, other_id]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                other_node = node_map.get(other_id)
                if other_node is None:
                    continue

                op_a = self._node_to_opinion(node)
                op_b = self._node_to_opinion(other_node)

                if op_a is None or op_b is None:
                    contradictions.append(
                        {
                            "node_a_id": node_id,
                            "node_b_id": other_id,
                            "conflict_k": 0.5,
                            "severity": "moderate",
                            "description": f"'{self._node_text(node)[:60]}' conflicts with '{self._node_text(other_node)[:60]}'",
                        }
                    )
                    continue

                k = dempster_conflict(op_a, op_b)
                severity = classify_conflict(k)
                if severity == ConflictSeverity.NONE:
                    continue

                text_a = self._node_text(node)[:60]
                text_b = self._node_text(other_node)[:60]
                if k >= 0.7:
                    desc = f"STRONG CONFLICT: '{text_a}' vs '{text_b}' (K={k:.2f})"
                else:
                    desc = f"Tension: '{text_a}' vs '{text_b}' (K={k:.2f})"

                contradictions.append(
                    {
                        "node_a_id": node_id,
                        "node_b_id": other_id,
                        "conflict_k": round(k, 3),
                        "severity": severity.value,
                        "description": desc,
                    }
                )

        return contradictions

    # =========================================================================
    # Query-Relevant Gap Identification
    # =========================================================================

    def _identify_query_gaps(
        self,
        ctx: ExtractedContext,
        nodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Identify knowledge gaps relevant to the current query."""
        gaps: list[dict[str, Any]] = []

        # 1. Missing technology coverage
        returned_techs: set[str] = set()
        for node in nodes:
            for t in node.get("technologies") or node.get("languages") or []:
                returned_techs.add(t.lower())
        for tech in ctx.technologies:
            if tech.lower() not in returned_techs:
                gaps.append(
                    {
                        "gap_type": "missing_technology",
                        "description": f"No knowledge found for technology '{tech}'",
                        "severity": 0.8,
                        "suggested_action": f"Brain has no rules for {tech}. Use general principles with caution.",
                    }
                )

        # 2. Missing layer coverage
        layers_present = {n.get("_layer", "") for n in nodes}
        if nodes and "L1" not in layers_present:
            gaps.append(
                {
                    "gap_type": "missing_principles",
                    "description": "No guiding principles found for this query",
                    "severity": 0.5,
                    "suggested_action": "Rely on general engineering principles; brain lacks specific WHY guidance here.",
                }
            )

        # 3. High aggregate uncertainty
        uncertainties = [float(n["ep_u"]) for n in nodes if n.get("ep_u") is not None]
        if uncertainties:
            avg_u = sum(uncertainties) / len(uncertainties)
            if avg_u > 0.5:
                gaps.append(
                    {
                        "gap_type": "high_aggregate_uncertainty",
                        "description": f"Average uncertainty is {avg_u:.0%} across returned knowledge",
                        "severity": round(avg_u, 2),
                        "suggested_action": "Brain is uncertain about this topic. Cross-reference with external docs.",
                    }
                )

        # 4. Unsupported rules (no EVIDENCED_BY edges)
        rules = [n for n in nodes if n.get("_layer") == "L3"]
        if rules:
            unsupported = 0
            for rule in rules:
                rid = rule.get("id", "")
                if rid:
                    ev_edges = self._graph.get_edges(
                        node_id=rid, edge_type="EVIDENCED_BY", direction="outgoing"
                    )
                    if not ev_edges:
                        unsupported += 1
            if unsupported > len(rules) * 0.5:
                gaps.append(
                    {
                        "gap_type": "unsupported_rules",
                        "description": f"{unsupported}/{len(rules)} returned rules have no supporting evidence",
                        "severity": 0.6,
                        "suggested_action": "Several rules lack concrete evidence. Treat as heuristic guidance.",
                    }
                )

        # 5. Missing domain coverage
        returned_domains: set[str] = set()
        for node in nodes:
            for d in node.get("domains") or []:
                returned_domains.add(d.lower())
        for domain in ctx.domains:
            if domain.lower() not in returned_domains and domain != "general":
                gaps.append(
                    {
                        "gap_type": "missing_domain",
                        "description": f"No knowledge found in domain '{domain}'",
                        "severity": 0.5,
                        "suggested_action": f"Brain has limited knowledge in {domain} for this query.",
                    }
                )

        return gaps

    # =========================================================================
    # Provenance Extraction
    # =========================================================================

    def _extract_provenance_summaries(
        self,
        nodes: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Extract provenance summary strings for each node."""
        summaries: dict[str, str] = {}
        for node in nodes:
            node_id = node.get("id", "")
            prov_data = node.get("provenance", [])

            if isinstance(prov_data, list) and prov_data:
                chain = ProvenanceChain.from_list(prov_data)
                summaries[node_id] = chain.summary()
            else:
                validation = node.get("validation_status", "unvalidated")
                if validation != "unvalidated":
                    summaries[node_id] = f"status: {validation}"
                else:
                    summaries[node_id] = "no provenance"

        return summaries

    # =========================================================================
    # Metacognitive Summary
    # =========================================================================

    def _llm_metacognitive_summary(
        self,
        tier_dist: dict,
        contradictions: list,
        gaps: list,
        overall: str,
    ) -> str | None:
        """LLM-generated metacognitive commentary. Returns None on failure."""
        from engineering_brain.llm_helpers import brain_llm_call, is_llm_enabled

        if not is_llm_enabled("BRAIN_LLM_METACOGNITION"):
            return None
        tiers = ", ".join(f"{v} {k}" for k, v in tier_dist.items() if v > 0)
        high_gaps = [g.get("description", "") for g in gaps if g.get("severity", 0) >= 0.7]
        system = (
            "Write a metacognitive summary for an engineering knowledge graph query. "
            "Tell the developer what the brain knows, how confident it is, and "
            "what to watch out for. 2-3 sentences max. Be direct and specific."
        )
        user = (
            f"Knowledge tiers: {tiers or 'none'}\n"
            f"Contradictions: {len(contradictions)}\n"
            f"Critical gaps: {'; '.join(high_gaps[:3]) if high_gaps else 'none'}\n"
            f"Overall confidence: {overall or 'unknown'}"
        )
        result = brain_llm_call(system, user, max_tokens=200)
        return result if result and len(result) >= 30 else None

    def _compose_metacognitive_summary(
        self,
        assessments: list[dict[str, Any]],
        contradictions: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        total_queried: int,
    ) -> str:
        """Compose natural language summary of what the brain knows/doesn't know."""
        n = len(assessments)
        if n == 0:
            return (
                "The brain has no relevant knowledge for this query. "
                "Proceed with general engineering principles and external documentation."
            )

        # Distribution (computed early for LLM path)
        dist: dict[str, int] = {}
        for a in assessments:
            t = a["tier"]
            dist[t] = dist.get(t, 0) + 1

        # Try LLM-generated summary first
        try:
            validated_pct = dist.get("validated", 0) / max(n, 1)
            contested_pct = dist.get("contested", 0) / max(n, 1)
            if contested_pct > 0.3:
                _overall = "contested"
            elif validated_pct >= 0.7:
                _overall = "high"
            elif validated_pct >= 0.4:
                _overall = "moderate"
            else:
                _overall = "low"
            llm_summary = self._llm_metacognitive_summary(dist, contradictions, gaps, _overall)
            if llm_summary:
                return llm_summary
        except Exception as exc:
            logger.debug("LLM metacognitive summary failed: %s", exc)

        parts = [f"The brain returned {n} knowledge nodes (from {total_queried} candidates)."]

        tier_parts = [f"{count} {tier.upper()}" for tier, count in sorted(dist.items())]
        parts.append(f"Confidence: {', '.join(tier_parts)}.")

        # Contradictions
        if contradictions:
            high = [c for c in contradictions if c["severity"] in ("high", "extreme")]
            if high:
                parts.append(
                    f"WARNING: {len(high)} strong contradiction(s) detected. "
                    "Review conflicting rules carefully."
                )
            else:
                parts.append(f"Note: {len(contradictions)} mild tension(s) between rules.")

        # Gaps
        high_gaps = [g for g in gaps if g["severity"] >= 0.7]
        if high_gaps:
            gap_descs = [g["description"] for g in high_gaps[:3]]
            parts.append(f"Gaps: {'; '.join(gap_descs)}.")

        # Overall
        validated_pct = dist.get("validated", 0) / max(n, 1)
        contested_pct = dist.get("contested", 0) / max(n, 1)
        if contested_pct > 0.3:
            parts.append("Overall: CONTESTED topic. Multiple conflicting views exist.")
        elif validated_pct >= 0.7:
            parts.append("Overall: HIGH CONFIDENCE. Most knowledge is validated.")
        elif validated_pct >= 0.4:
            parts.append("Overall: MODERATE CONFIDENCE. Mix of validated and uncertain knowledge.")
        else:
            parts.append("Overall: LOW CONFIDENCE. Use cautiously and cross-reference.")

        return " ".join(parts)

    # =========================================================================
    # Enhanced Formatting
    # =========================================================================

    def _format_enhanced_output(
        self,
        assessments: list[dict[str, Any]],
        contradictions: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        metacognitive_summary: str,
        scored_nodes: list[dict[str, Any]],
        budget_chars: int,
    ) -> str:
        """Format epistemically-annotated output for frontier model consumption."""
        sections: list[str] = []

        # Section 1: Brain Assessment
        sections.append(f"## Brain Assessment\n{metacognitive_summary}")

        # Section 2: Contradictions
        if contradictions:
            lines = ["## Contradictions Detected"]
            for c in contradictions:
                lines.append(f"- [{c['severity'].upper()}] {c['description']}")
            sections.append("\n".join(lines))

        # Section 3: Knowledge by tier
        assessment_map = {a["node_id"]: a for a in assessments}
        tier_nodes: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        for node in scored_nodes:
            nid = node.get("id", "")
            assessment = assessment_map.get(nid)
            if assessment:
                tier = assessment["tier"]
                tier_nodes.setdefault(tier, []).append((node, assessment))

        for tier_name in ["validated", "probable", "uncertain", "contested"]:
            items = tier_nodes.get(tier_name, [])
            if not items:
                continue
            lines = [f"## [{tier_name.upper()}] Knowledge"]
            for node, assessment in items:
                tag = self._format_node_tag(assessment)
                text = self._format_node_content(node)
                lines.append(f"- {tag} {text}")
            sections.append("\n".join(lines))

        # Section 4: Gaps
        if gaps:
            lines = ["## Knowledge Gaps"]
            for g in gaps:
                lines.append(f"- {g['description']}. {g['suggested_action']}")
            sections.append("\n".join(lines))

        full_text = "\n\n".join(sections)

        # Budget enforcement: trim progressively
        if len(full_text) > budget_chars:
            full_text = self._trim_to_budget(full_text, sections, budget_chars)

        return full_text

    def _format_node_tag(self, assessment: dict[str, Any]) -> str:
        """Format confidence tag: [VALIDATED|P=85%|E=72%]"""
        parts = [assessment["tier"].upper()]
        parts.append(f"P={assessment['projected_probability']:.0%}")
        if assessment["evidence_strength"] > 0:
            parts.append(f"E={assessment['evidence_strength']:.0%}")
        vs = assessment.get("validation_status", "")
        if vs and vs != "unvalidated":
            parts.append(vs.upper().replace("_", "-"))
        if assessment.get("contradiction_ids"):
            parts.append(f"CONFLICTS:{len(assessment['contradiction_ids'])}")
        return f"[{'|'.join(parts)}]"

    def _format_node_content(self, node: dict[str, Any]) -> str:
        """Format node content: text + WHY + HOW (compact)."""
        text = self._node_text(node)
        parts = [text]

        why = node.get("why", "")
        if why:
            parts.append(f"WHY: {why[:120]}")

        how = node.get("how_to_do_right") or node.get("how_to_apply") or ""
        if how:
            parts.append(f"DO: {how[:120]}")

        severity = node.get("severity", "")
        if severity:
            parts[0] = f"[{severity.upper()}] {parts[0]}"

        return " — ".join(parts)

    def _trim_to_budget(
        self,
        full_text: str,
        sections: list[str],
        budget: int,
    ) -> str:
        """Progressive trimming: drop UNCERTAIN, then gaps, then provenance."""
        # Try without UNCERTAIN section
        trimmed = [s for s in sections if "[UNCERTAIN]" not in s]
        candidate = "\n\n".join(trimmed)
        if len(candidate) <= budget:
            return candidate

        # Try without gaps
        trimmed = [s for s in trimmed if "Knowledge Gaps" not in s]
        candidate = "\n\n".join(trimmed)
        if len(candidate) <= budget:
            return candidate

        # Hard truncate
        return candidate[:budget]

    # =========================================================================
    # Helpers
    # =========================================================================

    def _node_to_opinion(self, node: dict[str, Any]) -> OpinionTuple | None:
        """Extract OpinionTuple from node, or None if no epistemic data."""
        ep_b = node.get("ep_b")
        if ep_b is None:
            return None
        return OpinionTuple(
            b=float(ep_b),
            d=float(node.get("ep_d", 0.0)),
            u=float(node.get("ep_u", 0.5)),
            a=float(node.get("ep_a", 0.5)),
        )

    def _node_text(self, node: dict[str, Any]) -> str:
        """Get primary text content from a node."""
        return (
            node.get("text")
            or node.get("name")
            or node.get("statement")
            or node.get("description")
            or node.get("id", "")
        )
