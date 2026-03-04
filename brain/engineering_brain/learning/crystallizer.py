"""Upgraded knowledge crystallizer for the Engineering Knowledge Brain.

Converts findings (L4 evidence) into rules (L3) with mandatory WHY + HOW fields.
This is the key transformation from "decoreba" to real understanding:
- Old: "Don't use CORS allowed_origins=[]"
- New: "Don't use CORS allowed_origins=[] | WHY: Empty list behavior varies by Flask
        version — not reliably deny-all | HOW: Use 'same-origin' string or explicit URL"
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from typing import Any

from engineering_brain.adapters.base import GraphAdapter
from engineering_brain.core.schema import EdgeType, NodeType
from engineering_brain.core.types import Finding, Rule

logger = logging.getLogger(__name__)


class KnowledgeCrystallizer:
    """Converts findings into rules with WHY + HOW understanding."""

    def __init__(self, graph: GraphAdapter, embedder: Any = None) -> None:
        self._graph = graph
        self._embedder = embedder  # BrainEmbedder instance (optional)

    def learn_from_finding(
        self,
        description: str,
        severity: str = "medium",
        resolution: str = "",
        lesson: str = "",
        hl_layer: str = "",
        file_path: str = "",
        line: int | None = None,
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> str | None:
        """Learn from a finding — create evidence and optionally crystallize into a rule.

        Returns the finding ID if stored successfully, None otherwise.
        """
        # 1. Create L4 finding node
        finding_id = _generate_finding_id(description, "", file_path, line)
        finding = Finding(
            id=finding_id,
            finding_type="bug" if severity in ("critical", "high") else "quality",
            description=description,
            severity=severity,
            file_path=file_path,
            line=line,
            resolution=resolution,
            lesson_learned=lesson,
        )

        self._graph.add_node(
            NodeType.FINDING.value,
            finding_id,
            finding.model_dump(mode="json"),
        )

        # 2. Check if a similar rule already exists
        existing_rule = self._find_similar_rule(description)
        if existing_rule:
            # Reinforce existing rule
            self._reinforce_rule(existing_rule, finding_id)
            return finding_id

        # 3. If resolution + lesson are provided, crystallize into a new rule
        if resolution and lesson:
            rule_id = self._crystallize_rule(
                description=description,
                resolution=resolution,
                lesson=lesson,
                severity=severity,
                finding_id=finding_id,
                technologies=technologies or [],
                domains=domains or [],
            )
            if rule_id:
                logger.info("Crystallized new rule %s from finding %s", rule_id, finding_id)

        return finding_id

    def _find_similar_rule(self, description: str) -> dict[str, Any] | None:
        """Find an existing rule that matches this finding's description.

        Uses embedding cosine similarity as the primary signal (SOTA: semantic match).
        Falls back to key-term counting when embedder is unavailable.
        Reference pattern: cluster_promoter.py _rule_similarity() (0.60 embed blend).
        """
        # 1. Try embedding similarity first (primary signal)
        if self._embedder:
            try:
                match = self._find_similar_rule_semantic(description)
                if match is not None:
                    return match
            except Exception as exc:
                logger.debug("Semantic similarity search failed, falling back to key-term: %s", exc)

        # 2. Fallback: original key-term matching
        return self._find_similar_rule_keyterm(description)

    def _find_similar_rule_semantic(self, description: str) -> dict[str, Any] | None:
        """Find similar rule using embedding cosine similarity.

        Embeds the description and compares against all rules in the graph.
        Threshold: 0.75 (high-confidence semantic match).
        """
        desc_vec = self._embedder.embed_text(description)
        if not desc_vec:
            return None

        # Get all rules
        rules = self._graph.query(label=NodeType.RULE.value, limit=500)

        best_rule: dict[str, Any] | None = None
        best_score = 0.0

        for rule in rules:
            rule_text = str(rule.get("text", ""))
            if not rule_text:
                continue
            rule_vec = self._embedder.embed_text(rule_text)
            if not rule_vec:
                continue
            score = _cosine_similarity(desc_vec, rule_vec)
            if score > best_score:
                best_score = score
                best_rule = rule

        if best_score >= 0.75 and best_rule is not None:
            # Check for contradiction before returning
            desc_lower = description.lower()
            rule_text = str(best_rule.get("text", "")).lower()
            if _is_opposing_polarity(desc_lower, rule_text):
                self._create_conflict_edge(best_rule, description)
                return None
            return best_rule

        return None

    def _find_similar_rule_keyterm(self, description: str) -> dict[str, Any] | None:
        """Find similar rule using key-term matching (original fallback)."""
        terms = _extract_key_terms(description)
        if not terms:
            return None

        for term in terms[:3]:
            results = self._graph.query(
                label=NodeType.RULE.value,
                filters={"text": term},
                limit=5,
            )
            for rule in results:
                rule_text = str(rule.get("text", "")).lower()
                desc_lower = description.lower()
                shared = sum(1 for t in terms if t.lower() in rule_text)
                if shared >= 2:
                    if _is_opposing_polarity(desc_lower, rule_text):
                        self._create_conflict_edge(rule, description)
                        return None
                    return rule

        return None

    def _create_conflict_edge(self, existing_rule: dict[str, Any], new_description: str) -> None:
        """Create CONFLICTS_WITH edge when a finding contradicts an existing rule."""
        rule_id = existing_rule.get("id", "")
        if not rule_id:
            return
        # Create a temporary finding node for the conflict
        conflict_id = _generate_finding_id(new_description, "conflict")
        self._graph.add_node(
            NodeType.FINDING.value,
            conflict_id,
            {"id": conflict_id, "description": new_description, "finding_type": "contradiction"},
        )
        self._graph.add_edge(rule_id, conflict_id, EdgeType.CONFLICTS_WITH.value)
        logger.info("Created CONFLICTS_WITH edge: %s ↔ %s", rule_id, conflict_id)

    def _reinforce_rule(self, rule: dict[str, Any], finding_id: str) -> None:
        """Reinforce an existing rule with new evidence."""
        rule_id = rule.get("id", "")
        if not rule_id:
            return

        current_count = int(rule.get("reinforcement_count", 0))
        current_confidence = float(rule.get("confidence", 0.5))
        source_findings = rule.get("source_findings", [])
        if isinstance(source_findings, str):
            try:
                import json

                source_findings = json.loads(source_findings)
            except Exception as exc:
                logger.debug("Failed to parse source_findings JSON: %s", exc)
                source_findings = []

        if finding_id not in source_findings:
            source_findings.append(finding_id)

        # Increase confidence with diminishing returns
        new_confidence = min(current_confidence + (1.0 - current_confidence) * 0.1, 0.99)

        self._graph.add_node(
            NodeType.RULE.value,
            rule_id,
            {
                **rule,
                "reinforcement_count": current_count + 1,
                "confidence": new_confidence,
                "last_violation": datetime.now(UTC).isoformat(),
                "source_findings": source_findings,
            },
        )

        # Add EVIDENCED_BY edge
        self._graph.add_edge(rule_id, finding_id, EdgeType.EVIDENCED_BY.value)
        logger.debug(
            "Reinforced rule %s (count=%d, confidence=%.2f)",
            rule_id,
            current_count + 1,
            new_confidence,
        )

    def _crystallize_rule(
        self,
        description: str,
        resolution: str,
        lesson: str,
        severity: str,
        finding_id: str,
        technologies: list[str],
        domains: list[str],
    ) -> str | None:
        """Crystallize a finding + resolution into a new rule with WHY + HOW."""
        rule_id = _generate_rule_id(description, technologies, domains)

        # Derive WHY from the lesson/description (LLM-enhanced with fallback)
        why = (
            lesson
            if lesson
            else (_llm_derive_why(description, resolution, lesson) or _derive_why(description))
        )

        # Derive HOW from the resolution
        how = resolution if resolution else ""

        rule = Rule(
            id=rule_id,
            text=_llm_derive_rule_text(description) or _derive_rule_text(description),
            why=why,
            how_to_do_right=how,
            severity=severity,
            technologies=technologies,
            domains=domains,
            reinforcement_count=1,
            confidence=0.3,
            source_findings=[finding_id],
        )

        success = self._graph.add_node(
            NodeType.RULE.value,
            rule_id,
            rule.model_dump(mode="json"),
        )

        if success:
            # Link rule to finding
            self._graph.add_edge(rule_id, finding_id, EdgeType.EVIDENCED_BY.value)
            # Link rule to technologies
            for tech in technologies:
                tech_id = f"tech:{tech.lower()}"
                self._graph.add_node(
                    NodeType.TECHNOLOGY.value, tech_id, {"id": tech_id, "name": tech}
                )
                self._graph.add_edge(rule_id, tech_id, EdgeType.APPLIES_TO.value)
            # Link rule to domains
            for domain in domains:
                domain_id = f"domain:{domain.lower()}"
                self._graph.add_node(
                    NodeType.DOMAIN.value, domain_id, {"id": domain_id, "name": domain}
                )
                self._graph.add_edge(rule_id, domain_id, EdgeType.IN_DOMAIN.value)
            return rule_id

        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors. Returns 0.0-1.0."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _generate_finding_id(
    description: str,
    sprint: str,
    file_path: str = "",
    line: int | None = None,
) -> str:
    """Generate a deterministic finding ID.

    Includes file_path and line to avoid collisions when the same
    description appears in different files/locations within a sprint.
    """
    parts = [description, sprint, file_path]
    if line is not None:
        parts.append(str(line))
    content = ":".join(parts)
    h = hashlib.sha256(content.encode()).hexdigest()[:12]
    return f"F-{h}"


def _generate_rule_id(
    description: str,
    technologies: list[str] | None = None,
    domains: list[str] | None = None,
) -> str:
    """Generate a deterministic rule ID.

    Includes technologies and domains to avoid collisions when similar
    descriptions apply to different tech stacks or domains.
    """
    parts = [description]
    if technologies:
        parts.append(",".join(sorted(t.lower() for t in technologies)))
    if domains:
        parts.append(",".join(sorted(d.lower() for d in domains)))
    content = ":".join(parts)
    h = hashlib.sha256(content.encode()).hexdigest()[:8]
    return f"CR-{h}"


def _extract_key_terms(text: str) -> list[str]:
    """Extract significant terms from text for matching."""
    # Remove common words and keep significant terms
    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "dare",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "up",
        "about",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "and",
        "but",
        "or",
        "nor",
        "not",
        "no",
        "so",
        "if",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "used",
        "using",
    }
    words = re.findall(r"\b\w{3,}\b", text.lower())
    return [w for w in words if w not in stop_words]


def _llm_derive_why(description: str, resolution: str, lesson: str) -> str | None:
    """LLM-generated WHY explanation. Returns None on failure."""
    from engineering_brain.llm_helpers import brain_llm_call, is_llm_enabled

    if not is_llm_enabled("BRAIN_LLM_CRYSTALLIZATION"):
        return None
    system = (
        "Write the WHY for an engineering rule. Explain the root cause or principle "
        "that makes this important. 1-2 sentences, max 200 chars. "
        "Do NOT restate the description."
    )
    user = (
        f"Description: {description[:300]}\nResolution: {resolution[:200]}\nLesson: {lesson[:200]}"
    )
    result = brain_llm_call(system, user, max_tokens=100)
    return result if result and len(result) <= 300 else None


def _llm_derive_rule_text(description: str) -> str | None:
    """LLM-generated prescriptive rule text. Returns None on failure."""
    from engineering_brain.llm_helpers import brain_llm_call, is_llm_enabled

    if not is_llm_enabled("BRAIN_LLM_CRYSTALLIZATION"):
        return None
    system = (
        "Write a concise engineering rule from a finding. "
        "Start with Always/Never/Use/Avoid. Max 150 chars. Return ONLY the rule."
    )
    result = brain_llm_call(system, f"Finding: {description[:500]}", max_tokens=80)
    return result if result and 10 <= len(result) <= 200 else None


def _derive_rule_text(description: str) -> str:
    """Derive a concise rule text from a finding description."""
    # Truncate to first sentence or 150 chars
    text = description.strip()
    for sep in (". ", "! ", "? ", "\n"):
        idx = text.find(sep)
        if 0 < idx < 150:
            return text[: idx + 1]
    return text[:150]


def _derive_why(description: str) -> str:
    """Derive a WHY explanation from the finding description."""
    return f"This was observed: {description[:200]}"


# Negation patterns for opposing polarity detection
_NEGATION_PAIRS: list[tuple[str, str]] = [
    ("always", "never"),
    ("must", "must not"),
    ("should", "should not"),
    ("require", "avoid"),
    ("use", "don't use"),
    ("enable", "disable"),
    ("allow", "deny"),
    ("accept", "reject"),
    ("include", "exclude"),
    ("do", "don't"),
    ("recommended", "not recommended"),
    ("safe", "unsafe"),
    ("secure", "insecure"),
]


def _is_opposing_polarity(text_a: str, text_b: str) -> bool:
    """Check if two descriptions have opposing polarity via keyword heuristic.

    Known limitations: substring matching may produce false positives
    (e.g., unrelated sentences containing "always" and "never") and false
    negatives (e.g., "recommended" vs "avoid" not paired). The semantic
    embedding gate (0.75 threshold) is the primary filter; this is secondary.
    """
    for pos, neg in _NEGATION_PAIRS:
        # A says positive, B says negative
        if pos in text_a and neg in text_b:
            return True
        # A says negative, B says positive
        if neg in text_a and pos in text_b:
            return True
    return False
