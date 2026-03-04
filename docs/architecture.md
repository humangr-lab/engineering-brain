# Architecture

## Knowledge Graph Structure

The Engineering Brain organizes knowledge in 6 hierarchical layers:

| Layer | Name | Description | Example |
|-------|------|-------------|---------|
| L0 | Axioms | Foundational truths. Confidence 1.0. Never decay. | "All input from external sources must be validated" |
| L1 | Principles | Engineering principles grounded by axioms | "Defense in depth" |
| L2 | Patterns | Recurring solutions promoted from rules | "Circuit breaker pattern" |
| L3 | Rules | Specific, actionable constraints | "Flask CORS: never use `origins='*'` in production" |
| L4 | Evidence | Observations from code analysis and feedback | Finding: "CORS misconfiguration in server.py:42" |
| L5 | Context | Temporal, ephemeral knowledge | Task context, session data |

### Edge Types

31 edge types organized in 7 categories:

- **Hierarchical**: GROUNDS, INFORMS, INSTANTIATES, EVIDENCED_BY, DEMONSTRATED_BY
- **Cross-layer**: APPLIES_TO, IN_DOMAIN, USED_IN, CAUGHT_BY, VIOLATED
- **Evolution**: SUPERSEDES, CONFLICTS_WITH, VARIANT_OF, REINFORCES, WEAKENS
- **Causal**: CAUSED_BY, PREVENTS, TRIGGERS
- **Context**: REQUIRES, PRODUCES, SUBDOMAIN_OF
- **Source**: CITES, SOURCED_FROM, VALIDATED_BY, VALIDATES
- **Reasoning**: RELATES_TO, STRENGTHENS, PREREQUISITE, DEEPENS, ALTERNATIVE, COMPLEMENTS

## Epistemic Engine

The brain performs reasoning without LLM calls using:

1. **Subjective Logic** — Opinion fusion (belief, disbelief, uncertainty, base rate)
2. **Dempster-Shafer** — Evidence combination with conflict detection
3. **Epistemic Ladder** — E0 (unverified) → E5 (axiom) classification
4. **Predictive Decay** — Per-domain freshness tracking with exponential half-life
5. **Trust Propagation** — EigenTrust algorithm for node credibility
6. **Thompson Sampling** — Bayesian optimization of retrieval signal weights

## Retrieval Pipeline

```
Query → Context Extraction → Sub-query Decomposition →
  Vector ANN (if available) + Graph Filtered →
  RRF Merge → 7-signal Scoring → Graph Expansion →
  Knowledge Assembly → Context Guard → Pack
```

### Knowledge Assembly Pipeline

After scoring, the `KnowledgeAssembler` classifies query complexity and selects a strategy:

| Complexity | Criteria | Strategy | LLM Calls |
|-----------|----------|----------|-----------|
| SIMPLE | < 8 words AND < 6 candidates | DIRECT | 0 |
| MODERATE | 6-10 candidates OR multi-word | CURATED | 1 (selection + ordering) |
| COMPLEX | > 10 candidates OR multi-domain | SYNTHESIZED | 1 (full synthesis) |

Each strategy produces a formatted knowledge pack with bookend structure (critical nodes first, supporting last) to maximize attention for LLM consumers.

Feature flag: `BRAIN_LLM_KNOWLEDGE_ASSEMBLY` (default: on). Falls back to deterministic pipeline on failure.

### Context Guard

The `ContextGuard` module prevents context-window rot:

1. **Marginal Value Filter** — Jaccard word-overlap dedup removes near-duplicate nodes (default threshold: 0.65)
2. **Token Limit Enforcer** — Hard token cap with smart truncation at section boundaries (default: 12,000 tokens)

### Guardrails System (RFC 2119)

The `guardrails` module annotates every retrieved node with structured obligation levels — zero LLM calls:

| Obligation | Derivation | Agent Instruction |
|-----------|------------|-------------------|
| **MUST** | critical severity + verified/proven | "You MUST...", "Always..." |
| **MUST NOT** | prohibition text + critical/high severity, or deprecated | "NEVER...", "Do NOT..." |
| **SHOULD** | high severity, or critical but unvalidated | "Prefer...", "You should..." |
| **SHOULD NOT** | prohibition text + medium severity | "Avoid...", "Should not..." |
| **MAY** | medium/low severity, or high uncertainty | "Consider...", "Optionally..." |

Decision tree inputs: `severity`, `validation_status`, `epistemic_status`, `deprecated`, prohibition pattern detection on primary text, `reinforcement_count`, belief mass.

**Applicability checking**: Nodes' `when_applies`/`when_not_applies` are matched against the query context (technologies, domains). Inapplicable nodes are annotated but never silently dropped.

Feature flag: `BRAIN_GUARDRAILS` (default: on).

### Proactive Push

The `ProactivePush` module recommends adjacent knowledge the user didn't explicitly ask for:

1. **Domain Adjacency** — Graph of related domains (e.g., `api` → `security`, `reliability`, `testing`)
2. **Technology Implications** — Known technology pairings (e.g., `Flask` → `Werkzeug`, `Jinja2`)
3. **Failure Pattern Detection** — Historical failure patterns from the observation log
4. **Cross-file Dependencies** — File type associations (e.g., `*.py` + `requirements.txt` → dependency rules)

### LLM Helpers

The `llm_helpers` module provides a shared utility for all brain modules needing LLM calls:

- Lazy Anthropic SDK import (no hard dependency)
- API key fallback chain: `BRAIN_AGENT_API_KEY` → `ANTHROPIC_API_KEY`
- 2-attempt retry with exponential backoff
- Non-retryable error filtering (auth failures, invalid requests)

### Evaluation Framework

A golden dataset of 50 curated queries across 5 categories measures retrieval quality:

| Category | Queries | Focus |
|----------|---------|-------|
| Security | 10 | CORS, JWT, injection, RBAC, secrets |
| Architecture | 10 | Patterns, sharding, CQRS, caching |
| Code Review | 10 | Anti-patterns, testing, logging, DI |
| Multi-hop | 10 | Cross-layer reasoning, multi-tech |
| Cross-domain | 10 | UX+API, SRE+ML, finance+architecture |

Metrics: NDCG@10, MRR, Recall@k. Results saved to `eval_results.json` for regression tracking.

## Agent System (Optional LLM)

For queries that span multiple domains or require deep reasoning, an optional LLM agent system builds on the deterministic brain:

```
AgentQuery → assess_complexity (deterministic)
  ├─ SIMPLE → brain.think() → ComposedKnowledge    [zero LLM, sub-second]
  └─ MODERATE/COMPLEX → decompose → workers → synthesize → ComposedKnowledge
                         [1 Opus]   [N Opus]   [1 Opus]    [N+2 calls max]
```

### Complexity Routing (zero LLM)

Deterministic scoring on 4 signals — intent, domain count, technology count, depth:

| Score | Complexity | Path |
|-------|-----------|------|
| 0-1 | SIMPLE | Fast path — brain.think() only, zero tokens |
| 2-4 | MODERATE | Deep path — orchestrator + workers |
| 5+ | COMPLEX | Deep path — orchestrator + workers |

### Orchestrator

Decomposes multi-domain questions into 1-N sub-questions (max 3 workers by default), dispatches domain-specialist workers, and synthesizes results into a unified `ComposedKnowledge` response.

### Domain Workers

5 specialized workers, each defined by a YAML runtime card:

| Worker | Domain | Specialization |
|--------|--------|---------------|
| `architecture_worker` | architecture | System design, patterns, trade-offs |
| `security_worker` | security | OWASP, auth, threat modeling |
| `performance_worker` | performance | Profiling, optimization, scalability |
| `debugging_worker` | debugging | Root cause analysis, error patterns |
| `general_worker` | general | Cross-domain, catch-all |

Each worker:
1. Retrieves knowledge from the brain (`brain_access.think()`)
2. Gets domain contradictions and gaps
3. Reasons over the evidence with an LLM (Opus)
4. Returns structured `WorkerResult` with claims, evidence citations, and confidence

### Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `BRAIN_AGENT_ENABLED` | `false` | Feature flag |
| `BRAIN_AGENT_API_KEY` | `""` | Anthropic API key (BYOK) |
| `BRAIN_AGENT_MODEL` | `claude-opus-4-20250514` | Worker model |
| `BRAIN_AGENT_ORCHESTRATOR_MODEL` | `claude-opus-4-20250514` | Orchestrator model |
| `BRAIN_AGENT_MAX_WORKERS` | `3` | Max workers per query |
| `BRAIN_AGENT_MAX_TOKENS` | `4096` | Max tokens per LLM call |
| `BRAIN_AGENT_TIMEOUT` | `60` | Timeout seconds |
| `BRAIN_AGENT_CARDS_DIR` | `""` | Custom cards directory |

### Runtime Cards

Agent personas are defined in YAML runtime cards. Each card specifies role, goal, key skills, constraints, and domain-specific instructions. Prompt injection sanitization is built-in.

## Configuration Flags

### Retrieval & Assembly

| Variable | Default | Purpose |
|----------|---------|---------|
| `BRAIN_LLM_KNOWLEDGE_ASSEMBLY` | `true` | Enable LLM-powered knowledge assembly |
| `BRAIN_GUARDRAILS` | `true` | Enable RFC 2119 obligation annotation |
| `BRAIN_CONTEXT_BUDGET` | `50000` | Max characters for context budget |
| `BRAIN_LLM_MODEL` | `claude-sonnet-4-20250514` | Default model for brain LLM calls |
| `BRAIN_RERANKER` | `false` | Enable cross-encoder reranking |
| `BRAIN_GRAPH_EXPANSION` | `true` | Enable multi-hop graph expansion |
| `BRAIN_QUERY_EXPANSION` | `true` | Enable synonym-based query expansion |

## Backend Adapters

| Backend | Purpose | Default |
|---------|---------|---------|
| Memory | In-process graph (no external deps) | Yes |
| FalkorDB | Graph database with Cypher queries | Optional |
| Qdrant | Vector similarity search | Optional |
| Redis | Caching and pub/sub | Optional |
| Neo4j | Enterprise graph database | Optional |

---

See also: [Getting Started](getting-started.md) · [MCP Tools Reference](mcp-tools.md) · [Extending the Knowledge Graph](extending.md)
