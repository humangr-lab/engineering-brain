"""Abstract adapter interfaces for the Engineering Knowledge Brain.

Three adapter types provide the hybrid storage engine:
- GraphAdapter: FalkorDB for graph traversal (relationships, hierarchy)
- VectorAdapter: Qdrant for semantic search (embeddings)
- CacheAdapter: Redis for hot caching (L1 memory + L2 distributed)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class GraphAdapter(ABC):
    """Abstract interface for graph storage backends (FalkorDB, Neo4j, memory)."""

    @abstractmethod
    def add_node(self, label: str, node_id: str, properties: dict[str, Any]) -> bool:
        """Create or update a node. Upsert semantics — idempotent."""

    @abstractmethod
    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Retrieve a node by ID. Returns None if not found."""

    @abstractmethod
    def get_all_nodes(self) -> list[dict[str, Any]]:
        """Return all nodes in the graph (for building dynamic indexes)."""

    @abstractmethod
    def update_node(self, node_id: str, properties: dict[str, Any]) -> bool:
        """Partial update — merge properties into existing node. Returns True if node exists."""

    @abstractmethod
    def delete_node(self, node_id: str) -> bool:
        """Delete a node and its edges. Returns True if deleted."""

    @abstractmethod
    def add_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> bool:
        """Create an edge between two nodes. Upsert semantics."""

    @abstractmethod
    def query(
        self,
        label: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query nodes by label and filters."""

    @abstractmethod
    def traverse(
        self,
        start_id: str,
        edge_type: str | None = None,
        direction: str = "outgoing",
        max_depth: int = 2,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Traverse the graph from a starting node."""

    @abstractmethod
    def batch_add_nodes(
        self,
        label: str,
        nodes: list[dict[str, Any]],
    ) -> int:
        """Batch insert nodes. Returns count of nodes added."""

    @abstractmethod
    def get_edges(
        self,
        node_id: str | None = None,
        edge_type: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        """Get edges, optionally filtered by node, type, and direction.

        Args:
            node_id: If set, only edges involving this node.
            edge_type: If set, only edges of this type.
            direction: 'outgoing', 'incoming', or 'both' (relative to node_id).
        """

    @abstractmethod
    def batch_add_edges(
        self,
        edges: list[dict[str, Any]],
    ) -> int:
        """Batch insert edges. Each dict has: from_id, to_id, edge_type, properties."""

    @abstractmethod
    def count(self, label: str | None = None) -> int:
        """Count nodes, optionally filtered by label."""

    @abstractmethod
    def stats(self) -> dict[str, Any]:
        """Get graph statistics: node counts per label, edge counts per type."""

    @abstractmethod
    def clear(self) -> bool:
        """Clear all data. Use with caution."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is reachable."""

    # --- Non-abstract extensions (concrete defaults, no breakage) ---

    def has_edge(self, from_id: str, to_id: str, edge_type: str | None = None) -> bool:
        """Check if an edge exists between two nodes.

        Default implementation scans outgoing edges. Override for O(1) lookups.
        """
        edges = self.get_edges(node_id=from_id, direction="outgoing")
        for edge in edges:
            if edge.get("to_id") == to_id:
                if edge_type is None or edge.get("edge_type") == edge_type:
                    return True
        return False

    def begin_transaction(self) -> None:
        """Begin a write transaction. Default: no-op for adapters without transactions."""

    def commit(self) -> None:
        """Commit the current transaction. Default: no-op."""

    def rollback(self) -> None:
        """Rollback the current transaction. Default: no-op."""

    def get_nodes_paginated(self, page_size: int = 500) -> Iterator[list[dict[str, Any]]]:
        """Yield pages of nodes for memory-efficient iteration.

        Default implementation wraps get_all_nodes() into chunks.
        Override in FalkorDB for SKIP/LIMIT cursor pagination.
        """
        all_nodes = self.get_all_nodes()
        for i in range(0, max(len(all_nodes), 1), page_size):
            page = all_nodes[i : i + page_size]
            if page:
                yield page

    def health_check(self) -> bool:
        """Verify connection is alive. Default: delegates to is_available()."""
        return self.is_available()


class VectorAdapter(ABC):
    """Abstract interface for vector storage backends (Qdrant, memory)."""

    @abstractmethod
    def upsert(
        self,
        collection: str,
        doc_id: str,
        text: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Upsert a single document with its embedding vector."""

    @abstractmethod
    def batch_upsert(
        self,
        collection: str,
        documents: list[dict[str, Any]],
    ) -> int:
        """Batch upsert documents. Each dict: id, text, vector, metadata."""

    @abstractmethod
    def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Search for similar documents. Returns list of {id, score, text, metadata}."""

    @abstractmethod
    def delete(self, collection: str, doc_id: str) -> bool:
        """Delete a document from a collection."""

    @abstractmethod
    def ensure_collection(self, collection: str, dimension: int) -> bool:
        """Ensure a collection exists with the given dimension."""

    @abstractmethod
    def count(self, collection: str) -> int:
        """Count documents in a collection."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is reachable."""

    def health_check(self) -> bool:
        """Verify connection is alive. Default: delegates to is_available()."""
        return self.is_available()


class CacheAdapter(ABC):
    """Abstract interface for caching backends (Redis, memory)."""

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None on miss."""

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        """Set a cached value with optional TTL."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a cached key."""

    @abstractmethod
    def invalidate_prefix(self, prefix: str) -> int:
        """Invalidate all keys with the given prefix. Returns count deleted."""

    @abstractmethod
    def stats(self) -> dict[str, Any]:
        """Get cache statistics: hit_count, miss_count, size, utilization."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the cache is reachable."""
