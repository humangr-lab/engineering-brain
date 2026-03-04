"""Neo4j graph + vector adapter for the Engineering Knowledge Brain.

Uses the official neo4j Python driver with bolt protocol.
Provides real ACID transactions, native list/dict properties,
connection pooling, access to APOC + GDS plugins, and native
vector indexes for semantic search (consolidates graph + vectors
in a single backend — no Qdrant needed for the knowledge graph).
"""

from __future__ import annotations

import atexit
import contextlib
import json
import logging
import os
import re
from collections.abc import Iterator
from typing import Any

from engineering_brain.adapters.base import GraphAdapter, VectorAdapter
from engineering_brain.core.config import BrainConfig

logger = logging.getLogger(__name__)

_CYPHER_IDENT_RE = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_cypher_identifier(s: str) -> str:
    sanitized = _CYPHER_IDENT_RE.sub("", s)
    if not sanitized:
        raise ValueError(f"Invalid Cypher identifier: {s!r}")
    return sanitized


def _sanitize_property_key(k: str) -> str:
    """Validate property key is safe for Cypher interpolation (alphanumeric + underscore only)."""
    sanitized = _CYPHER_IDENT_RE.sub("", k)
    if not sanitized or sanitized != k:
        raise ValueError(f"Invalid property key: {k!r}")
    return k


# Keys whose values are serialized to JSON because Neo4j
# does not support maps or lists-of-maps as property values.
_JSON_SERIALIZED_KEYS = frozenset({"sources", "example_good", "example_bad", "metadata"})


def _serialize_props(props: dict[str, Any]) -> dict[str, Any]:
    """Serialize complex values to JSON strings for Neo4j storage."""
    out: dict[str, Any] = {}
    for k, v in props.items():
        if v is None:
            continue
        if (
            k in _JSON_SERIALIZED_KEYS
            and not isinstance(v, str)
            or isinstance(v, dict)
            or isinstance(v, list)
            and v
            and isinstance(v[0], dict)
        ):
            out[k] = json.dumps(v, ensure_ascii=False, default=str)
        else:
            out[k] = v
    return out


def _deserialize_props(props: dict[str, Any]) -> dict[str, Any]:
    """Deserialize JSON strings back to Python objects on read."""
    out: dict[str, Any] = {}
    for k, v in props.items():
        if k in _JSON_SERIALIZED_KEYS and isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except (json.JSONDecodeError, ValueError):
                out[k] = v
        else:
            out[k] = v
    return out


# Lazy import to avoid hard dependency
_driver = None


def _cleanup_driver() -> None:
    """atexit handler: close the global driver to release connection pool."""
    global _driver
    if _driver is not None:
        try:
            _driver.close()
        except Exception as exc:
            # atexit: logging may be unavailable, but try anyway
            with contextlib.suppress(Exception):
                logger.debug("Neo4j driver close failed at exit: %s", exc)
        _driver = None


atexit.register(_cleanup_driver)


def _get_driver(config: BrainConfig | None = None) -> Any:
    """Lazy-load and return the Neo4j driver singleton."""
    global _driver
    if _driver is not None:
        return _driver
    try:
        import neo4j as neo4j_lib

        uri = config.neo4j_uri if config else "bolt://localhost:7687"
        user = config.neo4j_user if config else "neo4j"
        password = config.neo4j_password if config else os.getenv("BRAIN_NEO4J_PASSWORD", "")
        _driver = neo4j_lib.GraphDatabase.driver(uri, auth=(user, password))
        _driver.verify_connectivity()
        logger.info("Neo4j driver connected to %s", uri)
        return _driver
    except ImportError:
        logger.warning("neo4j package not installed — pip install neo4j")
        return None
    except Exception as e:
        logger.warning("Neo4j connection failed: %s", e)
        _driver = None
        return None


class Neo4jGraphAdapter(GraphAdapter):
    """Neo4j adapter using the official Python driver."""

    def __init__(self, config: BrainConfig | None = None) -> None:
        self._config = config
        self._database = config.neo4j_database if config else "neo4j"
        self._indexes_ensured = False
        # Transaction state
        self._session = None
        self._tx = None

    def _driver(self) -> Any:
        return _get_driver(self._config)

    def _run(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a Cypher query and return result records as dicts.

        If an explicit transaction is active, uses it.
        Otherwise, uses an auto-commit session.
        """
        if self._tx is not None:
            result = self._tx.run(cypher, params or {})
            return [record.data() for record in result]

        driver = self._driver()
        if driver is None:
            return []
        with driver.session(database=self._database) as session:
            result = session.run(cypher, params or {})
            return [record.data() for record in result]

    def _ensure_indexes(self) -> None:
        """Create indexes for common query patterns (idempotent)."""
        if self._indexes_ensured:
            return
        driver = self._driver()
        if driver is None:
            return
        labels = (
            "Rule",
            "Principle",
            "Pattern",
            "Finding",
            "Axiom",
            "Technology",
            "Domain",
            "CodeExample",
            "TestResult",
            "Task",
            "Source",
            "ValidationRun",
        )
        with driver.session(database=self._database) as session:
            for label in labels:
                try:
                    session.run(f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.id)")
                except Exception as exc:
                    logger.debug("Failed to create index for label %s: %s", label, exc)
        self._indexes_ensured = True

    # ------------------------------------------------------------------
    # Node CRUD
    # ------------------------------------------------------------------

    def add_node(self, label: str, node_id: str, properties: dict[str, Any]) -> bool:
        if self._driver() is None:
            return False
        if not self._indexes_ensured:
            self._ensure_indexes()
        try:
            label = _sanitize_cypher_identifier(label)
            raw = {_sanitize_property_key(k): v for k, v in properties.items() if v is not None}
            raw["id"] = node_id
            props = _serialize_props(raw)
            prop_str = ", ".join(f"{k}: ${k}" for k in props)
            cypher = f"MERGE (n:{label} {{id: $id}}) SET n += {{{prop_str}}}"
            self._run(cypher, props)
            return True
        except Exception as e:
            logger.error("Neo4j add_node failed: %s", e)
            return False

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        if self._driver() is None:
            return None
        try:
            records = self._run(
                "MATCH (n {id: $id}) RETURN n",
                {"id": node_id},
            )
            if records:
                node = records[0]["n"]
                return _deserialize_props(dict(node)) if node else None
            return None
        except Exception as e:
            logger.error("Neo4j get_node failed: %s", e)
            return None

    def get_all_nodes(self) -> list[dict[str, Any]]:
        """Return all nodes using cursor-based pagination (avoids OOM)."""
        if self._driver() is None:
            return []
        try:
            page_size = 500
            offset = 0
            all_nodes: list[dict[str, Any]] = []
            while True:
                records = self._run(
                    "MATCH (n) RETURN n SKIP $offset LIMIT $limit",
                    {"offset": offset, "limit": page_size},
                )
                batch = [_deserialize_props(dict(r["n"])) for r in records if r.get("n")]
                all_nodes.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
            return all_nodes
        except Exception as e:
            logger.error("Neo4j get_all_nodes failed: %s", e)
            return []

    def update_node(self, node_id: str, properties: dict[str, Any]) -> bool:
        if self._driver() is None:
            return False
        try:
            safe_props = {_sanitize_property_key(k): v for k, v in properties.items()}
            set_clauses = ", ".join(f"n.{k} = ${k}" for k in safe_props)
            params = {"id": node_id, **safe_props}
            self._run(
                f"MATCH (n {{id: $id}}) SET {set_clauses}",
                params,
            )
            return True
        except Exception as e:
            logger.error("Neo4j update_node failed: %s", e)
            return False

    def delete_node(self, node_id: str) -> bool:
        if self._driver() is None:
            return False
        try:
            self._run(
                "MATCH (n {id: $id}) DETACH DELETE n",
                {"id": node_id},
            )
            return True
        except Exception as e:
            logger.error("Neo4j delete_node failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> bool:
        if self._driver() is None:
            return False
        try:
            edge_type = _sanitize_cypher_identifier(edge_type)
            props = {k: v for k, v in (properties or {}).items() if v is not None}
            prop_str = " SET r += $props" if props else ""
            cypher = (
                f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) "
                f"MERGE (a)-[r:{edge_type}]->(b)"
                f"{prop_str}"
            )
            params: dict[str, Any] = {"from_id": from_id, "to_id": to_id}
            if props:
                params["props"] = props
            self._run(cypher, params)
            return True
        except Exception as e:
            logger.error("Neo4j add_edge failed: %s", e)
            return False

    def get_edges(
        self,
        node_id: str | None = None,
        edge_type: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        if self._driver() is None:
            return []
        try:
            if edge_type:
                edge_type = _sanitize_cypher_identifier(edge_type)
            if node_id:
                parts: list[str] = []
                params: dict[str, Any] = {"nid": node_id}
                rel = f":{edge_type}" if edge_type else ""
                if direction in ("outgoing", "both"):
                    parts.append(
                        f"MATCH (a {{id: $nid}})-[r{rel}]->(b) "
                        f"RETURN a.id AS from_id, type(r) AS edge_type, b.id AS to_id, properties(r) AS props"
                    )
                if direction in ("incoming", "both"):
                    parts.append(
                        f"MATCH (a)-[r{rel}]->(b {{id: $nid}}) "
                        f"RETURN a.id AS from_id, type(r) AS edge_type, b.id AS to_id, properties(r) AS props"
                    )
                cypher = " UNION ".join(parts)
            else:
                params = {}
                if edge_type:
                    cypher = (
                        f"MATCH (a)-[r:{edge_type}]->(b) "
                        f"RETURN a.id AS from_id, type(r) AS edge_type, b.id AS to_id, properties(r) AS props"
                    )
                else:
                    cypher = (
                        "MATCH (a)-[r]->(b) "
                        "RETURN a.id AS from_id, type(r) AS edge_type, b.id AS to_id, properties(r) AS props"
                    )
            records = self._run(cypher, params)
            edges: list[dict[str, Any]] = []
            for rec in records:
                edge: dict[str, Any] = {
                    "from_id": rec["from_id"],
                    "edge_type": rec["edge_type"],
                    "to_id": rec["to_id"],
                }
                if rec.get("props"):
                    edge.update(dict(rec["props"]))
                edges.append(edge)
            return edges
        except Exception as e:
            logger.error("Neo4j get_edges failed: %s", e)
            return []

    def has_edge(self, from_id: str, to_id: str, edge_type: str | None = None) -> bool:
        """O(1) edge existence check using direct MATCH."""
        if self._driver() is None:
            return False
        try:
            if edge_type:
                edge_type = _sanitize_cypher_identifier(edge_type)
            rel = f":{edge_type}" if edge_type else ""
            records = self._run(
                f"MATCH (a {{id: $from_id}})-[r{rel}]->(b {{id: $to_id}}) RETURN count(r) AS cnt",
                {"from_id": from_id, "to_id": to_id},
            )
            return bool(records and records[0].get("cnt", 0) > 0)
        except Exception as exc:
            logger.debug("Neo4j has_edge check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Query & Traverse
    # ------------------------------------------------------------------

    def query(
        self,
        label: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if self._driver() is None:
            return []
        try:
            if label:
                label = _sanitize_cypher_identifier(label)
                cypher = f"MATCH (n:{label})"
            else:
                cypher = "MATCH (n)"

            params: dict[str, Any] = {}
            if filters:
                conditions = []
                for i, (k, v) in enumerate(filters.items()):
                    safe_k = _sanitize_property_key(k)
                    param_name = f"f_{i}"
                    if isinstance(v, list):
                        # Hierarchical prefix matching for dotted taxonomy paths
                        tag = v[0] if v else ""
                        conditions.append(f"n.{safe_k} CONTAINS ${param_name}")
                        params[param_name] = tag
                    else:
                        conditions.append(f"n.{safe_k} = ${param_name}")
                        params[param_name] = v
                if conditions:
                    cypher += " WHERE " + " AND ".join(conditions)

            cypher += f" RETURN n LIMIT {limit}"
            records = self._run(cypher, params)
            return [dict(r["n"]) for r in records if r.get("n")]
        except Exception as e:
            logger.error("Neo4j query failed: %s", e)
            return []

    def traverse(
        self,
        start_id: str,
        edge_type: str | None = None,
        direction: str = "outgoing",
        max_depth: int = 2,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if self._driver() is None:
            return []
        try:
            if edge_type:
                edge_type = _sanitize_cypher_identifier(edge_type)
            rel = f":{edge_type}" if edge_type else ""
            if direction == "outgoing":
                pattern = f"-[{rel}*1..{max_depth}]->"
            elif direction == "incoming":
                pattern = f"<-[{rel}*1..{max_depth}]-"
            else:
                pattern = f"-[{rel}*1..{max_depth}]-"

            cypher = f"MATCH (start {{id: $start_id}}){pattern}(n) RETURN DISTINCT n LIMIT {limit}"
            records = self._run(cypher, {"start_id": start_id})
            return [dict(r["n"]) for r in records if r.get("n")]
        except Exception as e:
            logger.error("Neo4j traverse failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Batch Operations
    # ------------------------------------------------------------------

    def batch_add_nodes(self, label: str, nodes: list[dict[str, Any]]) -> int:
        """Batch add using UNWIND for efficient bulk writes."""
        driver = self._driver()
        if driver is None:
            return 0
        label = _sanitize_cypher_identifier(label)
        # Filter out nodes without ids and strip None values
        serialized = []
        for node in nodes:
            nid = node.get("id", "")
            if not nid:
                continue
            props = {k: v for k, v in node.items() if v is not None}
            props["id"] = nid
            serialized.append(props)
        if not serialized:
            return 0
        if not self._indexes_ensured:
            self._ensure_indexes()
        try:
            cypher = f"UNWIND $nodes AS props MERGE (n:{label} {{id: props.id}}) SET n += props"
            # Use an explicit write transaction for batch
            with driver.session(database=self._database) as session:
                session.execute_write(lambda tx: tx.run(cypher, {"nodes": serialized}).consume())
            return len(serialized)
        except Exception as exc:
            # Fallback to individual inserts
            logger.warning(
                "Neo4j batch_add_nodes UNWIND failed, falling back to individual inserts: %s", exc
            )
            count = 0
            for node in nodes:
                nid = node.get("id", "")
                if nid and self.add_node(label, nid, node):
                    count += 1
            return count

    def batch_add_edges(self, edges: list[dict[str, Any]]) -> int:
        """Batch add edges. Uses UNWIND grouped by edge_type for efficiency."""
        driver = self._driver()
        if driver is None:
            return 0

        # Group edges by type (UNWIND requires same relationship type per query)
        by_type: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            et = edge.get("edge_type", "")
            if not et:
                continue
            by_type.setdefault(et, []).append(edge)

        total = 0
        for edge_type, typed_edges in by_type.items():
            edge_type = _sanitize_cypher_identifier(edge_type)
            batch = []
            for e in typed_edges:
                item: dict[str, Any] = {
                    "from_id": e["from_id"],
                    "to_id": e["to_id"],
                }
                if e.get("properties"):
                    item["props"] = {k: v for k, v in e["properties"].items() if v is not None}
                else:
                    item["props"] = {}
                batch.append(item)

            try:
                cypher = (
                    f"UNWIND $edges AS e "
                    f"MATCH (a {{id: e.from_id}}), (b {{id: e.to_id}}) "
                    f"MERGE (a)-[r:{edge_type}]->(b) "
                    f"SET r += e.props"
                )
                with driver.session(database=self._database) as session:
                    session.execute_write(
                        lambda tx, c=cypher, b=batch: tx.run(c, {"edges": b}).consume()
                    )
                total += len(batch)
            except Exception as exc:
                logger.debug("Neo4j batch_add_edges UNWIND failed for type, falling back: %s", exc)
                # Fallback to individual inserts
                for e in typed_edges:
                    if self.add_edge(
                        e["from_id"],
                        e["to_id"],
                        e["edge_type"],
                        e.get("properties"),
                    ):
                        total += 1
        return total

    # ------------------------------------------------------------------
    # Counts & Stats
    # ------------------------------------------------------------------

    def count(self, label: str | None = None) -> int:
        if self._driver() is None:
            return 0
        try:
            if label:
                label = _sanitize_cypher_identifier(label)
                cypher = f"MATCH (n:{label}) RETURN count(n) AS cnt"
            else:
                cypher = "MATCH (n) RETURN count(n) AS cnt"
            records = self._run(cypher)
            return int(records[0]["cnt"]) if records else 0
        except Exception as e:
            logger.error("Neo4j count failed: %s", e)
            return 0

    def stats(self) -> dict[str, Any]:
        if self._driver() is None:
            return {"node_count": 0, "edge_count": 0, "node_labels": {}, "edge_types": {}}
        try:
            node_count = self.count()

            # Edge count
            try:
                records = self._run("MATCH ()-[r]->() RETURN count(r) AS cnt")
                edge_count = int(records[0]["cnt"]) if records else 0
            except Exception as exc:
                logger.debug("Neo4j edge count query failed: %s", exc)
                edge_count = 0

            # Label counts
            node_labels: dict[str, int] = {}
            try:
                records = self._run(
                    "CALL db.labels() YIELD label "
                    "CALL { WITH label "
                    "MATCH (n) WHERE label IN labels(n) "
                    "RETURN count(n) AS cnt } "
                    "RETURN label, cnt"
                )
                for r in records:
                    node_labels[r["label"]] = int(r["cnt"])
            except Exception as exc:
                logger.debug("Failed to fetch node label counts: %s", exc)

            # Relationship type counts
            edge_types: dict[str, int] = {}
            try:
                records = self._run(
                    "CALL db.relationshipTypes() YIELD relationshipType AS rt "
                    "CALL { WITH rt "
                    "MATCH ()-[r]->() WHERE type(r) = rt "
                    "RETURN count(r) AS cnt } "
                    "RETURN rt, cnt"
                )
                for r in records:
                    edge_types[r["rt"]] = int(r["cnt"])
            except Exception as exc:
                logger.debug("Failed to fetch relationship type counts: %s", exc)

            return {
                "node_count": node_count,
                "edge_count": edge_count,
                "node_labels": node_labels,
                "edge_types": edge_types,
            }
        except Exception as e:
            logger.error("Neo4j stats failed: %s", e)
            return {"node_count": 0, "edge_count": 0, "node_labels": {}, "edge_types": {}}

    # ------------------------------------------------------------------
    # Clear & Availability
    # ------------------------------------------------------------------

    def clear(self) -> bool:
        """Clear all data using batched deletes to avoid memory issues."""
        driver = self._driver()
        if driver is None:
            return False
        try:
            batch_size = 10000
            while True:
                records = self._run(
                    f"MATCH (n) WITH n LIMIT {batch_size} DETACH DELETE n RETURN count(*) AS deleted"
                )
                deleted = int(records[0]["deleted"]) if records else 0
                if deleted < batch_size:
                    break
            return True
        except Exception as e:
            logger.error("Neo4j clear failed: %s", e)
            return False

    def is_available(self) -> bool:
        try:
            driver = self._driver()
            if driver is None:
                return False
            driver.verify_connectivity()
            return True
        except Exception as exc:
            logger.debug("Neo4j availability check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Transactions (real ACID, unlike FalkorDB no-ops)
    # ------------------------------------------------------------------

    def begin_transaction(self) -> None:
        """Begin an explicit write transaction."""
        driver = self._driver()
        if driver is None:
            return
        if self._tx is not None:
            logger.warning("Neo4j: transaction already active, committing previous")
            self.commit()
        self._session = driver.session(database=self._database)
        try:
            self._tx = self._session.begin_transaction()
        except Exception as exc:
            logger.warning("Neo4j begin_transaction failed: %s", exc)
            self._session.close()
            self._session = None
            raise

    def commit(self) -> None:
        """Commit the current transaction."""
        if self._tx is not None:
            try:
                self._tx.commit()
            finally:
                self._tx = None
                if self._session:
                    self._session.close()
                    self._session = None

    def rollback(self) -> None:
        """Rollback the current transaction."""
        if self._tx is not None:
            try:
                self._tx.rollback()
            finally:
                self._tx = None
                if self._session:
                    self._session.close()
                    self._session = None

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def get_nodes_paginated(self, page_size: int = 500) -> Iterator[list[dict[str, Any]]]:
        """Yield pages of nodes using SKIP/LIMIT cursor pagination."""
        if self._driver() is None:
            return
        offset = 0
        while True:
            try:
                records = self._run(
                    "MATCH (n) RETURN n SKIP $offset LIMIT $limit",
                    {"offset": offset, "limit": page_size},
                )
                batch = [_deserialize_props(dict(r["n"])) for r in records if r.get("n")]
                if batch:
                    yield batch
                if len(batch) < page_size:
                    break
                offset += page_size
            except Exception as e:
                logger.error("Neo4j get_nodes_paginated failed: %s", e)
                break

    def health_check(self) -> bool:
        """Ping Neo4j to verify connection is alive."""
        try:
            records = self._run("RETURN 1 AS ok")
            return bool(records and records[0].get("ok") == 1)
        except Exception as exc:
            logger.debug("Neo4j health check failed: %s", exc)
            global _driver
            _driver = None  # Force reconnect on next call
            return False

    # ------------------------------------------------------------------
    # Neo4j-specific extras (not in base interface)
    # ------------------------------------------------------------------

    def run_cypher(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute arbitrary Cypher. Useful for GDS/APOC calls."""
        return self._run(cypher, params)

    def __del__(self) -> None:
        """Clean up session on garbage collection to prevent leaks.

        Guards against interpreter shutdown (globals may be None).
        """
        try:
            if self._session is not None:
                if self._tx is not None:
                    self._tx.rollback()
                self._session.close()
                self._session = None
                self._tx = None
        except Exception:
            pass

    def close(self) -> None:
        """Close the driver connection. Call on shutdown."""
        global _driver
        if self._tx:
            self.rollback()
        if _driver is not None:
            try:
                _driver.close()
            except Exception as exc:
                logger.debug("Error closing Neo4j driver: %s", exc)
            _driver = None


# ======================================================================
# Neo4j Vector Adapter — native vector index for semantic search
# ======================================================================

# Map brain collection names to Neo4j labels for vector indexing
_COLLECTION_TO_LABEL: dict[str, str] = {
    "brain_L1": "Principle",
    "brain_principles": "Principle",
    "L1": "Principle",
    "brain_L2": "Pattern",
    "brain_patterns": "Pattern",
    "L2": "Pattern",
    "brain_L3": "Rule",
    "brain_rules": "Rule",
    "L3": "Rule",
    "brain_L4": "Finding",
    "brain_evidence": "Finding",
    "L4": "Finding",
    "brain_axioms": "Axiom",
    "brain_L0": "Axiom",
    "L0": "Axiom",
}

# Reverse: label → canonical collection name (for count/stats)
_LABEL_TO_COLLECTION: dict[str, str] = {
    "Principle": "brain_L1",
    "Pattern": "brain_L2",
    "Rule": "brain_L3",
    "Finding": "brain_L4",
    "Axiom": "brain_L1",  # Axioms share L1 collection
}


class Neo4jVectorAdapter(VectorAdapter):
    """Vector adapter using Neo4j native vector indexes.

    Stores embeddings as a `_embedding` property on nodes and creates
    per-label vector indexes for cosine similarity search.
    Eliminates the need for Qdrant for knowledge graph vectors.
    """

    def __init__(self, config: BrainConfig | None = None) -> None:
        self._config = config
        self._database = config.neo4j_database if config else "neo4j"
        self._dimension = config.embedding_dimension if config else 1024
        self._indexes_created: set[str] = set()

    def _driver(self) -> Any:
        return _get_driver(self._config)

    def _run(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute Cypher and return records as dicts."""
        driver = self._driver()
        if driver is None:
            return []
        with driver.session(database=self._database) as session:
            result = session.run(cypher, params or {})
            return [record.data() for record in result]

    def _label_for_collection(self, collection: str) -> str:
        """Resolve collection name to Neo4j label."""
        # Strip prefix if present
        clean = (
            collection.replace("brain_", "").upper()
            if collection.startswith("brain_")
            else collection
        )
        return _COLLECTION_TO_LABEL.get(collection, _COLLECTION_TO_LABEL.get(clean, "Rule"))

    def _index_name(self, label: str) -> str:
        """Deterministic vector index name per label."""
        return f"brain_vec_{label.lower()}"

    def ensure_collection(self, collection: str, dimension: int) -> bool:
        """Create a Neo4j vector index for the given collection/label."""
        driver = self._driver()
        if driver is None:
            return False
        label = self._label_for_collection(collection)
        idx_name = self._index_name(label)
        if idx_name in self._indexes_created:
            return True
        try:
            # CREATE VECTOR INDEX is idempotent with IF NOT EXISTS (Neo4j 5.11+)
            cypher = (
                f"CREATE VECTOR INDEX {idx_name} IF NOT EXISTS "
                f"FOR (n:{label}) ON (n._embedding) "
                f"OPTIONS {{indexConfig: {{"
                f"  `vector.dimensions`: $dim,"
                f"  `vector.similarity_function`: 'cosine'"
                f"}}}}"
            )
            self._run(cypher, {"dim": dimension})
            self._indexes_created.add(idx_name)
            logger.info(
                "Neo4j vector index '%s' ensured (label=%s, dim=%d)", idx_name, label, dimension
            )
            return True
        except Exception as e:
            # Some Neo4j versions may not support CREATE VECTOR INDEX
            logger.warning("Neo4j ensure_collection (vector index) failed: %s", e)
            self._indexes_created.add(idx_name)  # Don't retry
            return False

    def upsert(
        self,
        collection: str,
        doc_id: str,
        text: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store embedding as _embedding property on the node."""
        driver = self._driver()
        if driver is None:
            return False
        try:
            self.ensure_collection(collection, len(vector))
            # Update existing node with embedding + text snippet
            cypher = "MATCH (n {id: $doc_id}) SET n._embedding = $vector, n._embed_text = $text"
            params: dict[str, Any] = {
                "doc_id": doc_id,
                "vector": vector,
                "text": text[:500],
            }
            if metadata:
                # Store searchable metadata fields
                for k in ("layer", "technologies", "domains", "confidence"):
                    if k in metadata:
                        cypher += f", n._meta_{k} = ${k}"
                        params[k] = metadata[k]
            self._run(cypher, params)
            return True
        except Exception as e:
            logger.error("Neo4j vector upsert failed for %s: %s", doc_id, e)
            return False

    def batch_upsert(self, collection: str, documents: list[dict[str, Any]]) -> int:
        """Batch store embeddings using UNWIND."""
        driver = self._driver()
        if driver is None or not documents:
            return 0
        try:
            dim = len(documents[0].get("vector", []))
            self.ensure_collection(collection, dim)

            batch = []
            for doc in documents:
                item: dict[str, Any] = {
                    "doc_id": doc["id"],
                    "vector": doc["vector"],
                    "text": doc.get("text", "")[:500],
                }
                batch.append(item)

            cypher = (
                "UNWIND $batch AS item "
                "MATCH (n {id: item.doc_id}) "
                "SET n._embedding = item.vector, n._embed_text = item.text"
            )
            with driver.session(database=self._database) as session:
                session.execute_write(lambda tx: tx.run(cypher, {"batch": batch}).consume())
            return len(batch)
        except Exception as e:
            logger.error("Neo4j vector batch_upsert failed: %s", e)
            # Fallback to individual upserts
            count = 0
            for doc in documents:
                if self.upsert(
                    collection, doc["id"], doc.get("text", ""), doc["vector"], doc.get("metadata")
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
        """Semantic search using Neo4j native vector index."""
        driver = self._driver()
        if driver is None:
            return []
        label = self._label_for_collection(collection)
        idx_name = self._index_name(label)
        try:
            # Use db.index.vector.queryNodes (Neo4j 5.11+)
            cypher = "CALL db.index.vector.queryNodes($idx, $top_k, $qvec) YIELD node, score "
            # Apply optional filters
            where_parts: list[str] = []
            params: dict[str, Any] = {
                "idx": idx_name,
                "top_k": top_k,
                "qvec": query_vector,
            }
            if score_threshold > 0:
                where_parts.append("score >= $threshold")
                params["threshold"] = score_threshold
            if filters:
                for k, v in filters.items():
                    pk = f"f_{k}"
                    where_parts.append(f"node._meta_{k} = ${pk}")
                    params[pk] = v

            if where_parts:
                cypher += "WHERE " + " AND ".join(where_parts) + " "

            cypher += (
                "RETURN node.id AS id, score, node._embed_text AS text, "
                "node.technologies AS technologies, node.domains AS domains, "
                "node._meta_layer AS layer, node._meta_confidence AS confidence "
                "ORDER BY score DESC"
            )
            records = self._run(cypher, params)
            results = []
            for r in records:
                results.append(
                    {
                        "id": r.get("id", ""),
                        "score": float(r.get("score", 0.0)),
                        "text": r.get("text", ""),
                        "metadata": {
                            "node_id": r.get("id", ""),
                            "layer": r.get("layer", ""),
                            "technologies": r.get("technologies", []),
                            "domains": r.get("domains", []),
                            "confidence": r.get("confidence", 0.5),
                        },
                    }
                )
            return results
        except Exception as e:
            logger.error("Neo4j vector search failed: %s", e)
            return []

    def delete(self, collection: str, doc_id: str) -> bool:
        """Remove embedding from a node."""
        try:
            self._run(
                "MATCH (n {id: $doc_id}) REMOVE n._embedding, n._embed_text",
                {"doc_id": doc_id},
            )
            return True
        except Exception as e:
            logger.error("Neo4j vector delete failed: %s", e)
            return False

    def count(self, collection: str) -> int:
        """Count nodes with embeddings in a collection."""
        try:
            label = self._label_for_collection(collection)
            records = self._run(
                f"MATCH (n:{label}) WHERE n._embedding IS NOT NULL RETURN count(n) AS cnt"
            )
            return int(records[0]["cnt"]) if records else 0
        except Exception as e:
            logger.error("Neo4j vector count failed: %s", e)
            return 0

    def is_available(self) -> bool:
        try:
            driver = self._driver()
            if driver is None:
                return False
            driver.verify_connectivity()
            return True
        except Exception as exc:
            logger.debug("Neo4j vector adapter availability check failed: %s", exc)
            return False

    def health_check(self) -> bool:
        """Check Neo4j connectivity + vector index availability."""
        try:
            records = self._run("RETURN 1 AS ok")
            return bool(records and records[0].get("ok") == 1)
        except Exception as exc:
            logger.debug("Neo4j vector adapter health check failed: %s", exc)
            return False
