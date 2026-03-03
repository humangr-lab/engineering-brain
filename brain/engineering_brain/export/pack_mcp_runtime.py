"""Self-contained MCP runtime for exported pack servers.

THIS FILE IS COPIED INTO EVERY EXPORTED PACK. It has ZERO dependency on
engineering_brain. All it needs is Python 3.11+ (stdlib only).

Contains:
- PackIndex — in-memory index over pack nodes
- 7 handler strategies (search, code, lookup, list, traverse, aggregate, stats)
- Formatters (standard, violation_check, chain, multi_layer, single_node)
- JSON-RPC 2.0 stdio loop (MCP protocol)
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any


# =============================================================================
# PackIndex — in-memory index over pack nodes
# =============================================================================

class PackIndex:
    """In-memory index over pack nodes for fast lookups."""

    def __init__(self, pack_data: dict[str, Any]) -> None:
        self.pack_data = pack_data
        self.nodes: list[dict[str, Any]] = pack_data.get("nodes", [])
        self.edges: list[dict[str, Any]] = pack_data.get("edges", [])
        self.reasoning_edges: list[dict[str, Any]] = pack_data.get("reasoning_edges", [])
        self.metadata = pack_data.get("metadata", {})

        # Build indexes
        self._by_id: dict[str, dict[str, Any]] = {}
        self._by_layer: dict[str, list[dict[str, Any]]] = {}
        self._by_domain: dict[str, list[dict[str, Any]]] = {}
        self._by_technology: dict[str, list[dict[str, Any]]] = {}
        self._by_severity: dict[str, list[dict[str, Any]]] = {}

        for node in self.nodes:
            nid = node.get("id", "")
            self._by_id[nid] = node

            layer = self._infer_layer(nid)
            self._by_layer.setdefault(layer, []).append(node)

            for d in (node.get("domains") or []):
                self._by_domain.setdefault(d.lower(), []).append(node)

            for t in (node.get("technologies") or node.get("languages") or []):
                self._by_technology.setdefault(t.lower(), []).append(node)

            severity = node.get("severity", "")
            if severity:
                self._by_severity.setdefault(severity.lower(), []).append(node)

    @staticmethod
    def _infer_layer(node_id: str) -> str:
        if node_id.startswith("AX-"):
            return "L0"
        if node_id.startswith("P-"):
            return "L1"
        if node_id.startswith(("PAT-", "CPAT-")):
            return "L2"
        if node_id.startswith("F-"):
            return "L4"
        return "L3"

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._by_id.get(node_id)

    def get_by_layer(self, layer: str) -> list[dict[str, Any]]:
        return self._by_layer.get(layer, [])

    def get_by_domain(self, domain: str) -> list[dict[str, Any]]:
        return self._by_domain.get(domain.lower(), [])

    def get_by_technology(self, technology: str) -> list[dict[str, Any]]:
        return self._by_technology.get(technology.lower(), [])

    def get_by_severity(self, severity: str) -> list[dict[str, Any]]:
        return self._by_severity.get(severity.lower(), [])

    def get_neighbors(self, node_id: str) -> list[dict[str, Any]]:
        """Get nodes connected by reasoning edges."""
        neighbor_ids: set[str] = set()
        for edge in self.reasoning_edges:
            if edge.get("from_id") == node_id:
                neighbor_ids.add(edge.get("to_id", ""))
            elif edge.get("to_id") == node_id:
                neighbor_ids.add(edge.get("from_id", ""))
        return [self._by_id[nid] for nid in neighbor_ids if nid in self._by_id]

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Keyword search with scoring."""
        query_lower = query.lower()
        query_words = set(re.findall(r'\w+', query_lower))
        scored: list[tuple[float, dict[str, Any]]] = []

        for node in self.nodes:
            score = self._relevance_score(node, query_lower, query_words)
            if score > 0:
                scored.append((score, node))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [n for _, n in scored[:top_k]]

    def _relevance_score(
        self,
        node: dict[str, Any],
        query_lower: str,
        query_words: set[str],
    ) -> float:
        """Compute relevance score for a node against a query."""
        score = 0.0

        # Text fields to search
        searchable = " ".join(str(node.get(f, "")) for f in (
            "text", "name", "why", "how_to_do_right", "how_to_apply",
            "intent", "statement", "description", "mental_model",
        )).lower()

        if not searchable:
            return 0.0

        # Exact substring match
        if query_lower in searchable:
            score += 3.0

        # Word overlap
        node_words = set(re.findall(r'\w+', searchable))
        overlap = query_words & node_words
        if overlap:
            score += len(overlap) / max(len(query_words), 1)

        # Technology match
        techs = [t.lower() for t in (node.get("technologies") or node.get("languages") or [])]
        tech_overlap = query_words & set(techs)
        if tech_overlap:
            score += 2.0

        # Severity boost
        severity = node.get("severity", "medium")
        severity_boost = {"critical": 0.4, "high": 0.2, "medium": 0.0, "low": -0.1}
        score += severity_boost.get(severity, 0.0)

        # Confidence boost
        confidence = float(node.get("confidence", 0.5))
        score += confidence * 0.3

        return score


# =============================================================================
# Handler strategies
# =============================================================================

def handle_query(index: PackIndex, args: dict[str, Any], config: dict[str, Any]) -> str:
    """Search by relevance — keyword search + boosts."""
    query = args.get("query", args.get("code", args.get("topic", args.get("description", ""))))
    if not query:
        return "No query provided."

    technology = args.get("technology", "")
    top_k = args.get("top_k", 10)

    # Combine query with technology for better matching
    search_query = f"{query} {technology}".strip()
    results = index.search(search_query, top_k=top_k)

    # Filter by config layers if specified
    layers = config.get("layers")
    if layers:
        results = [n for n in results if index._infer_layer(n.get("id", "")) in layers]

    # Filter by config domains if specified
    domains = config.get("domains")
    if domains:
        results = [
            n for n in results
            if any(d.lower() in [x.lower() for x in (n.get("domains") or [])] for d in domains)
            or not n.get("domains")
        ]

    if not results:
        return f"No relevant knowledge found for: {query}"

    return format_results(results, config)


def handle_filter(index: PackIndex, args: dict[str, Any], config: dict[str, Any]) -> str:
    """Filter nodes by layer/domain/technology."""
    results: list[dict[str, Any]] = list(index.nodes)

    # Layer filter
    layers = config.get("layers")
    if layers:
        results = [n for n in results if index._infer_layer(n.get("id", "")) in layers]

    # Domain filter (from config or args)
    domains = config.get("domains") or []
    domain_arg = args.get("domain", "")
    if domain_arg:
        domains = [domain_arg]
    if domains:
        filtered = []
        for n in results:
            node_doms = [d.lower() for d in (n.get("domains") or [])]
            if any(d.lower() in node_doms for d in domains) or not node_doms:
                filtered.append(n)
        results = filtered

    # Technology filter
    technology = args.get("technology", "")
    if technology:
        filtered = []
        for n in results:
            node_techs = [t.lower() for t in (n.get("technologies") or n.get("languages") or [])]
            if technology.lower() in node_techs or not node_techs:
                filtered.append(n)
        results = filtered

    # Sort by severity if configured
    sort_by = config.get("sort_by")
    if sort_by == "severity":
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        results.sort(key=lambda n: severity_order.get(n.get("severity", "medium"), 2))

    if not results:
        return "No matching knowledge found."

    return format_results(results, config)


def handle_lookup(index: PackIndex, args: dict[str, Any], config: dict[str, Any]) -> str:
    """Direct node ID lookup or pattern-based single node search."""
    node_id = args.get("rule_id", args.get("node_id", ""))
    if node_id:
        node = index.get_node(node_id)
        if node:
            return format_single_node(node, config)
        return f"Node {node_id!r} not found in this pack."

    # Pattern-based search
    pattern = args.get("pattern", args.get("topic", ""))
    if pattern:
        results = index.search(pattern, top_k=3)
        if results:
            return format_single_node(results[0], config)

    return "No node found. Provide a node_id or search pattern."


def handle_traverse(index: PackIndex, args: dict[str, Any], config: dict[str, Any]) -> str:
    """Follow reasoning edge chains from a starting point."""
    query = args.get("principle", args.get("component", args.get("topic", "")))
    if not query:
        return "No starting point provided."

    # Find starting node
    results = index.search(query, top_k=1)
    if not results:
        return f"No starting node found for: {query}"

    start_node = results[0]
    start_id = start_node.get("id", "")

    # BFS through reasoning edges (max 3 hops)
    visited: set[str] = {start_id}
    chain: list[dict[str, Any]] = [start_node]
    frontier = [start_id]

    for _hop in range(3):
        next_frontier: list[str] = []
        for nid in frontier:
            neighbors = index.get_neighbors(nid)
            for neighbor in neighbors:
                neighbor_id = neighbor.get("id", "")
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    chain.append(neighbor)
                    next_frontier.append(neighbor_id)
        frontier = next_frontier
        if not frontier:
            break

    return format_chain(chain, index)


def handle_aggregate(index: PackIndex, args: dict[str, Any], config: dict[str, Any]) -> str:
    """Multi-layer topic explanation."""
    topic = args.get("topic", args.get("options", args.get("concept", "")))
    if not topic:
        return "No topic provided."

    layers = config.get("layers", ["L0", "L1", "L2", "L3"])
    results_by_layer: dict[str, list[dict[str, Any]]] = {}

    for layer in layers:
        layer_nodes = index.get_by_layer(layer)
        # Score against topic
        query_words = set(re.findall(r'\w+', topic.lower()))
        scored = [
            (index._relevance_score(n, topic.lower(), query_words), n)
            for n in layer_nodes
        ]
        scored = [(s, n) for s, n in scored if s > 0]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [n for _, n in scored[:3]]
        if top:
            results_by_layer[layer] = top

    if not results_by_layer:
        return f"No knowledge found for: {topic}"

    return format_multi_layer(results_by_layer, topic)


def handle_stats(index: PackIndex, args: dict[str, Any], config: dict[str, Any]) -> str:
    """Pack metadata and statistics."""
    metadata = index.metadata
    layer_counts: dict[str, int] = {}
    for node in index.nodes:
        layer = index._infer_layer(node.get("id", ""))
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

    tech_counts: dict[str, int] = {}
    for node in index.nodes:
        for t in (node.get("technologies") or node.get("languages") or []):
            tech_counts[t] = tech_counts.get(t, 0) + 1

    domain_counts: dict[str, int] = {}
    for node in index.nodes:
        for d in (node.get("domains") or []):
            domain_counts[d] = domain_counts.get(d, 0) + 1

    lines = [
        f"## Pack Statistics",
        f"Template: {metadata.get('template_id', 'N/A')}",
        f"Total nodes: {len(index.nodes)}",
        f"Total edges: {len(index.edges)}",
        f"Reasoning edges: {len(index.reasoning_edges)}",
        "",
        "### Layers",
    ]
    for layer in sorted(layer_counts.keys()):
        lines.append(f"  {layer}: {layer_counts[layer]}")
    lines.append("")
    lines.append("### Technologies")
    for tech, count in sorted(tech_counts.items(), key=lambda x: -x[1])[:10]:
        lines.append(f"  {tech}: {count}")
    lines.append("")
    lines.append("### Domains")
    for dom, count in sorted(domain_counts.items(), key=lambda x: -x[1])[:10]:
        lines.append(f"  {dom}: {count}")

    return "\n".join(lines)


# =============================================================================
# Formatters
# =============================================================================

_LAYER_NAMES = {
    "L0": "Axioms", "L1": "Principles", "L2": "Patterns",
    "L3": "Rules", "L4": "Findings",
}


def format_results(nodes: list[dict[str, Any]], config: dict[str, Any]) -> str:
    """Standard multi-node formatter."""
    lines: list[str] = []
    for node in nodes[:15]:
        nid = node.get("id", "?")
        layer = PackIndex._infer_layer(nid)
        layer_name = _LAYER_NAMES.get(layer, layer)

        # Title
        name = node.get("name") or node.get("text", "")
        if len(name) > 100:
            name = name[:97] + "..."
        lines.append(f"### [{layer_name}] {nid}: {name}")

        # Key fields
        why = node.get("why", "")
        if why:
            lines.append(f"**WHY**: {why[:200]}")

        how = node.get("how_to_do_right") or node.get("how_to_apply", "")
        if how:
            lines.append(f"**HOW**: {how[:200]}")

        severity = node.get("severity")
        confidence = node.get("confidence")
        if severity or confidence:
            meta = []
            if severity:
                meta.append(f"Severity: {severity}")
            if confidence:
                meta.append(f"Confidence: {confidence}")
            lines.append(f"*{' | '.join(meta)}*")

        # Show examples if configured
        fields = config.get("fields", [])
        if "example_good" in fields or not fields:
            eg = node.get("example_good", "")
            if eg:
                lines.append(f"**Good**: ```\n{eg[:300]}\n```")
            eb = node.get("example_bad", "")
            if eb:
                lines.append(f"**Bad**: ```\n{eb[:300]}\n```")

        lines.append("")

    return "\n".join(lines)


def format_single_node(node: dict[str, Any], config: dict[str, Any]) -> str:
    """Detailed single-node formatter."""
    nid = node.get("id", "?")
    layer = PackIndex._infer_layer(nid)
    layer_name = _LAYER_NAMES.get(layer, layer)

    lines = [f"## [{layer_name}] {nid}"]

    name = node.get("name") or node.get("text") or node.get("statement", "")
    if name:
        lines.append(f"**{name}**")
        lines.append("")

    for field, label in [
        ("why", "WHY"), ("how_to_do_right", "HOW"), ("how_to_apply", "HOW"),
        ("when_applies", "WHEN"), ("when_not_applies", "WHEN NOT"),
        ("mental_model", "MENTAL MODEL"), ("intent", "INTENT"),
        ("when_to_use", "WHEN TO USE"), ("when_not_to_use", "WHEN NOT TO USE"),
        ("violation_consequence", "CONSEQUENCE"),
    ]:
        val = node.get(field, "")
        if val:
            lines.append(f"**{label}**: {val}")

    for field, label in [("example_good", "GOOD EXAMPLE"), ("example_bad", "BAD EXAMPLE")]:
        val = node.get(field, "")
        if val:
            lines.append(f"\n**{label}**:\n```\n{val}\n```")

    meta = []
    if node.get("severity"):
        meta.append(f"Severity: {node['severity']}")
    if node.get("confidence"):
        meta.append(f"Confidence: {node['confidence']}")
    if node.get("technologies"):
        meta.append(f"Tech: {', '.join(node['technologies'])}")
    if node.get("domains"):
        meta.append(f"Domains: {', '.join(node['domains'])}")
    if meta:
        lines.append(f"\n*{' | '.join(meta)}*")

    return "\n".join(lines)


def format_chain(chain: list[dict[str, Any]], index: PackIndex) -> str:
    """Format a reasoning chain."""
    lines = [f"## Reasoning Chain ({len(chain)} nodes)\n"]
    for i, node in enumerate(chain):
        nid = node.get("id", "?")
        layer = index._infer_layer(nid)
        name = node.get("name") or node.get("text", "")
        if len(name) > 80:
            name = name[:77] + "..."
        lines.append(f"{i + 1}. **[{layer}] {nid}**: {name}")
        why = node.get("why", "")
        if why:
            lines.append(f"   WHY: {why[:150]}")
    return "\n".join(lines)


def format_multi_layer(
    results_by_layer: dict[str, list[dict[str, Any]]],
    topic: str,
) -> str:
    """Format multi-layer aggregation."""
    lines = [f"## Multi-Layer Analysis: {topic}\n"]
    for layer in sorted(results_by_layer.keys()):
        layer_name = _LAYER_NAMES.get(layer, layer)
        lines.append(f"### {layer_name} ({layer})")
        for node in results_by_layer[layer]:
            nid = node.get("id", "?")
            name = node.get("name") or node.get("text") or node.get("statement", "")
            if len(name) > 80:
                name = name[:77] + "..."
            lines.append(f"- **{nid}**: {name}")
            why = node.get("why", "")
            if why:
                lines.append(f"  WHY: {why[:150]}")
        lines.append("")
    return "\n".join(lines)


# =============================================================================
# Handler dispatch
# =============================================================================

_HANDLER_MAP = {
    "query": handle_query,
    "filter": handle_filter,
    "lookup": handle_lookup,
    "traverse": handle_traverse,
    "aggregate": handle_aggregate,
    "stats": handle_stats,
    "reason": handle_aggregate,  # alias
}


# =============================================================================
# PackMCPServer — in-process MCP server
# =============================================================================

class PackMCPServer:
    """In-process MCP server for a pack. Handles JSON-RPC 2.0 over stdio."""

    def __init__(self, pack_data: dict[str, Any], tool_manifest: list[dict[str, Any]]) -> None:
        self.index = PackIndex(pack_data)
        self.tool_manifest = tool_manifest
        self.metadata = pack_data.get("metadata", {})

        # Build handler map from tool manifest
        self._handlers: dict[str, tuple[Any, dict[str, Any]]] = {}
        for tool in tool_manifest:
            name = tool.get("name", "")
            handler_type = tool.get("handler_type", "query")
            handler_config = tool.get("handler_config", {})
            handler_fn = _HANDLER_MAP.get(handler_type, handle_query)
            self._handlers[name] = (handler_fn, handler_config)

        # Resource manifest
        self._resources = [
            {
                "uri": "pack://stats",
                "name": "Pack Statistics",
                "description": "Node counts, technologies, domains",
                "mimeType": "application/json",
            },
            {
                "uri": "pack://nodes",
                "name": "Pack Nodes",
                "description": "List of all node IDs in this pack",
                "mimeType": "application/json",
            },
        ]

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Handle a single JSON-RPC 2.0 request."""
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        # Notifications
        if req_id is None and method == "notifications/initialized":
            return None

        if method == "initialize":
            return _make_response(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {
                    "name": self.metadata.get("server_name", "pack-server"),
                    "version": self.metadata.get("version", "1.0.0"),
                },
            })

        if method == "tools/list":
            tools = []
            for tool in self.tool_manifest:
                tools.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("input_schema", {"type": "object", "properties": {}, "required": []}),
                })
            return _make_response(req_id, {"tools": tools})

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            handler_entry = self._handlers.get(tool_name)
            if not handler_entry:
                return _make_error(req_id, -32601, f"Unknown tool: {tool_name}")
            handler_fn, handler_config = handler_entry
            try:
                text = handler_fn(self.index, arguments, handler_config)
                return _make_response(req_id, {
                    "content": [{"type": "text", "text": text}],
                })
            except Exception as exc:
                return _make_response(req_id, {
                    "content": [{"type": "text", "text": f"Error: {exc}"}],
                    "isError": True,
                })

        if method == "resources/list":
            return _make_response(req_id, {"resources": self._resources})

        if method == "resources/read":
            uri = params.get("uri", "")
            content = self._handle_resource(uri)
            if content is None:
                return _make_error(req_id, -32602, f"Resource not found: {uri}")
            return _make_response(req_id, {"contents": [content]})

        if req_id is not None:
            return _make_error(req_id, -32601, f"Method not found: {method}")
        return None

    def _handle_resource(self, uri: str) -> dict[str, Any] | None:
        if uri == "pack://stats":
            text = handle_stats(self.index, {}, {})
            return {"uri": uri, "mimeType": "text/plain", "text": text}
        if uri == "pack://nodes":
            node_ids = [n.get("id", "") for n in self.index.nodes]
            return {"uri": uri, "mimeType": "application/json", "text": json.dumps(node_ids)}
        return None

    def serve(self, port: int | None = None) -> None:
        """Run the MCP server (stdio JSON-RPC loop)."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                error = _make_error(None, -32700, f"Parse error: {exc}")
                sys.stdout.write(json.dumps(error) + "\n")
                sys.stdout.flush()
                continue

            response = self.handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()


# =============================================================================
# JSON-RPC helpers
# =============================================================================

def _make_response(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _make_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# =============================================================================
# Standalone entry point (used by exported server.py)
# =============================================================================

def run_server(pack_data_path: str) -> None:
    """Load pack data and run the MCP server."""
    with open(pack_data_path) as f:
        data = json.load(f)

    pack_data = {
        "nodes": data.get("nodes", []),
        "edges": data.get("edges", []),
        "reasoning_edges": data.get("reasoning_edges", []),
        "metadata": data.get("metadata", {}),
    }
    tool_manifest = data.get("tool_manifest", [])

    server = PackMCPServer(pack_data, tool_manifest)
    server.serve()
