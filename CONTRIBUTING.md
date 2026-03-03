# Contributing to Engineering Brain

Thanks for your interest in contributing! This guide will help you get started.

## Quick Start

```bash
# 1. Fork and clone
git clone https://github.com/<your-username>/engineering-brain.git
cd engineering-brain

# 2. Install everything
make install

# 3. Run tests
make test

# 4. Lint
make lint
```

You should be up and running in under 5 minutes.

## Development Setup

### Requirements

- Python 3.11+
- Node.js 18+ (for cockpit client tests)
- pip (or uv)

### Package Structure

```
brain/              Python knowledge graph package (pip-installable)
cockpit/            Visualization suite (server + client + desktop + TUI + extension)
docs/               Documentation
```

### Running Components

```bash
# Brain MCP server
make mcp

# Cockpit web server (http://localhost:8420)
make serve

# Tests
make test-brain     # Brain tests only
make test-cockpit   # Cockpit tests only
make test           # All tests
```

## Making Changes

### Branch Naming

- `feature/short-description` for new features
- `fix/short-description` for bug fixes
- `docs/short-description` for documentation

### Code Standards

- **Python**: Formatted with `ruff format`, linted with `ruff check`
- **Line length**: 100 characters
- **Type hints**: Required for public API functions
- **Docstrings**: Required for public functions and classes
- **Tests**: Required for new features, maintain 90%+ coverage

### Adding Knowledge Seeds

Seeds are YAML files in `brain/engineering_brain/seeds/`. Each seed becomes nodes in the knowledge graph.

```yaml
# brain/engineering_brain/seeds/my_domain.yaml
nodes:
  - id: CR-MY-001
    type: rule
    severity: high
    text: "Always validate input at system boundaries"
    technologies: [python, flask]
    domains: [security, api]
    why: "Unvalidated input is the root cause of injection attacks"
    how_to_do_right: "Use Pydantic models or marshmallow schemas"
```

### Commit Messages

Use conventional commits:

```
feat: add new MCP tool for graph statistics
fix: correct edge type mapping in schema
docs: update MCP tools reference table
test: add integration tests for pack creation
```

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with tests
3. Run `make test && make lint` — both must pass
4. Push and open a PR
5. Fill in the PR template
6. Wait for review (typically within 7 days)

## Reporting Issues

Use GitHub Issues with the provided templates:

- **Bug Report**: Include reproduction steps, expected vs actual behavior
- **Feature Request**: Describe the use case and proposed solution

## Questions?

Open a GitHub Discussion for questions about the codebase, architecture, or contribution ideas.
