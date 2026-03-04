"""Orchestrator — routes queries, decomposes, dispatches workers, synthesizes.

Complexity routing is fully deterministic (zero LLM).
Fast path (SIMPLE) uses brain.think() directly — zero tokens.
Deep path (MODERATE/COMPLEX) uses N+2 Opus calls max.
"""

from __future__ import annotations

import logging
from typing import Any

from engineering_brain.agent.brain_access import BrainAccess
from engineering_brain.agent.config import AgentConfig
from engineering_brain.agent.llm_client import LLMClient
from engineering_brain.agent.parsing import parse_claims, parse_confidence
from engineering_brain.agent.runtime_cards import load_card
from engineering_brain.agent.types import (
    AgentQuery,
    ComposedKnowledge,
    ConfidenceLevel,
    KnowledgeClaim,
    QueryComplexity,
    QueryIntent,
    WorkerResult,
)
from engineering_brain.agent.workers import get_worker_class

logger = logging.getLogger(__name__)

# Confidence ordering: higher index = lower confidence
_CONFIDENCE_ORDER = {
    ConfidenceLevel.HIGH: 0,
    ConfidenceLevel.MODERATE: 1,
    ConfidenceLevel.LOW: 2,
    ConfidenceLevel.CONTESTED: 3,
}

# Named limits for fast-path text handling
_MAX_CLAIM_TEXT = 500
_MAX_SUMMARY_TEXT = 1000

# Default priority for sub-questions without explicit priority
_DEFAULT_SUB_QUESTION_PRIORITY = 99

# Max claims used in fallback merge summary
_FALLBACK_SUMMARY_MAX_CLAIMS = 3


class Orchestrator:
    """Agent orchestrator — the entry point for deep reasoning."""

    def __init__(
        self,
        brain_access: BrainAccess,
        llm_client: LLMClient,
        config: AgentConfig,
    ) -> None:
        self._brain = brain_access
        self._llm = llm_client
        self._config = config

    def run(self, query: AgentQuery) -> ComposedKnowledge:
        """Execute the full orchestration flow.

        1. Assess complexity (deterministic)
        2. SIMPLE -> fast path (zero LLM)
        3. MODERATE/COMPLEX -> decompose -> workers -> synthesize
        """
        complexity = self.assess_complexity(query)
        logger.info("Query complexity: %s (intent=%s)", complexity.value, query.intent.value)

        if complexity == QueryComplexity.SIMPLE:
            return self._fast_path(query)

        return self._deep_path(query, complexity)

    # =========================================================================
    # Complexity Routing (deterministic, zero LLM)
    # =========================================================================

    def assess_complexity(self, query: AgentQuery) -> QueryComplexity:
        """Deterministic complexity assessment.

        Scoring table:
        - Intent: EXPLANATION=0, DECISION/ANALYSIS/INVESTIGATION=1, SYNTHESIS=2
        - Domains: 0-1=0, 2=1, 3+=2
        - Technologies: 0-1=0, 2=1, 3+=2
        - max_depth: 1=0, 2-3=1, 4+=2

        Total: 0-1=SIMPLE, 2-4=MODERATE, 5+=COMPLEX
        """
        score = 0

        # Intent signal
        intent_scores = {
            QueryIntent.EXPLANATION: 0,
            QueryIntent.DECISION: 1,
            QueryIntent.ANALYSIS: 1,
            QueryIntent.INVESTIGATION: 1,
            QueryIntent.SYNTHESIS: 2,
        }
        score += intent_scores.get(query.intent, 1)

        # Domain count signal
        n_domains = len(query.domain_hints)
        if n_domains >= 3:
            score += 2
        elif n_domains >= 2:
            score += 1

        # Technology count signal
        n_techs = len(query.technology_hints)
        if n_techs >= 3:
            score += 2
        elif n_techs >= 2:
            score += 1

        # Depth signal
        if query.max_depth >= 4:
            score += 2
        elif query.max_depth >= 2:
            score += 1

        if score <= 1:
            return QueryComplexity.SIMPLE
        elif score <= 4:
            return QueryComplexity.MODERATE
        else:
            return QueryComplexity.COMPLEX

    # =========================================================================
    # Fast Path (zero LLM)
    # =========================================================================

    def _fast_path(self, query: AgentQuery) -> ComposedKnowledge:
        """Fast path for simple queries — brain.think() only, zero tokens."""
        result = self._brain.think(
            query.question,
            technologies=query.technology_hints or None,
            domains=query.domain_hints or None,
        )

        text = result.get("text", "")
        confidence_str = result.get("confidence", "moderate")

        # Map brain confidence to agent confidence
        confidence_map = {
            "VALIDATED": ConfidenceLevel.HIGH,
            "PROBABLE": ConfidenceLevel.MODERATE,
            "UNCERTAIN": ConfidenceLevel.LOW,
            "CONTESTED": ConfidenceLevel.CONTESTED,
        }
        overall = confidence_map.get(str(confidence_str).upper(), ConfidenceLevel.MODERATE)

        claims = []
        if text:
            claims.append(
                KnowledgeClaim(
                    claim=text[:_MAX_CLAIM_TEXT],
                    confidence=overall,
                )
            )

        contradictions = [
            f"{c.get('node_a_id', '?')} vs {c.get('node_b_id', '?')}"
            for c in result.get("contradictions", [])
        ]
        gaps = [str(g.get("description", g.get("domain", "?"))) for g in result.get("gaps", [])]

        return ComposedKnowledge(
            query=query.question,
            summary=text[:_MAX_SUMMARY_TEXT] if text else "No relevant knowledge found.",
            claims=claims,
            overall_confidence=overall,
            contradictions=contradictions,
            gaps=gaps,
            fast_path=True,
            tokens_used=0,
        )

    # =========================================================================
    # Deep Path (N+2 Opus calls)
    # =========================================================================

    def _deep_path(self, query: AgentQuery, complexity: QueryComplexity) -> ComposedKnowledge:
        """Deep path: decompose -> workers -> synthesize."""
        # Step 1: Decompose (tracks its own tokens)
        sub_questions, decompose_tokens = self._decompose(query)
        if not sub_questions:
            logger.warning("Decomposition returned no sub-questions, falling back to fast path")
            result = self._fast_path(query)
            # Preserve decompose tokens that were already consumed
            if decompose_tokens > 0:
                result = result.model_copy(update={"tokens_used": decompose_tokens})
            return result

        # Step 2: Execute workers (each wrapped in try/except for isolation)
        worker_results: list[WorkerResult] = []
        worker_tokens = 0
        for sq in sub_questions[: self._config.max_workers]:
            domain = sq.get("domain", "general")
            technologies = sq.get("technologies", [])
            try:
                worker_cls = get_worker_class(domain)
                worker = worker_cls(
                    brain_access=self._brain,
                    llm_client=self._llm,
                    config=self._config,
                )
                result = worker.execute(sq["question"], technologies=technologies)
                worker_results.append(result)
                worker_tokens += result.tokens_used
            except Exception as exc:
                logger.error("Worker %s failed: %s", domain, exc)
                worker_results.append(
                    WorkerResult(
                        worker_id=f"{domain}_worker",
                        domain=domain,
                        gaps=[f"Worker execution failed: {type(exc).__name__}"],
                    )
                )

        # Step 3: Synthesize
        composed = self._synthesize(query, worker_results)
        # Total: decompose + workers + synthesis
        total_tokens = decompose_tokens + worker_tokens + composed.tokens_used
        return composed.model_copy(update={"tokens_used": total_tokens})

    def _decompose(self, query: AgentQuery) -> tuple[list[dict[str, Any]], int]:
        """Decompose query into sub-questions via orchestrator card + 1 Opus call.

        Returns:
            (sub_questions, tokens_used)
        """
        card = load_card("orchestrator", cards_dir=self._config.cards_dir)
        max_workers = self._config.max_workers
        system_prompt = card.build_decompose_prompt().replace("{max_workers}", str(max_workers))
        user_message = (
            f"## User Question\n{query.question}\n\n"
            f"## Context\n"
            f"- Intent: {query.intent.value}\n"
            f"- Domain hints: {', '.join(query.domain_hints) or 'none'}\n"
            f"- Technology hints: {', '.join(query.technology_hints) or 'none'}\n"
            f"- Constraints: {', '.join(query.constraints) or 'none'}\n"
            f"- Max workers: {max_workers}\n"
            f"- Additional context: {query.context or 'none'}\n\n"
            f"Decompose into 1-{max_workers} sub-questions. Return JSON."
        )

        try:
            result = self._llm.call_json(
                system_prompt=system_prompt,
                user_message=user_message,
                model=self._config.orchestrator_model,
            )
            tokens = result["input_tokens"] + result["output_tokens"]
            data = result["data"]
            if not isinstance(data, dict):
                logger.error("Decomposition returned non-dict: %s", type(data))
                return [], tokens
            sub_questions = data.get("sub_questions", [])
            if not isinstance(sub_questions, list):
                logger.error("Decomposition returned non-list: %s", type(sub_questions))
                return [], tokens
            # Validate each sub-question has at minimum a "question" field
            valid = []
            for sq in sub_questions:
                if isinstance(sq, dict) and sq.get("question"):
                    valid.append(
                        {
                            "question": sq["question"],
                            "domain": sq.get("domain", "general"),
                            "technologies": sq.get("technologies", []),
                            "priority": sq.get("priority", _DEFAULT_SUB_QUESTION_PRIORITY),
                        }
                    )
            return sorted(valid, key=lambda x: x["priority"]), tokens
        except Exception as exc:
            logger.error("Decomposition failed: %s", exc)
            # Fallback: single general sub-question (zero tokens since LLM failed)
            return [
                {
                    "question": query.question,
                    "domain": query.domain_hints[0] if query.domain_hints else "general",
                    "technologies": query.technology_hints,
                    "priority": 1,
                }
            ], 0

    def _synthesize(
        self,
        query: AgentQuery,
        worker_results: list[WorkerResult],
    ) -> ComposedKnowledge:
        """Synthesize worker results via orchestrator card + 1 Opus call."""
        card = load_card("orchestrator", cards_dir=self._config.cards_dir)
        system_prompt = card.build_synthesize_prompt().replace(
            "{n_workers}", str(len(worker_results))
        )

        # Build worker findings for synthesis
        findings_parts = []
        for wr in worker_results:
            findings_parts.append(f"\n### Worker: {wr.worker_id} (domain: {wr.domain})")
            for claim in wr.claims:
                evidence_ids = [e.node_id for e in claim.evidence if e.node_id]
                findings_parts.append(
                    f"- [{claim.confidence.value}] {claim.claim}\n"
                    f"  Evidence: {', '.join(evidence_ids) or 'none'}"
                )
            if wr.gaps:
                findings_parts.append(f"  Gaps: {', '.join(wr.gaps)}")
            if wr.contradictions_found:
                findings_parts.append(f"  Contradictions: {', '.join(wr.contradictions_found)}")

        user_message = (
            f"## Original Question\n{query.question}\n\n"
            f"## Worker Findings\n{''.join(findings_parts)}\n\n"
            f"Synthesize into composed knowledge. Return JSON."
        )

        try:
            result = self._llm.call_json(
                system_prompt=system_prompt,
                user_message=user_message,
                model=self._config.orchestrator_model,
            )
            data = result["data"]
            synthesis_tokens = result["input_tokens"] + result["output_tokens"]
        except Exception as exc:
            logger.error("Synthesis failed: %s", exc)
            return self._fallback_merge(query, worker_results)

        # Parse synthesis result (wrapped in try/except for fallback on parse errors)
        try:
            if not isinstance(data, dict):
                raise ValueError(f"Synthesis returned non-dict: {type(data)}")

            return ComposedKnowledge(
                query=query.question,
                summary=str(data.get("summary", "")),
                claims=parse_claims(data.get("claims", [])),
                worker_results=worker_results,
                overall_confidence=parse_confidence(
                    data.get("overall_confidence", "moderate"),
                ),
                contradictions=[str(c) for c in data.get("contradictions", [])],
                gaps=[str(g) for g in data.get("gaps", [])],
                fast_path=False,
                tokens_used=synthesis_tokens,
            )
        except Exception as exc:
            logger.error("Synthesis parse failed: %s", exc)
            return self._fallback_merge(query, worker_results)

    def _fallback_merge(
        self,
        query: AgentQuery,
        worker_results: list[WorkerResult],
    ) -> ComposedKnowledge:
        """Merge worker results without LLM when synthesis fails."""
        all_claims = []
        all_gaps = []
        all_contradictions = []

        for wr in worker_results:
            all_claims.extend(wr.claims)
            all_gaps.extend(wr.gaps)
            all_contradictions.extend(wr.contradictions_found)

        # Overall confidence = lowest among claims (CONTESTED always surfaces)
        if all_claims:
            min_conf = ConfidenceLevel.HIGH
            for claim in all_claims:
                claim_order = _CONFIDENCE_ORDER.get(claim.confidence, 3)
                min_order = _CONFIDENCE_ORDER.get(min_conf, 0)
                if claim_order > min_order:
                    min_conf = claim.confidence
            overall = min_conf
        else:
            overall = ConfidenceLevel.LOW

        summary_parts = [c.claim for c in all_claims[:_FALLBACK_SUMMARY_MAX_CLAIMS]]
        summary = " ".join(summary_parts) if summary_parts else "No claims produced."

        return ComposedKnowledge(
            query=query.question,
            summary=summary,
            claims=all_claims,
            worker_results=worker_results,
            overall_confidence=overall,
            contradictions=all_contradictions,
            gaps=all_gaps,
            fast_path=False,
            tokens_used=0,
        )
