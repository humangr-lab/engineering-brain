"""In-memory adapter for the Engineering Knowledge Brain.

Full-featured implementation for testing and development — no external
dependencies required. Supports graph, vector, and cache operations.
"""

from __future__ import annotations

import copy
import hashlib
import math
import time
from collections import OrderedDict, defaultdict
from collections.abc import Iterator
from typing import Any

from engineering_brain.adapters.base import CacheAdapter, GraphAdapter, VectorAdapter


def _list_prefix_match(query_tags: list[str], node_tags: list[str]) -> bool:
    """Hierarchy-aware tag matching via TagRegistry with prefix fallback.

    Uses the global TagRegistry for ancestor/descendant matching when available.
    Falls back to bidirectional prefix matching on dotted paths.
    """
    # Try hierarchy-aware matching first
    try:
        from engineering_brain.core.taxonomy import get_registry
        registry = get_registry()
        if registry.size > 0:
            return registry.match_flat(query_tags, node_tags)
    except Exception:
        pass

    # Fallback: original prefix matching
    for qt in query_tags:
        for nt in node_tags:
            if qt == nt:
                return True
            if "." in qt or "." in nt:
                qt_dot = qt + "."
                nt_dot = nt + "."
                if nt.startswith(qt_dot) or qt.startswith(nt_dot):
                    return True
    return False


class MemoryGraphAdapter(GraphAdapter):
    """In-memory graph storage using plain dicts.

    NOT thread-safe. Use only within a single thread or protect externally
    with a lock. The Brain class serializes all graph mutations through its
    public API, so this is safe when accessed exclusively through Brain methods.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges_out: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._edges_in: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._label_index: dict[str, set[str]] = defaultdict(set)
        self._in_transaction = False
        self._transaction_snapshot: dict[str, Any] | None = None

    def add_node(self, label: str, node_id: str, properties: dict[str, Any]) -> bool:
        props = {**properties, "_id": node_id, "_label": label}
        self._nodes[node_id] = props
        self._label_index[label].add(node_id)
        return True

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> list[dict[str, Any]]:
        """Return all knowledge nodes (for building dynamic indexes)."""
        return list(self._nodes.values())

    def update_node(self, node_id: str, properties: dict[str, Any]) -> bool:
        node = self._nodes.get(node_id)
        if node is None:
            return False
        node.update(properties)
        return True

    def delete_node(self, node_id: str) -> bool:
        node = self._nodes.pop(node_id, None)
        if node is None:
            return False
        label = node.get("_label", "")
        self._label_index[label].discard(node_id)
        # Remove outgoing edges
        for edge in self._edges_out.pop(node_id, []):
            self._edges_in[edge["to_id"]] = [
                e for e in self._edges_in.get(edge["to_id"], [])
                if e["from_id"] != node_id
            ]
        # Remove incoming edges
        for edge in self._edges_in.pop(node_id, []):
            self._edges_out[edge["from_id"]] = [
                e for e in self._edges_out.get(edge["from_id"], [])
                if e["to_id"] != node_id
            ]
        return True

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> bool:
        edge = {
            "from_id": from_id,
            "to_id": to_id,
            "edge_type": edge_type,
            "properties": properties or {},
        }
        # Upsert: remove existing edge of same type between same nodes
        self._edges_out[from_id] = [
            e for e in self._edges_out.get(from_id, [])
            if not (e["to_id"] == to_id and e["edge_type"] == edge_type)
        ]
        self._edges_in[to_id] = [
            e for e in self._edges_in.get(to_id, [])
            if not (e["from_id"] == from_id and e["edge_type"] == edge_type)
        ]
        self._edges_out[from_id].append(edge)
        self._edges_in[to_id].append(edge)
        return True

    def has_edge(self, from_id: str, to_id: str, edge_type: str | None = None) -> bool:
        for edge in self._edges_out.get(from_id, []):
            if edge["to_id"] == to_id:
                if edge_type is None or edge["edge_type"] == edge_type:
                    return True
        return False

    def query(
        self,
        label: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if label:
            candidates = [self._nodes[nid] for nid in self._label_index.get(label, set()) if nid in self._nodes]
        else:
            candidates = list(self._nodes.values())

        if filters:
            filtered = []
            for node in candidates:
                match = True
                for k, v in filters.items():
                    node_val = node.get(k)
                    if isinstance(v, list):
                        if not isinstance(node_val, list):
                            match = False
                            break
                        # Hierarchical prefix matching for dotted taxonomy paths.
                        # Query "language.python" matches node "language.python.web.flask"
                        # Query "language.python.web.flask.cors" matches node "language.python.web.flask"
                        if not _list_prefix_match(v, node_val):
                            match = False
                            break
                    elif node_val != v:
                        match = False
                        break
                if match:
                    filtered.append(node)
            candidates = filtered

        return candidates[:limit]

    def traverse(
        self,
        start_id: str,
        edge_type: str | None = None,
        direction: str = "outgoing",
        max_depth: int = 2,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        visited: set[str] = set()
        result: list[dict[str, Any]] = []
        queue: list[tuple[str, int]] = [(start_id, 0)]

        while queue and len(result) < limit:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)

            if current_id != start_id:
                node = self._nodes.get(current_id)
                if node:
                    result.append(node)

            # Use adjacency lists for O(degree) traversal instead of O(E)
            candidate_edges: list[dict[str, Any]] = []
            if direction in ("outgoing", "both"):
                candidate_edges.extend(self._edges_out.get(current_id, []))
            if direction in ("incoming", "both"):
                candidate_edges.extend(self._edges_in.get(current_id, []))
            for edge in candidate_edges:
                if edge_type and edge["edge_type"] != edge_type:
                    continue
                neighbor_id = edge["to_id"] if edge["from_id"] == current_id else edge["from_id"]
                if neighbor_id not in visited:
                    queue.append((neighbor_id, depth + 1))

        return result

    def get_edges(
        self,
        node_id: str | None = None,
        edge_type: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        if node_id:
            candidates: list[dict[str, Any]] = []
            if direction in ("outgoing", "both"):
                candidates.extend(self._edges_out.get(node_id, []))
            if direction in ("incoming", "both"):
                candidates.extend(self._edges_in.get(node_id, []))
            if edge_type:
                return [e for e in candidates if e["edge_type"] == edge_type]
            return candidates
        # No node_id — scan all edges
        all_edges: list[dict[str, Any]] = []
        for edges in self._edges_out.values():
            all_edges.extend(edges)
        if edge_type:
            return [e for e in all_edges if e["edge_type"] == edge_type]
        return all_edges

    def batch_add_nodes(self, label: str, nodes: list[dict[str, Any]]) -> int:
        count = 0
        for node in nodes:
            nid = node.get("id", node.get("_id", ""))
            if nid and self.add_node(label, nid, node):
                count += 1
        return count

    def batch_add_edges(self, edges: list[dict[str, Any]]) -> int:
        count = 0
        for edge in edges:
            if self.add_edge(
                edge["from_id"], edge["to_id"],
                edge["edge_type"], edge.get("properties"),
            ):
                count += 1
        return count

    def count(self, label: str | None = None) -> int:
        if label:
            return len(self._label_index.get(label, set()))
        return len(self._nodes)

    def stats(self) -> dict[str, Any]:
        label_counts = {label: len(ids) for label, ids in self._label_index.items() if ids}
        edge_type_counts: dict[str, int] = defaultdict(int)
        edge_count = 0
        for edges in self._edges_out.values():
            for edge in edges:
                edge_type_counts[edge["edge_type"]] += 1
                edge_count += 1
        return {
            "node_count": len(self._nodes),
            "edge_count": edge_count,
            "node_labels": dict(label_counts),
            "edge_types": dict(edge_type_counts),
        }

    def clear(self) -> bool:
        self._nodes.clear()
        self._edges_out.clear()
        self._edges_in.clear()
        self._label_index.clear()
        return True

    def begin_transaction(self) -> None:
        self._in_transaction = True
        self._transaction_snapshot = {
            "nodes": copy.deepcopy(self._nodes),
            "edges_out": {k: list(v) for k, v in self._edges_out.items()},
            "edges_in": {k: list(v) for k, v in self._edges_in.items()},
            "label_index": {k: set(v) for k, v in self._label_index.items()},
        }

    def commit(self) -> None:
        self._in_transaction = False
        self._transaction_snapshot = None

    def rollback(self) -> None:
        if self._transaction_snapshot:
            self._nodes = self._transaction_snapshot["nodes"]
            self._edges_out = defaultdict(list, self._transaction_snapshot["edges_out"])
            self._edges_in = defaultdict(list, self._transaction_snapshot["edges_in"])
            self._label_index = defaultdict(set, self._transaction_snapshot["label_index"])
        self._in_transaction = False
        self._transaction_snapshot = None

    def get_nodes_paginated(self, page_size: int = 500) -> Iterator[list[dict[str, Any]]]:
        items = list(self._nodes.values())
        for i in range(0, max(len(items), 1), page_size):
            page = items[i:i + page_size]
            if page:
                yield page

    def is_available(self) -> bool:
        return True


class MemoryVectorAdapter(VectorAdapter):
    """In-memory vector storage with cosine similarity search."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, dict[str, Any]]] = {}
        self._dimensions: dict[str, int] = {}

    def upsert(
        self,
        collection: str,
        doc_id: str,
        text: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if collection not in self._collections:
            self._collections[collection] = {}
            self._dimensions[collection] = len(vector)
        self._collections[collection][doc_id] = {
            "id": doc_id,
            "text": text,
            "vector": vector,
            "metadata": metadata or {},
        }
        return True

    def batch_upsert(self, collection: str, documents: list[dict[str, Any]]) -> int:
        count = 0
        for doc in documents:
            if self.upsert(
                collection, doc["id"], doc.get("text", ""),
                doc["vector"], doc.get("metadata"),
            ):
                count += 1
        return count

    def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        coll = self._collections.get(collection, {})
        scored: list[tuple[float, dict[str, Any]]] = []

        for doc in coll.values():
            if filters:
                meta = doc.get("metadata", {})
                skip = False
                for k, v in filters.items():
                    if meta.get(k) != v:
                        skip = True
                        break
                if skip:
                    continue

            score = _cosine_similarity(query_vector, doc["vector"])
            if score >= score_threshold:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"id": doc["id"], "score": score, "text": doc["text"], "metadata": doc["metadata"]}
            for score, doc in scored[:top_k]
        ]

    def delete(self, collection: str, doc_id: str) -> bool:
        coll = self._collections.get(collection, {})
        return coll.pop(doc_id, None) is not None

    def ensure_collection(self, collection: str, dimension: int) -> bool:
        if collection not in self._collections:
            self._collections[collection] = {}
            self._dimensions[collection] = dimension
        return True

    def count(self, collection: str) -> int:
        return len(self._collections.get(collection, {}))

    def is_available(self) -> bool:
        return True


class MemoryCacheAdapter(CacheAdapter):
    """In-memory LRU cache with TTL expiration using OrderedDict."""

    def __init__(self, max_size: int = 1000, default_ttl: int = 60) -> None:
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._last_cleanup = time.time()

    def get(self, key: str) -> Any | None:
        # Lazy cleanup every 30s
        if time.time() - self._last_cleanup > 30:
            self._evict_expired()
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[key]
            self._misses += 1
            return None
        self._hits += 1
        # Move to end (most recently used) for true LRU
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        if key in self._store:
            # Update existing — move to end
            del self._store[key]
        elif len(self._store) >= self._max_size:
            self._evict_expired()
            if len(self._store) >= self._max_size:
                # Evict least recently used (first item)
                self._store.popitem(last=False)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        self._store[key] = (value, time.time() + ttl)
        return True

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def invalidate_prefix(self, prefix: str) -> int:
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._store[k]
        return len(keys_to_delete)

    def stats(self) -> dict[str, Any]:
        self._evict_expired()
        total = self._hits + self._misses
        return {
            "size": len(self._store),
            "max_size": self._max_size,
            "hit_count": self._hits,
            "miss_count": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "utilization": len(self._store) / self._max_size if self._max_size > 0 else 0.0,
        }

    def is_available(self) -> bool:
        return True

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
        self._last_cleanup = now


class MultiTierCache(CacheAdapter):
    """Two-tier cache: fast in-memory L1 backed by slower L2 (e.g., Redis).

    On get: check L1 → L2 (promote to L1 on hit).
    On set: write both L1 and L2.
    On invalidate: invalidate both.
    """

    def __init__(self, l1: CacheAdapter, l2: CacheAdapter) -> None:
        self._l1 = l1
        self._l2 = l2

    def get(self, key: str) -> Any | None:
        # Try L1 first (fast, in-memory)
        val = self._l1.get(key)
        if val is not None:
            return val
        # Try L2 (slower, e.g. Redis)
        val = self._l2.get(key)
        if val is not None:
            # Promote to L1 for next access
            self._l1.set(key, val)
        return val

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        # Write to both tiers
        ok1 = self._l1.set(key, value, ttl_seconds=ttl_seconds)
        ok2 = self._l2.set(key, value, ttl_seconds=ttl_seconds)
        return ok1 or ok2

    def delete(self, key: str) -> bool:
        d1 = self._l1.delete(key)
        d2 = self._l2.delete(key)
        return d1 or d2

    def invalidate_prefix(self, prefix: str) -> int:
        c1 = self._l1.invalidate_prefix(prefix)
        c2 = self._l2.invalidate_prefix(prefix)
        return c1 + c2

    def stats(self) -> dict[str, Any]:
        l1_stats = self._l1.stats()
        l2_stats = self._l2.stats()
        return {
            "l1": l1_stats,
            "l2": l2_stats,
            "l1_hit_rate": l1_stats.get("hit_rate", 0),
            "l2_hit_rate": l2_stats.get("hit_rate", 0),
        }

    def is_available(self) -> bool:
        return self._l1.is_available()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
