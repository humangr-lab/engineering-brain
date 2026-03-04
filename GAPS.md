# Known Gaps After Pipeline Decoupling

Gaps introduced by removing pipeline-specific components from the public repo.
These are tracked for future resolution.

## 1. Embedding Provider Fallback

**Files**: `retrieval/embedder.py`, `adapters/async_embedding.py`

The embedding provider now tries to import `fastembed` then `voyageai` directly.
The previous `pipeline_autonomo.embedding_provider` wrapper handled provider
selection, batching, and model configuration centrally.

**Impact**: Users must install `fastembed` or `voyageai` manually and the
provider API surface may differ from what the adapter methods expect
(`embed()`, `embed_batch()`).

**Fix**: Create a lightweight `EmbeddingProvider` abstraction in
`engineering_brain/retrieval/embedding_provider.py` that wraps fastembed/voyageai
with a uniform API.

---

## 2. FalkorDB Client API

**File**: `adapters/falkordb.py`

The `_get_client()` now imports the native `falkordb` package directly.
The native API (`falkordb.FalkorDB.select_graph()`) should work but
has not been integration-tested without the pipeline wrapper.

**Impact**: FalkorDB adapter may need adjustments for the native client API.

**Fix**: Integration test with a local FalkorDB instance.

---

## 3. Qdrant Client API

**File**: `adapters/qdrant.py`

Fully rewritten to use native `qdrant_client.QdrantClient` API. Uses
`PointStruct`, `VectorParams`, deterministic UUID point IDs.

**Impact**: Functional but untested against a live Qdrant instance.
The old pipeline wrapper handled edge cases (retries, connection pooling).

**Fix**: Integration test with a local Qdrant instance. Consider adding
retry logic.

---

## 4. Proactive Push — Failure Patterns

**File**: `retrieval/proactive_push.py`

The `_failure_patterns()` method previously queried `pipeline_autonomo.amem_integration`
(A-MEM) for historical corrective actions and read `_prev_sprint_feedback` from
pipeline state. Now it queries the brain's own findings.

**Impact**: Reduced signal — the brain's built-in findings are limited compared
to a full A-MEM store with cross-sprint learning.

**Fix**: Implement an optional memory integration (MCP-based or local store)
that the proactive push can query for historical patterns.

---

## 5. Proactive Push — Dependency Analysis

**File**: `retrieval/proactive_push.py`

The `_dependency_analysis()` method previously read `granular_tasks` from
pipeline state to find cross-file dependencies. Now it only checks the
task's own `depends_on` field.

**Impact**: Cross-file dependency warnings only work if tasks explicitly
declare dependencies.

**Fix**: Implement static analysis or import graph scanning to detect
cross-file dependencies automatically.

---

## 6. Context Extractor — Phase Detection

**File**: `retrieval/context_extractor.py`

The `_PHASE_KEYWORDS` still includes "init", "spec", "exec", "qa" phases.
These are generic workflow phases that work standalone, but "vote" was
removed from `TaskContext.phase` description.

**Impact**: Minimal — phases are generic enough to be useful outside
any specific pipeline.

**Fix**: None needed unless adding new phase-specific features.

---

## 7. Removed Seed Files (15 files)

Pipeline-specific seed knowledge was removed:
- `pipeline_cross_cutting.yaml` — cross-cutting pipeline concerns
- `pipeline_exec_*.yaml` — execution phase knowledge
- `pipeline_qa_*.yaml` — QA phase knowledge
- `pipeline_spec_*.yaml` — spec phase knowledge
- `sacadas_*.yaml` — pipeline-specific insights
- `squad_lead_patterns.yaml` — squad coordination patterns

**Impact**: ~200 rules of pipeline-specific knowledge are no longer in
the public brain. General engineering knowledge is unaffected.

**Fix**: Consider extracting universally applicable rules from the
removed seeds and adding them back to domain-appropriate seed files.

---

## 8. Removed Pack Templates (4 files)

- `exec-implementation.yaml` — execution implementation packs
- `spec-analysis.yaml` — specification analysis packs
- `qa-review.yaml` — QA review packs
- `squad-coordination.yaml` — squad coordination packs

**Impact**: Pack manager cannot generate these specific pack types.
Generic packs still work.

**Fix**: Create standalone equivalents that work outside the pipeline
context (e.g., "code-review.yaml", "design-review.yaml").

---

## 9. Task Knowledge API Removed

**File**: `retrieval/task_knowledge.py` (deleted)

The entire task-driven knowledge API was removed:
- `get_knowledge_for_task()`
- `enrich_task_with_knowledge()`
- `enrich_tasks_batch()`
- `auto_tag_task()`
- `init_task_knowledge()`

**Impact**: External tools that imported these functions need to use
`brain.query()` directly instead.

**Fix**: Consider reimplementing a simplified version as a convenience
layer on top of `brain.query()`.

---

## 10. Sprint / Finding SBAR Fields

**Files**: `core/types.py`, `core/schema.py`

Removed:
- `Sprint` model entirely
- `Finding.sprint`, `Finding.run_id`, `Finding.expected`, `Finding.actual`,
  `Finding.requirement_id` fields
- `TestResult.sprint` field
- `NodeType.SPRINT`, `EdgeType.IN_SPRINT`

**Impact**: Findings and test results lose sprint context tracking.
The brain can still store findings but without sprint association.

**Fix**: If sprint tracking is needed for standalone use, re-add it
as an optional generic "context" or "batch_id" field.
