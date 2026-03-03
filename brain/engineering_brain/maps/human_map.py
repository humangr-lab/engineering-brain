"""Human-readable knowledge map generator.

Generates a browsable, hierarchical documentation of all knowledge
in the brain. Useful for auditing, teaching, and reviewing what
agents know.
"""

from __future__ import annotations

from typing import Any

from engineering_brain.adapters.base import GraphAdapter
from engineering_brain.core.schema import NodeType


def generate_human_map(graph: GraphAdapter) -> str:
    """Generate a full human-readable knowledge map.

    Returns a markdown-formatted document with all knowledge
    organized by layer.
    """
    sections: list[str] = []
    sections.append("# Engineering Knowledge Brain\n")

    # L0 — Axioms
    axioms = graph.query(label=NodeType.AXIOM.value, limit=100)
    if axioms:
        sections.append("## L0: Axioms (Immutable Truths)\n")
        for ax in sorted(axioms, key=lambda x: x.get("id", "")):
            sections.append(f"### {ax.get('id', '?')}")
            sections.append(f"**Statement**: {ax.get('statement', '')}")
            if ax.get("formal_notation"):
                sections.append(f"**Formal**: `{ax['formal_notation']}`")
            sections.append(f"**Domain**: {ax.get('domain', 'general')}\n")

    # L1 — Principles
    principles = graph.query(label=NodeType.PRINCIPLE.value, limit=200)
    if principles:
        sections.append("## L1: Principles (Stable Wisdom)\n")
        for p in sorted(principles, key=lambda x: x.get("id", "")):
            sections.append(f"### {p.get('id', '?')}: {p.get('name', '?')}")
            sections.append(f"**WHY**: {p.get('why', '-')}")
            sections.append(f"**HOW**: {p.get('how_to_apply', '-')}")
            if p.get("mental_model"):
                sections.append(f"**Mental Model**: {p['mental_model']}")
            if p.get("domains"):
                sections.append(f"**Domains**: {', '.join(p['domains'])}")
            sections.append("")

    # L2 — Patterns
    patterns = graph.query(label=NodeType.PATTERN.value, limit=500)
    if patterns:
        sections.append("## L2: Patterns (Established Practices)\n")
        for pat in sorted(patterns, key=lambda x: x.get("id", "")):
            sections.append(f"### {pat.get('id', '?')}: {pat.get('name', '?')}")
            sections.append(f"**Intent**: {pat.get('intent', '-')}")
            sections.append(f"**When to use**: {pat.get('when_to_use', '-')}")
            if pat.get("when_not_to_use"):
                sections.append(f"**When NOT to use**: {pat['when_not_to_use']}")
            if pat.get("languages"):
                sections.append(f"**Languages**: {', '.join(pat['languages'])}")
            if pat.get("example_good"):
                sections.append(f"**Good example**:\n```\n{pat['example_good']}\n```")
            if pat.get("example_bad"):
                sections.append(f"**Bad example**:\n```\n{pat['example_bad']}\n```")
            sections.append("")

    # L3 — Rules
    rules = graph.query(label=NodeType.RULE.value, limit=1000)
    if rules:
        sections.append("## L3: Rules (Learned Constraints)\n")
        # Group by severity
        for sev in ("critical", "high", "medium", "low"):
            sev_rules = [r for r in rules if r.get("severity", "medium") == sev]
            if not sev_rules:
                continue
            sections.append(f"### Severity: {sev.upper()} ({len(sev_rules)} rules)\n")
            for r in sorted(sev_rules, key=lambda x: -int(x.get("reinforcement_count", 0))):
                conf = float(r.get("confidence", 0))
                count = int(r.get("reinforcement_count", 0))
                sections.append(f"#### {r.get('id', '?')} [{sev.upper()}] (confidence={conf:.0%}, reinforced={count}x)")
                sections.append(f"**Rule**: {r.get('text', '-')}")
                sections.append(f"**WHY**: {r.get('why', '-')}")
                sections.append(f"**HOW**: {r.get('how_to_do_right', '-')}")
                if r.get("technologies"):
                    sections.append(f"**Technologies**: {', '.join(r['technologies'])}")
                sections.append("")

    # Summary
    total = len(axioms) + len(principles) + len(patterns) + len(rules)
    sections.append("---\n")
    sections.append(f"**Total knowledge nodes**: {total}")
    sections.append(f"- L0 Axioms: {len(axioms)}")
    sections.append(f"- L1 Principles: {len(principles)}")
    sections.append(f"- L2 Patterns: {len(patterns)}")
    sections.append(f"- L3 Rules: {len(rules)}")

    return "\n".join(sections)


def generate_layer_summary(graph: GraphAdapter) -> dict[str, Any]:
    """Generate a compact summary of knowledge distribution."""
    counts = {}
    for nt in (NodeType.AXIOM, NodeType.PRINCIPLE, NodeType.PATTERN, NodeType.RULE, NodeType.FINDING):
        counts[nt.value] = graph.count(nt.value)

    rules = graph.query(label=NodeType.RULE.value, limit=1000)
    severity_dist = {}
    for r in rules:
        sev = r.get("severity", "medium")
        severity_dist[sev] = severity_dist.get(sev, 0) + 1

    return {
        "layers": counts,
        "total": sum(counts.values()),
        "rule_severity_distribution": severity_dist,
    }
