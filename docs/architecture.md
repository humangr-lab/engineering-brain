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
| L5 | Context | Temporal, ephemeral knowledge | Task context, sprint data |

### Edge Types

31 edge types organized in 7 categories:

- **Hierarchical**: GROUNDS, INFORMS, INSTANTIATES, EVIDENCED_BY, DEMONSTRATED_BY
- **Cross-layer**: APPLIES_TO, IN_DOMAIN, USED_IN, CAUGHT_BY, VIOLATED, IN_SPRINT
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
  RRF Merge → 7-signal Scoring → Graph Expansion → Pack
```

## Backend Adapters

| Backend | Purpose | Default |
|---------|---------|---------|
| Memory | In-process graph (no external deps) | Yes |
| FalkorDB | Graph database with Cypher queries | Optional |
| Qdrant | Vector similarity search | Optional |
| Redis | Caching and pub/sub | Optional |
| Neo4j | Enterprise graph database | Optional |
