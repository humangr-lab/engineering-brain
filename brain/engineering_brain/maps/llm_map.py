"""LLM-consumable knowledge map generator.

Generates a compact schema description optimized for LLM context windows.
This enables meta-reasoning — the LLM understands what the brain KNOWS
and can ask targeted questions.
"""

from __future__ import annotations

from engineering_brain.adapters.base import GraphAdapter
from engineering_brain.core.schema import SHARD_DOMAINS, EdgeType, Layer, NodeType


def generate_llm_schema() -> str:
    """Generate the brain's schema description for LLM context.

    This is a STATIC description — it describes the structure,
    not the contents. Useful for tool/MCP descriptions.
    """
    lines: list[str] = []
    lines.append("## Engineering Knowledge Brain Schema")
    lines.append("")
    lines.append("### Layers (6 cortical levels)")
    for layer in Layer:
        lines.append(
            f"- **{layer.value}** ({layer.name}): stability={layer.stability:.1f}, max_ttl_days={layer.max_ttl_days}"
        )
    lines.append("")

    lines.append("### Node Types")
    for nt in NodeType:
        lines.append(f"- `{nt.value}` (layer: {nt.layer})")
    lines.append("")

    lines.append("### Relationship Types")
    for et in EdgeType:
        lines.append(f"- `{et.value}`")
    lines.append("")

    lines.append("### Domains")
    lines.append(f"Available: {', '.join(SHARD_DOMAINS)}")
    lines.append("")

    lines.append("### Query API")
    lines.append("```")
    lines.append(
        'brain.query(task_description="...", technologies=["Flask"], file_type=".py", phase="exec")'
    )
    lines.append("```")
    lines.append("Returns: KnowledgeResult with formatted_text (budget-capped, layered)")

    return "\n".join(lines)


def generate_llm_inventory(graph: GraphAdapter) -> str:
    """Generate a compact inventory of what the brain currently knows.

    This is a DYNAMIC description — summarizes actual contents.
    Useful for agents to understand available knowledge before querying.
    """
    lines: list[str] = []
    lines.append("## Brain Knowledge Inventory")
    lines.append("")

    # Count per layer
    for nt in (
        NodeType.AXIOM,
        NodeType.PRINCIPLE,
        NodeType.PATTERN,
        NodeType.RULE,
        NodeType.FINDING,
    ):
        count = graph.count(nt.value)
        lines.append(f"- **{nt.value}**: {count} nodes")

    # Technology coverage
    techs = graph.query(label=NodeType.TECHNOLOGY.value, limit=100)
    if techs:
        tech_names = sorted(set(t.get("name", "") for t in techs if t.get("name")))
        lines.append(f"\n### Technologies Covered ({len(tech_names)})")
        lines.append(", ".join(tech_names))

    # Domain coverage
    domains = graph.query(label=NodeType.DOMAIN.value, limit=50)
    if domains:
        domain_names = sorted(set(d.get("name", "") for d in domains if d.get("name")))
        lines.append(f"\n### Domains Covered ({len(domain_names)})")
        lines.append(", ".join(domain_names))

    # Rule severity distribution
    rules = graph.query(label=NodeType.RULE.value, limit=1000)
    if rules:
        sev_counts: dict[str, int] = {}
        for r in rules:
            sev = r.get("severity", "medium")
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
        lines.append("\n### Rule Severity Distribution")
        for sev in ("critical", "high", "medium", "low"):
            lines.append(f"- {sev}: {sev_counts.get(sev, 0)}")

    return "\n".join(lines)
