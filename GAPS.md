# Known Limitations

Areas where the brain has room for improvement. Tracked for future work.

## 1. Embedding Provider Abstraction

**Files**: `retrieval/embedder.py`, `adapters/async_embedding.py`

The embedding layer tries fastembed first, then voyageai. Each provider has a
different API surface (`embed()` return types, batch semantics).

**Fix**: Add a lightweight `EmbeddingProvider` abstraction with a uniform API
(`embed_text() -> list[float]`, `embed_batch() -> list[list[float]]`).

---

## 2. FalkorDB Integration Testing

**File**: `adapters/falkordb.py`

The FalkorDB adapter uses the native `falkordb` package directly. It has not
been integration-tested against a live FalkorDB instance.

**Fix**: Add a CI job with FalkorDB service container for integration tests.

---

## 3. Qdrant Integration Testing

**File**: `adapters/qdrant.py`

The Qdrant adapter uses `qdrant_client.QdrantClient` with deterministic UUID
point IDs. It works in unit tests but lacks integration coverage against a
live Qdrant instance (retries, connection pooling, etc.).

**Fix**: Add a CI job with Qdrant service container.

---

## 4. Proactive Push — Failure Pattern History

**File**: `retrieval/proactive_push.py`

The `_failure_patterns()` method queries the brain's own findings for
historical patterns. A richer signal would come from an external memory
store with cross-session learning.

**Fix**: Add an optional memory integration (MCP-based or local) that the
proactive push can query for historical failure patterns.

---

## 5. Proactive Push — Cross-File Dependencies

**File**: `retrieval/proactive_push.py`

Cross-file dependency warnings only work if tasks explicitly declare
`depends_on`. Implicit dependencies (imports, shared state) are not detected.

**Fix**: Add static analysis or import graph scanning to detect cross-file
dependencies automatically.

---

## 6. Pack Templates

Only generic pack templates ship today. Domain-specific templates (e.g.,
"security review", "design review", "code review") would improve the
`brain_pack` tool's usefulness out of the box.

**Fix**: Add 5-10 curated pack templates covering common review scenarios.

---

## 7. Task-Driven Convenience API

The brain exposes `query()`, `search()`, and `think()` as primitives. A
higher-level API that takes a task description and returns contextually
relevant knowledge (auto-tagging technologies and domains) would reduce
integration effort for agent frameworks.

**Fix**: Add a `brain.knowledge_for_task(description)` convenience method.
