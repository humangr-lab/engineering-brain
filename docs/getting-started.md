# Getting Started

This guide gets you from zero to running in under 5 minutes.

## Prerequisites

- Python 3.11+
- Node.js 18+ (optional, for cockpit client tests)
- pip

## Installation

```bash
git clone https://github.com/humangr-lab/engineering-brain.git
cd engineering-brain
make install
```

This installs both the Brain package and the Cockpit server in development mode.

## Quick Verification

```bash
make test
```

All tests should pass.

## Using the Brain

### As MCP Server

Add to your Claude config:

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

### As Python Library

```python
from engineering_brain import Brain

brain = Brain()
brain.seed()

# Query for engineering knowledge
result = brain.query("best practices for error handling in Python async code")
print(result.formatted_text[:500])

# Results include guardrails (RFC 2119 obligation levels)
if result.guardrails:
    for entry in result.guardrails.get("must_do", []):
        print(f"[MUST] {entry['text']}")
    for entry in result.guardrails.get("must_not_do", []):
        print(f"[MUST NOT] {entry['text']}")
```

### 3D Cockpit

```bash
make serve
# Open http://localhost:8420
```

Click any node to explore. Drag to rotate, scroll to zoom. Press Cmd+K to search.

## Agent System (Optional)

For deep multi-domain reasoning, enable the LLM agent system:

```bash
pip install -e "brain/[agent]"  # installs anthropic SDK
```

Set your Anthropic API key:

```bash
export BRAIN_AGENT_ENABLED=true
export BRAIN_AGENT_API_KEY=sk-ant-...
```

Or in the MCP config:

```json
{
  "mcpServers": {
    "engineering-brain": {
      "command": "python",
      "args": ["-m", "engineering_brain.mcp_server"],
      "env": {
        "BRAIN_AGENT_ENABLED": "true",
        "BRAIN_AGENT_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

Then ask: *"Use the brain agent to analyze the trade-offs between microservices and monolith for our Flask API"*

Simple queries still use the fast path (zero LLM). The agent only activates for complex multi-domain questions.

## Knowledge Assembly

Queries go through the Knowledge Assembly process:

- **Simple queries** (< 8 words) → direct rendering, zero LLM
- **Moderate queries** → LLM-curated selection and ordering
- **Complex queries** → full LLM synthesis with obligation-aware sections

Results include structured **guardrails** (MUST DO, MUST NOT, SHOULD, MAY) derived from node metadata — no extra LLM calls.

Disable assembly with `BRAIN_LLM_KNOWLEDGE_ASSEMBLY=false`. Disable guardrails with `BRAIN_GUARDRAILS=false`.

## Running Evaluations

The golden dataset measures retrieval quality across 50 queries in 5 categories:

```bash
cd brain && python -m pytest tests/test_evaluation.py -v
```

Results are saved to `brain/eval_results.json` with NDCG@10, MRR, and Recall@k metrics.

## Next Steps

- [Architecture](architecture.md) — understand how the brain works
- [MCP Tools](mcp-tools.md) — reference for all 22 MCP tools
- [Extending](extending.md) — add your own knowledge seeds
