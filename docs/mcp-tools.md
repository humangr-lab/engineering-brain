# MCP Tools Reference

The Engineering Brain exposes 22 tools and 5 resources via the [Model Context Protocol](https://modelcontextprotocol.io).

## Setup

Add to your Claude Desktop or Claude Code config:

```json
{
  "mcpServers": {
    "engineering-brain": {
      "command": "python",
      "args": ["-m", "engineering_brain.mcp_server"]
    }
  }
}
```

## Tools

### Query & Search

| Tool | Description |
|------|-------------|
| `brain_query` | Query knowledge by topic, technology, and file type. Returns formatted text organized by layer (Principles, Patterns, Rules). |
| `brain_search` | Search nodes by technology, domain, or text. Returns raw node data for programmatic use. |
| `brain_think` | Enhanced query with confidence tiers, reasoning chain, and gap analysis. Use for complex decisions. |
| `brain_reason` | Multi-chain structured reasoning. Explores alternative approaches and trade-offs. |

### Learning & Feedback

| Tool | Description |
|------|-------------|
| `brain_learn` | Report a new finding for the brain to learn from. Findings enter at L4 (Evidence) and may promote to L3 (Rules) over time. |
| `brain_reinforce` | Strengthen or weaken an existing rule with new evidence. Adjusts epistemic belief/disbelief. |
| `brain_feedback` | Report that a retrieved rule was unhelpful. Triggers adaptive weight adjustment. |
| `brain_observe_outcome` | Record whether a query result was actually useful. Feeds Thompson Sampling optimizer. |
| `brain_prediction_outcome` | Record whether a rule's prediction came true. Adjusts prediction accuracy score. |
| `brain_promotion_outcome` | Track whether promoted knowledge (L4 to L3) survived or was demoted. |

### Validation & Analysis

| Tool | Description |
|------|-------------|
| `brain_validate` | Validate a rule against external sources. Updates epistemic confidence. |
| `brain_contradictions` | List detected contradictions in the knowledge graph. Returns pairs of conflicting rules with conflict scores. |
| `brain_provenance` | Trace the full origin chain of a rule: what evidence supports it, what principles ground it. |
| `brain_communities` | List knowledge communities (clusters of related nodes). |
| `brain_stats` | Graph statistics: node/edge counts, layer distribution, health metrics. |

### Knowledge Packs

| Tool | Description |
|------|-------------|
| `brain_pack` | Create a curated knowledge pack for a specific task (e.g., "security review for Flask API"). |
| `brain_pack_templates` | List available pack templates (architecture_tradeoff, incident_diagnosis, security_review, etc.). |
| `brain_pack_compose` | Compose multiple packs into a unified context. |
| `brain_pack_export` | Export a pack as a standalone MCP server or JSON file. |

### Code Analysis

| Tool | Description |
|------|-------------|
| `brain_mine_code` | Mine patterns from Python source files via AST analysis. Discovers anti-patterns and creates L4 Findings. |

### Agent (Deep Reasoning)

Requires `BRAIN_AGENT_ENABLED=true` and `BRAIN_AGENT_API_KEY` set to an Anthropic API key (BYOK).

| Tool | Description |
|------|-------------|
| `brain_agent` | Deep multi-domain reasoning via orchestrator + domain workers. Decomposes complex questions, dispatches specialist workers (security, architecture, performance, debugging, general) that reason over brain knowledge with an LLM, and synthesizes a composed answer with evidence citations and confidence scores. Simple queries use the fast path (zero LLM). |
| `brain_agent_status` | Check agent availability. Returns whether the agent is configured, enabled, and which model is active. |

**Parameters for `brain_agent`:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question` | string | Yes | The engineering question to analyze |
| `intent` | string | No | Query intent: `explanation`, `decision`, `analysis`, `investigation`, `synthesis` (default: `explanation`) |
| `domain_hints` | list | No | Domain hints: `security`, `architecture`, `performance`, `debugging`, `general` |
| `technology_hints` | list | No | Technology hints: `python`, `flask`, `react`, etc. |
| `context` | string | No | Additional context for the query |
| `constraints` | list | No | Constraints to apply during reasoning |
| `max_depth` | int | No | Reasoning depth (1-5, default: 2) |

## Resources

| Resource URI | Description |
|-------------|-------------|
| `brain://stats` | Graph statistics (node count, edge count, layer distribution) |
| `brain://health` | Health check (backend status, seed count, last update) |
| `brain://layers` | Layer definitions and current node counts |
| `brain://gaps` | Knowledge gaps identified by the epistemic engine |
| `brain://version` | Server version and capabilities |

## Knowledge Assembly & Guardrails

Query tools (`brain_query`, `brain_think`, `brain_reason`) return results that go through the Knowledge Assembly pipeline:

1. **Complexity classification** — simple/moderate/complex based on query length and candidate count
2. **Strategy selection** — DIRECT (zero LLM), CURATED (LLM-selected), or SYNTHESIZED (full LLM synthesis)
3. **Guardrail annotation** — Each node is tagged with RFC 2119 obligations (MUST/MUST NOT/SHOULD/MAY)

The `KnowledgeResult` includes a `guardrails` field:

```json
{
  "guardrails": {
    "must_do": [{"node_id": "CR-SEC-001", "obligation": "MUST", "text": "Set explicit CORS origins", "why": "Wildcard allows any domain"}],
    "must_not_do": [{"node_id": "CR-SEC-042", "obligation": "MUST NOT", "text": "Never use eval() on user input"}],
    "should_do": [...],
    "may_do": [...],
    "inapplicable_ids": ["CR-REACT-001"]
  }
}
```

Disable with `BRAIN_GUARDRAILS=false` or `BRAIN_LLM_KNOWLEDGE_ASSEMBLY=false`.

## Example Usage

Ask your AI agent:

- *"Query the engineering brain about Flask CORS security"*
- *"Think about the trade-offs between REST and GraphQL for our API"*
- *"Create a security review pack for our Python backend"*
- *"What contradictions exist in the knowledge about caching?"*
- *"Mine patterns from src/api/ for anti-patterns"*

---

See also: [Architecture](architecture.md) · [Getting Started](getting-started.md) · [Extending the Knowledge Graph](extending.md)
