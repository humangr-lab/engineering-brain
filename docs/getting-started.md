# Getting Started

This guide gets you from zero to running in under 5 minutes.

## Prerequisites

- Python 3.11+
- Node.js 18+ (optional, for cockpit client tests)
- pip

## Installation

```bash
git clone https://github.com/<username>/engineering-brain.git
cd engineering-brain
make install
```

This installs both the Brain package and the Cockpit server in development mode.

## Quick Verification

```bash
make test
```

All 700+ tests should pass.

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
for node in result.nodes[:3]:
    print(f"[{node['id']}] {node['text']}")
```

### 3D Cockpit

```bash
make serve
# Open http://localhost:8420
```

Click any node to explore. Drag to rotate, scroll to zoom. Press Cmd+K to search.

## Next Steps

- [Architecture](architecture.md) — understand how the brain works
- [MCP Tools](mcp-tools.md) — reference for all 20 MCP tools
- [Extending](extending.md) — add your own knowledge seeds
