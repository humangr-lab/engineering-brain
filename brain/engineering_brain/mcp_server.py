"""Engineering Brain MCP Server — pull-based knowledge delivery for agents.

MCP server (JSON-RPC 2.0 over stdio) that wraps the Engineering Knowledge Brain.
20 tools + 5 resources for full knowledge graph access.

Usage (stdio):
    PYTHONPATH=src python -m engineering_brain.mcp_server

Register in .mcp.json:
    {
      "mcpServers": {
        "engineering-brain": {
          "command": ".venv/bin/python",
          "args": ["-m", "engineering_brain.mcp_server"],
          "env": {"PYTHONPATH": "src"}
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy Brain singleton — delegated to centralized factory
# ---------------------------------------------------------------------------

from engineering_brain.core.brain_factory import get_brain as _get_brain  # noqa: E402


# ---------------------------------------------------------------------------
# Tool definitions (20 tools)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "brain_query",
        "description": (
            "Query the Engineering Knowledge Brain for rules, patterns, and "
            "principles relevant to your current task. Returns formatted text "
            "organized by layer: L1 Principles (WHY), L2 Patterns (HOW to think), "
            "L3 Rules (specific constraints). Use this BEFORE implementing to "
            "understand best practices, and DURING implementation when you "
            "encounter unfamiliar patterns."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "What you need to know. Be specific about the technology "
                        "and concern. E.g. 'Flask CORS security best practices' "
                        "or 'Path traversal validation in Python'."
                    ),
                },
                "technologies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Specific technologies to filter by (e.g. ['flask', 'socketio']). "
                        "Auto-detected from query if omitted."
                    ),
                },
                "file_type": {
                    "type": "string",
                    "description": "File extension being worked on (e.g. '.py', '.css', '.js').",
                },
                "budget_chars": {
                    "type": "integer",
                    "description": "Max characters to return. Default 3000.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "brain_search",
        "description": (
            "Search the Engineering Brain for rules by technology or domain. "
            "Returns a list of rule IDs and summaries for discovery. Use this "
            "to explore what the brain knows about a topic before making a "
            "targeted brain_query."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "technology": {
                    "type": "string",
                    "description": "Technology to search rules for (e.g. 'flask', 'cors', 'qdrant').",
                },
                "domain": {
                    "type": "string",
                    "description": "Domain to search (e.g. 'security', 'api', 'testing', 'ui').",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max number of rules to return. Default 10.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "brain_think",
        "description": (
            "Enhanced query with epistemic reasoning. Returns confidence tiers "
            "(VALIDATED / PROBABLE / UNCERTAIN / CONTESTED), contradiction "
            "detection between returned rules, knowledge gap identification, "
            "and metacognitive assessment of what the brain knows vs doesn't know. "
            "Use this instead of brain_query when you need to understand HOW CERTAIN "
            "the brain is about its knowledge, especially for security-critical or "
            "complex architectural decisions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "What you need to know. Be specific about the technology "
                        "and concern. E.g. 'Flask CORS security in production' "
                        "or 'WebSocket authentication best practices'."
                    ),
                },
                "technologies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Specific technologies to filter by (e.g. ['flask', 'cors']). "
                        "Auto-detected from query if omitted."
                    ),
                },
                "file_type": {
                    "type": "string",
                    "description": "File extension being worked on (e.g. '.py', '.css', '.js').",
                },
                "budget_chars": {
                    "type": "integer",
                    "description": "Max characters for enhanced output. Default 4500.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "brain_learn",
        "description": (
            "Report a finding to the Engineering Brain so it can learn from it. "
            "Use this when you discover an anti-pattern, security issue, or "
            "important lesson during implementation. The brain will crystallize "
            "this into a rule for future agents."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What was found — the problem or anti-pattern.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "How severe is this finding.",
                },
                "resolution": {
                    "type": "string",
                    "description": "How the issue was fixed or should be fixed.",
                },
                "lesson": {
                    "type": "string",
                    "description": "What to do differently next time — the prevention strategy.",
                },
            },
            "required": ["description", "severity"],
        },
    },
    {
        "name": "brain_validate",
        "description": (
            "Trigger validation of brain knowledge against external sources "
            "(PyPI, npm, NVD, StackOverflow, official docs). Returns validation "
            "progress and results. Use sparingly — makes external API calls."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "technology": {
                    "type": "string",
                    "description": "Validate rules for a specific technology (e.g. 'flask').",
                },
                "max_nodes": {
                    "type": "integer",
                    "description": "Max nodes to validate in this batch. Default 50.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "brain_stats",
        "description": (
            "Get graph statistics: node counts per layer, cache hit rates, "
            "version, health status. Quick overview of brain state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "brain_contradictions",
        "description": (
            "List detected contradictions in the knowledge graph. Returns pairs "
            "of conflicting rules with conflict severity and suggested resolution. "
            "Use this to identify areas where knowledge is contested."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Minimum contradiction severity to return. Default: all.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "brain_provenance",
        "description": (
            "Trace the origin of a specific rule or knowledge node. Returns the "
            "provenance chain showing how the knowledge was derived (evidence -> "
            "rule -> pattern -> principle). Use to understand WHY a rule exists."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "The ID of the node to trace (e.g. 'CR-SEC-001').",
                },
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "brain_communities",
        "description": (
            "List or query knowledge communities — densely-connected clusters "
            "of rules. Use for global queries like 'what security patterns exist?' "
            "or to understand knowledge graph topology."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_size": {
                    "type": "integer",
                    "description": "Minimum community size. Default 3.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "brain_feedback",
        "description": (
            "Report that a rule was unhelpful or wrong for a given context. "
            "Creates a WEAKENS edge and records feedback for active learning. "
            "This helps the brain improve over time."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {
                    "type": "string",
                    "description": "The ID of the rule that was unhelpful (e.g. 'CR-SEC-001').",
                },
                "context": {
                    "type": "string",
                    "description": "What you were trying to do when the rule was unhelpful.",
                },
                "reason": {
                    "type": "string",
                    "description": "Why the rule was unhelpful (wrong, outdated, too generic, etc.).",
                },
            },
            "required": ["rule_id", "reason"],
        },
    },
    {
        "name": "brain_pack",
        "description": (
            "Create a curated knowledge pack from a template. One-liner API: "
            "specify a template ID (security-review, code-review, architecture, "
            "incident-response, onboarding, data-pipeline, testing, api-design, "
            "performance, full-stack) and optionally filter by technology/domain. "
            "Returns a quality-scored knowledge pack with reasoning edges."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_id": {
                    "type": "string",
                    "description": (
                        "Template to use. Available: security-review, code-review, "
                        "architecture, incident-response, onboarding, data-pipeline, "
                        "testing, api-design, performance, full-stack."
                    ),
                },
                "technologies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Technologies to filter by (e.g. ['flask', 'python']).",
                },
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Domains to filter by (e.g. ['security', 'auth']).",
                },
            },
            "required": ["template_id"],
        },
    },
    {
        "name": "brain_pack_templates",
        "description": (
            "List all available pack templates. Each template is a recipe for "
            "creating a curated knowledge pack with domain-specific tools."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by tags (e.g. ['security', 'testing']).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "brain_pack_export",
        "description": (
            "Export a knowledge pack as a standalone MCP server. The exported "
            "server has ZERO dependency on engineering_brain — just Python 3.11+. "
            "Creates a directory with server.py + pack_data.json."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_id": {
                    "type": "string",
                    "description": "Template to use for the pack.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory to export to (e.g. '/tmp/my-pack').",
                },
                "technologies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Technologies to filter by.",
                },
            },
            "required": ["template_id", "output_dir"],
        },
    },
    {
        "name": "brain_pack_compose",
        "description": (
            "Compose multiple pack templates into a single merged pack. "
            "Deduplicates nodes and merges tool surfaces."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Templates to compose (e.g. ['security-review', 'code-review']).",
                },
                "technologies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Technologies to filter by.",
                },
            },
            "required": ["template_ids"],
        },
    },
    {
        "name": "brain_observe_outcome",
        "description": (
            "Record whether a query result was helpful or not. This closes the "
            "feedback loop: Thompson Sampling weights update, adaptive promotion "
            "learns from outcomes. Call this AFTER using brain_query/brain_think "
            "results to report whether they were useful."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_id": {
                    "type": "string",
                    "description": "Identifier for the query (any unique string).",
                },
                "node_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Node IDs from the query result that you used.",
                },
                "helpful": {
                    "type": "boolean",
                    "description": "Were the results helpful for your task?",
                },
                "signal_name": {
                    "type": "string",
                    "description": "Optional: which signal was most relevant (tech_match, domain_match, etc.).",
                },
            },
            "required": ["query_id", "node_ids", "helpful"],
        },
    },
    {
        "name": "brain_promotion_outcome",
        "description": (
            "Record whether a promoted knowledge node survived (stayed useful over "
            "time). Feeds the adaptive promotion policy so promotion thresholds "
            "become domain-specific and data-driven."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Knowledge domain (e.g. 'security', 'api', 'testing').",
                },
                "node_id": {
                    "type": "string",
                    "description": "The promoted node's ID.",
                },
                "promoted": {
                    "type": "boolean",
                    "description": "Whether the node was promoted.",
                },
                "survived": {
                    "type": "boolean",
                    "description": "Whether the promoted node survived (stayed useful).",
                },
            },
            "required": ["domain", "node_id", "promoted", "survived"],
        },
    },
    {
        "name": "brain_reason",
        "description": (
            "Structured epistemic reasoning. Builds reasoning chains with causal "
            "edges (PREREQUISITE, DEEPENS, ALTERNATIVE), confidence tiers per step, "
            "cross-chain synthesis, contradiction detection, and gap analysis. "
            "Use this for complex architectural decisions, cross-technology problems, "
            "or when you need to understand the reasoning structure — not just a list "
            "of rules. Returns chain-structured markdown with metacognitive assessment."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What you need to reason about.",
                },
                "technologies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Technologies involved.",
                },
                "profile": {
                    "type": "string",
                    "description": "Reasoning profile: data_engineer | security_engineer | fullstack.",
                },
                "max_chains": {
                    "type": "integer",
                    "description": "Max reasoning chains. Default 3.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "brain_reinforce",
        "description": (
            "Reinforce or weaken a rule based on evidence. Creates a STRENGTHENS "
            "or WEAKENS edge in the knowledge graph. Use this when you find concrete "
            "evidence that supports or refutes a rule — e.g. a production incident "
            "confirming a security rule, or a test proving a pattern wrong."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {
                    "type": "string",
                    "description": "The rule to reinforce/weaken (e.g. 'CR-SEC-001').",
                },
                "evidence_id": {
                    "type": "string",
                    "description": "ID of the evidence node (e.g. 'EV-INCIDENT-042').",
                },
                "positive": {
                    "type": "boolean",
                    "description": "True to strengthen the rule, False to weaken it.",
                },
            },
            "required": ["rule_id", "evidence_id", "positive"],
        },
    },
    {
        "name": "brain_prediction_outcome",
        "description": (
            "Record whether a rule's prediction was confirmed or refuted in practice. "
            "Feeds the confidence calibration system: tracks prediction_tested_count "
            "and prediction_success_count per rule. Over time this enables the brain "
            "to know which rules are reliably predictive vs over/under-confident."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {
                    "type": "string",
                    "description": "The rule whose prediction was tested (e.g. 'CR-API-003').",
                },
                "success": {
                    "type": "boolean",
                    "description": "Whether the rule's prediction was confirmed (True) or refuted (False).",
                },
            },
            "required": ["rule_id", "success"],
        },
    },
    {
        "name": "brain_mine_code",
        "description": (
            "Mine recurring patterns from Python source code via AST analysis. "
            "Extracts error handling anti-patterns, API conventions, security "
            "risks, and import clusters. Returns L4 Finding proposals with "
            "frequency and confidence scores. Use this to analyze a codebase "
            "before implementing to understand existing patterns and risks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to mine (recursive Python file analysis)",
                },
                "min_frequency": {
                    "type": "integer",
                    "description": "Minimum pattern frequency to become a Finding (default: 3)",
                    "default": 3,
                },
                "ingest": {
                    "type": "boolean",
                    "description": "If true, automatically ingest findings as L4 nodes (default: false)",
                    "default": False,
                },
            },
            "required": ["path"],
        },
    },
]

# ---------------------------------------------------------------------------
# MCP Resources (O-02)
# ---------------------------------------------------------------------------

RESOURCES: list[dict[str, Any]] = [
    {
        "uri": "brain://stats",
        "name": "Brain Statistics",
        "description": "Node counts per layer, version, health status",
        "mimeType": "application/json",
    },
    {
        "uri": "brain://health",
        "name": "Brain Health",
        "description": "Comprehensive health dashboard: cache, latency, weak rules, dead letters",
        "mimeType": "application/json",
    },
    {
        "uri": "brain://layers",
        "name": "Brain Layers",
        "description": "Knowledge hierarchy: axioms, principles, patterns, rules, findings",
        "mimeType": "application/json",
    },
    {
        "uri": "brain://gaps",
        "name": "Knowledge Gaps",
        "description": "Under-covered domains and technologies needing more rules",
        "mimeType": "application/json",
    },
    {
        "uri": "brain://version",
        "name": "Brain Version",
        "description": "Current epoch version (monotonic write counter)",
        "mimeType": "text/plain",
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def _handle_brain_query(args: dict[str, Any]) -> str:
    """Handle brain_query tool call."""
    brain = _get_brain()
    query = args.get("query", "")
    if not query:
        return "Error: 'query' parameter is required."

    technologies = args.get("technologies")
    file_type = args.get("file_type", "")
    budget_chars = args.get("budget_chars", 50000)

    result = brain.query(
        task_description=query,
        technologies=technologies,
        file_type=file_type,
        phase="exec",
        budget_chars=budget_chars,
    )

    if not result.formatted_text:
        return f"No relevant knowledge found for: {query}"

    # Record observation (non-blocking)
    rule_ids = [r.get("id", "") for r in result.rules if r.get("id")]
    brain.observe_query(
        rule_ids=rule_ids,
        query=query,
        technologies=technologies or [],
        file_type=file_type,
    )

    header = (
        f"## Engineering Brain — {result.total_nodes_queried} rules matched\n"
        f"Query: {query}\n\n"
    )
    return header + result.formatted_text


def _handle_brain_search(args: dict[str, Any]) -> str:
    """Handle brain_search tool call."""
    brain = _get_brain()
    technology = args.get("technology", "")
    domain = args.get("domain", "")
    top_k = args.get("top_k", 10)

    if not technology and not domain:
        # Return brain stats as overview
        stats = brain.stats()
        layers = stats.get("layers", {})
        total = stats.get("total", 0)
        lines = [f"Engineering Brain: {total} knowledge nodes"]
        for name, count in layers.items():
            lines.append(f"  {name}: {count}")
        return "\n".join(lines)

    # Build a search query from technology + domain
    query_parts = []
    if technology:
        query_parts.append(technology)
    if domain:
        query_parts.append(domain)
    query = " ".join(query_parts) + " rules and best practices"

    techs = [technology] if technology else None
    domains = [domain] if domain else None

    result = brain.query(
        task_description=query,
        technologies=techs,
        domains=domains,
        phase="exec",
        budget_chars=top_k * 300,  # ~300 chars per rule summary
    )

    if not result.formatted_text:
        return f"No rules found for technology={technology!r} domain={domain!r}"

    return result.formatted_text


def _handle_brain_think(args: dict[str, Any]) -> str:
    """Handle brain_think tool call."""
    brain = _get_brain()
    query = args.get("query", "")
    if not query:
        return "Error: 'query' parameter is required."

    technologies = args.get("technologies")
    file_type = args.get("file_type", "")
    budget_chars = args.get("budget_chars")

    result = brain.think(
        task_description=query,
        technologies=technologies,
        file_type=file_type,
        phase="exec",
        budget_chars=budget_chars,
    )

    if not result.enhanced_text:
        return f"No relevant knowledge found for: {query}"

    header = (
        f"## Engineering Brain — Enhanced Epistemic Query\n"
        f"Query: {query}\n"
        f"Confidence: {result.overall_confidence.upper()} | "
        f"Nodes: {result.base_result.total_nodes_queried} | "
        f"Contradictions: {len(result.contradictions)} | "
        f"Gaps: {len(result.gaps)}\n\n"
    )
    return header + result.enhanced_text


def _handle_brain_learn(args: dict[str, Any]) -> str:
    """Handle brain_learn tool call."""
    brain = _get_brain()
    description = args.get("description", "")
    severity = args.get("severity", "medium")
    resolution = args.get("resolution", "")
    lesson = args.get("lesson", "")

    if not description:
        return "Error: 'description' parameter is required."

    try:
        rule_id = brain.learn_from_finding(
            description=description,
            severity=severity,
            resolution=resolution,
            lesson=lesson,
        )
        if rule_id:
            return f"Finding crystallized into rule {rule_id}. The brain will remember this."
        return "Finding recorded but not crystallized (may need resolution + lesson for crystallization)."
    except Exception as exc:
        return f"Learning failed (non-blocking): {exc}"


def _handle_brain_validate(args: dict[str, Any]) -> str:
    """Handle brain_validate tool call — trigger external validation."""
    brain = _get_brain()
    node_id = args.get("node_id")
    force_refresh = args.get("force_refresh", False)
    dry_run = args.get("dry_run", False)
    layer_filter = args.get("layer_filter", "")

    try:
        import asyncio
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(brain.validate(
            node_id=node_id,
            force_refresh=force_refresh,
            dry_run=dry_run,
            layer_filter=layer_filter,
        ))
        loop.close()

        if isinstance(result, dict):
            validated = result.get("validated", 0)
            failed = result.get("failed", 0)
            skipped = result.get("skipped", 0)
            return (
                f"Validation complete: {validated} validated, {failed} failed, "
                f"{skipped} skipped"
            )
        return f"Validation result: {result}"
    except Exception as exc:
        return f"Validation failed: {exc}"


def _handle_brain_stats(args: dict[str, Any]) -> str:
    """Handle brain_stats tool call — comprehensive stats."""
    brain = _get_brain()
    stats = brain.stats()
    healthy = brain.is_healthy()
    version = brain.version

    lines = [
        f"## Engineering Brain — v{version}",
        f"Health: {'OK' if healthy else 'DEGRADED'}",
        "",
        "### Node Counts",
    ]

    layers = stats.get("layers", {})
    total = stats.get("total", 0)
    for name, count in layers.items():
        lines.append(f"  {name}: {count}")
    lines.append(f"  TOTAL: {total}")

    cache = stats.get("cache", {})
    if cache:
        hits = cache.get("hit_count", cache.get("hits", 0))
        misses = cache.get("miss_count", cache.get("misses", 0))
        total_q = hits + misses
        rate = f"{hits / total_q * 100:.0f}%" if total_q > 0 else "N/A"
        lines.extend(["", "### Cache", f"  Hit rate: {rate} ({hits}/{total_q})"])

    config = stats.get("config", {})
    if config:
        lines.extend([
            "", "### Config",
            f"  Adapter: {config.get('adapter', 'memory')}",
            f"  Sharding: {config.get('sharding', False)}",
            f"  Budget: {config.get('budget_chars', 3000)} chars",
        ])

    # O-10: Extended health metrics
    try:
        weak_count = len(brain._reinforcer.get_weak_rules()) if hasattr(brain, "_reinforcer") else 0
        lines.extend(["", "### Health", f"  Weak rules: {weak_count}"])
    except Exception:
        pass
    try:
        maint_ago = int(time.time() - brain._last_maintenance_at) if hasattr(brain, "_last_maintenance_at") else -1
        lines.append(f"  Last maintenance: {maint_ago}s ago")
    except Exception:
        pass
    try:
        from engineering_brain.observability.dead_letter import get_dead_letter_queue
        dlq_count = get_dead_letter_queue().count()
        lines.append(f"  Dead letters: {dlq_count}")
    except Exception:
        pass

    return "\n".join(lines)


def _handle_brain_contradictions(args: dict[str, Any]) -> str:
    """Handle brain_contradictions tool call."""
    brain = _get_brain()
    min_severity = args.get("min_severity")

    contradictions = brain.detect_contradictions()

    if min_severity:
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        min_level = severity_order.get(min_severity, 0)
        contradictions = [
            c for c in contradictions
            if severity_order.get(c.get("severity", "low"), 0) >= min_level
        ]

    if not contradictions:
        return "No contradictions detected in the knowledge graph."

    lines = [f"## {len(contradictions)} Contradictions Found\n"]
    for c in contradictions[:20]:
        lines.append(
            f"- **{c.get('node_a_id')}** vs **{c.get('node_b_id')}**: "
            f"conflict_k={c.get('conflict_k', 0):.2f}, "
            f"severity={c.get('severity', '?')}, "
            f"resolution={c.get('resolution_method', 'none')}"
        )

    return "\n".join(lines)


def _handle_brain_provenance(args: dict[str, Any]) -> str:
    """Handle brain_provenance tool call."""
    brain = _get_brain()
    node_id = args.get("node_id", "")
    if not node_id:
        return "Error: 'node_id' parameter is required."

    chain = brain.get_provenance(node_id)

    if not chain:
        # Also try epistemic status for context
        status = brain.epistemic_status(node_id)
        if status is None:
            return f"Node {node_id!r} not found in the brain."
        lines = [f"## Provenance for {node_id}", "No provenance chain recorded.", ""]
        lines.append("### Epistemic Status")
        for k, v in status.items():
            if k != "node_id":
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    lines = [f"## Provenance for {node_id}\n"]
    for i, entry in enumerate(chain):
        src_type = entry.get("source_type", "unknown")
        url = entry.get("url", "")
        detail = entry.get("detail", "")
        lines.append(f"{i + 1}. [{src_type}] {detail or url}")

    return "\n".join(lines)


def _handle_brain_communities(args: dict[str, Any]) -> str:
    """Handle brain_communities tool call."""
    brain = _get_brain()
    min_size = args.get("min_size", 3)

    communities = brain.detect_communities(min_size=min_size)

    if not communities:
        return "No communities detected (graph may be too sparse)."

    lines = [f"## {len(communities)} Knowledge Communities\n"]
    for c in communities[:20]:
        lines.append(
            f"- **Community {c.get('id')}** (size={c.get('size', 0)}): "
            f"{c.get('summary', 'no summary')[:100]}"
        )
        dom = c.get("dominant_domain")
        tech = c.get("dominant_technology")
        if dom or tech:
            lines.append(f"  Domain: {dom or '?'} | Tech: {tech or '?'}")

    return "\n".join(lines)


def _handle_brain_feedback(args: dict[str, Any]) -> str:
    """Handle brain_feedback tool call — negative feedback for active learning."""
    brain = _get_brain()
    rule_id = args.get("rule_id", "")
    reason = args.get("reason", "")
    context = args.get("context", "")

    if not rule_id:
        return "Error: 'rule_id' parameter is required."
    if not reason:
        return "Error: 'reason' parameter is required."

    # Create a WEAKENS edge by calling reinforce with positive=False
    feedback_id = f"FEEDBACK-{int(time.time())}"
    try:
        # Record as negative reinforcement
        brain.reinforce(rule_id, feedback_id, positive=False)

        # Also record as observation if available
        if brain._observation_log is not None:
            try:
                brain._observation_log.record_feedback(
                    rule_id=rule_id,
                    reason=reason,
                    context=context,
                )
            except (AttributeError, Exception):
                pass  # record_feedback may not exist yet

        return (
            f"Feedback recorded: rule {rule_id} weakened. "
            f"Reason: {reason[:100]}"
        )
    except Exception as exc:
        return f"Feedback recording failed: {exc}"


def _handle_brain_observe_outcome(args: dict[str, Any]) -> str:
    """Handle brain_observe_outcome tool call — record query feedback."""
    brain = _get_brain()
    query_id = args.get("query_id", "")
    node_ids = args.get("node_ids", [])
    helpful = args.get("helpful", False)
    signal_name = args.get("signal_name", "")

    if not query_id:
        return "Error: 'query_id' parameter is required."
    if not node_ids:
        return "Error: 'node_ids' parameter is required (non-empty list)."

    try:
        count = brain.observe_query_outcome(
            query_id=query_id,
            node_ids=node_ids,
            helpful=helpful,
            signal_name=signal_name,
        )
        sentiment = "helpful" if helpful else "unhelpful"
        return (
            f"Feedback recorded: {count} observations for {len(node_ids)} nodes "
            f"(query={query_id}, {sentiment}). Thompson Sampling updated."
        )
    except Exception as exc:
        return f"Feedback recording failed: {exc}"


def _handle_brain_promotion_outcome(args: dict[str, Any]) -> str:
    """Handle brain_promotion_outcome tool call — record promotion survival."""
    brain = _get_brain()
    domain = args.get("domain", "")
    node_id = args.get("node_id", "")
    promoted = args.get("promoted", False)
    survived = args.get("survived", False)

    if not domain:
        return "Error: 'domain' parameter is required."
    if not node_id:
        return "Error: 'node_id' parameter is required."

    try:
        success = brain.record_promotion_outcome(
            domain=domain,
            node_id=node_id,
            promoted=promoted,
            survived=survived,
        )
        if success:
            status = "survived" if survived else "did not survive"
            return (
                f"Promotion outcome recorded: node {node_id} in domain '{domain}' "
                f"{status}. Adaptive promotion policy updated."
            )
        return (
            "Promotion outcome not recorded — adaptive promotion is not enabled. "
            "Set BRAIN_ADAPTIVE_PROMOTION=true to enable."
        )
    except Exception as exc:
        return f"Promotion outcome recording failed: {exc}"


def _handle_brain_reason(args: dict[str, Any]) -> str:
    """Handle brain_reason tool call — structured epistemic reasoning."""
    brain = _get_brain()
    query = args.get("query", "")
    if not query:
        return "Error: 'query' parameter is required."

    result = brain.reason(
        task_description=query,
        technologies=args.get("technologies"),
        profile=args.get("profile"),
        max_chains=args.get("max_chains"),
    )

    if not result.formatted_text:
        return f"No relevant knowledge found for: {query}"

    header = (
        f"## Engineering Brain — Structured Reasoning\n"
        f"Query: {query}\n"
        f"Chains: {len(result.chains)} | "
        f"Nodes: {result.nodes_activated}/{result.total_nodes_in_packs} | "
        f"Contradictions: {len(result.contradictions)} | "
        f"Gaps: {len(result.gaps)} | "
        f"Time: {result.reasoning_time_ms:.0f}ms\n\n"
    )
    return header + result.formatted_text


def _handle_brain_pack(args: dict[str, Any]) -> str:
    """Handle brain_pack tool call — create pack from template."""
    brain = _get_brain()
    template_id = args.get("template_id", "")
    if not template_id:
        return "Error: 'template_id' parameter is required."

    technologies = args.get("technologies")
    domains = args.get("domains")

    try:
        pack = brain.pack(
            template_id,
            technologies=technologies,
            domains=domains,
        )
        lines = [
            f"## Knowledge Pack Created: {template_id}",
            f"Pack ID: {pack.id}",
            f"Nodes: {pack.node_count}",
            f"Layers: {', '.join(pack.layers_present)}",
            f"Technologies: {', '.join(pack.technologies) or 'all'}",
            f"Domains: {', '.join(pack.domains) or 'all'}",
            f"Quality Score: {pack.quality_score:.2f}",
            f"Reasoning Edges: {len(pack.reasoning_edges)}",
            "",
            "### Nodes",
        ]
        for node in pack.nodes[:20]:
            nid = node.get("id", "?")
            name = node.get("name") or node.get("text", "")
            if len(name) > 80:
                name = name[:77] + "..."
            lines.append(f"- **{nid}**: {name}")
        if pack.node_count > 20:
            lines.append(f"... and {pack.node_count - 20} more")
        return "\n".join(lines)
    except KeyError as e:
        return f"Template not found: {e}"
    except Exception as exc:
        return f"Pack creation failed: {exc}"


def _handle_brain_pack_templates(args: dict[str, Any]) -> str:
    """Handle brain_pack_templates tool call — list available templates."""
    from engineering_brain.core.config import get_brain_config
    from engineering_brain.retrieval.pack_templates import get_template_registry

    registry = get_template_registry(get_brain_config())
    tags = args.get("tags")

    if tags:
        templates = registry.search(tags=tags)
    else:
        templates = registry.list_templates()

    if not templates:
        return "No pack templates found."

    lines = [f"## {len(templates)} Pack Templates Available\n"]
    for t in templates:
        lines.append(f"### `{t.id}` — {t.name}")
        lines.append(f"{t.description[:150]}")
        if t.domains:
            lines.append(f"Domains: {', '.join(t.domains)}")
        if t.mcp_tools:
            tool_names = [tool.name for tool in t.mcp_tools]
            lines.append(f"Tools: {', '.join(tool_names)}")
        if t.tags:
            lines.append(f"Tags: {', '.join(t.tags)}")
        lines.append("")

    return "\n".join(lines)


def _handle_brain_pack_export(args: dict[str, Any]) -> str:
    """Handle brain_pack_export tool call — export as standalone MCP server."""
    brain = _get_brain()
    template_id = args.get("template_id", "")
    output_dir = args.get("output_dir", "")

    if not template_id:
        return "Error: 'template_id' parameter is required."
    if not output_dir:
        return "Error: 'output_dir' parameter is required."
    real_dir = os.path.realpath(output_dir)
    if ".." in output_dir:
        return "Error: output_dir must not contain '..'"
    output_dir = real_dir

    technologies = args.get("technologies")

    try:
        pack = brain.pack(template_id, technologies=technologies)
        pack.export(output_dir)
        return (
            f"Pack exported to {output_dir}/\n"
            f"Nodes: {pack.node_count}\n"
            f"Quality: {pack.quality_score:.2f}\n"
            f"\nRun: python {output_dir}/server.py"
        )
    except KeyError as e:
        return f"Template not found: {e}"
    except Exception as exc:
        return f"Export failed: {exc}"


def _handle_brain_pack_compose(args: dict[str, Any]) -> str:
    """Handle brain_pack_compose tool call — compose multiple templates."""
    brain = _get_brain()
    template_ids = args.get("template_ids", [])
    technologies = args.get("technologies")

    if not template_ids or len(template_ids) < 2:
        return "Error: provide at least 2 template_ids to compose."

    try:
        pack = brain.compose(template_ids, technologies=technologies)
        return (
            f"## Composed Pack\n"
            f"Templates: {', '.join(template_ids)}\n"
            f"Nodes: {pack.node_count}\n"
            f"Layers: {', '.join(pack.layers_present)}\n"
            f"Technologies: {', '.join(pack.technologies) or 'all'}\n"
            f"Quality Score: {pack.quality_score:.2f}\n"
            f"Reasoning Edges: {len(pack.reasoning_edges)}"
        )
    except Exception as exc:
        return f"Composition failed: {exc}"


def _handle_brain_reinforce(args: dict[str, Any]) -> str:
    """Handle brain_reinforce tool call — reinforce or weaken a rule."""
    brain = _get_brain()
    rule_id = args.get("rule_id", "")
    evidence_id = args.get("evidence_id", "")
    positive = args.get("positive", True)

    if not rule_id:
        return "Error: 'rule_id' parameter is required."
    if not evidence_id:
        return "Error: 'evidence_id' parameter is required."

    try:
        success = brain.reinforce(rule_id, evidence_id, positive)
        verb = "strengthened" if positive else "weakened"
        if success:
            return (
                f"Rule {rule_id} {verb} with evidence {evidence_id}. "
                f"Edge recorded in knowledge graph."
            )
        return f"Reinforcement failed: rule {rule_id} or evidence {evidence_id} not found."
    except Exception as exc:
        return f"Reinforcement failed: {exc}"


def _handle_brain_prediction_outcome(args: dict[str, Any]) -> str:
    """Handle brain_prediction_outcome tool call — record prediction test result."""
    brain = _get_brain()
    rule_id = args.get("rule_id", "")
    success = args.get("success", False)

    if not rule_id:
        return "Error: 'rule_id' parameter is required."

    try:
        recorded = brain.record_prediction_outcome(rule_id, success)
        verdict = "confirmed" if success else "refuted"
        if recorded:
            return (
                f"Prediction outcome recorded: rule {rule_id} was {verdict}. "
                f"Calibration counters updated."
            )
        return f"Prediction outcome not recorded: rule {rule_id} not found in graph."
    except Exception as exc:
        return f"Prediction outcome recording failed: {exc}"


def _handle_brain_mine_code(args: dict[str, Any]) -> str:
    """Handle brain_mine_code tool call — mine code patterns via AST analysis."""
    brain = _get_brain()
    path = args.get("path", "")
    if not path:
        return "Error: 'path' parameter is required."
    real_path = os.path.realpath(path)
    if not os.path.isdir(real_path):
        return f"Error: '{path}' is not a valid directory"
    path = real_path

    min_freq = args.get("min_frequency", 3)
    ingest = args.get("ingest", False)

    findings = brain.mine_code(path, min_frequency=min_freq)

    ingested = 0
    if ingest:
        for f in findings:
            try:
                brain.learn_from_finding(
                    description=f["description"],
                    severity=f.get("severity", "medium"),
                    technologies=f.get("technologies", []),
                    domains=f.get("domains", []),
                    file_path=(f.get("source_files") or [""])[0],
                )
                ingested += 1
            except Exception:
                pass

    lines = [f"Mined {len(findings)} findings from {path}"]
    if ingest:
        lines.append(f"Ingested {ingested} as L4 nodes")
    lines.append("")
    for f in findings:
        lines.append(
            f"[{f['pattern_type']}] freq={f['frequency']} conf={f['confidence']:.1f} "
            f"| {f['description'][:80]}"
        )
    return "\n".join(lines)


_TOOL_HANDLERS = {
    "brain_query": _handle_brain_query,
    "brain_think": _handle_brain_think,
    "brain_search": _handle_brain_search,
    "brain_learn": _handle_brain_learn,
    "brain_validate": _handle_brain_validate,
    "brain_stats": _handle_brain_stats,
    "brain_contradictions": _handle_brain_contradictions,
    "brain_provenance": _handle_brain_provenance,
    "brain_communities": _handle_brain_communities,
    "brain_feedback": _handle_brain_feedback,
    "brain_observe_outcome": _handle_brain_observe_outcome,
    "brain_promotion_outcome": _handle_brain_promotion_outcome,
    "brain_reason": _handle_brain_reason,
    "brain_reinforce": _handle_brain_reinforce,
    "brain_prediction_outcome": _handle_brain_prediction_outcome,
    "brain_pack": _handle_brain_pack,
    "brain_pack_templates": _handle_brain_pack_templates,
    "brain_pack_export": _handle_brain_pack_export,
    "brain_pack_compose": _handle_brain_pack_compose,
    "brain_mine_code": _handle_brain_mine_code,
}


# ---------------------------------------------------------------------------
# Resource handlers (O-02)
# ---------------------------------------------------------------------------


def _handle_resource(uri: str) -> dict[str, Any] | None:
    """Handle a resource read request. Returns content dict or None."""
    brain = _get_brain()

    if uri == "brain://stats":
        stats = brain.stats()
        stats["version"] = brain.version
        stats["healthy"] = brain.is_healthy()
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(stats, indent=2)}

    if uri == "brain://health":
        stats = brain.stats()
        cache = stats.get("cache", {})
        health = {
            "healthy": brain.is_healthy(),
            "version": brain.version,
            "total_nodes": stats.get("total", 0),
            "layers": stats.get("layers", {}),
            "cache_hits": cache.get("hits", 0),
            "cache_misses": cache.get("misses", 0),
            "adapter": stats.get("config", {}).get("adapter", "memory"),
        }
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(health, indent=2)}

    if uri == "brain://layers":
        stats = brain.stats()
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(stats.get("layers", {}), indent=2)}

    if uri == "brain://gaps":
        gaps = brain.analyze_gaps()
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(gaps[:20], indent=2)}

    if uri == "brain://version":
        return {"uri": uri, "mimeType": "text/plain", "text": str(brain.version)}

    return None


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 over stdio
# ---------------------------------------------------------------------------

_SERVER_INFO = {
    "name": "engineering-brain",
    "version": "2.0.0",
}

_CAPABILITIES = {
    "tools": {},
    "resources": {},
}


def _make_response(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _make_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    """Handle a single JSON-RPC request."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    # Notifications (no id) — just acknowledge
    if req_id is None and method == "notifications/initialized":
        return None

    if method == "initialize":
        return _make_response(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": _CAPABILITIES,
            "serverInfo": _SERVER_INFO,
        })

    if method == "tools/list":
        return _make_response(req_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        handler = _TOOL_HANDLERS.get(tool_name)
        if not handler:
            return _make_error(req_id, -32601, f"Unknown tool: {tool_name}")
        try:
            text = handler(arguments)
            return _make_response(req_id, {
                "content": [{"type": "text", "text": text}],
            })
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            return _make_response(req_id, {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "isError": True,
            })

    # Resource methods (O-02)
    if method == "resources/list":
        return _make_response(req_id, {"resources": RESOURCES})

    if method == "resources/read":
        uri = params.get("uri", "")
        content = _handle_resource(uri)
        if content is None:
            return _make_error(req_id, -32602, f"Resource not found: {uri}")
        return _make_response(req_id, {"contents": [content]})

    # Unknown method
    if req_id is not None:
        return _make_error(req_id, -32601, f"Method not found: {method}")
    return None


def main() -> None:
    """Run the MCP server (stdio JSON-RPC loop)."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(name)s: %(message)s",
        stream=sys.stderr,
    )

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            error = _make_error(None, -32700, f"Parse error: {exc}")
            sys.stdout.write(json.dumps(error) + "\n")
            sys.stdout.flush()
            continue

        response = _handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
