"""Reasoning Engine — structured epistemic reasoning for ERG.

Builds reasoning chains with causal edges (PREREQUISITE, DEEPENS, ALTERNATIVE),
confidence tiers per step, cross-chain synthesis via Dempster-Shafer theory,
contradiction detection, and gap analysis.

Zero LLM calls — everything is graph traversal + scoring + epistemic math.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import yaml

from engineering_brain.adapters.base import CacheAdapter, GraphAdapter, VectorAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.types import (
    BrainProfile,
    ChainResult,
    Pack,
    ReasoningResult,
    ReasoningStep,
    ReasoningTemplate,
)
from engineering_brain.retrieval.context_extractor import ExtractedContext
from engineering_brain.retrieval.pack_manager import PackManager, _infer_layer
from engineering_brain.retrieval.scorer import rank_results, score_knowledge

logger = logging.getLogger(__name__)


def _hierarchy_match_tags(a: list[str], b: list[str]) -> bool:
    """Check if any tag in 'a' hierarchy-matches any tag in 'b'.

    Uses the TagRegistry for ancestor/descendant matching when available,
    falling back to exact set intersection.
    """
    if not a or not b:
        return False
    try:
        from engineering_brain.core.taxonomy import get_registry
        registry = get_registry()
        if registry.size > 0:
            return registry.match_flat(a, b)
    except Exception:
        pass
    return bool({x.lower() for x in a} & {x.lower() for x in b})


# Default template directory
_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "templates",
)

# Hardcoded fallback template (used when no YAML templates exist)
_DEFAULT_TEMPLATE = ReasoningTemplate(
    id="T-LINEAR-DEFAULT",
    name="Default Linear Reasoning",
    applicable_when={},
    steps=[
        ReasoningStep(
            order=1,
            description="Gather guiding principles",
            operation="activate",
            node_filter={"layer": "L1"},
            max_nodes=3,
            edge_to_next="TRIGGERS",
        ),
        ReasoningStep(
            order=2,
            description="Find technology-specific rules",
            operation="activate",
            node_filter={"layer": "L3", "match_query_tech": True},
            max_nodes=10,
            edge_to_next="DEEPENS",
        ),
        ReasoningStep(
            order=3,
            description="Synthesize with confidence assessment",
            operation="score",
            node_filter={},
            max_nodes=0,
        ),
    ],
)


class ReasoningEngine:
    """Orchestrates structured epistemic reasoning through packs, templates, and chains."""

    def __init__(
        self,
        graph: GraphAdapter,
        vector: VectorAdapter | None = None,
        cache: CacheAdapter | None = None,
        config: BrainConfig | None = None,
        query_router: Any = None,
    ) -> None:
        self._graph = graph
        self._vector = vector
        self._cache = cache
        self._config = config or BrainConfig()
        self._query_router = query_router
        self._pack_manager = PackManager(graph, vector, self._config, query_router)
        self._templates = self._load_templates()

    # ------------------------------------------------------------------
    # Public: reason()
    # ------------------------------------------------------------------

    def reason(
        self,
        ctx: ExtractedContext,
        packs: list[Pack] | None = None,
        profile: BrainProfile | str | None = None,
        max_chains: int | None = None,
    ) -> ReasoningResult:
        """Main entry point: query -> packs -> template -> chains -> synthesis -> output."""
        start = time.time()
        max_ch = max_chains or self._config.reasoning_max_chains

        # Resolve string profile to BrainProfile
        if isinstance(profile, str):
            from engineering_brain.retrieval.brain_profiles import load_profile
            profile = load_profile(profile)

        # 1. Select or generate packs
        if packs:
            selected_packs = self._pack_manager.select_packs(ctx, packs, profile, top_n=max_ch)
        else:
            auto_packs = self._pack_manager.auto_generate_packs()
            selected_packs = self._pack_manager.select_packs(ctx, auto_packs, profile, top_n=max_ch)

        if not selected_packs:
            return ReasoningResult(
                formatted_text="",
                reasoning_time_ms=(time.time() - start) * 1000,
            )

        # 2. Select template
        template = self._select_template(ctx, profile)

        # 3. Collect all nodes from selected packs
        pack_nodes = self._collect_pack_nodes(selected_packs)
        total_in_packs = len(pack_nodes)

        # 4. Execute chains (1 chain per pack)
        chains: list[ChainResult] = []
        for pack in selected_packs:
            pack_node_pool = [n for n in pack_nodes if n.get("id", "") in set(pack.node_ids)]
            chain = self._execute_chain(pack.description or pack.id, template, pack_node_pool, ctx)
            chains.append(chain)

        # 5. Cross-chain synthesis
        overall_opinion, cross_contradictions = self._synthesize_chains(chains)

        # 6. Detect gaps
        all_activated = []
        for ch in chains:
            for step in ch.steps:
                all_activated.extend(step.get("nodes", []))
        gaps = self._detect_gaps(ctx, all_activated)

        # 7. Collect all contradictions
        all_contradictions = list(cross_contradictions)
        for ch in chains:
            all_contradictions.extend(ch.contradictions)

        # 8. Confidence distribution
        conf_dist = self._confidence_distribution(chains)

        # 9. Metacognitive summary
        meta = self._metacognitive_summary(chains, all_contradictions, gaps, conf_dist)

        # 10. Format output
        formatted = self._format_output(chains, overall_opinion, all_contradictions, gaps, meta)

        elapsed_ms = (time.time() - start) * 1000
        nodes_activated = sum(ch.nodes_activated for ch in chains)

        return ReasoningResult(
            chains=chains,
            overall_opinion=overall_opinion,
            confidence_distribution=conf_dist,
            contradictions=all_contradictions,
            gaps=gaps,
            metacognitive_summary=meta,
            formatted_text=formatted,
            packs_used=[p.id for p in selected_packs],
            template_used=template.id,
            profile_used=profile.id if profile else None,
            nodes_activated=nodes_activated,
            total_nodes_in_packs=total_in_packs,
            reasoning_time_ms=round(elapsed_ms, 1),
        )

    # ------------------------------------------------------------------
    # Chain execution
    # ------------------------------------------------------------------

    def _execute_chain(
        self,
        chain_name: str,
        template: ReasoningTemplate,
        node_pool: list[dict[str, Any]],
        ctx: ExtractedContext,
    ) -> ChainResult:
        """Execute a reasoning chain by stepping through a template."""
        steps: list[dict[str, Any]] = []
        chain_opinions: list[Any] = []
        total_activated = 0
        chain_contradictions: list[dict[str, Any]] = []

        for tmpl_step in template.steps:
            if tmpl_step.operation == "score":
                # Synthesis step — no new nodes, just aggregation
                steps.append({
                    "order": tmpl_step.order,
                    "description": tmpl_step.description,
                    "operation": "score",
                    "nodes": [],
                    "opinion": None,
                    "tier": "",
                })
                continue

            # Filter nodes from pool
            filtered = self._filter_nodes(node_pool, tmpl_step.node_filter, ctx)

            # Score and rank
            max_n = tmpl_step.max_nodes or self._config.reasoning_max_nodes_per_step
            scored = rank_results(
                filtered,
                query_technologies=ctx.technologies,
                query_domains=ctx.domains,
                top_k=max_n,
                config=self._config,
            )

            # Classify confidence for activated nodes
            step_nodes: list[dict[str, Any]] = []
            for node in scored:
                tier = self._classify_node_tier(node)
                step_nodes.append({
                    "id": node.get("id", ""),
                    "text": self._node_text(node)[:120],
                    "tier": tier,
                    "score": round(node.get("_relevance_score", 0), 3),
                    "layer": _infer_layer(str(node.get("id", ""))),
                })

            # Compute step opinion from node epistemic data
            step_opinion = self._compute_step_opinion(scored)
            if step_opinion:
                chain_opinions.append(step_opinion)

            # Detect intra-step contradictions
            step_contras = self._detect_step_contradictions(scored)
            chain_contradictions.extend(step_contras)

            total_activated += len(step_nodes)
            steps.append({
                "order": tmpl_step.order,
                "description": tmpl_step.description,
                "operation": tmpl_step.operation,
                "edge_to_next": tmpl_step.edge_to_next,
                "nodes": step_nodes,
                "opinion": step_opinion,
                "tier": self._dominant_tier(step_nodes),
            })

        # Chain-level opinion from step opinions
        chain_opinion = self._fuse_opinions(chain_opinions)
        chain_tier = self._tier_from_opinion(chain_opinion)

        return ChainResult(
            name=chain_name,
            steps=steps,
            chain_opinion=chain_opinion,
            confidence_tier=chain_tier,
            nodes_activated=total_activated,
            contradictions=chain_contradictions,
        )

    # ------------------------------------------------------------------
    # Cross-chain synthesis
    # ------------------------------------------------------------------

    def _synthesize_chains(
        self,
        chains: list[ChainResult],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Synthesize across chains using D-S theory.

        Returns (overall_opinion, cross_chain_contradictions).
        """
        if not chains:
            return {}, []

        contradictions: list[dict[str, Any]] = []
        chain_opinions: list[Any] = []

        for ch in chains:
            op = ch.chain_opinion
            if op and isinstance(op, dict) and "b" in op:
                chain_opinions.append(op)

        if len(chain_opinions) < 2:
            return chain_opinions[0] if chain_opinions else {}, []

        # Pairwise conflict detection
        try:
            from engineering_brain.epistemic.conflict_resolution import (
                classify_conflict,
                dempster_conflict,
            )
            from engineering_brain.epistemic.opinion import OpinionTuple

            ops = []
            for op_dict in chain_opinions:
                ops.append(OpinionTuple(
                    b=op_dict["b"], d=op_dict["d"],
                    u=op_dict["u"], a=op_dict.get("a", 0.5),
                ))

            for i in range(len(ops)):
                for j in range(i + 1, len(ops)):
                    k = dempster_conflict(ops[i], ops[j])
                    severity = classify_conflict(k)
                    if severity.value not in ("none",):
                        contradictions.append({
                            "chain_a": chains[i].name,
                            "chain_b": chains[j].name,
                            "conflict_k": round(k, 3),
                            "severity": severity.value,
                            "description": f"Chain '{chains[i].name}' vs '{chains[j].name}' (K={k:.2f})",
                        })

            # Fuse based on max conflict level
            max_k = max(
                (dempster_conflict(ops[i], ops[j])
                 for i in range(len(ops)) for j in range(i + 1, len(ops))),
                default=0.0,
            )

            if max_k < 0.3:
                # Low conflict — standard CBF
                from engineering_brain.epistemic.fusion import multi_source_cbf
                fused = multi_source_cbf(ops)
            elif max_k < 0.7:
                # Moderate conflict — Murphy's weighted average
                from engineering_brain.epistemic.conflict_resolution import murphy_weighted_average
                fused = murphy_weighted_average(ops)
            else:
                # High conflict — report both, use Murphy as fallback
                from engineering_brain.epistemic.conflict_resolution import murphy_weighted_average
                fused = murphy_weighted_average(ops)

            return {
                "b": round(fused.b, 4), "d": round(fused.d, 4),
                "u": round(fused.u, 4), "a": round(fused.a, 4),
                "P": round(fused.projected_probability, 4),
                "fusion_strategy": "cbf" if max_k < 0.3 else ("murphy" if max_k < 0.7 else "conflict_report"),
            }, contradictions

        except Exception as e:
            logger.debug("Cross-chain synthesis fallback: %s", e)
            # Simple average fallback
            if chain_opinions:
                avg = {k: sum(op.get(k, 0) for op in chain_opinions) / len(chain_opinions)
                       for k in ("b", "d", "u")}
                avg["a"] = 0.5
                avg["P"] = avg["b"] + avg["a"] * avg["u"]
                return avg, contradictions
            return {}, contradictions

    # ------------------------------------------------------------------
    # Node filtering for template steps
    # ------------------------------------------------------------------

    def _filter_nodes(
        self,
        pool: list[dict[str, Any]],
        node_filter: dict[str, Any],
        ctx: ExtractedContext,
    ) -> list[dict[str, Any]]:
        """Filter node pool based on step's node_filter."""
        if not node_filter:
            return list(pool)

        result = list(pool)

        # Filter by layer
        layer_filter = node_filter.get("layer")
        if layer_filter:
            if isinstance(layer_filter, str):
                layer_filter = [layer_filter]
            result = [n for n in result if _infer_layer(str(n.get("id", ""))) in layer_filter]

        # Filter by domains (hierarchy-aware)
        domain_filter = node_filter.get("domains")
        if domain_filter:
            domain_filter_list = [d.lower() for d in domain_filter]
            result = [
                n for n in result
                if _hierarchy_match_tags(domain_filter_list, [d.lower() for d in (n.get("domains") or [])])
            ]

        # Filter by match_query_tech (hierarchy-aware)
        if node_filter.get("match_query_tech"):
            query_techs = [t.lower() for t in ctx.technologies]
            if query_techs:
                result = [
                    n for n in result
                    if _hierarchy_match_tags(query_techs, [t.lower() for t in (n.get("technologies") or n.get("languages") or [])])
                ]

        return result

    # ------------------------------------------------------------------
    # Gap detection
    # ------------------------------------------------------------------

    def _detect_gaps(
        self,
        ctx: ExtractedContext,
        activated_nodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Detect knowledge gaps in reasoning results."""
        gaps: list[dict[str, Any]] = []

        # Missing technology coverage (hierarchy-aware)
        returned_techs: list[str] = []
        for node in activated_nodes:
            nid = node.get("id", "")
            full_node = self._graph.get_node(nid) if nid else None
            if full_node:
                for t in (full_node.get("technologies") or full_node.get("languages") or []):
                    returned_techs.append(t.lower())

        for tech in ctx.technologies:
            if not _hierarchy_match_tags([tech.lower()], returned_techs):
                gaps.append({
                    "gap_type": "missing_technology",
                    "description": f"No knowledge found for technology '{tech}'",
                    "severity": 0.8,
                })

        # Missing layer coverage
        layers_present: set[str] = set()
        for node in activated_nodes:
            layers_present.add(node.get("layer", _infer_layer(node.get("id", ""))))
        if activated_nodes and "L1" not in layers_present:
            gaps.append({
                "gap_type": "missing_principles",
                "description": "No guiding principles activated in reasoning chains",
                "severity": 0.5,
            })

        # Missing domain coverage (hierarchy-aware)
        returned_domains: list[str] = []
        for node in activated_nodes:
            nid = node.get("id", "")
            full_node = self._graph.get_node(nid) if nid else None
            if full_node:
                for d in (full_node.get("domains") or []):
                    returned_domains.append(d.lower())
        for domain in ctx.domains:
            if domain != "general" and not _hierarchy_match_tags([domain.lower()], returned_domains):
                gaps.append({
                    "gap_type": "missing_domain",
                    "description": f"No knowledge found in domain '{domain}'",
                    "severity": 0.5,
                })

        return gaps

    # ------------------------------------------------------------------
    # Template selection & loading
    # ------------------------------------------------------------------

    def _load_templates(self) -> list[ReasoningTemplate]:
        """Load reasoning templates from YAML directory.

        YAML templates override the hardcoded default if they share the same ID.
        """
        templates: list[ReasoningTemplate] = []
        seen_ids: set[str] = set()

        if os.path.isdir(_TEMPLATES_DIR):
            for fname in sorted(os.listdir(_TEMPLATES_DIR)):
                if not fname.endswith(".yaml"):
                    continue
                path = os.path.join(_TEMPLATES_DIR, fname)
                try:
                    with open(path, "r") as f:
                        data = yaml.safe_load(f)
                    if isinstance(data, dict) and "id" in data:
                        tmpl = ReasoningTemplate(**data)
                        templates.append(tmpl)
                        seen_ids.add(tmpl.id)
                except Exception as e:
                    logger.debug("Failed to load template %s: %s", fname, e)

        # Add hardcoded default only if no YAML with same ID was loaded
        if _DEFAULT_TEMPLATE.id not in seen_ids:
            templates.insert(0, _DEFAULT_TEMPLATE)

        return templates

    def _select_template(
        self,
        ctx: ExtractedContext,
        profile: BrainProfile | None = None,
    ) -> ReasoningTemplate:
        """Select best matching template for the query context."""
        # Profile default template takes priority
        if profile and profile.default_template:
            for tmpl in self._templates:
                if tmpl.id == profile.default_template:
                    return tmpl

        # Pattern match ctx against template.applicable_when
        # Start at 0 so templates only win if they actually match something
        best_score = 0
        best_template = _DEFAULT_TEMPLATE

        for tmpl in self._templates:
            if not tmpl.applicable_when:
                continue
            score = self._template_match_score(tmpl.applicable_when, ctx)
            if score > best_score:
                best_score = score
                best_template = tmpl

        return best_template

    def _template_match_score(
        self,
        applicable_when: dict[str, Any],
        ctx: ExtractedContext,
    ) -> int:
        """Score how well a template matches the context (hierarchy-aware)."""
        score = 0
        # Match domains (hierarchy-aware)
        tmpl_domains = applicable_when.get("domains", [])
        if tmpl_domains:
            tmpl_list = [d.lower() for d in tmpl_domains]
            ctx_list = [x.lower() for x in ctx.domains]
            for d in tmpl_list:
                if _hierarchy_match_tags([d], ctx_list):
                    score += 2
        # Match keywords in raw text
        tmpl_keywords = applicable_when.get("keywords", [])
        if tmpl_keywords:
            text_lower = ctx.raw_text.lower()
            for kw in tmpl_keywords:
                if kw.lower() in text_lower:
                    score += 1
        return score

    # ------------------------------------------------------------------
    # Node helpers
    # ------------------------------------------------------------------

    def _collect_pack_nodes(self, packs: list[Pack]) -> list[dict[str, Any]]:
        """Collect all unique nodes from selected packs."""
        seen: set[str] = set()
        nodes: list[dict[str, Any]] = []
        for pack in packs:
            for nid in pack.node_ids:
                if nid in seen:
                    continue
                seen.add(nid)
                node = self._graph.get_node(nid)
                if node and not node.get("deprecated"):
                    nodes.append(node)
        return nodes

    def _classify_node_tier(self, node: dict[str, Any]) -> str:
        """Classify a node into a confidence tier."""
        ep_b = node.get("ep_b")
        if ep_b is not None:
            b = float(ep_b)
            d = float(node.get("ep_d", 0.0))
            u = float(node.get("ep_u", 0.5))
            a = float(node.get("ep_a", 0.5))
            projected = b + a * u
            if d > 0.3:
                return "contested"
            validation = str(node.get("validation_status", "unvalidated"))
            evidence_strength = 1.0 - u
            eigentrust = float(node.get("eigentrust_score", 0.5))
            if (validation in ("cross_checked", "human_verified")
                    and projected >= 0.7 and evidence_strength >= 0.5 and eigentrust >= 0.4):
                return "validated"
            if projected >= 0.6 and evidence_strength >= 0.3:
                return "probable"
            return "uncertain"
        else:
            confidence = float(node.get("confidence", 0.5))
            validation = str(node.get("validation_status", "unvalidated"))
            if validation in ("cross_checked", "human_verified") and confidence >= 0.7:
                return "validated"
            if confidence >= 0.5:
                return "probable"
            return "uncertain"

    def _compute_step_opinion(self, nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Compute fused opinion for a step's activated nodes."""
        if not nodes:
            return None
        try:
            from engineering_brain.epistemic.fusion import multi_source_cbf
            from engineering_brain.epistemic.opinion import OpinionTuple

            opinions: list[OpinionTuple] = []
            for node in nodes:
                ep_b = node.get("ep_b")
                if ep_b is not None:
                    opinions.append(OpinionTuple(
                        b=float(ep_b),
                        d=float(node.get("ep_d", 0.0)),
                        u=float(node.get("ep_u", 0.5)),
                        a=float(node.get("ep_a", 0.5)),
                    ))
                else:
                    # Construct opinion from confidence heuristic
                    conf = float(node.get("confidence", 0.5))
                    validation = str(node.get("validation_status", "unvalidated"))
                    if validation in ("cross_checked", "human_verified"):
                        opinions.append(OpinionTuple(b=conf, d=0.0, u=1.0 - conf, a=0.5))
                    else:
                        opinions.append(OpinionTuple(b=conf * 0.5, d=0.0, u=1.0 - conf * 0.5, a=0.5))

            if not opinions:
                return None

            fused = multi_source_cbf(opinions)
            return {
                "b": round(fused.b, 4),
                "d": round(fused.d, 4),
                "u": round(fused.u, 4),
                "a": round(fused.a, 4),
                "P": round(fused.projected_probability, 4),
            }
        except Exception as e:
            logger.debug("Step opinion computation failed: %s", e)
            return None

    def _fuse_opinions(self, opinions: list[dict[str, Any] | None]) -> dict[str, Any]:
        """Fuse multiple step opinions into a chain opinion."""
        valid = [op for op in opinions if op and isinstance(op, dict) and "b" in op]
        if not valid:
            return {}
        try:
            from engineering_brain.epistemic.fusion import multi_source_cbf
            from engineering_brain.epistemic.opinion import OpinionTuple

            ops = [OpinionTuple(b=o["b"], d=o["d"], u=o["u"], a=o.get("a", 0.5)) for o in valid]
            fused = multi_source_cbf(ops)
            return {
                "b": round(fused.b, 4), "d": round(fused.d, 4),
                "u": round(fused.u, 4), "a": round(fused.a, 4),
                "P": round(fused.projected_probability, 4),
            }
        except Exception:
            # Fallback: average
            avg = {k: sum(o.get(k, 0) for o in valid) / len(valid) for k in ("b", "d", "u")}
            avg["a"] = 0.5
            avg["P"] = avg["b"] + avg["a"] * avg["u"]
            return avg

    def _detect_step_contradictions(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect contradictions between nodes within a step."""
        result_ids = {n.get("id", "") for n in nodes if n.get("id")}
        contradictions: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()

        for node in nodes:
            nid = node.get("id", "")
            if not nid:
                continue
            try:
                edges = self._graph.get_edges(node_id=nid, edge_type="CONFLICTS_WITH")
            except Exception:
                continue
            for edge in edges:
                other_id = edge["to_id"] if edge["from_id"] == nid else edge["from_id"]
                if other_id not in result_ids:
                    continue
                pair = tuple(sorted([nid, other_id]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                contradictions.append({
                    "node_a_id": nid,
                    "node_b_id": other_id,
                    "severity": "moderate",
                    "description": f"Intra-step conflict: {nid} vs {other_id}",
                })

        return contradictions

    # ------------------------------------------------------------------
    # Tier helpers
    # ------------------------------------------------------------------

    def _tier_from_opinion(self, opinion: dict[str, Any]) -> str:
        """Derive confidence tier from an opinion dict."""
        if not opinion or "P" not in opinion:
            return "uncertain"
        p = opinion["P"]
        d = opinion.get("d", 0)
        if d > 0.3:
            return "contested"
        if p >= 0.75:
            return "validated"
        if p >= 0.55:
            return "probable"
        return "uncertain"

    def _dominant_tier(self, step_nodes: list[dict[str, Any]]) -> str:
        """Get the dominant confidence tier from step nodes."""
        if not step_nodes:
            return ""
        tiers = [n.get("tier", "uncertain") for n in step_nodes]
        counts: dict[str, int] = {}
        for t in tiers:
            counts[t] = counts.get(t, 0) + 1
        return max(counts, key=lambda t: counts[t]) if counts else "uncertain"

    # ------------------------------------------------------------------
    # Confidence distribution
    # ------------------------------------------------------------------

    def _confidence_distribution(self, chains: list[ChainResult]) -> dict[str, int]:
        """Count nodes per confidence tier across all chains."""
        dist: dict[str, int] = {}
        for ch in chains:
            for step in ch.steps:
                for node in step.get("nodes", []):
                    tier = node.get("tier", "uncertain")
                    dist[tier] = dist.get(tier, 0) + 1
        return dist

    # ------------------------------------------------------------------
    # Metacognitive summary
    # ------------------------------------------------------------------

    def _metacognitive_summary(
        self,
        chains: list[ChainResult],
        contradictions: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        conf_dist: dict[str, int],
    ) -> str:
        """Natural language summary of reasoning assessment."""
        total_nodes = sum(ch.nodes_activated for ch in chains)
        if total_nodes == 0:
            return "No relevant knowledge activated. Proceed with external documentation."

        parts = [f"Activated {total_nodes} nodes across {len(chains)} reasoning chain(s)."]

        # Distribution
        tier_parts = [f"{count} {tier.upper()}" for tier, count in sorted(conf_dist.items())]
        if tier_parts:
            parts.append(f"Confidence: {', '.join(tier_parts)}.")

        # Contradictions
        high_contras = [c for c in contradictions if c.get("severity") in ("high", "extreme")]
        if high_contras:
            parts.append(f"WARNING: {len(high_contras)} strong contradiction(s) detected.")
        elif contradictions:
            parts.append(f"{len(contradictions)} tension(s) between knowledge sources.")

        # Gaps
        high_gaps = [g for g in gaps if g.get("severity", 0) >= 0.7]
        if high_gaps:
            gap_descs = [g["description"] for g in high_gaps[:3]]
            parts.append(f"Gaps: {'; '.join(gap_descs)}.")

        # Overall assessment
        validated_pct = conf_dist.get("validated", 0) / max(total_nodes, 1)
        contested_pct = conf_dist.get("contested", 0) / max(total_nodes, 1)
        if contested_pct > 0.3:
            parts.append("Overall: CONTESTED. Multiple conflicting views exist.")
        elif validated_pct >= 0.7:
            parts.append("Overall: HIGH CONFIDENCE.")
        elif validated_pct >= 0.4:
            parts.append("Overall: MODERATE CONFIDENCE.")
        else:
            parts.append("Overall: LOW CONFIDENCE. Cross-reference recommended.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Output formatting
    # ------------------------------------------------------------------

    def _format_output(
        self,
        chains: list[ChainResult],
        overall_opinion: dict[str, Any],
        contradictions: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        meta: str,
    ) -> str:
        """Format reasoning result as chain-structured markdown."""
        lines: list[str] = []

        # Reasoning assessment
        lines.append("## Reasoning Assessment")
        lines.append(meta)
        lines.append("")

        # Per-chain output
        for i, chain in enumerate(chains, 1):
            p_val = chain.chain_opinion.get("P", 0) if chain.chain_opinion else 0
            tier = chain.confidence_tier.upper() or "UNCERTAIN"
            lines.append(f"## Chain {i}: {chain.name} [{tier}, P={p_val:.0%}]")

            for step in chain.steps:
                if step["operation"] == "score":
                    lines.append(f"  Step {step['order']}: {step['description']}")
                    continue

                edge = step.get("edge_to_next", "")
                edge_label = f" [{edge}]" if edge else ""
                lines.append(f"  Step {step['order']}: {step['description']}{edge_label}")

                for node in step.get("nodes", []):
                    tier_tag = node.get("tier", "?").upper()
                    score = node.get("score", 0)
                    layer = node.get("layer", "?")
                    text = node.get("text", "")
                    lines.append(f"    [{tier_tag}|{layer}|{score:.2f}] {text}")

            # Chain contradictions
            if chain.contradictions:
                lines.append(f"  Contradictions ({len(chain.contradictions)}):")
                for c in chain.contradictions:
                    lines.append(f"    - {c.get('description', '')}")

            lines.append("")

        # Cross-chain synthesis
        if overall_opinion:
            strategy = overall_opinion.get("fusion_strategy", "cbf")
            p = overall_opinion.get("P", 0)
            lines.append(f"## Cross-Chain Synthesis [strategy={strategy}, P={p:.0%}]")
            lines.append(f"  Opinion: b={overall_opinion.get('b', 0):.3f} "
                         f"d={overall_opinion.get('d', 0):.3f} "
                         f"u={overall_opinion.get('u', 0):.3f}")

            # Cross-chain contradictions
            cross = [c for c in contradictions if "chain_a" in c]
            if cross:
                lines.append(f"  Cross-chain contradictions ({len(cross)}):")
                for c in cross:
                    lines.append(f"    - {c.get('description', '')}")
            lines.append("")

        # Gaps
        if gaps:
            lines.append(f"## Knowledge Gaps ({len(gaps)})")
            for g in gaps:
                sev = g.get("severity", 0)
                lines.append(f"  [{sev:.0%}] {g.get('description', '')}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _node_text(node: dict[str, Any]) -> str:
        return str(
            node.get("text", "")
            or node.get("name", "")
            or node.get("statement", "")
            or node.get("id", "")
        )
