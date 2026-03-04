"""Output formatter for the Engineering Knowledge Brain.

Formats knowledge results into LLM-optimized or human-readable text.
Focuses on teaching WHY and HOW — not just listing rules.
Shows [VERIFIED] / [UNVERIFIED] tags and source citations.
"""

from __future__ import annotations

from typing import Any

from engineering_brain.core.config import BrainConfig


def format_for_llm(
    results_by_layer: dict[str, list[dict[str, Any]]],
    config: BrainConfig | None = None,
) -> str:
    """Format knowledge results for LLM injection (agent prompt).

    Produces concise, hierarchical output:
    - Principles first (WHY)
    - Patterns second (HOW to think)
    - Rules third (specific constraints with HOW to do it right)
    - Evidence last (concrete examples)
    """
    sections: list[str] = []

    # L1: Principles
    principles = results_by_layer.get("L1", [])
    if principles:
        lines = ["## Engineering Principles"]
        for p in principles:
            name = p.get("name", p.get("text", ""))
            why = p.get("why", "")
            how = p.get("how_to_apply", "")
            when = p.get("when_applies", "")
            when_not = p.get("when_not_applies", "")
            line = f"- **{name}**: {why}"
            if when:
                line += f" WHEN: {when}"
            if when_not:
                line += f" NOT WHEN: {when_not}"
            if how:
                line += f" HOW: {how}"
            lines.append(line)
        sections.append("\n".join(lines))

    # L2: Patterns
    patterns = results_by_layer.get("L2", [])
    if patterns:
        lines = ["## Design Patterns"]
        for p in patterns:
            name = p.get("name", p.get("text", ""))
            intent = p.get("intent", p.get("when_to_use", ""))
            line = f"- **{name}**: {intent}"
            example = p.get("example_good", "")
            if example:
                # Compact example (first 2 lines only)
                ex_lines = str(example).strip().split("\n")[:2]
                line += " | " + "; ".join(ex_lines)
            lines.append(line)
        sections.append("\n".join(lines))

    # L3: Rules (with WHY + HOW)
    rules = results_by_layer.get("L3", [])
    if rules:
        lines = ["## Rules (from experience)"]
        for r in rules:
            text = r.get("text", "")
            why = r.get("why", "")
            how = r.get("how_to_do_right", "")
            reinforcement = r.get("reinforcement_count", 0)
            severity = r.get("severity", "medium")

            tag = f"[{severity.upper()}]"
            validation = r.get("validation_status", "unvalidated")
            if validation in ("cross_checked", "human_verified"):
                tag += "[VERIFIED]"
            else:
                tag += "[UNVERIFIED]"
            if reinforcement:
                tag += f"[{reinforcement}x]"

            when = r.get("when_applies", "")
            when_not = r.get("when_not_applies", "")

            line = f"- {tag} {text}"
            if when:
                line += f" WHEN: {when}"
            if when_not:
                line += f" NOT WHEN: {when_not}"
            if why:
                line += f" WHY: {why}"
            if how:
                line += f" DO: {how}"
            # Prediction rendering
            pred_if = r.get("prediction_if", "")
            pred_then = r.get("prediction_then", "")
            if pred_if and pred_then:
                tested = int(r.get("prediction_tested_count", 0))
                succeeded = int(r.get("prediction_success_count", 0))
                if tested > 0:
                    rate = succeeded / tested * 100
                    line += f" PREDICT: IF {pred_if} THEN {pred_then} (tested {succeeded}/{tested} = {rate:.0f}%)"
                else:
                    line += f" PREDICT: IF {pred_if} THEN {pred_then} (untested)"
            lines.append(line)
            # Source citations (max 2, shortened)
            sources = r.get("sources", [])
            if sources:
                src_parts = []
                for src in sources[:2]:
                    url = src.get("url", "") if isinstance(src, dict) else ""
                    if url:
                        src_parts.append(_shorten_url(url))
                if src_parts:
                    lines.append(f"  -> Sources: {' | '.join(src_parts)}")
        sections.append("\n".join(lines))

    # L4: Evidence (examples)
    evidence = results_by_layer.get("L4", [])
    if evidence:
        lines = ["## Examples"]
        for e in evidence:
            quality = e.get("quality", "good")
            code = e.get("code", e.get("description", ""))
            explanation = e.get("explanation", e.get("lesson_learned", ""))
            marker = "GOOD" if quality == "good" else "BAD"
            line = f"- [{marker}] {explanation}"
            if code:
                code_preview = str(code).strip().split("\n")[0][:80]
                line += f" | `{code_preview}`"
            lines.append(line)
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def _shorten_url(url: str, max_len: int = 60) -> str:
    """Shorten URL to domain+path for display."""
    url = url.replace("https://", "").replace("http://", "")
    if len(url) > max_len:
        url = url[: max_len - 3] + "..."
    return url


def format_for_human(
    results_by_layer: dict[str, list[dict[str, Any]]],
    config: BrainConfig | None = None,
) -> str:
    """Format knowledge results for human reading (documentation, maps).

    More verbose than LLM format — includes full examples and explanations.
    """
    sections: list[str] = []

    # L1: Principles
    principles = results_by_layer.get("L1", [])
    if principles:
        lines = ["# Engineering Principles", ""]
        for p in principles:
            name = p.get("name", p.get("text", ""))
            why = p.get("why", "")
            how = p.get("how_to_apply", "")
            mental_model = p.get("mental_model", "")
            when = p.get("when_applies", "")
            when_not = p.get("when_not_applies", "")
            lines.append(f"## {name}")
            if why:
                lines.append(f"**Why**: {why}")
            if when:
                lines.append(f"**When**: {when}")
            if when_not:
                lines.append(f"**When NOT**: {when_not}")
            if how:
                lines.append(f"**How**: {how}")
            if mental_model:
                lines.append(f"**Mental Model**: {mental_model}")
            lines.append("")
        sections.append("\n".join(lines))

    # L2: Patterns
    patterns = results_by_layer.get("L2", [])
    if patterns:
        lines = ["# Design Patterns", ""]
        for p in patterns:
            name = p.get("name", "")
            intent = p.get("intent", "")
            when = p.get("when_to_use", "")
            when_not = p.get("when_not_to_use", "")
            good = p.get("example_good", "")
            bad = p.get("example_bad", "")
            lines.append(f"## {name}")
            if intent:
                lines.append(f"**Intent**: {intent}")
            if when:
                lines.append(f"**When to use**: {when}")
            if when_not:
                lines.append(f"**When NOT to use**: {when_not}")
            if good:
                lines.append(f"**Good example**:\n```\n{good.strip()}\n```")
            if bad:
                lines.append(f"**Bad example**:\n```\n{bad.strip()}\n```")
            lines.append("")
        sections.append("\n".join(lines))

    # L3: Rules
    rules = results_by_layer.get("L3", [])
    if rules:
        lines = ["# Rules", ""]
        for r in rules:
            rid = r.get("id", "")
            text = r.get("text", "")
            why = r.get("why", "")
            how = r.get("how_to_do_right", "")
            severity = r.get("severity", "medium")
            reinforcement = r.get("reinforcement_count", 0)
            good = r.get("example_good", "")
            bad = r.get("example_bad", "")

            validation = r.get("validation_status", "unvalidated")
            lines.append(f"## {rid}: {text}")
            when = r.get("when_applies", "")
            when_not = r.get("when_not_applies", "")
            lines.append(
                f"**Severity**: {severity} | **Reinforced**: {reinforcement}x | **Validation**: {validation}"
            )
            if why:
                lines.append(f"**Why**: {why}")
            if when:
                lines.append(f"**When**: {when}")
            if when_not:
                lines.append(f"**When NOT**: {when_not}")
            if how:
                lines.append(f"**How to do it right**: {how}")
            if good:
                lines.append(f"**Good**:\n```\n{good.strip()}\n```")
            if bad:
                lines.append(f"**Bad**:\n```\n{bad.strip()}\n```")
            # Prediction fields
            pred_if = r.get("prediction_if", "")
            pred_then = r.get("prediction_then", "")
            if pred_if and pred_then:
                lines.append(f"**Prediction**: IF {pred_if} THEN {pred_then}")
                tested = int(r.get("prediction_tested_count", 0))
                succeeded = int(r.get("prediction_success_count", 0))
                if tested > 0:
                    rate = succeeded / tested * 100
                    lines.append(f"**Prediction Accuracy**: {succeeded}/{tested} ({rate:.0f}%)")
                else:
                    lines.append("**Prediction Accuracy**: untested")
            # Full source bibliography
            sources = r.get("sources", [])
            if sources:
                lines.append("")
                lines.append("**Sources**:")
                for src in sources:
                    if isinstance(src, dict):
                        stype = src.get("source_type", "").upper().replace("_", " ")
                        title = src.get("title", "")
                        url = src.get("url", "")
                        votes = src.get("vote_count")
                        accepted = src.get("is_accepted_answer", False)
                        cvss = src.get("cvss_score")
                        extra = ""
                        if votes is not None:
                            extra += f" ({votes} votes"
                            if accepted:
                                extra += ", accepted"
                            extra += ")"
                        if cvss is not None:
                            extra += f" [CVSS {cvss}]"
                        lines.append(f"- [{stype}] {title}{extra} — {url}")
            lines.append("")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)
