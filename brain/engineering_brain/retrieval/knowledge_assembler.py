"""LLM-powered knowledge pack assembler for the Engineering Knowledge Brain.

Replaces the static enforce_budget() + format_for_llm() pipeline with an
intelligent assembly step that curates, orders, and tailor-makes knowledge
packs per query.

Architecture:
  scored_nodes → classify → filter → annotate_guardrails → assemble(strategy) → validate

Three strategies:
  DIRECT:      Simple queries (≤8 words, 1 tech). No LLM. Top nodes → format_for_llm().
  CURATED:     Moderate queries. LLM selects + orders via JSON. Hydrated to markdown.
  SYNTHESIZED: Complex queries (3+ techs, design/architecture). LLM produces markdown directly.

Feature-flagged via BRAIN_LLM_KNOWLEDGE_ASSEMBLY (default ON).
Falls back to deterministic pipeline on any failure.
"""

from __future__ import annotations

import logging
import re
import time
from enum import StrEnum
from typing import Any

from engineering_brain.core.config import BrainConfig
from engineering_brain.core.types import AssemblyResult, GuardrailEntry, GuardrailMetadata
from engineering_brain.retrieval.budget import enforce_budget
from engineering_brain.retrieval.context_guard import (
    enforce_token_limit,
    filter_marginal_value,
)
from engineering_brain.retrieval.formatter import format_for_llm

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class QueryComplexity(StrEnum):
    """Classified complexity of an incoming query (drives strategy selection)."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class AssemblyStrategy(StrEnum):
    """Assembly strategy mapped from query complexity."""

    DIRECT = "direct"
    CURATED = "curated"
    SYNTHESIZED = "synthesized"


# =============================================================================
# Classification constants
# =============================================================================

_COMPLEX_SIGNALS = frozenset(
    {
        "design",
        "architect",
        "architecture",
        "system",
        "microservice",
        "microservices",
        "fullstack",
        "infrastructure",
        "migrate",
        "migration",
        "refactor",
        "rewrite",
        "overhaul",
    }
)
# Multi-word signals that require substring matching (after hyphen normalization)
_COMPLEX_MULTI_WORD = ("full stack",)

# Dynamic score cutoffs per complexity
_SCORE_CUTOFFS: dict[QueryComplexity, float] = {
    QueryComplexity.SIMPLE: 0.45,
    QueryComplexity.MODERATE: 0.30,
    QueryComplexity.COMPLEX: 0.20,
}

# Max candidates to send to LLM
_CANDIDATE_CAPS: dict[QueryComplexity, int] = {
    QueryComplexity.SIMPLE: 8,
    QueryComplexity.MODERATE: 18,
    QueryComplexity.COMPLEX: 25,
}

# Token budgets per complexity (characters, not tokens)
_CHAR_BUDGETS: dict[QueryComplexity, int] = {
    QueryComplexity.SIMPLE: 2400,  # ~700 tokens
    QueryComplexity.MODERATE: 6000,  # ~1700 tokens
    QueryComplexity.COMPLEX: 12000,  # ~3500 tokens
}


# =============================================================================
# LLM Prompts
# =============================================================================

_CURATED_SYSTEM = """\
You are a knowledge curator for an engineering knowledge graph. Given candidate \
knowledge nodes and a query, select and order the most relevant ones.

RULES:
1. Include ONLY directly relevant nodes. Aggressively exclude tangential ones.
2. Order: most critical guidance FIRST, supporting detail LAST.
3. Treatment per node: "full" (all fields) or "summary" (one-line essence).
4. If two nodes say the same thing, keep only the better-evidenced one.
5. Target ~{budget} characters total output when hydrated.

Output ONLY valid JSON:
{{"selected": [{{"id": "...", "treatment": "full"}}, ...], "summary_hint": "one sentence about what the brain knows"}}"""

_CURATED_USER = """\
QUERY: {query}
TECHNOLOGIES: {technologies}
DOMAINS: {domains}

CANDIDATES ({count}):
{candidates}

Select and order for a knowledge pack of ~{budget} characters."""

_SYNTHESIZED_SYSTEM = """\
You are a knowledge synthesizer for an engineering knowledge graph. Assemble a \
coherent, actionable knowledge pack from the candidate nodes below.

RULES:
1. Group by TOPIC, not by graph layer. Use ## headers for topic groups.
2. Start with CRITICAL guidance (security > correctness > performance > style).
3. End with CAVEATS and CONTRADICTIONS — these go last so the consumer reads them \
after absorbing the main guidance.
4. Compress verbose explanations. If WHY can be said in 10 words, use 10 words.
5. Cross-reference when rules depend on or contradict each other.
6. NEVER invent knowledge. Only use what's provided in the candidates.
7. Use severity badges: [CRITICAL], [HIGH], [MEDIUM]. Use [VERIFIED] for validated nodes.
8. Include WHY: and DO: labels for actionable fields.
9. Respect obligation levels annotated on each node:
   - [MUST] → imperative: "You MUST...", "Always..."
   - [MUST NOT] → prohibition: "NEVER...", "Do NOT..."
   - [SHOULD] → recommendation: "Prefer...", "You should..."
   - [MAY] → optional: "Consider...", "Optionally..."
10. Include source node IDs in brackets [ID] for traceability.
11. Total output MUST be under {budget} characters.

Output structured markdown directly. No JSON wrapping."""

_SYNTHESIZED_USER = """\
QUERY: {query}
TECHNOLOGIES: {technologies}
DOMAINS: {domains}

CANDIDATES ({count} nodes, sorted by relevance):
{candidates}

Synthesize into a coherent knowledge pack. Budget: {budget} characters max."""


# =============================================================================
# KnowledgeAssembler
# =============================================================================


class KnowledgeAssembler:
    """LLM-powered knowledge pack assembler.

    Sits between scoring/reranking and output formatting in the retrieval
    pipeline. Replaces static budget + mechanical formatting with
    intelligent curation.
    """

    def __init__(self, config: BrainConfig | None = None):
        self._config = config or BrainConfig()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def assemble(
        self,
        query: str,
        ctx: Any,
        scored_nodes: list[dict[str, Any]],
        budget_chars: int | None = None,
    ) -> AssemblyResult:
        """Assemble a curated knowledge pack from scored candidates.

        Parameters
        ----------
        query:
            The user's original query text.
        ctx:
            ExtractedContext with technologies, domains, etc.
        scored_nodes:
            Nodes sorted by ``_relevance_score`` descending.
        budget_chars:
            Character budget override. Uses config default if None.

        Returns
        -------
        AssemblyResult with formatted_text and metadata.
        """
        start = time.time()
        total_budget = budget_chars or self._config.context_budget_chars

        # Check feature flag
        if not self._is_assembly_enabled():
            return self._fallback(scored_nodes, total_budget, start)

        try:
            return self._assemble_internal(query, ctx, scored_nodes, total_budget, start)
        except Exception as exc:
            logger.warning("LLM assembly failed, falling back: %s", exc)
            return self._fallback(scored_nodes, total_budget, start)

    # -------------------------------------------------------------------------
    # Internal pipeline
    # -------------------------------------------------------------------------

    def _assemble_internal(
        self,
        query: str,
        ctx: Any,
        scored_nodes: list[dict[str, Any]],
        total_budget: int,
        start: float,
    ) -> AssemblyResult:
        # Step 1: Classify query
        complexity, strategy = self._classify(query, ctx, len(scored_nodes))

        # Dynamic budget based on complexity
        budget = min(total_budget, _CHAR_BUDGETS.get(complexity, total_budget))

        # Step 2: Filter candidates
        candidates = self._filter_candidates(scored_nodes, complexity, ctx)

        if not candidates:
            return self._empty_result(start)

        # Step 2.5: Guardrails annotation (obligation + applicability)
        guardrail_meta = None
        if self._config.guardrails_enabled:
            try:
                from engineering_brain.retrieval.guardrails import annotate_guardrails

                candidates, _summary = annotate_guardrails(candidates, ctx)
                guardrail_meta = self._build_guardrail_metadata(candidates)
            except Exception as exc:
                logger.warning("Guardrails annotation failed (non-blocking): %s", exc)

        # Step 3: Assemble by strategy
        if strategy == AssemblyStrategy.DIRECT:
            formatted, included, excluded = self._assemble_direct(candidates, budget)
        elif strategy == AssemblyStrategy.CURATED:
            formatted, included, excluded = self._assemble_curated(
                query,
                ctx,
                candidates,
                budget,
            )
        else:  # SYNTHESIZED
            formatted, included, excluded = self._assemble_synthesized(
                query,
                ctx,
                candidates,
                budget,
            )

        # Step 4: Validate (quality is metadata, never triggers fallback)
        formatted, quality = self._validate(formatted, candidates, included, budget)

        included_nodes = [n for n in candidates if n.get("id", "") in included]
        elapsed = (time.time() - start) * 1000
        return AssemblyResult(
            formatted_text=formatted,
            included_nodes=included_nodes,
            excluded_node_ids=excluded,
            strategy=strategy.value,
            quality_score=quality,
            assembly_time_ms=elapsed,
            fallback_used=False,
            by_layer=self._split_by_layer(included_nodes),
            guardrails=guardrail_meta,
        )

    # -------------------------------------------------------------------------
    # Step 1: Classification (pure heuristic, zero LLM)
    # -------------------------------------------------------------------------

    def _classify(
        self,
        query: str,
        ctx: Any,
        node_count: int,
    ) -> tuple[QueryComplexity, AssemblyStrategy]:
        """Classify query complexity → assembly strategy.

        Uses heuristics only — no LLM tokens spent on classification.
        """
        query_lower = query.lower()
        words = query_lower.split()
        word_count = len(words)
        techs = getattr(ctx, "technologies", []) or []
        domains = getattr(ctx, "domains", []) or []
        tech_count = len(techs)
        domain_count = len(domains)

        # COMPLEX: multi-tech, multi-domain, or architecture keywords
        has_complex_signal = bool(_COMPLEX_SIGNALS & set(words))
        if not has_complex_signal:
            # Check multi-word signals (normalize hyphens)
            normalized = query_lower.replace("-", " ")
            has_complex_signal = any(mw in normalized for mw in _COMPLEX_MULTI_WORD)
        if tech_count >= 3 or domain_count >= 3 or has_complex_signal:
            return QueryComplexity.COMPLEX, AssemblyStrategy.SYNTHESIZED

        # SIMPLE: short query, single focus, few nodes
        if word_count <= 8 and tech_count <= 1 and domain_count <= 1 and node_count <= 10:
            return QueryComplexity.SIMPLE, AssemblyStrategy.DIRECT

        # MODERATE: everything else
        return QueryComplexity.MODERATE, AssemblyStrategy.CURATED

    # -------------------------------------------------------------------------
    # Step 2: Candidate filtering (deterministic)
    # -------------------------------------------------------------------------

    def _filter_candidates(
        self,
        scored_nodes: list[dict[str, Any]],
        complexity: QueryComplexity,
        ctx: Any,
    ) -> list[dict[str, Any]]:
        """Filter scored nodes to a compact candidate set."""
        min_score = _SCORE_CUTOFFS[complexity]
        max_count = _CANDIDATE_CAPS[complexity]

        # Score cutoff
        candidates = [n for n in scored_nodes if n.get("_relevance_score", 0) >= min_score]

        # Cap
        candidates = candidates[:max_count]

        # Vertical coverage: ensure at least 1 node from L1, L2, L3
        # Floor prevents pulling nodes with near-zero relevance scores
        _VERTICAL_COVERAGE_FLOOR = 0.10
        layers_present = {n.get("_layer", "") for n in candidates}
        candidate_ids = {n.get("id", "") for n in candidates}
        for needed in ("L1", "L2", "L3"):
            if needed not in layers_present:
                for n in scored_nodes:
                    nid = n.get("id", "")
                    score = n.get("_relevance_score", 0)
                    if (
                        n.get("_layer") == needed
                        and nid
                        and nid not in candidate_ids
                        and score >= _VERTICAL_COVERAGE_FLOOR
                    ):
                        candidates.append(n)
                        candidate_ids.add(nid)
                        break

        # Marginal value dedup
        candidates = filter_marginal_value(candidates)

        return candidates

    # -------------------------------------------------------------------------
    # Step 3a: DIRECT assembly (no LLM)
    # -------------------------------------------------------------------------

    def _assemble_direct(
        self,
        candidates: list[dict[str, Any]],
        budget: int,
    ) -> tuple[str, set[str], list[str]]:
        """Assemble simple queries without LLM. Top nodes → bookend structure."""
        top = candidates[:5]

        # Use same bookend rendering as CURATED for consistent output
        ordered_nodes = [(n, "full") for n in top]
        formatted = self._hydrate_curated(ordered_nodes, "")
        formatted = enforce_token_limit(formatted, budget)

        included = {n["id"] for n in top if n.get("id")}
        excluded = [n["id"] for n in candidates if n.get("id") and n["id"] not in included]
        return formatted, included, excluded

    # -------------------------------------------------------------------------
    # Step 3b: CURATED assembly (LLM selects + orders via JSON)
    # -------------------------------------------------------------------------

    def _assemble_curated(
        self,
        query: str,
        ctx: Any,
        candidates: list[dict[str, Any]],
        budget: int,
    ) -> tuple[str, set[str], list[str]]:
        """LLM selects and orders candidates. Returns hydrated markdown."""
        serialized = self._serialize_candidates(candidates)

        # Token budget guard: don't spend more on assembly than the output
        if len(serialized) > budget * 3:
            return self._assemble_direct(candidates, budget)

        techs = ", ".join(getattr(ctx, "technologies", []) or []) or "general"
        domains = ", ".join(getattr(ctx, "domains", []) or []) or "general"

        from engineering_brain.llm_helpers import brain_llm_call_json

        result = brain_llm_call_json(
            system_prompt=_CURATED_SYSTEM.format(budget=budget),
            user_message=_CURATED_USER.format(
                query=query,
                technologies=techs,
                domains=domains,
                count=len(candidates),
                candidates=serialized,
                budget=budget,
            ),
            max_tokens=500,
        )

        if result is None:
            logger.debug("Curated LLM call returned None, falling back to direct")
            return self._assemble_direct(candidates, budget)

        # Parse LLM decisions
        selected = result.get("selected", [])
        summary_hint = result.get("summary_hint", "")

        if not selected or not isinstance(selected, list):
            return self._assemble_direct(candidates, budget)

        # Build node map
        node_map = {n.get("id", ""): n for n in candidates}

        # Hydrate in the order LLM specified
        included_ids: set[str] = set()
        ordered_nodes: list[tuple[dict[str, Any], str]] = []
        for item in selected:
            nid = item.get("id", "") if isinstance(item, dict) else str(item)
            treatment = item.get("treatment", "full") if isinstance(item, dict) else "full"
            node = node_map.get(nid)
            if node:
                included_ids.add(nid)
                ordered_nodes.append((node, treatment))

        if not ordered_nodes:
            return self._assemble_direct(candidates, budget)

        # Render
        formatted = self._hydrate_curated(ordered_nodes, summary_hint)
        formatted = enforce_token_limit(formatted, budget)

        excluded = [n["id"] for n in candidates if n.get("id") and n["id"] not in included_ids]
        return formatted, included_ids, excluded

    # -------------------------------------------------------------------------
    # Step 3c: SYNTHESIZED assembly (LLM produces markdown)
    # -------------------------------------------------------------------------

    def _assemble_synthesized(
        self,
        query: str,
        ctx: Any,
        candidates: list[dict[str, Any]],
        budget: int,
    ) -> tuple[str, set[str], list[str]]:
        """LLM synthesizes cross-topic markdown from candidates."""
        serialized = self._serialize_candidates(candidates)

        # Token budget guard
        if len(serialized) > budget * 3:
            return self._assemble_direct(candidates, budget)

        techs = ", ".join(getattr(ctx, "technologies", []) or []) or "general"
        domains = ", ".join(getattr(ctx, "domains", []) or []) or "general"

        from engineering_brain.llm_helpers import brain_llm_call

        result = brain_llm_call(
            system_prompt=_SYNTHESIZED_SYSTEM.format(budget=budget),
            user_message=_SYNTHESIZED_USER.format(
                query=query,
                technologies=techs,
                domains=domains,
                count=len(candidates),
                candidates=serialized,
                budget=budget,
            ),
            max_tokens=1500,
        )

        if result is None:
            logger.debug("Synthesized LLM call returned None, falling back to direct")
            return self._assemble_direct(candidates, budget)

        result = enforce_token_limit(result, budget)

        # Extract which candidate IDs were mentioned in the output
        included_ids = self._extract_mentioned_ids(result, candidates)
        excluded = [n["id"] for n in candidates if n.get("id") and n["id"] not in included_ids]
        return result, included_ids, excluded

    # -------------------------------------------------------------------------
    # Step 4: Validation + quality scoring
    # -------------------------------------------------------------------------

    def _validate(
        self,
        text: str,
        candidates: list[dict[str, Any]],
        included_ids: set[str],
        budget: int,
    ) -> tuple[str, float]:
        """Validate assembled output. Returns (text, quality_score)."""
        signals: dict[str, float] = {}

        # 1. Budget compliance
        if len(text) <= int(budget * 1.1):
            signals["budget"] = 1.0
        elif len(text) <= int(budget * 1.3):
            signals["budget"] = 0.6
        else:
            text = enforce_token_limit(text, budget)
            signals["budget"] = 0.3

        # 2. Structure quality (tolerant, variant-aware matching)
        has_headers = "##" in text
        has_bullets = "- " in text or "* " in text
        has_why = bool(
            re.search(
                r"\b(WHY|REASON|BECAUSE|RATIONALE)\s*[:—]",
                text,
                re.IGNORECASE,
            )
        )
        has_do = bool(
            re.search(
                r"\b(DO|HOW|ACTION|FIX|IMPLEMENT)\s*[:—]",
                text,
                re.IGNORECASE,
            )
        )
        signals["structure"] = sum([has_headers, has_bullets, has_why, has_do]) / 4.0

        # 3. Critical node coverage
        critical = [
            n
            for n in candidates
            if n.get("severity") == "critical" and n.get("_relevance_score", 0) >= 0.5
        ]
        if critical:
            covered = sum(1 for n in critical if n.get("id", "") in included_ids)
            signals["critical"] = covered / len(critical)
        else:
            signals["critical"] = 1.0

        # 4. Content density
        signals["density"] = min(len(text) / max(budget * 0.3, 1), 1.0)

        # Weighted score
        weights = {"budget": 0.25, "structure": 0.25, "critical": 0.30, "density": 0.20}
        quality = sum(signals[k] * weights[k] for k in weights)

        return text, round(quality, 3)

    # -------------------------------------------------------------------------
    # Rendering helpers
    # -------------------------------------------------------------------------

    def _hydrate_curated(
        self,
        ordered_nodes: list[tuple[dict[str, Any], str]],
        summary_hint: str,
    ) -> str:
        """Render LLM-selected nodes into structured markdown.

        When guardrails are annotated (``_obligation`` key present), uses
        obligation-based bookend structure: MUST first, Supporting last.
        Falls back to severity-based sections when guardrails are absent.
        """
        sections: list[str] = []

        if summary_hint:
            sections.append(f"## Brain: {summary_hint}")

        # Check if guardrails are annotated
        has_guardrails = any(n.get("_obligation") for n, _ in ordered_nodes)

        if has_guardrails:
            must_lines: list[str] = []
            must_not_lines: list[str] = []
            should_lines: list[str] = []
            supporting_lines: list[str] = []

            for node, treatment in ordered_nodes:
                rendered = self._render_node(node, treatment)
                obligation = node.get("_obligation", "")
                if obligation == "MUST NOT":
                    must_not_lines.append(rendered)
                elif obligation == "MUST":
                    must_lines.append(rendered)
                elif obligation in ("SHOULD", "SHOULD NOT"):
                    should_lines.append(rendered)
                else:
                    supporting_lines.append(rendered)

            if must_lines:
                sections.append("### MUST DO\n" + "\n".join(must_lines))
            if must_not_lines:
                sections.append("### MUST NOT DO\n" + "\n".join(must_not_lines))
            if should_lines:
                sections.append("### SHOULD\n" + "\n".join(should_lines))
            if supporting_lines:
                sections.append("### Supporting Knowledge\n" + "\n".join(supporting_lines))
        else:
            # Fallback: severity-based sections (backward compatible)
            critical_lines: list[str] = []
            supporting_lines_fb: list[str] = []

            for node, treatment in ordered_nodes:
                rendered = self._render_node(node, treatment)
                severity = node.get("severity", "medium")
                if severity in ("critical", "high"):
                    critical_lines.append(rendered)
                else:
                    supporting_lines_fb.append(rendered)

            if critical_lines:
                sections.append("### Critical Guidance\n" + "\n".join(critical_lines))
            if supporting_lines_fb:
                sections.append("### Supporting Knowledge\n" + "\n".join(supporting_lines_fb))

        return "\n\n".join(sections)

    def _render_node(self, node: dict[str, Any], treatment: str) -> str:
        """Render a single node with treatment (full or summary)."""
        node.get("_layer", "L3")
        severity = node.get("severity", "medium")
        validation = node.get("validation_status", "unvalidated")
        reinforcement = node.get("reinforcement_count", 0)

        # Build tag (obligation badge first if present)
        tag_parts = []
        obligation = node.get("_obligation", "")
        if obligation:
            tag_parts.append(f"[{obligation}]")
        tag_parts.append(f"[{severity.upper()}]")
        if validation in ("cross_checked", "human_verified"):
            tag_parts.append("[VERIFIED]")
        if reinforcement:
            tag_parts.append(f"[{reinforcement}x]")
        tag = "".join(tag_parts)

        # Primary text
        text = (
            node.get("text")
            or node.get("name")
            or node.get("statement")
            or node.get("description", "")
        )

        if treatment == "summary":
            return f"- {tag} {text}"

        # Full treatment: include WHY, DO, PREDICT, WHEN
        line = f"- {tag} {text}"
        why = node.get("why", "")
        how = node.get("how_to_do_right") or node.get("how_to_apply", "")
        when = node.get("when_applies", "")
        when_not = node.get("when_not_applies", "")

        if why:
            line += f"\n  WHY: {why}"
        if how:
            line += f"\n  DO: {how}"
        if when:
            line += f"\n  WHEN: {when}"
        if when_not:
            line += f"\n  NOT WHEN: {when_not}"

        pred_if = node.get("prediction_if", "")
        pred_then = node.get("prediction_then", "")
        if pred_if and pred_then:
            tested = int(node.get("prediction_tested_count", 0))
            succeeded = int(node.get("prediction_success_count", 0))
            if tested > 0:
                rate = succeeded / tested * 100
                line += f"\n  PREDICT: IF {pred_if} THEN {pred_then} ({rate:.0f}%)"
            else:
                line += f"\n  PREDICT: IF {pred_if} THEN {pred_then}"

        return line

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------

    def _serialize_candidates(self, candidates: list[dict[str, Any]]) -> str:
        """Serialize candidates into compact text for LLM consumption.

        ~100-150 chars per node. Designed for token efficiency.
        """
        lines: list[str] = []
        for node in candidates:
            nid = node.get("id", "?")
            layer = node.get("_layer", "?")
            score = node.get("_relevance_score", 0)
            severity = node.get("severity", "")
            validation = node.get("validation_status", "unvalidated")
            reinf = node.get("reinforcement_count", 0)

            text = (
                node.get("text")
                or node.get("name")
                or node.get("statement")
                or node.get("description", "")
            )[:200]
            why = (node.get("why", ""))[:150]
            how = (node.get("how_to_do_right") or node.get("how_to_apply", ""))[:150]

            obligation = node.get("_obligation", "")
            obl_str = f" | Obligation:{obligation}" if obligation else ""
            parts = [
                f"---\nID: {nid} | {layer} | S:{score:.2f} | Sev:{severity} | V:{validation} | R:{reinf}x{obl_str}"
            ]
            parts.append(f"TEXT: {text}")
            if why:
                parts.append(f"WHY: {why}")
            if how:
                parts.append(f"DO: {how}")

            lines.append("\n".join(parts))

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Utility
    # -------------------------------------------------------------------------

    def _extract_mentioned_ids(
        self,
        text: str,
        candidates: list[dict[str, Any]],
    ) -> set[str]:
        """Find which candidate IDs appear in the assembled text.

        Uses word-boundary-aware matching to avoid false positives
        (e.g., "api" matching inside "capitalize").

        Falls back to content-overlap heuristic when the LLM paraphrases
        without citing IDs — matches nodes whose distinctive words appear
        in the output (≥40% overlap).
        """
        mentioned: set[str] = set()
        for node in candidates:
            nid = node.get("id", "")
            if not nid:
                continue
            pattern = r"(?<![a-zA-Z0-9_-])" + re.escape(nid) + r"(?![a-zA-Z0-9_-])"
            if re.search(pattern, text):
                mentioned.add(nid)

        # Fallback: infer by content overlap when no IDs cited
        if not mentioned:
            mentioned = self._infer_mentioned_by_content(text, candidates)

        return mentioned

    def _infer_mentioned_by_content(
        self,
        text: str,
        candidates: list[dict[str, Any]],
    ) -> set[str]:
        """Fallback: infer which candidates were used by word overlap.

        If the LLM paraphrased without citing IDs, check whether each
        node's distinctive words (≥3 chars) appear in the output.
        Threshold: 40% of a node's words must appear.
        """
        text_words = set(re.findall(r"[a-z0-9_-]{3,}", text.lower()))
        if not text_words:
            return set()

        inferred: set[str] = set()
        for node in candidates:
            node_text = node.get("text") or node.get("name") or node.get("statement") or ""
            node_words = set(re.findall(r"[a-z0-9_-]{3,}", node_text.lower()))
            if not node_words:
                continue
            overlap = len(node_words & text_words) / len(node_words)
            if overlap >= 0.4:
                nid = node.get("id", "")
                if nid:
                    inferred.add(nid)
        return inferred

    def _split_by_layer(
        self,
        nodes: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Split nodes into per-layer buckets.

        Uses ``_layer`` if present, falls back to ``_label``.
        Defaults unknowns to L3 (rules) — consistent with router.
        """
        by_layer: dict[str, list[dict[str, Any]]] = {
            "L1": [],
            "L2": [],
            "L3": [],
            "L4": [],
        }
        for node in nodes:
            layer = node.get("_layer", "")
            label = node.get("_label", "")
            if layer in by_layer:
                by_layer[layer].append(node)
            elif label == "Principle":
                by_layer["L1"].append(node)
            elif label == "Pattern":
                by_layer["L2"].append(node)
            elif label in ("Finding", "CodeExample", "TestResult"):
                by_layer["L4"].append(node)
            else:
                by_layer["L3"].append(node)  # Default to rules
        return by_layer

    def _build_guardrail_metadata(
        self,
        candidates: list[dict[str, Any]],
    ) -> GuardrailMetadata:
        """Build structured guardrail metadata from annotated candidates."""
        _OBLIGATION_BUCKET = {
            "MUST": "must_do",
            "MUST NOT": "must_not_do",
            "SHOULD": "should_do",
            "SHOULD NOT": "should_not_do",
            "MAY": "may_do",
        }
        meta = GuardrailMetadata()
        for node in candidates:
            obligation = node.get("_obligation", "MAY")
            applicability = node.get("_applicability", {})
            entry = GuardrailEntry(
                node_id=node.get("id", ""),
                obligation=obligation,
                text=(node.get("text") or node.get("name") or node.get("statement") or "")[:200],
                why=(node.get("why") or "")[:150],
                applicable=applicability.get("applicable", True),
                excluded_by=applicability.get("excluded_by", ""),
            )
            bucket = _OBLIGATION_BUCKET.get(obligation, "may_do")
            getattr(meta, bucket).append(entry)

            if not applicability.get("applicable", True):
                nid = node.get("id", "")
                if nid:
                    meta.inapplicable_ids.append(nid)

        return meta

    def _is_assembly_enabled(self) -> bool:
        """Check if LLM assembly is enabled (flag + API key)."""
        if not self._config.llm_knowledge_assembly:
            return False
        from engineering_brain.llm_helpers import is_llm_enabled

        return is_llm_enabled("BRAIN_LLM_KNOWLEDGE_ASSEMBLY")

    def _fallback(
        self,
        scored_nodes: list[dict[str, Any]],
        budget: int,
        start: float,
    ) -> AssemblyResult:
        """Deterministic fallback: existing enforce_budget + format_for_llm."""
        by_layer = self._split_by_layer(scored_nodes)

        # Apply per-layer top-K limits
        cfg = self._config
        limits = {
            "L1": cfg.top_k_principles,
            "L2": cfg.top_k_patterns,
            "L3": cfg.top_k_rules,
            "L4": cfg.top_k_evidence,
        }
        for layer_key, limit in limits.items():
            if layer_key in by_layer:
                by_layer[layer_key] = by_layer[layer_key][:limit]

        by_layer = enforce_budget(by_layer, config=cfg)
        formatted = format_for_llm(by_layer, config=cfg)

        # Collect all included nodes
        included = []
        for layer_nodes in by_layer.values():
            included.extend(layer_nodes)

        elapsed = (time.time() - start) * 1000
        return AssemblyResult(
            formatted_text=formatted,
            included_nodes=included,
            excluded_node_ids=[],
            strategy="direct",
            quality_score=0.0,
            assembly_time_ms=elapsed,
            fallback_used=True,
            by_layer=by_layer,
        )

    def _empty_result(self, start: float) -> AssemblyResult:
        """Return empty result when no candidates match."""
        elapsed = (time.time() - start) * 1000
        return AssemblyResult(
            formatted_text="## Brain: No relevant knowledge found\nProceed with general engineering principles.",
            included_nodes=[],
            excluded_node_ids=[],
            strategy="direct",
            quality_score=0.0,
            assembly_time_ms=elapsed,
            fallback_used=False,
            by_layer={"L1": [], "L2": [], "L3": [], "L4": []},
        )
