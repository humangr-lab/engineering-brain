# HuGR Engineering Brain — Benchmark & Evaluation Framework

A reproducible evaluation framework that measures the Engineering Brain's retrieval quality against controlled baselines using standard information retrieval metrics.

## Quick Start

```bash
# From the repository root, with the venv activated:
cd brain

# Full benchmark (all systems, generates PDF report)
python -m benchmarks run

# Specific systems only
python -m benchmarks run --systems brain,naive_rag

# Skip PDF generation (JSON only)
python -m benchmarks run --no-report

# Or use Makefile targets from the repo root
make benchmark
```

Results are saved to `benchmarks/reports/` as timestamped JSON and an optional PDF report.

## What This Framework Measures

### 1. Comparative Benchmark (`run`)

Evaluates the Engineering Brain against controlled baselines on the same knowledge base (270 YAML seed files, ~6,500 nodes). The comparison isolates **retrieval and scoring quality** — not knowledge content.

**Systems under test:**

| System | What's enabled | What's disabled |
|--------|---------------|-----------------|
| **Engineering Brain** | Everything: 7-signal scoring, adaptive weights (Thompson Sampling), cross-layer inference, link prediction, ontology alignment, guardrails, LLM enhancements | Nothing |
| **Naive RAG** | Embedding similarity + basic graph query | Graph expansion, query expansion, adaptive weights, cross-layer inference, link prediction, ontology alignment, all LLM enhancements, guardrails, maintenance |
| **GraphRAG** | Embedding similarity + multi-hop graph expansion | Adaptive scoring, cross-layer inference, link prediction, ontology alignment, all LLM enhancements, guardrails, maintenance |
| **Raw LLM** *(optional)* | Direct Claude API call, matched to Brain nodes by cosine similarity | Everything — no graph, no scoring | Requires `BRAIN_AGENT_API_KEY` |

Each baseline extends `BrainSystem` with env var overrides that disable specific features. This guarantees identical seed data and query API — the only variable is retrieval/scoring behavior.

### 2. Ablation Study (`ablation`)

Systematically toggles each of the Brain's 37+ boolean feature flags one at a time, measuring the delta on all metrics. Flags are organized into logical groups:

| Group | Flags | What it tests |
|-------|-------|---------------|
| `retrieval` | embedding, graph expansion, query expansion, reranker, sharding | Core retrieval pipeline |
| `gaps` | cross-layer inference, code mining, adaptive weights, link prediction, ontology alignment, adaptive promotion | The 7 SOTA improvement gaps |
| `epistemic` | epistemic ladder, Bayesian edges, predictive decay, contradiction tensor, DST evidence | Epistemic reasoning features |
| `llm` | 11 LLM enhancement flags | LLM-assisted operations |
| `maintenance` | maintenance, crystallize, promote, prune | Background maintenance |
| `other` | guardrails, observation log, HAKE, relationship learning, agent, pack v2 | Remaining features |

```bash
# Full ablation (all flags — slow, one Brain per flag)
python -m benchmarks ablation

# Single group
python -m benchmarks ablation --group gaps

# Specific flags
python -m benchmarks ablation --flags cross_layer_inference_enabled link_prediction_enabled
```

### 3. Robustness Evaluation (`robustness`)

Measures resilience against adversarial knowledge injection. Injects 30 adversarial rules (from `datasets/adversarial_v1.yaml`) into a live Brain and measures:

| Scenario | Attack vector | Example |
|----------|--------------|---------|
| `conflicting` | Rules that contradict established engineering practices | "Raw SQL queries are always faster and safer than ORMs" |
| `obsolete` | Rules for deprecated/removed APIs and patterns | "Use Python 2's `print` statement for output" |
| `biased` | Technology-biased rules that push a single solution | "Always use MongoDB for every data storage need" |

**Metrics per scenario:**
- **Contamination rate** — fraction of returned results that are adversarial
- **Detection rate** — fraction of injected rules flagged by validation
- **NDCG degradation** — quality drop compared to clean baseline
- **Resilience score** — composite: `(1 - contamination) * 0.4 + detection * 0.3 + (1 + degradation) * 0.3`

### 4. Cost/Benefit Analysis (`cost`)

Profiles each system on identical queries measuring:

- Latency percentiles (p50, p95, p99)
- Token consumption per query
- Peak memory delta (via `resource.getrusage`)
- Setup time (seed + embed + index)

```bash
python -m benchmarks cost
```

## Evaluation Metrics

All metrics follow standard IR definitions and return values in `[0.0, 1.0]`:

| Metric | Definition | Why it matters |
|--------|-----------|----------------|
| **NDCG@k** | Normalized Discounted Cumulative Gain | Rank-sensitive quality — penalizes relevant results buried deep |
| **MRR** | Mean Reciprocal Rank | How quickly the first relevant result appears |
| **Recall@k** | Fraction of relevant items found in top-k | Coverage — are we finding everything relevant? |
| **Precision@k** | Fraction of top-k results that are relevant | Signal-to-noise ratio |
| **MAP** | Mean Average Precision | Precision across all recall levels |
| **F1@k** | Harmonic mean of Precision@k and Recall@k | Balance of precision and recall |

Each query produces a `MetricSuite` with all metrics at k=5 and k=10. Results are aggregated per-system, per-category, and per-difficulty.

## Golden Dataset

`datasets/golden_v1.yaml` — 50 queries across 5 categories:

| Category | Queries | Examples |
|----------|---------|---------|
| `security` | 10 | CORS configuration, JWT validation, SQL injection, RBAC, zero-trust |
| `architecture` | 10 | CQRS design, microservice decomposition, event sourcing |
| `code_review` | 10 | Code smell detection, refactoring strategies, PR review |
| `cross_domain` | 10 | ML pipeline + DevOps, blockchain + compliance, IoT + security |
| `multi_hop` | 10 | Queries requiring graph traversal across multiple knowledge layers |

Each query includes:
- `expected_technologies` and `expected_domains` for system queries
- `ground_truth_ids` — human-annotated list of node IDs that are genuinely relevant (curated by searching all 270 seed files and verifying each node's `text` content for semantic relevance)

**Ground truth curation**: For each query, all seed YAML files were searched for nodes whose text content is semantically relevant to answering the question — not just keyword or tag overlap. This makes the evaluation independent of the system under test.

**Difficulty distribution:** easy, medium, hard (mixed across categories).

## Brain Strengths Dataset

`datasets/brain_strengths_v1.yaml` — 20 specialized queries across 4 categories designed to test where the Brain's multi-signal scoring provides measurable advantages:

| Category | Queries | What it tests |
|----------|---------|---------------|
| `multi_hop_deep` | 5 | Cross-layer traversal: axioms → principles → patterns → rules → evidence |
| `domain_depth` | 5 | Niche domain expertise: LMSR markets, TimescaleDB, eBPF, SKOS ontology, Merkle audit logs |
| `contradiction` | 5 | Balanced retrieval of opposing viewpoints: ORM vs SQL, monolith vs microservices, SSR vs CSR |
| `obsolescence` | 5 | Deprecated patterns vs modern replacements: security evolution, DevOps practices |

```bash
# Run all categories
python -m benchmarks strengths

# Single category
python -m benchmarks strengths --category domain_depth
```

## Adversarial Dataset

`datasets/adversarial_v1.yaml` — 30 adversarial rules (10 per scenario):

- Injected directly into the Brain's graph as L3 nodes with `_adversarial: true`
- Tagged with `validation_status: unverified` to test guardrail detection
- Each rule has realistic `technologies`, `domains`, and `severity` to blend in

## Project Structure

```
benchmarks/
├── __main__.py              # Entry point: python -m benchmarks
├── cli.py                   # argparse CLI (run, ablation, robustness, cost, report, compare)
├── runner.py                # BenchmarkRunner: systems x queries orchestrator
├── metrics.py               # NDCG, MRR, Recall, Precision, MAP, F1, MetricSuite
├── results.py               # Typed dataclasses with JSON serialization
├── report_generator.py      # Jinja2 HTML -> WeasyPrint PDF
│
├── datasets/
│   ├── loader.py            # Versioned YAML loader with filtering
│   ├── golden_v1.yaml            # 50 evaluation queries (5 categories x 10)
│   ├── brain_strengths_v1.yaml   # 20 specialized queries (4 categories x 5)
│   └── adversarial_v1.yaml       # 30 adversarial rules (3 scenarios x 10)
│
├── baselines/
│   ├── base.py              # BaselineSystem ABC + SystemResult
│   ├── brain_system.py      # Full Brain (all features on)
│   ├── naive_rag.py         # Embedding-only (23 features disabled)
│   ├── graph_rag.py         # Graph + embedding (no scoring/LLM)
│   └── raw_llm.py           # Direct Claude API (optional)
│
├── ablation/
│   ├── flag_scanner.py      # Introspects BrainConfig for boolean flags
│   ├── flag_groups.py       # Logical groupings (retrieval, gaps, epistemic, ...)
│   └── ablation_runner.py   # Toggle-and-measure loop
│
├── robustness/
│   ├── knowledge_injector.py # Injects adversarial rules into Brain graph
│   └── robustness_runner.py  # Contamination, detection, degradation measurement
│
├── cost/
│   ├── profiler.py          # Per-query latency + memory + token profiling
│   └── cost_analyzer.py     # Multi-system cost comparison
│
├── charts/                  # matplotlib chart generators (HuGR themed)
│   ├── theme.py             # Colors, fonts, base64 encoding
│   ├── comparison.py        # Bar, radar, heatmap
│   ├── ablation.py          # Waterfall, flag heatmap
│   ├── robustness.py        # Degradation curves
│   └── cost.py              # Latency distributions, quality vs cost scatter
│
├── templates/               # Jinja2 HTML templates for PDF report
│   ├── report_base.html.j2
│   ├── section_cover.html.j2
│   ├── section_executive.html.j2
│   ├── section_methodology.html.j2
│   ├── section_comparison.html.j2
│   ├── section_ablation.html.j2
│   ├── section_robustness.html.j2
│   ├── section_cost.html.j2
│   ├── section_appendix.html.j2
│   └── partials/
│       ├── chart.html.j2
│       ├── table.html.j2
│       └── metric_card.html.j2
│
├── assets/
│   ├── report.css           # Print-ready A4 CSS (HuGR branding)
│   └── hugr-logo-dark.svg
│
├── reports/                 # Generated output (gitignored)
│   └── .gitkeep
│
└── tests/                   # 34 tests
    ├── test_metrics.py      # 19 tests — all metric functions
    ├── test_runner.py       # 6 tests — DatasetLoader + BenchmarkRunner
    ├── test_baselines.py    # 7 tests — ABC contracts for all systems
    └── test_report.py       # 2 tests — JSON roundtrip + HTML fallback
```

## CLI Reference

```
python -m benchmarks <command> [options]

Commands:
  run          Run benchmark suite (golden dataset, 50 queries)
  strengths    Run Brain Strengths benchmark (20 specialized queries)
  ablation     Run ablation study
  robustness   Run robustness evaluation
  cost         Run cost/benefit analysis
  report       Generate PDF report from existing JSON results
  compare      Compare two benchmark runs (exits 1 on regression)
```

### `run`
```
--systems      Comma-separated system names (default: all)
               Available: brain, naive_rag, graph_rag, raw_llm
--category     Filter by category (e.g., security architecture)
--difficulty   Filter by difficulty (e.g., hard)
--dataset      Custom dataset YAML path
--k            Rank cutoff (default: 10)
--output       Output directory (default: benchmarks/reports/)
--no-report    Skip PDF generation
```

### `strengths`
```
--systems      Comma-separated system names (default: all)
--category     Filter: multi_hop_deep, domain_depth, contradiction, obsolescence
--k            Rank cutoff (default: 10)
--output       Output directory
```

### `ablation`
```
--group        Flag group: retrieval, gaps, epistemic, llm, maintenance, other
--flags        Specific flag field names
--dataset      Custom dataset YAML path
```

### `robustness`
```
--scenario     Specific scenarios: conflicting, obsolete, biased
```

### `report`
```
--input        Results JSON path (default: reports/latest.json)
--output       Output directory
--dark         Use dark theme for charts
```

### `compare`
```
python -m benchmarks compare run1.json run2.json
```
Exits with code 1 if NDCG drops >1% or MRR drops >2% (regression detection).

## PDF Report

The report generator produces a publication-quality PDF using WeasyPrint:

- **Cover page** — HuGR-branded gradient, timestamp, dataset version
- **Executive summary** — KPI metric cards, key findings, winner declaration
- **Methodology** — Dataset description, system configurations, metric definitions
- **System comparison** — Bar charts, radar chart, category heatmap, full results table
- **Ablation study** — Waterfall chart (most impactful flags), flag heatmap
- **Robustness** — Degradation charts, contamination/detection rates
- **Cost analysis** — Latency distributions, quality-vs-cost scatter
- **Appendix** — Full per-query results

If WeasyPrint is not installed, the generator falls back to HTML output.

## Dependencies

Core benchmark (metrics, runner, baselines) requires only `pyyaml` (already in the main project).

For charts and PDF reports, install the benchmark extras:

```bash
pip install -e "brain/[benchmark]"
```

This adds: `matplotlib>=3.8.0`, `jinja2>=3.1.0`, `weasyprint>=60.0`

**Note:** Embedding-based retrieval requires `fastembed`, which needs `onnxruntime`. Currently compatible with Python <= 3.13 (onnxruntime does not yet support Python 3.14).

## Reproducibility

Every benchmark run:
1. Seeds the Brain from the same 270 YAML files (deterministic)
2. Runs the same 50 golden queries in the same order
3. Uses the same relevance criteria (technology/domain overlap)
4. Saves raw results as timestamped JSON with dataset version
5. Can be compared across runs via `python -m benchmarks compare`

The `compare` command detects regressions and is used in CI (`.github/workflows/ci-benchmark.yml`) to prevent quality degradation on PRs.

## Adding a New Baseline

Implement the `BaselineSystem` ABC:

```python
from benchmarks.baselines.base import BaselineSystem, SystemResult

class MySystem(BaselineSystem):
    @property
    def name(self) -> str:
        return "My System"

    @property
    def description(self) -> str:
        return "Description for the methodology section."

    def setup(self) -> None:
        # Initialize your system
        ...

    def query(self, task_description, technologies, domains) -> SystemResult:
        # Run query, return ranked results
        return SystemResult(
            ranked_ids=["id1", "id2", ...],
            raw_results=[{"id": "id1", "technologies": [...], "domains": [...]}, ...],
            latency_ms=42.0,
        )

    def teardown(self) -> None:
        # Cleanup
        ...
```

Register it in `cli.py`:
```python
SYSTEM_REGISTRY["my_system"] = "baselines.my_system.MySystem"
```

## Latest Results (2026-03-04)

### General Benchmark (50 queries, ground truth v2.0)

| System | NDCG@10 | MRR | Recall@10 | Avg Latency |
|--------|---------|-----|-----------|-------------|
| Engineering Brain | 0.122 | 0.299 | 0.054 | 1974ms |
| Naive RAG | 0.122 | 0.301 | 0.050 | 1102ms |
| GraphRAG | 0.121 | 0.298 | 0.050 | 716ms |

On the general benchmark with correct NDCG (IDCG considers all relevant items, not just retrieved ones) and human-annotated ground truth, the three systems perform comparably. The Brain does not yet demonstrate a statistically significant advantage on general-purpose queries.

**Why scores are low**: Ground truth pools average ~20 nodes per query (range 5-42). The system returns top-10, so recall@10 is naturally bounded at ~50%. NDCG is further reduced because the ideal DCG now accounts for all relevant items that *could* have been retrieved.

### Brain Strengths Benchmark (20 queries, 4 categories)

Specialized queries designed to test where the Brain's multi-signal scoring and graph traversal should provide advantages:

| Category | Brain NDCG | Naive RAG | GraphRAG | Delta |
|----------|-----------|-----------|----------|-------|
| **Domain Depth** | **0.311** | 0.255 | 0.255 | **+22.0%** |
| Contradiction | 0.022 | 0.022 | 0.022 | 0% |
| Multi-hop Deep | 0.044 | 0.116 | 0.116 | -62.1% |
| Obsolescence | 0.000 | 0.000 | 0.000 | 0% |

**Key findings:**
- **Domain Depth (+22%)**: The Brain's strongest category — multi-signal scoring surfaces niche domain knowledge (prediction markets, TimescaleDB, eBPF, hash-chain audit logs) that flat embedding search misses.
- **Multi-hop Deep (-62%)**: The Brain underperforms on cross-layer traversal queries. Its scoring currently deprioritizes some layer-crossing results. This is the #1 optimization target.
- **Contradiction / Obsolescence**: Both near zero for all systems — seed data doesn't explicitly encode opposing viewpoints or temporal deprecation context.

**Honest assessment**: The Brain shows measurable advantage only on domain depth. Multi-hop (its theoretical strength) is currently a weakness. This is a cold-start system — adaptive weights (Thompson Sampling) need query feedback to converge, and cross-layer inference thresholds may need tuning.
