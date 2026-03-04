"""FalkorDB graph adapter for the Engineering Knowledge Brain.

Provides graph traversal, relationship queries, and batch operations
for the knowledge graph. Requires `falkordb` package.

Graceful degradation:
- _get_client() returns None if falkordb is not installed
- All methods return empty results / False on unavailable client
- Use BRAIN_ADAPTER=memory for fully standalone operation (no FalkorDB needed)
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from typing import Any

from engineering_brain.adapters.base import GraphAdapter
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


_falkordb_client = None


def _get_client(config: BrainConfig | None = None) -> Any:
    """Lazy-load and return the FalkorDB client singleton."""
    global _falkordb_client
    if _falkordb_client is not None:
        return _falkordb_client
    try:
        import falkordb

        host = config.falkordb_host if config else "localhost"
        port = config.falkordb_port if config else 6379
        _falkordb_client = falkordb.FalkorDB(host=host, port=port)
        return _falkordb_client
    except ImportError:
        logger.info("falkordb package not installed — FalkorDB adapter disabled")
        return None
    except Exception as e:
        logger.warning("FalkorDB connection failed: %s", e)
        return None


def _serialize_value(value: Any) -> Any:
    """Serialize a value for FalkorDB storage."""
    if isinstance(value, list):
        return json.dumps(value)
    if isinstance(value, dict):
        return json.dumps(value)
    if value is None:
        return ""
    return value


def _deserialize_node(raw: dict[str, Any]) -> dict[str, Any]:
    """Deserialize FalkorDB node properties back to Python types."""
    result = {}
    for k, v in raw.items():
        if isinstance(v, str) and v.startswith("[") and v.endswith("]"):
            try:
                result[k] = json.loads(v)
                continue
            except (json.JSONDecodeError, ValueError):
                pass
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            try:
                result[k] = json.loads(v)
                continue
            except (json.JSONDecodeError, ValueError):
                pass
        result[k] = v
    return result


class FalkorDBGraphAdapter(GraphAdapter):
    """FalkorDB graph adapter with Cypher-based queries."""

    def __init__(self, config: BrainConfig | None = None) -> None:
        self._config = config
        self._graph_name = config.falkordb_database if config else "engineering_brain"
        self._graph_instance = None
        self._indexes_ensured = False

    def _client(self) -> Any:
        return _get_client(self._config)

    def _graph(self) -> Any:
        """Get the FalkorDB graph instance (cached after first access)."""
        if self._graph_instance is not None:
            return self._graph_instance
        client = self._client()
        if client is None:
            return None
        try:
            self._graph_instance = client.select_graph(self._graph_name)
        except Exception as e:
            logger.warning("Cannot get FalkorDB graph: %s", e)
            return None
        if self._graph_instance and not self._indexes_ensured:
            self._ensure_indexes()
        return self._graph_instance

    def _ensure_indexes(self) -> None:
        """Create indexes for common query patterns (idempotent)."""
        graph = self._graph_instance
        if graph is None:
            return
        for label in (
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
        ):
            for prop in ("id",):
                try:
                    graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
                except Exception as exc:
                    logger.debug("Index creation skipped for %s.%s: %s", label, prop, exc)
        self._indexes_ensured = True

    def add_node(self, label: str, node_id: str, properties: dict[str, Any]) -> bool:
        graph = self._graph()
        if graph is None:
            return False
        try:
            label = _sanitize_cypher_identifier(label)
            props = {_sanitize_property_key(k): _serialize_value(v) for k, v in properties.items()}
            props["id"] = node_id
            prop_str = ", ".join(f"{k}: ${k}" for k in props)
            cypher = f"MERGE (n:{label} {{id: $id}}) SET n += {{{prop_str}}}"
            graph.query(cypher, props)
            return True
        except Exception as e:
            logger.error("FalkorDB add_node failed: %s", e)
            return False

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        graph = self._graph()
        if graph is None:
            return None
        try:
            result = graph.query(
                "MATCH (n {id: $id}) RETURN n",
                {"id": node_id},
            )
            if result.result_set:
                row = result.result_set[0]
                if row:
                    node = row[0]
                    return _deserialize_node(
                        node.properties if hasattr(node, "properties") else dict(node)
                    )
            return None
        except Exception as e:
            logger.error("FalkorDB get_node failed: %s", e)
            return None

    def get_all_nodes(self) -> list[dict[str, Any]]:
        """Return all nodes using cursor-based pagination (avoids OOM on large graphs)."""
        graph = self._graph()
        if graph is None:
            return []
        try:
            page_size = 500
            offset = 0
            all_nodes: list[dict[str, Any]] = []
            while True:
                result = graph.query(f"MATCH (n) RETURN n SKIP {offset} LIMIT {page_size}")
                batch = []
                for row in result.result_set or []:
                    if row:
                        node = row[0]
                        props = node.properties if hasattr(node, "properties") else dict(node)
                        batch.append(_deserialize_node(props))
                all_nodes.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
            return all_nodes
        except Exception as e:
            logger.error("FalkorDB get_all_nodes failed: %s", e)
            return []

    def update_node(self, node_id: str, properties: dict[str, Any]) -> bool:
        graph = self._graph()
        if graph is None:
            return False
        try:
            safe_props = {_sanitize_property_key(k): v for k, v in properties.items()}
            set_clauses = ", ".join(f"n.{k} = ${k}" for k in safe_props)
            params = {"id": node_id, **safe_props}
            graph.query(
                f"MATCH (n {{id: $id}}) SET {set_clauses}",
                params,
            )
            return True
        except Exception as e:
            logger.error("FalkorDB update_node failed: %s", e)
            return False

    def delete_node(self, node_id: str) -> bool:
        graph = self._graph()
        if graph is None:
            return False
        try:
            graph.query(
                "MATCH (n {id: $id}) DETACH DELETE n",
                {"id": node_id},
            )
            return True
        except Exception as e:
            logger.error("FalkorDB delete_node failed: %s", e)
            return False

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> bool:
        graph = self._graph()
        if graph is None:
            return False
        try:
            edge_type = _sanitize_cypher_identifier(edge_type)
            props = {
                _sanitize_property_key(k): _serialize_value(v)
                for k, v in (properties or {}).items()
            }
            prop_str = " {" + ", ".join(f"{k}: ${k}" for k in props) + "}" if props else ""
            cypher = (
                f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) MERGE (a)-[r:{edge_type}]->(b) "
            )
            if prop_str:
                cypher += f"SET r += {prop_str}"
            params = {"from_id": from_id, "to_id": to_id, **props}
            graph.query(cypher, params)
            return True
        except Exception as e:
            logger.error("FalkorDB add_edge failed: %s", e)
            return False

    def query(
        self,
        label: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        graph = self._graph()
        if graph is None:
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
                        # Hierarchical prefix matching for dotted taxonomy paths.
                        # "language.python" matches node tag "language.python.web.flask"
                        # "language.python.web.flask.cors" matches node tag "language.python.web.flask"
                        tag = v[0] if v else ""
                        conditions.append(f"n.{safe_k} CONTAINS ${param_name}")
                        params[param_name] = tag
                    else:
                        conditions.append(f"n.{safe_k} = ${param_name}")
                        params[param_name] = v
                if conditions:
                    cypher += " WHERE " + " AND ".join(conditions)

            cypher += f" RETURN n LIMIT {limit}"
            result = graph.query(cypher, params)
            nodes = []
            for row in result.result_set or []:
                if row:
                    node = row[0]
                    props = node.properties if hasattr(node, "properties") else dict(node)
                    nodes.append(_deserialize_node(props))
            return nodes
        except Exception as e:
            logger.error("FalkorDB query failed: %s", e)
            return []

    def traverse(
        self,
        start_id: str,
        edge_type: str | None = None,
        direction: str = "outgoing",
        max_depth: int = 2,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        graph = self._graph()
        if graph is None:
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
            result = graph.query(cypher, {"start_id": start_id})
            nodes = []
            for row in result.result_set or []:
                if row:
                    node = row[0]
                    props = node.properties if hasattr(node, "properties") else dict(node)
                    nodes.append(_deserialize_node(props))
            return nodes
        except Exception as e:
            logger.error("FalkorDB traverse failed: %s", e)
            return []

    def get_edges(
        self,
        node_id: str | None = None,
        edge_type: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        graph = self._graph()
        if graph is None:
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
                        f"RETURN a.id AS from_id, type(r) AS edge_type, b.id AS to_id, r"
                    )
                if direction in ("incoming", "both"):
                    parts.append(
                        f"MATCH (a)-[r{rel}]->(b {{id: $nid}}) "
                        f"RETURN a.id AS from_id, type(r) AS edge_type, b.id AS to_id, r"
                    )
                cypher = " UNION ".join(parts)
            else:
                params = {}
                if edge_type:
                    cypher = (
                        f"MATCH (a)-[r:{edge_type}]->(b) "
                        f"RETURN a.id AS from_id, type(r) AS edge_type, b.id AS to_id, r"
                    )
                else:
                    cypher = (
                        "MATCH (a)-[r]->(b) "
                        "RETURN a.id AS from_id, type(r) AS edge_type, b.id AS to_id, r"
                    )
            result = graph.query(cypher, params)
            edges: list[dict[str, Any]] = []
            for row in result.result_set or []:
                if row and len(row) >= 3:
                    edge: dict[str, Any] = {
                        "from_id": row[0],
                        "edge_type": row[1],
                        "to_id": row[2],
                    }
                    if len(row) > 3 and row[3] is not None:
                        raw_props = row[3].properties if hasattr(row[3], "properties") else {}
                        if raw_props:
                            deserialized = _deserialize_node(dict(raw_props))
                            edge.update(deserialized)
                    edges.append(edge)
            return edges
        except Exception as e:
            logger.error("FalkorDB get_edges failed: %s", e)
            return []

    def has_edge(self, from_id: str, to_id: str, edge_type: str | None = None) -> bool:
        """O(1) edge existence check using direct MATCH."""
        graph = self._graph()
        if graph is None:
            return False
        try:
            if edge_type:
                edge_type = _sanitize_cypher_identifier(edge_type)
            rel = f":{edge_type}" if edge_type else ""
            result = graph.query(
                f"MATCH (a {{id: $from_id}})-[r{rel}]->(b {{id: $to_id}}) RETURN count(r) AS cnt",
                {"from_id": from_id, "to_id": to_id},
            )
            if result.result_set and result.result_set[0]:
                return int(result.result_set[0][0]) > 0
            return False
        except Exception as exc:
            logger.debug("FalkorDB has_edge check failed: %s", exc)
            return False

    def batch_add_nodes(self, label: str, nodes: list[dict[str, Any]]) -> int:
        """Batch add using UNWIND for efficient bulk writes."""
        graph = self._graph()
        if graph is None:
            return 0
        label = _sanitize_cypher_identifier(label)
        serialized = []
        for node in nodes:
            nid = node.get("id", "")
            if not nid:
                continue
            props = {k: _serialize_value(v) for k, v in node.items()}
            props["id"] = nid
            serialized.append(props)
        if not serialized:
            return 0
        try:
            cypher = f"UNWIND $nodes AS props MERGE (n:{label} {{id: props.id}}) SET n += props"
            graph.query(cypher, {"nodes": serialized})
            return len(serialized)
        except Exception as exc:
            logger.debug("FalkorDB batch add failed, falling back to individual inserts: %s", exc)
            # Fallback to individual inserts
            count = 0
            for node in nodes:
                nid = node.get("id", "")
                if nid and self.add_node(label, nid, node):
                    count += 1
            return count

    def batch_add_edges(self, edges: list[dict[str, Any]]) -> int:
        count = 0
        for edge in edges:
            if self.add_edge(
                edge["from_id"],
                edge["to_id"],
                edge["edge_type"],
                edge.get("properties"),
            ):
                count += 1
        return count

    def count(self, label: str | None = None) -> int:
        graph = self._graph()
        if graph is None:
            return 0
        try:
            if label:
                label = _sanitize_cypher_identifier(label)
                cypher = f"MATCH (n:{label}) RETURN count(n) as cnt"
            else:
                cypher = "MATCH (n) RETURN count(n) as cnt"
            result = graph.query(cypher)
            if result.result_set and result.result_set[0]:
                return int(result.result_set[0][0])
            return 0
        except Exception as e:
            logger.error("FalkorDB count failed: %s", e)
            return 0

    def stats(self) -> dict[str, Any]:
        graph = self._graph()
        if graph is None:
            return {"node_count": 0, "edge_count": 0, "node_labels": {}, "edge_types": {}}
        try:
            node_count = self.count()
            # Count edges
            try:
                result = graph.query("MATCH ()-[r]->() RETURN count(r) as cnt")
                edge_count = int(result.result_set[0][0]) if result.result_set else 0
            except Exception as exc:
                logger.debug("FalkorDB edge count query failed: %s", exc)
                edge_count = 0

            # Label counts
            node_labels: dict[str, int] = {}
            for label in (
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
            ):
                try:
                    cnt = self.count(label)
                    if cnt > 0:
                        node_labels[label] = cnt
                except Exception as exc:
                    logger.debug("Failed to count nodes for label %s: %s", label, exc)

            # Edge type counts
            edge_types: dict[str, int] = {}
            try:
                result = graph.query("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS cnt")
                for row in result.result_set or []:
                    if row and len(row) >= 2:
                        edge_types[str(row[0])] = int(row[1])
            except Exception as exc:
                logger.debug("Failed to query edge type counts: %s", exc)

            return {
                "node_count": node_count,
                "edge_count": edge_count,
                "node_labels": node_labels,
                "edge_types": edge_types,
            }
        except Exception as e:
            logger.error("FalkorDB stats failed: %s", e)
            return {"node_count": 0, "edge_count": 0, "node_labels": {}, "edge_types": {}}

    def clear(self) -> bool:
        graph = self._graph()
        if graph is None:
            return False
        try:
            graph.query("MATCH (n) DETACH DELETE n")
            return True
        except Exception as e:
            logger.error("FalkorDB clear failed: %s", e)
            return False

    def begin_transaction(self) -> None:
        """FalkorDB uses implicit transactions per query. No explicit begin needed."""

    def commit(self) -> None:
        """FalkorDB auto-commits each query."""

    def rollback(self) -> None:
        """FalkorDB has no multi-statement rollback via Python client."""

    def get_nodes_paginated(self, page_size: int = 500) -> Iterator[list[dict[str, Any]]]:
        """Yield pages of nodes using SKIP/LIMIT cursor pagination."""
        graph = self._graph()
        if graph is None:
            return
        offset = 0
        while True:
            try:
                result = graph.query(f"MATCH (n) RETURN n SKIP {offset} LIMIT {page_size}")
                batch = []
                for row in result.result_set or []:
                    if row:
                        node = row[0]
                        props = node.properties if hasattr(node, "properties") else dict(node)
                        batch.append(_deserialize_node(props))
                if batch:
                    yield batch
                if len(batch) < page_size:
                    break
                offset += page_size
            except Exception as e:
                logger.error("FalkorDB get_nodes_paginated failed: %s", e)
                break

    def health_check(self) -> bool:
        """Ping FalkorDB to verify connection is alive."""
        try:
            graph = self._graph()
            if graph is None:
                return False
            graph.query("RETURN 1")
            return True
        except Exception as exc:
            logger.debug("FalkorDB health check failed: %s", exc)
            self._graph_instance = None  # Force reconnect on next call
            return False

    def is_available(self) -> bool:
        try:
            client = self._client()
            return client is not None
        except Exception as exc:
            logger.debug("FalkorDB availability check failed: %s", exc)
            return False
