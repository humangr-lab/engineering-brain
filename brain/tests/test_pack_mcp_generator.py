"""Tests for PackMCPGenerator — MCP server generation + export + standalone run."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import EdgeType, NodeType
from engineering_brain.core.types import MCPToolSpec, MaterializedPack, PackTemplate
from engineering_brain.export.pack_mcp_generator import PackMCPGenerator
from engineering_brain.export.pack_mcp_runtime import (
    PackIndex,
    PackMCPServer,
    handle_aggregate,
    handle_filter,
    handle_lookup,
    handle_query,
    handle_stats,
    handle_traverse,
)


@pytest.fixture
def sample_nodes():
    """Sample nodes for testing."""
    return [
        {
            "id": "P-SEC-BOUNDARY",
            "name": "Validate at Boundary",
            "why": "All input is hostile until proven otherwise",
            "how_to_apply": "Validate at every system boundary",
            "mental_model": "Castle walls metaphor",
            "domains": ["security"],
        },
        {
            "id": "PAT-SEC-INPUT-VALID",
            "name": "Input Validation Pattern",
            "intent": "Prevent injection attacks by validating input",
            "when_to_use": "Any user-facing input",
            "languages": ["python", "flask"],
            "domains": ["security"],
        },
        {
            "id": "CR-SEC-001",
            "text": "Always validate user input on the server side",
            "why": "Client-side validation can be bypassed",
            "how_to_do_right": "Use Pydantic models or marshmallow schemas",
            "severity": "critical",
            "confidence": 0.9,
            "technologies": ["flask"],
            "domains": ["security"],
            "example_good": "schema.load(request.json)",
            "example_bad": "data = request.json  # no validation",
        },
        {
            "id": "CR-SEC-002",
            "text": "Sanitize file paths to prevent path traversal",
            "why": "Attackers can access files outside intended directory",
            "how_to_do_right": "Use os.path.realpath and check prefix",
            "severity": "critical",
            "confidence": 0.95,
            "technologies": ["python"],
            "domains": ["security"],
            "example_good": "safe = os.path.realpath(path); assert safe.startswith(base)",
            "example_bad": "open(user_provided_path)",
        },
        {
            "id": "CR-SEC-003",
            "text": "Use CORS allowlists, never allow all origins",
            "why": "Wildcard CORS exposes API to any origin",
            "how_to_do_right": "Explicit origin list in CORS config",
            "severity": "high",
            "confidence": 0.85,
            "technologies": ["flask"],
            "domains": ["security", "cors"],
        },
        {
            "id": "CR-FLASK-001",
            "text": "Use Flask application factory pattern",
            "why": "Enables testing and multiple configurations",
            "how_to_do_right": "def create_app(config=None): ...",
            "severity": "medium",
            "confidence": 0.8,
            "technologies": ["flask"],
            "domains": ["architecture"],
        },
    ]


@pytest.fixture
def sample_edges():
    return [
        {"from_id": "P-SEC-BOUNDARY", "to_id": "PAT-SEC-INPUT-VALID", "edge_type": "INFORMS"},
        {"from_id": "PAT-SEC-INPUT-VALID", "to_id": "CR-SEC-001", "edge_type": "INSTANTIATES"},
        {"from_id": "PAT-SEC-INPUT-VALID", "to_id": "CR-SEC-002", "edge_type": "INSTANTIATES"},
    ]


@pytest.fixture
def sample_reasoning_edges():
    return [
        {"from_id": "P-SEC-BOUNDARY", "to_id": "CR-SEC-001", "edge_type": "TRIGGERS"},
        {"from_id": "P-SEC-BOUNDARY", "to_id": "CR-SEC-002", "edge_type": "TRIGGERS"},
        {"from_id": "CR-SEC-001", "to_id": "CR-SEC-002", "edge_type": "PREREQUISITE"},
    ]


@pytest.fixture
def sample_pack(sample_nodes, sample_edges, sample_reasoning_edges):
    return MaterializedPack(
        id="test-pack",
        description="Test security pack",
        node_ids=[n["id"] for n in sample_nodes],
        reasoning_edges=sample_reasoning_edges,
        technologies=["flask", "python"],
        domains=["security"],
        layers_present=["L1", "L2", "L3"],
        quality_score=0.75,
        node_count=len(sample_nodes),
        nodes=sample_nodes,
        edges=sample_edges,
        template_id="security-review",
        template_version="1.0.0",
    )


@pytest.fixture
def sample_template():
    return PackTemplate(
        id="security-review",
        name="Security Review Pack",
        mcp_server_name="security-review",
        mcp_server_description="Security review knowledge",
        mcp_tools=[
            MCPToolSpec(
                name="check_vulnerability",
                description="Check code for vulnerabilities",
                input_schema={
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
                handler_type="query",
                handler_config={"boost_severity": True, "layers": ["L3"]},
            ),
            MCPToolSpec(
                name="get_security_rules",
                description="List security rules",
                handler_type="filter",
                handler_config={"layers": ["L3"], "sort_by": "severity"},
            ),
            MCPToolSpec(
                name="get_node",
                description="Lookup a specific node",
                handler_type="lookup",
            ),
            MCPToolSpec(
                name="explain_security",
                description="Multi-layer security explanation",
                handler_type="aggregate",
                handler_config={"layers": ["L1", "L2", "L3"]},
            ),
            MCPToolSpec(
                name="trace_chain",
                description="Follow reasoning chains",
                handler_type="traverse",
            ),
            MCPToolSpec(
                name="pack_info",
                description="Pack statistics",
                handler_type="stats",
            ),
        ],
    )


@pytest.fixture
def pack_data(sample_nodes, sample_edges, sample_reasoning_edges):
    return {
        "nodes": sample_nodes,
        "edges": sample_edges,
        "reasoning_edges": sample_reasoning_edges,
        "metadata": {
            "template_id": "security-review",
            "server_name": "security-review",
            "version": "1.0.0",
        },
    }


class TestPackIndex:
    """Test the in-memory index."""

    def test_index_creation(self, pack_data):
        index = PackIndex(pack_data)
        assert len(index.nodes) == 6

    def test_get_node(self, pack_data):
        index = PackIndex(pack_data)
        node = index.get_node("CR-SEC-001")
        assert node is not None
        assert node["severity"] == "critical"

    def test_get_by_layer(self, pack_data):
        index = PackIndex(pack_data)
        l3 = index.get_by_layer("L3")
        assert len(l3) == 4  # CR-SEC-001, CR-SEC-002, CR-SEC-003, CR-FLASK-001

    def test_get_by_domain(self, pack_data):
        index = PackIndex(pack_data)
        sec = index.get_by_domain("security")
        assert len(sec) >= 4

    def test_get_by_technology(self, pack_data):
        index = PackIndex(pack_data)
        flask = index.get_by_technology("flask")
        assert len(flask) >= 2

    def test_get_by_severity(self, pack_data):
        index = PackIndex(pack_data)
        critical = index.get_by_severity("critical")
        assert len(critical) == 2  # CR-SEC-001, CR-SEC-002

    def test_search(self, pack_data):
        index = PackIndex(pack_data)
        results = index.search("input validation")
        assert len(results) > 0
        # The input validation pattern should be high-ranked
        ids = [r.get("id") for r in results]
        assert "PAT-SEC-INPUT-VALID" in ids or "CR-SEC-001" in ids

    def test_search_by_technology(self, pack_data):
        index = PackIndex(pack_data)
        results = index.search("flask")
        assert len(results) > 0

    def test_get_neighbors(self, pack_data):
        index = PackIndex(pack_data)
        neighbors = index.get_neighbors("P-SEC-BOUNDARY")
        assert len(neighbors) >= 1


class TestHandlers:
    """Test the 7 handler strategies."""

    def test_handle_query(self, pack_data):
        index = PackIndex(pack_data)
        result = handle_query(index, {"query": "input validation flask"}, {})
        assert "input" in result.lower() or "validation" in result.lower() or "SEC" in result

    def test_handle_query_with_layers(self, pack_data):
        index = PackIndex(pack_data)
        result = handle_query(index, {"query": "security"}, {"layers": ["L3"]})
        assert "CR-SEC" in result or "security" in result.lower()

    def test_handle_filter(self, pack_data):
        index = PackIndex(pack_data)
        result = handle_filter(index, {}, {"layers": ["L3"]})
        assert "CR-SEC" in result or "CR-FLASK" in result

    def test_handle_filter_by_domain(self, pack_data):
        index = PackIndex(pack_data)
        result = handle_filter(index, {"domain": "security"}, {})
        assert "SEC" in result

    def test_handle_filter_by_severity(self, pack_data):
        index = PackIndex(pack_data)
        result = handle_filter(index, {}, {"layers": ["L3"], "sort_by": "severity"})
        assert "critical" in result.lower() or "CR-SEC" in result

    def test_handle_lookup_by_id(self, pack_data):
        index = PackIndex(pack_data)
        result = handle_lookup(index, {"rule_id": "CR-SEC-001"}, {})
        assert "CR-SEC-001" in result
        assert "validate" in result.lower() or "input" in result.lower()

    def test_handle_lookup_not_found(self, pack_data):
        index = PackIndex(pack_data)
        result = handle_lookup(index, {"rule_id": "NONEXISTENT"}, {})
        assert "not found" in result.lower()

    def test_handle_traverse(self, pack_data):
        index = PackIndex(pack_data)
        result = handle_traverse(index, {"principle": "boundary validation"}, {})
        assert "Reasoning Chain" in result or "SEC" in result or "Boundary" in result

    def test_handle_aggregate(self, pack_data):
        index = PackIndex(pack_data)
        result = handle_aggregate(index, {"topic": "input security"}, {"layers": ["L1", "L2", "L3"]})
        assert "Multi-Layer" in result or "security" in result.lower()

    def test_handle_stats(self, pack_data):
        index = PackIndex(pack_data)
        result = handle_stats(index, {}, {})
        assert "Pack Statistics" in result
        assert "Total nodes: 6" in result


class TestPackMCPServer:
    """Test the in-process MCP server."""

    def test_initialize(self, pack_data, sample_template):
        gen = PackMCPGenerator()
        server = gen.generate_server(
            MaterializedPack(
                id="test", nodes=pack_data["nodes"], edges=pack_data["edges"],
                reasoning_edges=pack_data["reasoning_edges"],
                node_count=len(pack_data["nodes"]),
                template_id="security-review",
            ),
            template=sample_template,
        )
        resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert resp["result"]["serverInfo"]["name"] == "security-review"

    def test_tools_list(self, pack_data, sample_template):
        gen = PackMCPGenerator()
        server = gen.generate_server(
            MaterializedPack(
                id="test", nodes=pack_data["nodes"], edges=pack_data["edges"],
                reasoning_edges=pack_data["reasoning_edges"],
                node_count=len(pack_data["nodes"]),
                template_id="security-review",
            ),
            template=sample_template,
        )
        resp = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = resp["result"]["tools"]
        assert len(tools) == 6
        tool_names = [t["name"] for t in tools]
        assert "check_vulnerability" in tool_names
        assert "get_security_rules" in tool_names

    def test_tool_call(self, pack_data, sample_template):
        gen = PackMCPGenerator()
        server = gen.generate_server(
            MaterializedPack(
                id="test", nodes=pack_data["nodes"], edges=pack_data["edges"],
                reasoning_edges=pack_data["reasoning_edges"],
                node_count=len(pack_data["nodes"]),
                template_id="security-review",
            ),
            template=sample_template,
        )
        resp = server.handle_request({
            "jsonrpc": "2.0", "id": 3,
            "method": "tools/call",
            "params": {"name": "check_vulnerability", "arguments": {"code": "user input validation"}},
        })
        assert "result" in resp
        content = resp["result"]["content"]
        assert len(content) > 0
        assert content[0]["type"] == "text"
        assert len(content[0]["text"]) > 0

    def test_unknown_tool(self, pack_data, sample_template):
        gen = PackMCPGenerator()
        server = gen.generate_server(
            MaterializedPack(
                id="test", nodes=pack_data["nodes"], edges=pack_data["edges"],
                reasoning_edges=pack_data["reasoning_edges"],
                node_count=len(pack_data["nodes"]),
                template_id="security-review",
            ),
            template=sample_template,
        )
        resp = server.handle_request({
            "jsonrpc": "2.0", "id": 4,
            "method": "tools/call",
            "params": {"name": "nonexistent", "arguments": {}},
        })
        assert "error" in resp

    def test_resources_list(self, pack_data, sample_template):
        gen = PackMCPGenerator()
        server = gen.generate_server(
            MaterializedPack(
                id="test", nodes=pack_data["nodes"], edges=pack_data["edges"],
                reasoning_edges=pack_data["reasoning_edges"],
                node_count=len(pack_data["nodes"]),
                template_id="security-review",
            ),
            template=sample_template,
        )
        resp = server.handle_request({"jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {}})
        resources = resp["result"]["resources"]
        assert len(resources) == 2
        uris = [r["uri"] for r in resources]
        assert "pack://stats" in uris

    def test_resource_read_stats(self, pack_data, sample_template):
        gen = PackMCPGenerator()
        server = gen.generate_server(
            MaterializedPack(
                id="test", nodes=pack_data["nodes"], edges=pack_data["edges"],
                reasoning_edges=pack_data["reasoning_edges"],
                node_count=len(pack_data["nodes"]),
                template_id="security-review",
            ),
            template=sample_template,
        )
        resp = server.handle_request({
            "jsonrpc": "2.0", "id": 6,
            "method": "resources/read",
            "params": {"uri": "pack://stats"},
        })
        assert "result" in resp
        contents = resp["result"]["contents"]
        assert len(contents) == 1

    def test_notification_returns_none(self, pack_data, sample_template):
        gen = PackMCPGenerator()
        server = gen.generate_server(
            MaterializedPack(
                id="test", nodes=pack_data["nodes"], edges=pack_data["edges"],
                reasoning_edges=pack_data["reasoning_edges"],
                node_count=len(pack_data["nodes"]),
                template_id="security-review",
            ),
            template=sample_template,
        )
        resp = server.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        assert resp is None


class TestPackExport:
    """Test export pipeline — directory structure + standalone run."""

    def test_export_creates_directory(self, sample_pack, sample_template):
        gen = PackMCPGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "my-pack")
            stats = gen.export(sample_pack, output, template=sample_template)

            assert os.path.isdir(output)
            assert os.path.isfile(os.path.join(output, "server.py"))
            assert os.path.isfile(os.path.join(output, "pack_data.json"))
            assert os.path.isfile(os.path.join(output, "pack_mcp_runtime.py"))
            assert os.path.isfile(os.path.join(output, "README.md"))
            assert os.path.isfile(os.path.join(output, ".mcp.json"))

    def test_export_pack_data_valid_json(self, sample_pack, sample_template):
        gen = PackMCPGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "my-pack")
            gen.export(sample_pack, output, template=sample_template)

            with open(os.path.join(output, "pack_data.json")) as f:
                data = json.load(f)

            assert "nodes" in data
            assert "tool_manifest" in data
            assert "metadata" in data
            assert len(data["nodes"]) == 6

    def test_export_mcp_json(self, sample_pack, sample_template):
        gen = PackMCPGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "my-pack")
            gen.export(sample_pack, output, template=sample_template)

            with open(os.path.join(output, ".mcp.json")) as f:
                mcp_config = json.load(f)

            assert "mcpServers" in mcp_config
            assert "security-review" in mcp_config["mcpServers"]

    def test_export_readme_content(self, sample_pack, sample_template):
        gen = PackMCPGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "my-pack")
            gen.export(sample_pack, output, template=sample_template)

            readme = open(os.path.join(output, "README.md")).read()
            assert "security-review" in readme
            assert "python" in readme.lower() or "Python" in readme

    def test_export_standalone_importable(self, sample_pack, sample_template):
        """Test that the exported runtime can be imported standalone."""
        gen = PackMCPGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "my-pack")
            gen.export(sample_pack, output, template=sample_template)

            # Test that runtime can be imported from the export directory
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "pack_mcp_runtime",
                os.path.join(output, "pack_mcp_runtime.py"),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # The module should have PackMCPServer and run_server
            assert hasattr(module, "PackMCPServer")
            assert hasattr(module, "run_server")

    def test_export_server_can_create_server(self, sample_pack, sample_template):
        """Test that the exported pack_data.json can create a working server."""
        gen = PackMCPGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "my-pack")
            gen.export(sample_pack, output, template=sample_template)

            # Load the exported data
            with open(os.path.join(output, "pack_data.json")) as f:
                data = json.load(f)

            # Create a server from the exported data
            pack_data = {
                "nodes": data["nodes"],
                "edges": data.get("edges", []),
                "reasoning_edges": data.get("reasoning_edges", []),
                "metadata": data.get("metadata", {}),
            }
            server = PackMCPServer(pack_data, data["tool_manifest"])

            # Test initialize
            resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            assert resp["result"]["protocolVersion"] == "2024-11-05"

            # Test tools/list
            resp = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            assert len(resp["result"]["tools"]) > 0


class TestDefaultToolManifest:
    """Test that packs without template tools get default tools."""

    def test_default_tools_when_no_template(self, sample_pack):
        gen = PackMCPGenerator()
        server = gen.generate_server(sample_pack, template=None)

        resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = resp["result"]["tools"]
        assert len(tools) == 4  # default tools
        tool_names = [t["name"] for t in tools]
        assert "search_knowledge" in tool_names
        assert "list_nodes" in tool_names
        assert "get_node" in tool_names
        assert "pack_stats" in tool_names

    def test_default_search_works(self, sample_pack):
        gen = PackMCPGenerator()
        server = gen.generate_server(sample_pack, template=None)

        resp = server.handle_request({
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {"name": "search_knowledge", "arguments": {"query": "security validation"}},
        })
        assert "result" in resp
        text = resp["result"]["content"][0]["text"]
        assert len(text) > 0
