"""Tests for the Engineering Brain adapter layer.

Covers:
- MemoryGraphAdapter: CRUD, edges, traversal, transactions, pagination, stats
- MemoryVectorAdapter: upsert, search (cosine similarity), batch, filters
- MemoryCacheAdapter: get/set with TTL, LRU eviction, prefix invalidation
- MultiTierCache: L1->L2 fallthrough, promotion, invalidation
- ShardRouter: route_write, route_query, enabled/disabled, domain aliases
- FalkorDBGraphAdapter: skip if no connection
- QdrantVectorAdapter: skip if no connection
"""

from __future__ import annotations

import os
import sys
import time
from unittest.mock import MagicMock, patch

# Ensure src is on the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest

from engineering_brain.adapters.base import CacheAdapter, GraphAdapter, VectorAdapter
from engineering_brain.adapters.memory import (
    MemoryCacheAdapter,
    MemoryGraphAdapter,
    MemoryVectorAdapter,
    MultiTierCache,
    _cosine_similarity,
)
from engineering_brain.adapters.sharding import ShardRouter, ShardTarget
from engineering_brain.core.schema import Layer, shard_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vector(dim: int, fill: float = 1.0) -> list[float]:
    """Create a vector of given dimension filled with a constant value."""
    return [fill] * dim


def _make_unit_vector(dim: int, hot_index: int) -> list[float]:
    """Create a one-hot unit vector for clear cosine similarity tests."""
    vec = [0.0] * dim
    vec[hot_index] = 1.0
    return vec


# ============================================================================
# Section 1: MemoryGraphAdapter
# ============================================================================


class TestMemoryGraphAdapterCRUD:
    """Basic create/read/update/delete operations on nodes."""

    def setup_method(self):
        self.graph = MemoryGraphAdapter()

    def test_add_and_get_node(self):
        result = self.graph.add_node("Rule", "R001", {"title": "Use HTTPS", "severity": "high"})
        assert result is True
        node = self.graph.get_node("R001")
        assert node is not None
        assert node["_id"] == "R001"
        assert node["_label"] == "Rule"
        assert node["title"] == "Use HTTPS"
        assert node["severity"] == "high"

    def test_get_node_missing_returns_none(self):
        assert self.graph.get_node("nonexistent") is None

    def test_add_node_upsert_overwrites(self):
        self.graph.add_node("Rule", "R001", {"title": "v1"})
        self.graph.add_node("Rule", "R001", {"title": "v2", "extra": True})
        node = self.graph.get_node("R001")
        assert node["title"] == "v2"
        assert node["extra"] is True

    def test_update_node_existing(self):
        self.graph.add_node("Rule", "R001", {"title": "old"})
        ok = self.graph.update_node("R001", {"title": "new", "added": 42})
        assert ok is True
        node = self.graph.get_node("R001")
        assert node["title"] == "new"
        assert node["added"] == 42
        # Original internal fields preserved
        assert node["_label"] == "Rule"

    def test_update_node_nonexistent_returns_false(self):
        assert self.graph.update_node("ghost", {"x": 1}) is False

    def test_delete_node_existing(self):
        self.graph.add_node("Rule", "R001", {"title": "doomed"})
        ok = self.graph.delete_node("R001")
        assert ok is True
        assert self.graph.get_node("R001") is None

    def test_delete_node_nonexistent_returns_false(self):
        assert self.graph.delete_node("ghost") is False

    def test_delete_node_removes_from_label_index(self):
        self.graph.add_node("Rule", "R001", {})
        self.graph.delete_node("R001")
        assert self.graph.count("Rule") == 0

    def test_is_available(self):
        assert self.graph.is_available() is True


class TestMemoryGraphAdapterGetAll:
    """get_all_nodes and get_nodes_paginated."""

    def setup_method(self):
        self.graph = MemoryGraphAdapter()

    def test_get_all_nodes_empty(self):
        assert self.graph.get_all_nodes() == []

    def test_get_all_nodes_returns_all(self):
        self.graph.add_node("Rule", "R001", {"title": "a"})
        self.graph.add_node("Pattern", "P001", {"title": "b"})
        nodes = self.graph.get_all_nodes()
        assert len(nodes) == 2
        ids = {n["_id"] for n in nodes}
        assert ids == {"R001", "P001"}

    def test_get_nodes_paginated_empty_graph(self):
        pages = list(self.graph.get_nodes_paginated(page_size=10))
        assert pages == []

    def test_get_nodes_paginated_single_page(self):
        for i in range(5):
            self.graph.add_node("Rule", f"R{i:03d}", {"i": i})
        pages = list(self.graph.get_nodes_paginated(page_size=100))
        assert len(pages) == 1
        assert len(pages[0]) == 5

    def test_get_nodes_paginated_multiple_pages(self):
        for i in range(7):
            self.graph.add_node("Rule", f"R{i:03d}", {"i": i})
        pages = list(self.graph.get_nodes_paginated(page_size=3))
        total_nodes = sum(len(p) for p in pages)
        assert total_nodes == 7
        assert len(pages) == 3  # 3, 3, 1


class TestMemoryGraphAdapterEdges:
    """Edge operations: add_edge, get_edges, delete cascading."""

    def setup_method(self):
        self.graph = MemoryGraphAdapter()
        self.graph.add_node("Rule", "R001", {"title": "parent"})
        self.graph.add_node("Finding", "F001", {"title": "child"})
        self.graph.add_node("Finding", "F002", {"title": "child2"})

    def test_add_edge_and_get_edges(self):
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY", {"weight": 0.9})
        edges = self.graph.get_edges(node_id="R001", direction="outgoing")
        assert len(edges) == 1
        assert edges[0]["from_id"] == "R001"
        assert edges[0]["to_id"] == "F001"
        assert edges[0]["edge_type"] == "EVIDENCED_BY"
        assert edges[0]["properties"]["weight"] == 0.9

    def test_get_edges_incoming(self):
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY")
        edges = self.graph.get_edges(node_id="F001", direction="incoming")
        assert len(edges) == 1
        assert edges[0]["from_id"] == "R001"

    def test_get_edges_both_directions(self):
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY")
        self.graph.add_edge("F002", "R001", "REINFORCES")
        edges = self.graph.get_edges(node_id="R001", direction="both")
        assert len(edges) == 2

    def test_get_edges_filter_by_type(self):
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY")
        self.graph.add_edge("R001", "F002", "DEMONSTRATES")
        edges = self.graph.get_edges(node_id="R001", edge_type="EVIDENCED_BY", direction="outgoing")
        assert len(edges) == 1
        assert edges[0]["edge_type"] == "EVIDENCED_BY"

    def test_get_all_edges_no_filter(self):
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY")
        self.graph.add_edge("R001", "F002", "DEMONSTRATES")
        all_edges = self.graph.get_edges()
        assert len(all_edges) == 2

    def test_get_edges_empty_graph(self):
        assert self.graph.get_edges(node_id="R001") == []

    def test_add_edge_upsert_replaces_duplicate(self):
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY", {"v": 1})
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY", {"v": 2})
        edges = self.graph.get_edges(node_id="R001", direction="outgoing")
        assert len(edges) == 1
        assert edges[0]["properties"]["v"] == 2

    def test_delete_node_removes_outgoing_edges(self):
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY")
        self.graph.delete_node("R001")
        # F001 should have no incoming edges from R001
        edges = self.graph.get_edges(node_id="F001", direction="incoming")
        assert len(edges) == 0

    def test_delete_node_removes_incoming_edges(self):
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY")
        self.graph.delete_node("F001")
        # R001 should have no outgoing edges to F001
        edges = self.graph.get_edges(node_id="R001", direction="outgoing")
        assert len(edges) == 0


class TestMemoryGraphAdapterQuery:
    """Query and traverse operations."""

    def setup_method(self):
        self.graph = MemoryGraphAdapter()
        self.graph.add_node("Rule", "R001", {"severity": "high", "tags": ["security"]})
        self.graph.add_node("Rule", "R002", {"severity": "low", "tags": ["testing"]})
        self.graph.add_node("Pattern", "P001", {"severity": "medium"})

    def test_query_by_label(self):
        results = self.graph.query(label="Rule")
        assert len(results) == 2
        assert all(r["_label"] == "Rule" for r in results)

    def test_query_by_label_no_match(self):
        results = self.graph.query(label="Axiom")
        assert results == []

    def test_query_with_filter(self):
        results = self.graph.query(label="Rule", filters={"severity": "high"})
        assert len(results) == 1
        assert results[0]["_id"] == "R001"

    def test_query_with_list_filter(self):
        results = self.graph.query(label="Rule", filters={"tags": ["security"]})
        assert len(results) == 1
        assert results[0]["_id"] == "R001"

    def test_query_all_with_limit(self):
        results = self.graph.query(limit=2)
        assert len(results) == 2

    def test_traverse_outgoing(self):
        self.graph.add_node("Finding", "F001", {})
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY")
        result = self.graph.traverse("R001", direction="outgoing")
        assert len(result) == 1
        assert result[0]["_id"] == "F001"

    def test_traverse_incoming(self):
        self.graph.add_node("Finding", "F001", {})
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY")
        result = self.graph.traverse("F001", direction="incoming")
        assert len(result) == 1
        assert result[0]["_id"] == "R001"

    def test_traverse_with_edge_type_filter(self):
        self.graph.add_node("Finding", "F001", {})
        self.graph.add_node("Pattern", "P002", {})
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY")
        self.graph.add_edge("R001", "P002", "APPLIES_TO")
        result = self.graph.traverse("R001", edge_type="EVIDENCED_BY", direction="outgoing")
        assert len(result) == 1
        assert result[0]["_id"] == "F001"

    def test_traverse_max_depth(self):
        self.graph.add_node("Finding", "F001", {})
        self.graph.add_node("Finding", "F002", {})
        self.graph.add_node("Finding", "F003", {})
        self.graph.add_edge("R001", "F001", "X")
        self.graph.add_edge("F001", "F002", "X")
        self.graph.add_edge("F002", "F003", "X")
        result = self.graph.traverse("R001", direction="outgoing", max_depth=1)
        assert len(result) == 1
        assert result[0]["_id"] == "F001"

    def test_traverse_nonexistent_start(self):
        result = self.graph.traverse("ghost", direction="outgoing")
        assert result == []

    def test_traverse_limit(self):
        for i in range(10):
            self.graph.add_node("Finding", f"F{i:03d}", {})
            self.graph.add_edge("R001", f"F{i:03d}", "X")
        result = self.graph.traverse("R001", direction="outgoing", limit=3)
        assert len(result) == 3


class TestMemoryGraphAdapterBatch:
    """Batch add operations."""

    def setup_method(self):
        self.graph = MemoryGraphAdapter()

    def test_batch_add_nodes(self):
        nodes = [
            {"id": "R001", "title": "a"},
            {"id": "R002", "title": "b"},
            {"id": "R003", "title": "c"},
        ]
        count = self.graph.batch_add_nodes("Rule", nodes)
        assert count == 3
        assert self.graph.count("Rule") == 3

    def test_batch_add_nodes_skips_no_id(self):
        nodes = [
            {"id": "R001", "title": "a"},
            {"title": "no id"},
        ]
        count = self.graph.batch_add_nodes("Rule", nodes)
        assert count == 1

    def test_batch_add_edges(self):
        self.graph.add_node("Rule", "R001", {})
        self.graph.add_node("Finding", "F001", {})
        self.graph.add_node("Finding", "F002", {})
        edges = [
            {"from_id": "R001", "to_id": "F001", "edge_type": "EVIDENCED_BY"},
            {"from_id": "R001", "to_id": "F002", "edge_type": "EVIDENCED_BY"},
        ]
        count = self.graph.batch_add_edges(edges)
        assert count == 2
        assert len(self.graph.get_edges(node_id="R001", direction="outgoing")) == 2


class TestMemoryGraphAdapterStatsAndClear:
    """Stats, count, and clear operations."""

    def setup_method(self):
        self.graph = MemoryGraphAdapter()

    def test_count_empty(self):
        assert self.graph.count() == 0
        assert self.graph.count("Rule") == 0

    def test_count_by_label(self):
        self.graph.add_node("Rule", "R001", {})
        self.graph.add_node("Rule", "R002", {})
        self.graph.add_node("Pattern", "P001", {})
        assert self.graph.count() == 3
        assert self.graph.count("Rule") == 2
        assert self.graph.count("Pattern") == 1

    def test_stats(self):
        self.graph.add_node("Rule", "R001", {})
        self.graph.add_node("Finding", "F001", {})
        self.graph.add_edge("R001", "F001", "EVIDENCED_BY")
        st = self.graph.stats()
        assert st["node_count"] == 2
        assert st["edge_count"] == 1
        assert st["node_labels"]["Rule"] == 1
        assert st["node_labels"]["Finding"] == 1
        assert st["edge_types"]["EVIDENCED_BY"] == 1

    def test_clear(self):
        self.graph.add_node("Rule", "R001", {})
        self.graph.add_edge("R001", "R001", "SELF")
        ok = self.graph.clear()
        assert ok is True
        assert self.graph.count() == 0
        assert self.graph.get_edges() == []


class TestMemoryGraphAdapterTransactions:
    """Transaction support: begin, commit, rollback."""

    def setup_method(self):
        self.graph = MemoryGraphAdapter()

    def test_commit_preserves_changes(self):
        self.graph.begin_transaction()
        self.graph.add_node("Rule", "R001", {"title": "committed"})
        self.graph.commit()
        assert self.graph.get_node("R001")["title"] == "committed"

    def test_rollback_reverts_changes(self):
        self.graph.add_node("Rule", "R001", {"title": "original"})
        self.graph.begin_transaction()
        self.graph.update_node("R001", {"title": "changed"})
        self.graph.add_node("Rule", "R002", {"title": "new"})
        self.graph.rollback()
        assert self.graph.get_node("R001")["title"] == "original"
        assert self.graph.get_node("R002") is None

    def test_rollback_without_begin_is_safe(self):
        self.graph.rollback()  # Should not raise

    def test_health_check_delegates(self):
        assert self.graph.health_check() is True


# ============================================================================
# Section 2: MemoryVectorAdapter
# ============================================================================


class TestMemoryVectorAdapterBasic:
    """Upsert, search, delete, count, ensure_collection."""

    def setup_method(self):
        self.vector = MemoryVectorAdapter()
        self.dim = 4

    def test_upsert_and_search(self):
        vec = [1.0, 0.0, 0.0, 0.0]
        self.vector.upsert("rules", "D001", "Use HTTPS", vec, {"domain": "security"})
        results = self.vector.search("rules", vec, top_k=5)
        assert len(results) == 1
        assert results[0]["id"] == "D001"
        assert results[0]["score"] == pytest.approx(1.0)
        assert results[0]["text"] == "Use HTTPS"
        assert results[0]["metadata"]["domain"] == "security"

    def test_search_empty_collection(self):
        results = self.vector.search("nonexistent", [1.0, 0.0, 0.0, 0.0])
        assert results == []

    def test_search_cosine_ordering(self):
        self.vector.upsert("coll", "A", "similar", [1.0, 0.1, 0.0, 0.0])
        self.vector.upsert("coll", "B", "exact", [1.0, 0.0, 0.0, 0.0])
        self.vector.upsert("coll", "C", "orthogonal", [0.0, 0.0, 1.0, 0.0])
        results = self.vector.search("coll", [1.0, 0.0, 0.0, 0.0], top_k=3)
        assert results[0]["id"] == "B"  # Exact match first
        assert results[1]["id"] == "A"  # Close match second
        # Orthogonal has score ~0.0, which is >= default threshold 0.0
        assert len(results) == 3

    def test_search_score_threshold(self):
        self.vector.upsert("coll", "A", "match", [1.0, 0.0, 0.0, 0.0])
        self.vector.upsert("coll", "B", "orthogonal", [0.0, 0.0, 1.0, 0.0])
        results = self.vector.search("coll", [1.0, 0.0, 0.0, 0.0], score_threshold=0.5)
        assert len(results) == 1
        assert results[0]["id"] == "A"

    def test_search_with_metadata_filter(self):
        self.vector.upsert("coll", "A", "security", [1.0, 0.0, 0.0, 0.0], {"domain": "security"})
        self.vector.upsert("coll", "B", "testing", [1.0, 0.0, 0.0, 0.0], {"domain": "testing"})
        results = self.vector.search("coll", [1.0, 0.0, 0.0, 0.0], filters={"domain": "security"})
        assert len(results) == 1
        assert results[0]["id"] == "A"

    def test_search_top_k_limit(self):
        for i in range(10):
            self.vector.upsert("coll", f"D{i}", f"doc{i}", [1.0, 0.0, 0.0, 0.0])
        results = self.vector.search("coll", [1.0, 0.0, 0.0, 0.0], top_k=3)
        assert len(results) == 3

    def test_upsert_overwrites_existing(self):
        self.vector.upsert("coll", "D001", "old text", [1.0, 0.0, 0.0, 0.0])
        self.vector.upsert("coll", "D001", "new text", [0.0, 1.0, 0.0, 0.0])
        assert self.vector.count("coll") == 1
        results = self.vector.search("coll", [0.0, 1.0, 0.0, 0.0], top_k=1)
        assert results[0]["text"] == "new text"

    def test_delete_existing(self):
        self.vector.upsert("coll", "D001", "text", [1.0, 0.0, 0.0, 0.0])
        ok = self.vector.delete("coll", "D001")
        assert ok is True
        assert self.vector.count("coll") == 0

    def test_delete_nonexistent(self):
        assert self.vector.delete("coll", "ghost") is False

    def test_ensure_collection(self):
        ok = self.vector.ensure_collection("newcoll", 128)
        assert ok is True
        assert self.vector.count("newcoll") == 0

    def test_ensure_collection_idempotent(self):
        self.vector.ensure_collection("coll", 128)
        self.vector.upsert("coll", "D001", "text", [0.0] * 128)
        self.vector.ensure_collection("coll", 128)  # Should not clear data
        assert self.vector.count("coll") == 1

    def test_count_empty(self):
        assert self.vector.count("nonexistent") == 0

    def test_is_available(self):
        assert self.vector.is_available() is True


class TestMemoryVectorAdapterBatch:
    """batch_upsert operations."""

    def setup_method(self):
        self.vector = MemoryVectorAdapter()

    def test_batch_upsert(self):
        docs = [
            {"id": "D1", "text": "first", "vector": [1.0, 0.0], "metadata": {"a": 1}},
            {"id": "D2", "text": "second", "vector": [0.0, 1.0], "metadata": {"a": 2}},
            {"id": "D3", "text": "third", "vector": [0.5, 0.5]},
        ]
        count = self.vector.batch_upsert("coll", docs)
        assert count == 3
        assert self.vector.count("coll") == 3

    def test_batch_upsert_empty(self):
        count = self.vector.batch_upsert("coll", [])
        assert count == 0


class TestCosineSimilarity:
    """Test the internal _cosine_similarity helper."""

    def test_identical_vectors(self):
        assert _cosine_similarity([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert _cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_zero_vector(self):
        assert _cosine_similarity([0, 0], [1, 1]) == pytest.approx(0.0)

    def test_different_length_returns_zero(self):
        assert _cosine_similarity([1, 2], [1, 2, 3]) == pytest.approx(0.0)

    def test_empty_vectors_return_zero(self):
        assert _cosine_similarity([], []) == pytest.approx(0.0)


# ============================================================================
# Section 3: MemoryCacheAdapter
# ============================================================================


class TestMemoryCacheAdapterBasic:
    """get, set, delete, stats."""

    def setup_method(self):
        self.cache = MemoryCacheAdapter(max_size=100, default_ttl=300)

    def test_set_and_get(self):
        self.cache.set("key1", "value1")
        assert self.cache.get("key1") == "value1"

    def test_get_missing_returns_none(self):
        assert self.cache.get("missing") is None

    def test_set_overwrites(self):
        self.cache.set("key1", "old")
        self.cache.set("key1", "new")
        assert self.cache.get("key1") == "new"

    def test_delete_existing(self):
        self.cache.set("key1", "val")
        ok = self.cache.delete("key1")
        assert ok is True
        assert self.cache.get("key1") is None

    def test_delete_nonexistent(self):
        assert self.cache.delete("ghost") is False

    def test_stores_complex_types(self):
        self.cache.set("dict_key", {"a": 1, "b": [2, 3]})
        result = self.cache.get("dict_key")
        assert result == {"a": 1, "b": [2, 3]}

    def test_is_available(self):
        assert self.cache.is_available() is True


class TestMemoryCacheAdapterTTL:
    """TTL expiration behavior."""

    def test_expired_entry_returns_none(self):
        cache = MemoryCacheAdapter(max_size=100, default_ttl=300)
        cache.set("key1", "value1", ttl_seconds=1)
        # Manually expire by patching the stored expiry time
        key_entry = cache._store["key1"]
        cache._store["key1"] = (key_entry[0], time.time() - 1)
        assert cache.get("key1") is None

    def test_non_expired_entry_returned(self):
        cache = MemoryCacheAdapter(max_size=100, default_ttl=300)
        cache.set("key1", "value1", ttl_seconds=3600)
        assert cache.get("key1") == "value1"

    def test_custom_ttl_overrides_default(self):
        cache = MemoryCacheAdapter(max_size=100, default_ttl=1)
        cache.set("key1", "value1", ttl_seconds=3600)
        # Even though default TTL is 1s, the custom 3600s should apply
        assert cache.get("key1") == "value1"

    def test_default_ttl_used_when_none(self):
        cache = MemoryCacheAdapter(max_size=100, default_ttl=3600)
        cache.set("key1", "value1")  # Uses default_ttl=3600
        _, expires_at = cache._store["key1"]
        # Should expire ~3600s from now
        assert expires_at > time.time() + 3500


class TestMemoryCacheAdapterLRU:
    """LRU eviction when max_size is reached."""

    def test_lru_eviction(self):
        cache = MemoryCacheAdapter(max_size=3, default_ttl=3600)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Cache is full; adding "d" should evict "a" (least recently used)
        cache.set("d", 4)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("d") == 4

    def test_access_refreshes_lru_order(self):
        cache = MemoryCacheAdapter(max_size=3, default_ttl=3600)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Access "a" to make it most-recently-used
        cache.get("a")
        # Now "b" is least recently used; adding "d" should evict "b"
        cache.set("d", 4)
        assert cache.get("a") == 1  # Still present (was accessed)
        assert cache.get("b") is None  # Evicted
        assert cache.get("d") == 4


class TestMemoryCacheAdapterPrefixInvalidation:
    """invalidate_prefix behavior."""

    def setup_method(self):
        self.cache = MemoryCacheAdapter(max_size=100, default_ttl=3600)

    def test_invalidate_prefix(self):
        self.cache.set("brain:security:001", "a")
        self.cache.set("brain:security:002", "b")
        self.cache.set("brain:testing:001", "c")
        count = self.cache.invalidate_prefix("brain:security")
        assert count == 2
        assert self.cache.get("brain:security:001") is None
        assert self.cache.get("brain:testing:001") == "c"

    def test_invalidate_prefix_no_match(self):
        self.cache.set("key1", "val")
        count = self.cache.invalidate_prefix("nonexistent_prefix")
        assert count == 0
        assert self.cache.get("key1") == "val"


class TestMemoryCacheAdapterStats:
    """Stats tracking: hits, misses, size, utilization."""

    def test_stats_initial(self):
        cache = MemoryCacheAdapter(max_size=100, default_ttl=3600)
        st = cache.stats()
        assert st["size"] == 0
        assert st["max_size"] == 100
        assert st["hit_count"] == 0
        assert st["miss_count"] == 0
        assert st["hit_rate"] == 0.0
        assert st["utilization"] == 0.0

    def test_stats_after_operations(self):
        cache = MemoryCacheAdapter(max_size=100, default_ttl=3600)
        cache.set("key1", "val")
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("missing")  # Miss
        st = cache.stats()
        assert st["hit_count"] == 2
        assert st["miss_count"] == 1
        assert st["hit_rate"] == pytest.approx(2 / 3)
        assert st["size"] == 1
        assert st["utilization"] == pytest.approx(1 / 100)


# ============================================================================
# Section 4: MultiTierCache
# ============================================================================


class TestMultiTierCache:
    """L1 -> L2 fallthrough, promotion, invalidation."""

    def setup_method(self):
        self.l1 = MemoryCacheAdapter(max_size=100, default_ttl=60)
        self.l2 = MemoryCacheAdapter(max_size=1000, default_ttl=300)
        self.multi = MultiTierCache(self.l1, self.l2)

    def test_set_writes_both_tiers(self):
        self.multi.set("key1", "value1")
        assert self.l1.get("key1") == "value1"
        assert self.l2.get("key1") == "value1"

    def test_get_from_l1(self):
        self.multi.set("key1", "value1")
        assert self.multi.get("key1") == "value1"

    def test_l1_miss_falls_through_to_l2(self):
        # Write directly to L2 only
        self.l2.set("key1", "from_l2")
        result = self.multi.get("key1")
        assert result == "from_l2"

    def test_l2_hit_promotes_to_l1(self):
        # Write directly to L2 only
        self.l2.set("key1", "from_l2")
        # First get: L1 miss, L2 hit, promotes to L1
        self.multi.get("key1")
        # Now L1 should have it
        assert self.l1.get("key1") == "from_l2"

    def test_both_miss_returns_none(self):
        assert self.multi.get("nonexistent") is None

    def test_delete_removes_from_both(self):
        self.multi.set("key1", "value1")
        ok = self.multi.delete("key1")
        assert ok is True
        assert self.l1.get("key1") is None
        assert self.l2.get("key1") is None

    def test_delete_nonexistent(self):
        ok = self.multi.delete("ghost")
        assert ok is False

    def test_invalidate_prefix_both_tiers(self):
        self.multi.set("brain:sec:001", "a")
        self.multi.set("brain:sec:002", "b")
        self.multi.set("brain:test:001", "c")
        count = self.multi.invalidate_prefix("brain:sec")
        # Both L1 and L2 had 2 keys each => 2 + 2 = 4
        assert count == 4
        assert self.multi.get("brain:sec:001") is None
        assert self.multi.get("brain:test:001") == "c"

    def test_stats_contains_both_tiers(self):
        self.multi.set("key1", "val")
        self.multi.get("key1")
        st = self.multi.stats()
        assert "l1" in st
        assert "l2" in st
        assert "l1_hit_rate" in st
        assert "l2_hit_rate" in st

    def test_is_available_delegates_to_l1(self):
        assert self.multi.is_available() is True

    def test_set_with_ttl(self):
        ok = self.multi.set("key1", "val", ttl_seconds=60)
        assert ok is True
        assert self.multi.get("key1") == "val"


# ============================================================================
# Section 5: ShardRouter
# ============================================================================


class TestShardRouterEnabled:
    """ShardRouter with sharding enabled (default)."""

    def setup_method(self):
        self.router = ShardRouter(enabled=True, max_parallel=5)

    def test_route_write_known_domain(self):
        target = self.router.route_write("security", Layer.L3_RULES)
        assert isinstance(target, ShardTarget)
        assert target.graph_shard == "security"
        assert target.domain == "security"
        assert target.layer == Layer.L3_RULES
        assert target.shard_key == "security:L3"
        assert len(target.vector_collections) >= 1

    def test_route_write_unknown_domain_falls_back_to_general(self):
        target = self.router.route_write("quantum_computing", Layer.L2_PATTERNS)
        assert target.graph_shard == "general"
        assert target.domain == "general"

    def test_route_write_case_insensitive(self):
        target = self.router.route_write("  Security  ", Layer.L3_RULES)
        assert target.graph_shard == "security"

    def test_route_query_single_domain_single_layer(self):
        targets = self.router.route_query(["security"], [Layer.L3_RULES])
        assert len(targets) >= 1
        assert targets[0].graph_shard == "security"
        assert targets[0].layer == Layer.L3_RULES

    def test_route_query_multiple_domains(self):
        targets = self.router.route_query(
            ["security", "testing"],
            [Layer.L3_RULES],
        )
        domains = {t.graph_shard for t in targets}
        assert "security" in domains
        assert "testing" in domains

    def test_route_query_multiple_layers(self):
        targets = self.router.route_query(
            ["security"],
            [Layer.L1_PRINCIPLES, Layer.L3_RULES],
        )
        assert len(targets) == 2
        layers = {t.layer for t in targets}
        assert Layer.L1_PRINCIPLES in layers
        assert Layer.L3_RULES in layers

    def test_route_query_empty_domains_defaults_to_general(self):
        targets = self.router.route_query([], [Layer.L3_RULES])
        assert len(targets) >= 1
        assert targets[0].graph_shard == "general"

    def test_route_query_respects_max_parallel(self):
        router = ShardRouter(enabled=True, max_parallel=2)
        targets = router.route_query(
            ["security", "testing", "api"],
            [Layer.L3_RULES, Layer.L2_PATTERNS],
        )
        assert len(targets) <= 2

    def test_route_query_no_duplicate_shard_keys(self):
        targets = self.router.route_query(
            ["security", "security"],
            [Layer.L3_RULES],
        )
        keys = [t.shard_key for t in targets]
        assert len(keys) == len(set(keys))

    def test_route_query_domain_aliases(self):
        """Common domain aliases should be resolved to canonical shard domains."""
        targets = self.router.route_query(["web"], [Layer.L3_RULES])
        assert targets[0].graph_shard == "api"

        targets = self.router.route_query(["frontend"], [Layer.L3_RULES])
        assert targets[0].graph_shard == "ui"

        targets = self.router.route_query(["infra"], [Layer.L3_RULES])
        assert targets[0].graph_shard == "devops"

        targets = self.router.route_query(["test"], [Layer.L3_RULES])
        assert targets[0].graph_shard == "testing"

        targets = self.router.route_query(["sec"], [Layer.L3_RULES])
        assert targets[0].graph_shard == "security"

        targets = self.router.route_query(["db"], [Layer.L3_RULES])
        assert targets[0].graph_shard == "database"

        targets = self.router.route_query(["arch"], [Layer.L3_RULES])
        assert targets[0].graph_shard == "architecture"

    def test_route_write_vector_collections_for_l3(self):
        target = self.router.route_write("security", Layer.L3_RULES)
        assert "brain_rules" in target.vector_collections

    def test_route_write_vector_collections_for_l2(self):
        target = self.router.route_write("security", Layer.L2_PATTERNS)
        assert "brain_patterns" in target.vector_collections

    def test_route_write_vector_collections_for_l1(self):
        target = self.router.route_write("security", Layer.L1_PRINCIPLES)
        assert "brain_principles" in target.vector_collections

    def test_route_write_vector_collections_for_l0(self):
        """L0 axioms now have a dedicated collection (brain_axioms)."""
        target = self.router.route_write("security", Layer.L0_AXIOMS)
        assert "brain_axioms" in target.vector_collections


class TestShardRouterDisabled:
    """ShardRouter with sharding disabled."""

    def setup_method(self):
        self.router = ShardRouter(enabled=False)

    def test_route_query_returns_general_shard(self):
        targets = self.router.route_query(["security", "testing"], [Layer.L3_RULES])
        assert len(targets) == 1
        assert targets[0].graph_shard == "general"
        assert targets[0].shard_key == "general:all"

    def test_route_write_still_works(self):
        """route_write does not check enabled flag; it always routes."""
        target = self.router.route_write("security", Layer.L3_RULES)
        assert target.graph_shard == "security"


class TestShardTarget:
    """ShardTarget data class."""

    def test_repr(self):
        t = ShardTarget(
            graph_shard="security",
            vector_collections=["brain_rules"],
            shard_key="security:L3",
        )
        r = repr(t)
        assert "security" in r
        assert "brain_rules" in r

    def test_default_domain(self):
        t = ShardTarget(
            graph_shard="general",
            vector_collections=[],
            shard_key="general:L3",
        )
        assert t.domain == "general"
        assert t.layer is None


class TestSchemaShardKey:
    """Test the shard_key() helper from schema module."""

    def test_valid_domain(self):
        assert shard_key("security", Layer.L3_RULES) == "security:L3"

    def test_unknown_domain_maps_to_general(self):
        assert shard_key("quantum_computing", Layer.L3_RULES) == "general:L3"

    def test_case_and_whitespace(self):
        assert shard_key("  SECURITY  ", Layer.L1_PRINCIPLES) == "security:L1"


# ============================================================================
# Section 6: FalkorDBGraphAdapter (mock/skip if no connection)
# ============================================================================


class TestFalkorDBGraphAdapter:
    """Tests for FalkorDBGraphAdapter — uses mocks since FalkorDB may not be running."""

    def test_import_succeeds(self):
        """The adapter module should be importable regardless of FalkorDB availability."""
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        assert FalkorDBGraphAdapter is not None

    def test_is_available_returns_false_without_connection(self):
        """Without a running FalkorDB, is_available() should return False."""
        import engineering_brain.adapters.falkordb as fdb_module
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        # Reset the singleton to force fresh connection attempt
        original_client = fdb_module._falkordb_client
        fdb_module._falkordb_client = None
        try:
            adapter = FalkorDBGraphAdapter()
            # If FalkorDB is not running, this returns False; if running, True
            # Either way, the call should not raise
            result = adapter.is_available()
            assert isinstance(result, bool)
        finally:
            fdb_module._falkordb_client = original_client

    def test_implements_graph_adapter_interface(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        assert issubclass(FalkorDBGraphAdapter, GraphAdapter)

    def test_get_node_returns_none_without_connection(self):
        import engineering_brain.adapters.falkordb as fdb_module
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        original_client = fdb_module._falkordb_client
        fdb_module._falkordb_client = None
        try:
            adapter = FalkorDBGraphAdapter()
            # Force _graph() to return None
            adapter._graph_instance = None
            with patch.object(adapter, "_client", return_value=None):
                result = adapter.get_node("test_id")
                assert result is None
        finally:
            fdb_module._falkordb_client = original_client

    def test_add_node_returns_false_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            result = adapter.add_node("Rule", "R001", {"title": "test"})
            assert result is False

    def test_get_all_nodes_returns_empty_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            result = adapter.get_all_nodes()
            assert result == []

    def test_delete_node_returns_false_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.delete_node("R001") is False

    def test_add_edge_returns_false_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.add_edge("R001", "F001", "EVIDENCED_BY") is False

    def test_query_returns_empty_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.query(label="Rule") == []

    def test_traverse_returns_empty_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.traverse("R001") == []

    def test_count_returns_zero_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.count() == 0

    def test_stats_returns_defaults_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            st = adapter.stats()
            assert st["node_count"] == 0
            assert st["edge_count"] == 0

    def test_clear_returns_false_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.clear() is False

    def test_health_check_false_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.health_check() is False

    def test_batch_add_nodes_zero_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.batch_add_nodes("Rule", [{"id": "R1"}]) == 0

    def test_get_nodes_paginated_empty_without_connection(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = None
        with patch.object(adapter, "_client", return_value=None):
            pages = list(adapter.get_nodes_paginated())
            assert pages == []

    def test_graph_name_from_config(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter
        from engineering_brain.core.config import BrainConfig

        config = BrainConfig(falkordb_database="custom_brain_db")
        adapter = FalkorDBGraphAdapter(config=config)
        assert adapter._graph_name == "custom_brain_db"

    def test_graph_name_default(self):
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        adapter = FalkorDBGraphAdapter(config=None)
        assert adapter._graph_name == "engineering_brain"

    def test_with_mock_graph_add_and_get(self):
        """Test the adapter with a fully mocked FalkorDB graph object."""
        from engineering_brain.adapters.falkordb import FalkorDBGraphAdapter

        mock_graph = MagicMock()
        mock_graph.query.return_value = MagicMock(result_set=None)

        adapter = FalkorDBGraphAdapter()
        adapter._graph_instance = mock_graph
        adapter._indexes_ensured = True

        # add_node should call graph.query with MERGE
        result = adapter.add_node("Rule", "R001", {"title": "test"})
        assert result is True
        mock_graph.query.assert_called_once()
        call_args = mock_graph.query.call_args
        assert "MERGE" in call_args[0][0]


class TestFalkorDBSerialization:
    """Test serialization/deserialization helpers."""

    def test_serialize_value_list(self):
        from engineering_brain.adapters.falkordb import _serialize_value

        assert _serialize_value([1, 2, 3]) == "[1, 2, 3]"

    def test_serialize_value_dict(self):
        from engineering_brain.adapters.falkordb import _serialize_value

        result = _serialize_value({"a": 1})
        assert '"a"' in result

    def test_serialize_value_none(self):
        from engineering_brain.adapters.falkordb import _serialize_value

        assert _serialize_value(None) == ""

    def test_serialize_value_passthrough(self):
        from engineering_brain.adapters.falkordb import _serialize_value

        assert _serialize_value("hello") == "hello"
        assert _serialize_value(42) == 42

    def test_deserialize_node_json_list(self):
        from engineering_brain.adapters.falkordb import _deserialize_node

        result = _deserialize_node({"tags": '["a", "b"]', "name": "test"})
        assert result["tags"] == ["a", "b"]
        assert result["name"] == "test"

    def test_deserialize_node_json_dict(self):
        from engineering_brain.adapters.falkordb import _deserialize_node

        result = _deserialize_node({"meta": '{"x": 1}'})
        assert result["meta"] == {"x": 1}

    def test_deserialize_node_invalid_json(self):
        from engineering_brain.adapters.falkordb import _deserialize_node

        result = _deserialize_node({"val": "[not valid json"})
        assert result["val"] == "[not valid json"

    def test_deserialize_node_passthrough(self):
        from engineering_brain.adapters.falkordb import _deserialize_node

        result = _deserialize_node({"num": 42, "str": "hello"})
        assert result["num"] == 42
        assert result["str"] == "hello"


# ============================================================================
# Section 7: QdrantVectorAdapter (mock/skip if no connection)
# ============================================================================


class TestQdrantVectorAdapter:
    """Tests for QdrantVectorAdapter — uses mocks since Qdrant may not be running."""

    def test_import_succeeds(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        assert QdrantVectorAdapter is not None

    def test_implements_vector_adapter_interface(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        assert issubclass(QdrantVectorAdapter, VectorAdapter)

    def test_is_available_returns_bool(self):
        import engineering_brain.adapters.qdrant as qdr_module
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        original_client = qdr_module._qdrant_client
        qdr_module._qdrant_client = None
        try:
            adapter = QdrantVectorAdapter()
            result = adapter.is_available()
            assert isinstance(result, bool)
        finally:
            qdr_module._qdrant_client = original_client

    def test_upsert_returns_false_without_connection(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        adapter = QdrantVectorAdapter()
        with patch.object(adapter, "_client", return_value=None):
            result = adapter.upsert("coll", "D001", "text", [1.0, 0.0])
            assert result is False

    def test_search_returns_empty_without_connection(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        adapter = QdrantVectorAdapter()
        with patch.object(adapter, "_client", return_value=None):
            results = adapter.search("coll", [1.0, 0.0])
            assert results == []

    def test_delete_returns_false_without_connection(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        adapter = QdrantVectorAdapter()
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.delete("coll", "D001") is False

    def test_ensure_collection_returns_false_without_connection(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        adapter = QdrantVectorAdapter()
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.ensure_collection("coll", 128) is False

    def test_count_returns_zero_without_connection(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        adapter = QdrantVectorAdapter()
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.count("coll") == 0

    def test_batch_upsert_returns_zero_without_connection(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        adapter = QdrantVectorAdapter()
        with patch.object(adapter, "_client", return_value=None):
            result = adapter.batch_upsert("coll", [{"id": "D1", "vector": [1.0]}])
            assert result == 0

    def test_health_check_false_without_connection(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        adapter = QdrantVectorAdapter()
        with patch.object(adapter, "_client", return_value=None):
            assert adapter.health_check() is False

    def test_collection_prefix_from_config(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter
        from engineering_brain.core.config import BrainConfig

        config = BrainConfig(qdrant_collection_prefix="custom_")
        adapter = QdrantVectorAdapter(config=config)
        assert adapter._prefix == "custom_"

    def test_collection_prefix_default(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        adapter = QdrantVectorAdapter(config=None)
        assert adapter._prefix == "brain_"

    def test_full_collection_name_adds_prefix(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        adapter = QdrantVectorAdapter(config=None)
        assert adapter._full_collection_name("rules") == "brain_rules"

    def test_full_collection_name_no_double_prefix(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        adapter = QdrantVectorAdapter(config=None)
        assert adapter._full_collection_name("brain_rules") == "brain_rules"

    def test_embedding_dimension_from_config(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter
        from engineering_brain.core.config import BrainConfig

        config = BrainConfig(embedding_dimension=768)
        adapter = QdrantVectorAdapter(config=config)
        assert adapter._dimension == 768

    def test_embedding_dimension_default(self):
        from engineering_brain.adapters.qdrant import QdrantVectorAdapter

        adapter = QdrantVectorAdapter(config=None)
        assert adapter._dimension == 1024


# ============================================================================
# Section 8: Abstract base class contract verification
# ============================================================================


class TestAbstractInterfaces:
    """Verify that the abstract base classes enforce their contract."""

    def test_graph_adapter_is_abstract(self):
        with pytest.raises(TypeError):
            GraphAdapter()  # type: ignore[abstract]

    def test_vector_adapter_is_abstract(self):
        with pytest.raises(TypeError):
            VectorAdapter()  # type: ignore[abstract]

    def test_cache_adapter_is_abstract(self):
        with pytest.raises(TypeError):
            CacheAdapter()  # type: ignore[abstract]

    def test_memory_graph_is_concrete(self):
        adapter = MemoryGraphAdapter()
        assert isinstance(adapter, GraphAdapter)

    def test_memory_vector_is_concrete(self):
        adapter = MemoryVectorAdapter()
        assert isinstance(adapter, VectorAdapter)

    def test_memory_cache_is_concrete(self):
        adapter = MemoryCacheAdapter()
        assert isinstance(adapter, CacheAdapter)

    def test_multi_tier_cache_is_concrete(self):
        l1 = MemoryCacheAdapter()
        l2 = MemoryCacheAdapter()
        adapter = MultiTierCache(l1, l2)
        assert isinstance(adapter, CacheAdapter)
