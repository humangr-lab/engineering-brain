# Engineering Brain

A knowledge graph for AI coding agents. 3,700+ curated engineering rules across 66 technologies, each with reasoning, examples, and sources. Ships as an MCP server — plug it into Claude Code, Cursor, or any MCP-compatible tool in 30 seconds.

## What it does

Your AI coding agent reads the rule, understands **why** it matters, sees a good and bad example, and writes better code. No fine-tuning, no RAG pipeline to build — just install and query.

```
You:    brain_query("Flask CORS security best practices")

Brain:  CR-SEC-CORS-001 [CRITICAL]
        "Never use CORS wildcard (*) in production"

        WHY: A wildcard origin allows any website to make authenticated
        requests to your API. An attacker hosts evil.com, user visits it,
        browser sends cookies to your API. Game over.

        DO THIS:
        CORS(app, origins=["https://yourapp.com"])

        NOT THIS:
        CORS(app, origins="*")

        Source: https://owasp.org/www-community/attacks/CORS_OriginHeaderScrutiny
```

## Quick Start

### Option 1: MCP Server (recommended)

Add to your Claude Code config (`~/.claude/mcp.json`):

```json
{
  "mcpServers": {
    "engineering-brain": {
      "command": "python",
      "args": ["-m", "engineering_brain.mcp_server"],
      "env": { "PYTHONPATH": "path/to/engineering-brain/src" }
    }
  }
}
```

Restart Claude Code. You now have `brain_query`, `brain_think`, `brain_search`, and 17 more tools available.

### Option 2: Python API

```python
from engineering_brain import Brain

brain = Brain()
brain.seed()  # Load 3,700+ built-in rules

result = brain.query("React useEffect cleanup patterns")
print(result.formatted_text)
```

## Features

- **3,724 curated rules** across 285 knowledge files — each with `why`, `how_to_do_right`, `example_good`, `example_bad`, and `sources`
- **4-layer knowledge hierarchy** — Axioms (why) > Principles (how to think) > Patterns (how to design) > Rules (what to do)
- **Cross-layer inference** — Ask about a rule, get the reasoning chain back to first principles
- **66 technologies** — React, Flask, AWS, Kubernetes, Go, Rust, Django, Next.js, Kafka, MongoDB, and 56 more
- **69 domains** — Security, API design, databases, testing, DevOps, architecture, performance, accessibility, and more
- **MCP server with 20 tools** — `brain_query`, `brain_think`, `brain_reason`, `brain_search`, `brain_learn`, and more
- **Epistemic reasoning** — Confidence tiers (VALIDATED / PROBABLE / UNCERTAIN / CONTESTED) per response
- **Adaptive retrieval** — Thompson Sampling learns which knowledge is most helpful over time
- **Extensible** — Add your own rules as YAML files, the brain indexes them automatically
- **Zero external services required** — Works fully in-memory out of the box. Optional backends (FalkorDB, Qdrant, Redis) for production scale

## Architecture

```
                    brain_query("Flask CORS security")
                                  |
                                  v
                    +---------------------------+
                    |      QUERY ROUTER         |
                    |  embedding + BM25 hybrid  |
                    +---------------------------+
                                  |
              +-------------------+-------------------+
              v                   v                   v
        +-----------+      +-----------+       +-----------+
        | L1        |      | L2        |       | L3        |
        | PRINCIPLES|----->| PATTERNS  |------>| RULES     |
        | (why)     |      | (how)     |       | (what)    |
        +-----------+      +-----------+       +-----------+
              ^                                       |
              |          Cross-layer edges             |
              +----------- inferred by ---------------+
                          embedding similarity
```

**L0 Axioms** (foundational truths) ground the entire graph but are rarely returned directly.

## Knowledge Coverage

| Domain | Technologies | Example Rule |
|--------|-------------|-------------|
| Web Security | Flask, Django, Express, FastAPI | Never use CORS wildcard in production |
| Cloud | AWS, GCP, Azure, IBM Cloud | Use customer-managed KMS keys for sensitive data |
| Frontend | React, Vue, Angular, Svelte, Next.js | Always return cleanup from useEffect subscriptions |
| Backend | Node.js, Go, Rust, Python, Java | Use structured logging with correlation IDs |
| Databases | PostgreSQL, MongoDB, Redis, Cassandra | Always use parameterized queries, never string concat |
| Infrastructure | Kubernetes, Docker, Terraform, Helm | Set CPU/memory limits on every container |
| API Design | REST, GraphQL, gRPC, WebSocket | API contract evolution must be additive only |
| Testing | pytest, Jest, Cypress, Hypothesis | Focus code review on logic and security, automate style |
| Observability | Prometheus, Grafana, Datadog, OpenTelemetry | Use RED method for service-level metrics |
| AI/LLM | LangChain, CrewAI, RAG, Agents | Validate all LLM outputs before acting on them |

Every rule includes:
- **`text`** — The rule itself
- **`why`** — Explanation with real-world consequences
- **`how_to_do_right`** — Step-by-step guidance
- **`example_good`** — Code that follows the rule
- **`example_bad`** — Code that violates the rule
- **`severity`** — critical / high / medium / low
- **`when_applies`** — When this rule is relevant
- **`when_not_applies`** — When to ignore it
- **`sources`** — Links to official docs, papers, or postmortems

## MCP Tools

| Tool | Description |
|------|------------|
| `brain_query` | Query rules by topic, technology, and domain |
| `brain_search` | Discover rules by technology or domain |
| `brain_think` | Epistemic reasoning with confidence tiers |
| `brain_reason` | Structured reasoning chains with causal edges |
| `brain_learn` | Report a finding so the brain can learn from it |
| `brain_validate` | Validate rules against external sources (PyPI, npm, NVD) |
| `brain_feedback` | Report when a rule was unhelpful |
| `brain_reinforce` | Strengthen/weaken rules based on evidence |
| `brain_pack` | Create curated knowledge packs from templates |
| `brain_pack_templates` | List available pack templates |
| `brain_pack_compose` | Merge multiple packs |
| `brain_pack_export` | Export a pack as standalone MCP server |
| `brain_stats` | Graph statistics and health |
| `brain_contradictions` | Detect conflicting rules |
| `brain_provenance` | Trace a rule back to its axiom |
| `brain_communities` | Discover knowledge clusters |
| `brain_mine_code` | Extract patterns from Python source via AST |
| `brain_observe_outcome` | Record whether query results were helpful |
| `brain_prediction_outcome` | Track prediction accuracy |
| `brain_promotion_outcome` | Track promoted rule survival |

## Configuration

All configuration via environment variables with sensible defaults:

| Variable | Default | Description |
|----------|---------|------------|
| `BRAIN_ADAPTER` | `memory` | Storage backend: `memory`, `falkordb`, `neo4j` |
| `BRAIN_QDRANT_ENABLED` | `false` | Enable Qdrant vector search |
| `BRAIN_REDIS_ENABLED` | `false` | Enable Redis L2 cache |
| `BRAIN_EMBEDDING_ENABLED` | `true` | Enable embedding-based retrieval |
| `BRAIN_CONTEXT_BUDGET` | `3000` | Max characters per query response |
| `BRAIN_TOP_K_RESULTS` | `10` | Max rules returned per query |

Full configuration reference: [`core/config.py`](src/engineering_brain/core/config.py)

## Adding Your Own Rules

Create a YAML file in `seeds/`:

```yaml
layer: rules
technology: MyFramework
domain: security
knowledge:
  - id: CR-MYFW-001
    text: "Always validate webhook signatures before processing payloads"
    why: "Without signature validation, anyone can send fake webhooks..."
    how_to_do_right: "1. Extract the signature header..."
    severity: critical
    technologies:
      framework: [myframework]
    domains:
      domain: [security]
      concern: [webhooks]
    example_good: |
      sig = request.headers.get("X-Signature")
      if not hmac.compare_digest(compute_sig(body), sig):
          abort(401)
    example_bad: |
      payload = request.get_json()  # No signature check!
      process_webhook(payload)
    sources: ["https://docs.myframework.com/webhooks/security"]
```

Run `brain.seed()` and your rules are indexed, embedded, and queryable.

## Optional Backends

For production use with thousands of rules:

| Backend | Purpose | Install |
|---------|---------|---------|
| FalkorDB | Graph storage (relationships between rules) | `pip install engineering-brain[backends]` |
| Qdrant | Vector search (semantic retrieval) | `pip install engineering-brain[backends]` |
| Redis | L2 cache (faster repeated queries) | `pip install engineering-brain[backends]` |
| Voyage AI | High-quality embeddings | `pip install engineering-brain[voyage]` |
| FastEmbed | Local embeddings (free, no API key) | `pip install engineering-brain[fastembed]` |

Without backends, everything runs in-memory. Fast for development, not recommended for 10,000+ rules.

## License

Apache 2.0 — see [LICENSE](LICENSE)
