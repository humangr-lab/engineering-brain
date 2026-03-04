# Extending the Knowledge Graph

Add your own engineering knowledge as YAML seed files.

## Seed File Structure

Seeds live in `brain/engineering_brain/seeds/`. Each file defines nodes that are loaded into the knowledge graph on startup.

```yaml
# brain/engineering_brain/seeds/my_domain.yaml
layer: rules         # axioms | principles | patterns | rules
domain: security     # any of the 9 shard domains

knowledge:
  - id: CR-SEC-001
    statement: "Never store API keys in source code"
    text: "Never store API keys in source code"
    severity: critical   # critical | high | medium | low
    technologies:
      lang: [python, javascript, go]
    domains:
      domain: [security]
      concern: [secrets]
    why: "Leaked keys grant attackers full API access"
    how_to_do_right: |
      1. Use environment variables or a secrets manager
      2. Add .env to .gitignore
      3. Rotate keys if they were ever committed
    example_good: |
      import os
      api_key = os.environ["API_KEY"]
    example_bad: |
      API_KEY = "sk-1234567890abcdef"
```

## Node ID Conventions

| Layer | Prefix | Example |
|-------|--------|---------|
| L0 Axioms | `AX-` | `AX-TYPE-001` |
| L1 Principles | `P-` | `P-SEC-001` |
| L2 Patterns | `PAT-` | `PAT-CIRCUIT-001` |
| L3 Rules | `CR-` | `CR-FLASK-001` |
| L4 Evidence | `FND-` | `FND-CORS-001` |

## Shard Domains

Seeds are partitioned across 9 domains for efficient retrieval:

`security`, `testing`, `architecture`, `ui`, `api`, `database`, `performance`, `devops`, `general`

## Taxonomy Facets

Tag nodes using 7 taxonomy facets:

| Facet | Weight | Examples |
|-------|--------|----------|
| `lang` | 0.25 | python, typescript, rust, go |
| `domain` | 0.25 | security, testing, api |
| `framework` | 0.20 | flask, react, django |
| `library` | 0.10 | pydantic, pytest, redis-py |
| `concern` | 0.10 | auth, caching, validation |
| `pattern` | 0.05 | circuit-breaker, retry, saga |
| `platform` | 0.05 | aws, gcp, kubernetes |

## Adding Seeds

1. Create a YAML file in `brain/engineering_brain/seeds/`
2. Follow the structure above
3. Run `make test-brain` to validate
4. The brain loads all seeds on `brain.seed()`

## Programmatic Learning

The brain also learns from code analysis and feedback:

```python
from engineering_brain import Brain

brain = Brain()
brain.seed()

# Mine patterns from source code
brain.mine_code("src/api/", min_frequency=3)

# Report a finding
brain.learn(
    text="Connection pool exhaustion under load",
    technologies=["python", "sqlalchemy"],
    domains=["performance", "database"],
    severity="high",
)
```

Findings enter at L4 (Evidence). After 5+ reinforcements, they promote to L3 (Rules).

## Guardrail-Aware Seeds

Nodes support metadata that drives the RFC 2119 guardrails system. The assembler derives obligation levels (MUST/SHOULD/MAY) from these fields:

```yaml
knowledge:
  - id: CR-SEC-042
    statement: "Never use eval() on user input"
    text: "Never use eval() on user input"
    severity: critical          # critical | high | medium | low
    validation_status: verified # verified | cross_checked | unvalidated
    epistemic_status: E3        # E0-E5
    when_applies: "dynamic code execution, template rendering"
    when_not_applies: "internal config parsing, test fixtures"
    technologies:
      lang: [python, javascript]
    domains:
      domain: [security]
```

**How obligation is derived:**

| Field | Effect |
|-------|--------|
| `severity: critical` + `validation_status: verified` | → MUST |
| Text contains "never"/"do not"/"avoid" + `severity: critical` | → MUST NOT |
| `severity: high` | → SHOULD |
| `severity: medium/low` | → MAY |
| `deprecated: true` | → MUST NOT (always) |
| `reinforcement_count >= 10` | Promotes MAY → SHOULD |

The `when_applies`/`when_not_applies` fields control applicability — nodes are annotated but never silently dropped.

## Golden Dataset

Contribute evaluation queries to `brain/golden_dataset.yaml`:

```yaml
queries:
  - id: "SEC-11"
    query: "How to securely store OAuth tokens in a mobile app"
    category: "security"       # security | architecture | code_review | multi_hop | cross_domain
    difficulty: "medium"       # easy | medium | hard
    expected_technologies: ["python", "oauth"]
    expected_domains: ["security", "authentication"]
```

Each category must have exactly 10 queries. Run `pytest tests/test_evaluation.py` to validate.

## Custom Agent Cards

The agent system uses YAML runtime cards to define worker personas. You can create custom workers for your domain:

```yaml
# my_cards/devops_worker.yml
agent_id: devops_worker
version: "1.0.0"
level: 1
reports_to: orchestrator

role: "DevOps & Infrastructure Specialist"
goal: "Reason about CI/CD, deployment, and infrastructure using brain knowledge"
backstory: |
  Expert in containerization, orchestration, and deployment pipelines.

key_skills:
  - "Docker and Kubernetes patterns"
  - "CI/CD pipeline design"
  - "Infrastructure as code"

key_constraints:
  - "Base ALL claims on brain evidence — cite node IDs"
  - "Return structured claims, not prose"

worker_instructions: |
  Analyze the brain's knowledge about infrastructure and DevOps.
  Focus on deployment safety, scalability, and operational concerns.
```

Point the agent to your custom cards directory:

```bash
export BRAIN_AGENT_CARDS_DIR=/path/to/my_cards
```

The agent will look for cards in your directory first, then fall back to built-in cards.

---

See also: [Architecture](architecture.md) · [MCP Tools Reference](mcp-tools.md) · [Getting Started](getting-started.md)
