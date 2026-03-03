"""Proactive Knowledge Push — surfaces implicit knowledge gaps.

The per-task query (Phase B) uses explicit tags from auto_tag_task.
Proactive push discovers IMPLICIT knowledge — things the task doesn't
mention but that are relevant based on:

1. Technology implications (Flask → CORS, CSRF, session management)
2. Domain proximity (if task touches "api" → also check "security", "auth")
3. Historical failure patterns (if similar tasks failed → push corrective rules)
4. Cross-file dependencies (if task modifies file A → push rules for importers of A)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PushRecommendation:
    """A single proactive knowledge recommendation."""

    node_id: str
    title: str
    content: str
    push_reason: str       # WHY this was pushed (human-readable)
    signal: str            # "implication" | "proximity" | "failure_pattern" | "dependency"
    confidence: float      # 0.0-1.0


# ──────────────────────────────────────────────────────────────────────────
# Domain proximity graph — adjacent domains that often co-occur in failures
# ──────────────────────────────────────────────────────────────────────────
_DOMAIN_ADJACENCY: dict[str, list[str]] = {
    "api": ["security", "reliability", "testing"],
    "security": ["api", "database", "testing"],
    "database": ["security", "performance", "reliability"],
    "ui": ["performance", "testing", "accessibility"],
    "performance": ["database", "reliability", "observability"],
    "reliability": ["performance", "api", "observability"],
    "observability": ["reliability", "devops"],
    "devops": ["reliability", "observability", "security"],
    "architecture": ["testing", "performance", "reliability"],
    "testing": ["api", "security", "architecture"],
    "ai_ml": ["performance", "api", "reliability"],
    "data_engineering": ["database", "performance", "reliability"],
}


def _get_brain():
    """Get brain instance (lazy import to avoid circular deps)."""
    try:
        from engineering_brain.retrieval.task_knowledge import _get_brain as _gb
        return _gb()
    except Exception:
        return None


def _extract_task_description(task: dict[str, Any]) -> str:
    """Extract description text from a task dict."""
    for f in ("description", "instruction", "task_description", "task_prompt", "prompt", "objective"):
        v = task.get(f, "")
        if v and len(str(v)) > 20:
            return str(v)
    return str(task.get("name", ""))


class ProactivePush:
    """Generates proactive push recommendations for a task.

    Combines 4 signals:
    1. Technology Implication Graph (TIG) expansion
    2. Domain proximity via adjacency graph
    3. Historical failure patterns from postmortem/A-MEM
    4. Cross-file dependency analysis
    """

    def __init__(self, brain: Any):
        self.brain = brain

    def generate_push(
        self,
        task: dict[str, Any],
        state: dict[str, Any],
        max_items: int = 5,
    ) -> list[PushRecommendation]:
        """Generate proactive push recommendations for a task."""
        recommendations: list[PushRecommendation] = []

        # Signal 1: TIG expansion — find technologies implied but not tagged
        recommendations.extend(self._tig_expansion(task))

        # Signal 2: Domain proximity — adjacent domains from adjacency graph
        recommendations.extend(self._domain_proximity(task))

        # Signal 3: Historical failures — learn from postmortem/A-MEM
        recommendations.extend(self._failure_patterns(task, state))

        # Signal 4: Cross-file deps — if task touches file A, what else matters?
        recommendations.extend(self._dependency_analysis(task, state))

        # Deduplicate and rank
        return self._rank_and_deduplicate(recommendations, max_items=max_items)

    def _tig_expansion(self, task: dict[str, Any]) -> list[PushRecommendation]:
        """Find knowledge for implied technologies not explicitly in task description."""
        tags = task.get("knowledge_tags", [])
        expanded_domains = task.get("knowledge_domains", [])
        provenance = task.get("knowledge_provenance", {})
        task_desc = _extract_task_description(task).lower()

        # Find domains that were TIG-inferred (not explicitly in description)
        implicit_domains = [
            d for d in expanded_domains
            if d not in task_desc and provenance.get(d) == "tig"
        ]

        if not implicit_domains:
            return []

        _budget = int(os.getenv("BRAIN_PUSH_BUDGET", "20000"))
        try:
            result = self.brain.query(
                task_description=f"Common pitfalls and best practices for {', '.join(implicit_domains)}",
                domains=implicit_domains,
                budget_chars=_budget,
            )
            if result.formatted_text:
                # Build recommendations from the query result
                recs = []
                for layer in (result.rules, result.patterns):
                    for node in layer:
                        nid = node.get("id", "")
                        title = node.get("title", node.get("name", ""))
                        content = node.get("description", node.get("content", ""))[:300]
                        if nid and title:
                            recs.append(PushRecommendation(
                                node_id=nid,
                                title=title,
                                content=content,
                                push_reason=f"Implied by technologies: {', '.join(implicit_domains[:3])}",
                                signal="implication",
                                confidence=0.7,
                            ))
                return recs[:3]
        except Exception as e:
            logger.debug(f"[PUSH] TIG expansion failed: {e}")

        return []

    def _domain_proximity(self, task: dict[str, Any]) -> list[PushRecommendation]:
        """Push knowledge from adjacent domains that the task doesn't mention."""
        explicit_domains = set(task.get("knowledge_domains", []))
        task_desc = _extract_task_description(task).lower()

        # Find adjacent domains not already in task
        adjacent: set[str] = set()
        for domain in explicit_domains:
            for adj in _DOMAIN_ADJACENCY.get(domain, []):
                if adj not in explicit_domains and adj not in task_desc:
                    adjacent.add(adj)

        if not adjacent:
            return []

        # Pick top 2 most commonly adjacent domains
        adjacent_list = sorted(adjacent)[:2]

        _budget = int(os.getenv("BRAIN_PUSH_BUDGET", "20000"))
        try:
            result = self.brain.query(
                task_description=f"Critical rules when {', '.join(explicit_domains)} interacts with {', '.join(adjacent_list)}",
                domains=adjacent_list,
                budget_chars=_budget,
            )
            if result.formatted_text:
                recs = []
                for node in (result.rules or []):
                    nid = node.get("id", "")
                    title = node.get("title", node.get("name", ""))
                    content = node.get("description", node.get("content", ""))[:300]
                    if nid and title:
                        recs.append(PushRecommendation(
                            node_id=nid,
                            title=title,
                            content=content,
                            push_reason=f"Adjacent domain: {', '.join(adjacent_list)} (task uses {', '.join(list(explicit_domains)[:2])})",
                            signal="proximity",
                            confidence=0.5,
                        ))
                return recs[:2]
        except Exception as e:
            logger.debug(f"[PUSH] Domain proximity failed: {e}")

        return []

    def _failure_patterns(
        self,
        task: dict[str, Any],
        state: dict[str, Any],
    ) -> list[PushRecommendation]:
        """Push knowledge based on historical failure patterns."""
        deliverable = task.get("deliverable", "")
        tags = task.get("knowledge_tags", [])
        recs: list[PushRecommendation] = []

        # Check feed_forward from previous sprint (postmortem learnings)
        feed_forward = state.get("_prev_sprint_feedback", {})
        spec_quality_issues = feed_forward.get("spec_quality_issues", [])
        for issue in spec_quality_issues[:3]:
            if isinstance(issue, dict):
                desc = issue.get("description", str(issue))
            else:
                desc = str(issue)
            if desc:
                recs.append(PushRecommendation(
                    node_id=f"postmortem:{hash(desc) % 10000}",
                    title="Previous Sprint Issue",
                    content=desc[:300],
                    push_reason="Similar issue in previous sprint postmortem",
                    signal="failure_pattern",
                    confidence=0.6,
                ))

        # Check A-MEM corrective actions
        try:
            from pipeline_autonomo.amem_integration import get_amem_integration
            amem = get_amem_integration()
            _query = f"failures in {deliverable} {' '.join(tags[:3])}"
            _context = amem.get_relevant_context(
                query=_query,
                max_notes=3,
            )
            if _context and len(_context) > 50:
                recs.append(PushRecommendation(
                    node_id="amem:corrective_actions",
                    title="Historical Corrective Actions",
                    content=_context[:500],
                    push_reason="A-MEM: similar tasks had failures requiring these fixes",
                    signal="failure_pattern",
                    confidence=0.65,
                ))
        except Exception:
            pass  # A-MEM not available

        return recs[:2]

    def _dependency_analysis(
        self,
        task: dict[str, Any],
        state: dict[str, Any],
    ) -> list[PushRecommendation]:
        """Push rules for files that depend on the file being modified."""
        deliverable = task.get("deliverable", "") or (task.get("deliverables", [""])[0] if task.get("deliverables") else "")
        if not deliverable:
            return []

        # Check if other tasks in the sprint depend on this file
        granular_tasks = state.get("granular_tasks", [])
        dependent_files: list[str] = []
        for other in granular_tasks:
            deps = other.get("depends_on", [])
            other_del = other.get("deliverable", "") or (other.get("deliverables", [""])[0] if other.get("deliverables") else "")
            if deliverable in str(deps) and other_del != deliverable:
                dependent_files.append(other_del)

        if not dependent_files:
            return []

        return [PushRecommendation(
            node_id="dep:cross_file",
            title="Cross-File Dependencies",
            content=(
                f"This file ({deliverable}) is depended on by: {', '.join(dependent_files[:5])}. "
                f"Changes to public API (function signatures, return types, imports) "
                f"MUST maintain backward compatibility or update all dependents."
            ),
            push_reason=f"{len(dependent_files)} file(s) depend on this deliverable",
            signal="dependency",
            confidence=0.8,
        )]

    def _rank_and_deduplicate(
        self,
        recommendations: list[PushRecommendation],
        max_items: int = 5,
    ) -> list[PushRecommendation]:
        """Deduplicate by node_id and rank by confidence."""
        seen: set[str] = set()
        unique: list[PushRecommendation] = []
        for r in recommendations:
            if r.node_id not in seen:
                seen.add(r.node_id)
                unique.append(r)
        unique.sort(key=lambda r: r.confidence, reverse=True)
        return unique[:max_items]
