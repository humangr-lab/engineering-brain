<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/hugr-logo-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/hugr-logo-light.svg">
  <img alt="HuGR — Human Guardrail" src="docs/assets/hugr-logo-dark.svg" width="380">
</picture>

<br><br>

# Engineering Brain

A curated knowledge graph for AI coding agents. Zero LLM by default.

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/hero-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/hero-light.png">
  <img alt="3D Ontology Cockpit" src="docs/assets/hero-dark.png" width="900">
</picture>

<br><br>

[![License](https://img.shields.io/badge/license-Apache_2.0-blue?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-22_tools-7c3aed?style=flat-square)](#mcp-tools)
[![Tests](https://img.shields.io/badge/tests-2,400+_passing-22c55e?style=flat-square)](#)

</div>

<br>

3,700+ engineering rules, patterns, and principles organized in 6 layers — from axioms down to code-level evidence. Agents query the graph and get deterministic, source-backed answers in milliseconds.

## Quick start

### MCP Server

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

### Python

```python
from engineering_brain import Brain

brain = Brain()
brain.seed()

result = brain.query("async error handling in Python")
pack = brain.create_pack("security review", technologies=["flask"])
contradictions = brain.detect_contradictions()
```

### 3D Cockpit

```bash
make serve
# → http://localhost:8420
```

## How it works

Knowledge is layered, not flat:

```
L0  Axioms       "All input from external sources must be validated"
L1  Principles   "Defense in depth"
L2  Patterns     "Circuit breaker pattern"
L3  Rules        "Flask CORS: never use origins='*' in production"
L4  Evidence     Code analysis findings, user feedback
L5  Context      Temporal / per-session
```

Each node carries epistemic metadata — belief scores ([Subjective Logic](https://en.wikipedia.org/wiki/Subjective_logic)), evidence fusion ([Dempster-Shafer](https://en.wikipedia.org/wiki/Dempster%E2%80%93Shafer_theory)), decay curves, and contradiction detection. Retrieval ranks on 7 signals (tech match, domain, severity, reinforcement, recency, confidence, vector similarity) with weights optimized via [Thompson Sampling](https://en.wikipedia.org/wiki/Thompson_sampling).

When a finding at L4 gets reinforced 5+ times, it promotes to a Rule at L3. Bayesian priors per domain prevent premature promotion.

**Guardrails** — every retrieved node gets an RFC 2119 obligation level (MUST / MUST NOT / SHOULD / MAY) derived from its metadata. Zero LLM.

**Agent** (optional, BYOK) — for queries spanning multiple domains, an orchestrator decomposes the question, dispatches domain workers (security, architecture, performance, debugging, general), and synthesizes a composed answer. Simple queries never touch the agent.

## MCP tools

22 tools via [Model Context Protocol](https://modelcontextprotocol.io):

| | Tool | What it does |
|---|------|-------------|
| **Query** | `brain_query` | Knowledge retrieval with epistemic confidence |
| | `brain_think` | Confidence tiers + gap analysis |
| | `brain_reason` | Multi-chain reasoning with alternatives |
| | `brain_search` | Filter by technology, domain, or text |
| **Learn** | `brain_learn` | Report findings for the brain to absorb |
| | `brain_reinforce` | Strengthen or weaken rules with evidence |
| | `brain_mine_code` | AST pattern mining from Python source |
| **Validate** | `brain_validate` | Check rules against external sources |
| | `brain_contradictions` | Surface conflicting knowledge |
| | `brain_provenance` | Trace a rule's full origin chain |
| **Packs** | `brain_pack` | Curated knowledge bundle for a task |
| | `brain_pack_templates` | Architecture tradeoff, security review, etc. |
| | `brain_pack_compose` | Merge multiple packs |
| | `brain_pack_export` | Export as standalone MCP server |
| **Feedback** | `brain_feedback` | Flag unhelpful results |
| | `brain_observe_outcome` | Record if a result was useful |
| | `brain_prediction_outcome` | Track prediction accuracy |
| | `brain_promotion_outcome` | Monitor promoted knowledge survival |
| **Agent** | `brain_agent` | Deep reasoning via orchestrator + domain workers |
| | `brain_agent_status` | Check agent availability |
| **Meta** | `brain_stats` | Graph health and metrics |
| | `brain_communities` | Knowledge clusters |

Full reference: [docs/mcp-tools.md](docs/mcp-tools.md)

## Install

```bash
git clone https://github.com/humangr-lab/engineering-brain.git
cd engineering-brain
make install
make test     # 2,400+ tests
```

Or just the brain:

```bash
pip install -e brain/            # core
pip install -e "brain/[agent]"   # + LLM agent
pip install -e "brain/[backends]" # + vector backends
pip install -e "brain/[all]"     # everything
```

## Project layout

```
brain/                  Knowledge graph engine
├── engineering_brain/  3,700+ knowledge nodes, 22 MCP tools
│   └── agent/          Orchestrator + 5 domain workers (BYOK)
├── tests/              2,400+ tests
└── pyproject.toml

cockpit/                3D visualization
├── server/             FastAPI backend
├── client/             Three.js frontend
├── tui/                Rust terminal UI
├── app/                Tauri desktop app
└── vscode/             VS Code extension

docs/                   Architecture, MCP reference, extending guide
```

## Extending

Add your own knowledge as YAML seeds:

```yaml
# brain/engineering_brain/seeds/my_domain.yaml
layer: rules
domain: security
knowledge:
  - id: CR-MY-001
    statement: "Never store API keys in source code"
    severity: critical
    technologies: { lang: [python, javascript] }
    domains: { domain: [security], concern: [secrets] }
```

Full guide: [docs/extending.md](docs/extending.md)

## Docs

- [Architecture](docs/architecture.md) — layers, epistemic engine, retrieval pipeline
- [MCP Tools](docs/mcp-tools.md) — all 22 tools with parameters
- [Extending](docs/extending.md) — seeds, agent cards, golden dataset
- [Getting Started](docs/getting-started.md) — setup in 5 minutes

## Contributing

```bash
make install && make test && make lint
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache 2.0](LICENSE)

---

<div align="center">
<sub>Built by <a href="https://github.com/gustavoschneiter">Gustavo Schneiter</a> · <a href="https://github.com/humangr-lab">Human Guardrail</a></sub>
</div>
