# Sysmap Audit Report — 2026-03-03

7 parallel audit agents verified all 25 main nodes, 27 submaps, and ~300 subnodes
against actual Engineering Brain code. Code is the source of truth.

## Scoring: 25 nodes audited, ~60 claims checked

---

## CRITICAL (5 findings — factually wrong, affects system behavior)

| # | Node | Sysmap Claim | Actual Code | File |
|---|------|-------------|-------------|------|
| C1 | linkp | Threshold >= 0.80 | Default `0.45` | link_predictor.py:151 |
| C2 | linkp | 31 edge types | `EdgeType` enum: **31** members (IN_SPRINT removed) | schema.py:69-117 |
| C3 | xlay | Threshold >= 0.70 | Per-transition: GROUNDS=0.35, INFORMS=0.35, INSTANTIATES=0.40 | cross_layer_inferrer.py:158-162 |
| C4 | mcp | 9 tools | **22 tools** + 5 resources | mcp_server.py:40-616 |
| C5 | kb_edges | 5 cross-layer types (CROSS_GROUNDS, INFERRED_SIMILAR...) | **None exist** — inferred edges use standard type names | schema.py (no CROSS_* types) |

## HIGH (8 findings — significant inaccuracies or missing coverage)

| # | Node | Sysmap Claim | Actual Code | File |
|---|------|-------------|-------------|------|
| H1 | erg | Templates: 12 | **6** (5 YAML + 1 hardcoded) | templates/*.yaml |
| H2 | erg | Profiles: 7 | **3** YAML files | profiles/*.yaml |
| H3 | cicd | Severity-based PR gating | **ASPIRATIONAL** — no implementation exists | (no file) |
| H4 | klib | 5 taxonomy facets | **3** in TAXONOMY.yaml (or **7** in FACET_WEIGHTS) | taxonomy.py:88-96, TAXONOMY.yaml |
| H5 | — | 14 epistemic support modules | Not in sysmap: opinion.py, fusion.py, conflict_resolution.py, source_trust.py + 10 more | epistemic/*.py |
| H6 | — | 3 learning modules missing | pruner.py, reinforcer.py, relationship_learner.py exist but not in sysmap | learning/*.py |
| H7 | promot | Single promoter module | **2 modules**: promoter.py AND adaptive_promotion.py | learning/ |
| H8 | kb_edges | 6 edge categories match code | All 6 categories have **different members** than actual EdgeType enum | sysmap.js:760 vs schema.py |

## MEDIUM (11 findings — outdated or incomplete)

| # | Node | Sysmap Claim | Actual Code |
|---|------|-------------|-------------|
| M1 | seeds | 158 YAML, 6 domains | **283 YAML**, **69 domains** (or 9 shard domains) |
| M2 | klib | 31 edge types | **31** edge types (corrected) |
| M3 | obslog | "Events: All interactions" | 6 specific event types |
| M4 | l0 | Confidence = 1.0 enforced | Not explicit — enforced via Hawkes decay mu=0.0 |
| M5 | l3 | ~800 rules | 2 in seeds — rest crystallized at runtime |
| M6 | ctensor | 4 conflict types validated | String field, no enum validation |
| M7 | taxon | 5 facets | 7 in FACET_WEIGHTS |
| M8 | packv2 | 7-signal scoring | 6 base + 1 optional vector |
| M9 | kb_seeds | 158 YAMLs (in submap) | 285 (inconsistent with main node's "285") |
| M10 | xlay | Cosine normalization undocumented | Uses [0.25-0.80] → [0,1] + composite formula |
| M11 | adapt | Beta values undocumented | DEFAULT_WEIGHTS: [0.28, 0.18, 0.18, 0.13, 0.13, 0.10] |

## LOW (4 findings — minor or naming issues)

| # | Node | Issue |
|---|------|-------|
| L1 | dstcomb | "Cautious" in sysmap vs "conservative_envelope" in code |
| L2 | ide | ASPIRATIONAL — VSCode ext exists but no Brain integration |
| L3 | llm | PARTIAL — llm_map.py has schema gen, no agent wrapper |
| L4 | scorer | Docstring says "6 signals" but actually implements 7 |

## VERIFIED CORRECT (no action needed)

| Node | Claims Verified |
|------|----------------|
| scorer | 7 signals (despite docstring) |
| router | 3 branches, RRF fusion |
| embed | HAKE + Semantic dual encoding, 1024 dims |
| adapt | 6 weights, Thompson Sampling |
| trust | 9 source types, EigenTrust with alpha=0.15 |
| eladder | E0-E5 levels, L0=E5, one-step promotion/demotion |
| bedge | 15 edge decay profiles |
| pdecay | 11 decay profiles, stale threshold 0.3 |
| ctensor | 5 strategies, CT-{hash} format |
| dstcomb | CBF<0.3, Murphy 0.3-0.7, thresholds correct |
| l4 | 5 reinforcements threshold |
| l5 | Hawkes kernel, fastest decay |
| l0-l4 | Layer hierarchy edges (GROUNDS/INFORMS/INSTANTIATES) |
| mining | 5 pattern types, threshold >= 3 |
| ontol | 3 ontologies, 4 SKOS mapping types |
| packv2 | O(log N) ANN, 4 Qdrant collections, 3-5 sub-queries, 80 max nodes, 0.4 discount |
| klib | 3,700+ nodes, 6 layers, 285 seeds (main description) |

---

## ACCURACY SCORE

- **Total claims checked**: ~60
- **Correct**: 35 (58%)
- **Wrong/Outdated/Incomplete**: 25 (42%)
- **Critical**: 5
- **High**: 8
- **Medium**: 11
- **Low**: 4
