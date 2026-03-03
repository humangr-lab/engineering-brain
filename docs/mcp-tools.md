# MCP Tools Reference

The Engineering Brain exposes 20 tools and 5 resources via the [Model Context Protocol](https://modelcontextprotocol.io).

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

## Resources

| Resource URI | Description |
|-------------|-------------|
| `brain://stats` | Graph statistics (node count, edge count, layer distribution) |
| `brain://health` | Health check (backend status, seed count, last update) |
| `brain://layers` | Layer definitions and current node counts |
| `brain://gaps` | Knowledge gaps identified by the epistemic engine |
| `brain://version` | Server version and capabilities |

## Example Usage

Ask your AI agent:

- *"Query the engineering brain about Flask CORS security"*
- *"Think about the trade-offs between REST and GraphQL for our API"*
- *"Create a security review pack for our Python backend"*
- *"What contradictions exist in the knowledge about caching?"*
- *"Mine patterns from src/api/ for anti-patterns"*
