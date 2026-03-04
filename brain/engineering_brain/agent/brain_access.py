"""Read-only facade for agent workers to access brain knowledge.

Workers never modify the brain. This facade exposes only the query methods
they need: think(), get_contradictions(), get_gaps(), format_context().
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engineering_brain.core.brain import Brain

logger = logging.getLogger(__name__)

# Limits for format_context output
_DEFAULT_MAX_CONTEXT_CHARS = 8000
_MAX_CONTEXT_ITEMS = 5


class BrainAccess:
    """Read-only brain facade for agent workers."""

    def __init__(self, brain: Brain) -> None:
        self._brain = brain

    def think(
        self,
        question: str,
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Query the brain with epistemic reasoning.

        Returns a dict with:
        - text: formatted knowledge text
        - confidence: overall confidence level
        - contradictions: list of contradiction dicts
        - gaps: list of gap dicts
        - nodes_consulted: count of nodes in result
        """
        try:
            result = self._brain.think(
                task_description=question,
                technologies=technologies,
                domains=domains,
            )
            return {
                "text": result.enhanced_text,
                "confidence": result.overall_confidence,
                "contradictions": result.contradictions,
                "gaps": result.gaps,
                "guardrails": result.base_result.guardrails,
                "nodes_consulted": result.base_result.total_nodes_queried,
            }
        except Exception as exc:
            logger.warning("brain.think() failed for worker: %s", exc)
            return {
                "text": "",
                "confidence": "unknown",
                "contradictions": [],
                "gaps": [],
                "guardrails": None,
                "nodes_consulted": 0,
            }

    def query(
        self,
        question: str,
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Simple brain query (no epistemic reasoning).

        Returns a dict with:
        - text: formatted knowledge text
        - nodes_consulted: count
        """
        try:
            result = self._brain.query(
                task_description=question,
                technologies=technologies,
                domains=domains,
            )
            return {
                "text": result.formatted_text,
                "guardrails": result.guardrails,
                "nodes_consulted": result.total_nodes_queried,
            }
        except Exception as exc:
            logger.warning("brain.query() failed for worker: %s", exc)
            return {"text": "", "guardrails": None, "nodes_consulted": 0}

    def get_contradictions(self, domain: str = "") -> list[dict[str, Any]]:
        """Get contradictions, optionally filtered by domain."""
        try:
            all_contradictions = self._brain.detect_contradictions()
            if not domain:
                return all_contradictions
            return [
                c
                for c in all_contradictions
                if domain.lower() in str(c.get("domains", "")).lower()
                or domain.lower() in str(c.get("node_a_id", "")).lower()
                or domain.lower() in str(c.get("node_b_id", "")).lower()
            ]
        except Exception as exc:
            logger.warning("detect_contradictions() failed: %s", exc)
            return []

    def get_gaps(self, domain: str = "") -> list[dict[str, Any]]:
        """Get knowledge gaps, optionally filtered by domain."""
        try:
            all_gaps = self._brain.analyze_gaps()
            if not domain:
                return all_gaps
            return [
                g
                for g in all_gaps
                if domain.lower() in str(g.get("domain", "")).lower()
                or domain.lower() in str(g.get("technology", "")).lower()
            ]
        except Exception as exc:
            logger.warning("analyze_gaps() failed: %s", exc)
            return []

    def format_context(
        self,
        question: str,
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
        max_chars: int = _DEFAULT_MAX_CONTEXT_CHARS,
    ) -> str:
        """Build a concise knowledge context string for an LLM prompt.

        Combines think() output into a single text block suitable for
        inclusion in a worker's user message.
        """
        result = self.think(question, technologies=technologies, domains=domains)
        text = result.get("text", "")

        parts = []
        if text:
            parts.append("## Brain Knowledge\n" + text)

        contradictions = result.get("contradictions", [])
        if contradictions:
            parts.append("\n## Contradictions")
            for c in contradictions[:_MAX_CONTEXT_ITEMS]:
                node_a = c.get("node_a_id", "?")
                node_b = c.get("node_b_id", "?")
                severity = c.get("severity", "?")
                parts.append(f"- {node_a} vs {node_b} (severity: {severity})")

        gaps = result.get("gaps", [])
        if gaps:
            parts.append("\n## Knowledge Gaps")
            for g in gaps[:_MAX_CONTEXT_ITEMS]:
                parts.append(
                    f"- {g.get('domain', '?')}: {g.get('description', g.get('technology', '?'))}"
                )

        context = "\n".join(parts)
        if len(context) > max_chars:
            context = context[:max_chars] + "\n\n[... truncated ...]"

        return context

    @property
    def stats(self) -> dict[str, Any]:
        """Brain statistics for diagnostic output."""
        try:
            return self._brain.stats()
        except Exception as exc:
            logger.warning("Failed to collect brain stats: %s", exc)
            return {}
