"""Tests for the MCP server protocol layer and tool/resource definitions.

Tests the JSON-RPC 2.0 surface: tool list, resource list, request routing,
response/error formatting, and handler dict completeness.
Does NOT test actual Brain calls (heavy imports).
"""

from __future__ import annotations

import sys
import os

# Ensure src/ is on the path so we can import the module directly.
_SRC = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src")
sys.path.insert(0, os.path.abspath(_SRC))

import pytest

from engineering_brain.mcp_server import (
    TOOLS,
    RESOURCES,
    _handle_request,
    _make_response,
    _make_error,
    _TOOL_HANDLERS,
    _SERVER_INFO,
    _CAPABILITIES,
)


# ---------------------------------------------------------------------------
# 1. TOOLS list has exactly 10 tools
# ---------------------------------------------------------------------------


class TestToolDefinitions:
    """Verify the TOOLS list structure and completeness."""

    def test_tools_count_is_17(self):
        assert len(TOOLS) == 20, f"Expected 20 tools, got {len(TOOLS)}"

    def test_every_tool_has_required_keys(self):
        required_keys = {"name", "description", "inputSchema"}
        for tool in TOOLS:
            missing = required_keys - set(tool.keys())
            assert not missing, (
                f"Tool {tool.get('name', '???')} is missing keys: {missing}"
            )

    def test_every_input_schema_has_type_object(self):
        for tool in TOOLS:
            schema = tool["inputSchema"]
            assert schema.get("type") == "object", (
                f"Tool {tool['name']} inputSchema.type should be 'object'"
            )
            assert "properties" in schema, (
                f"Tool {tool['name']} inputSchema must have 'properties'"
            )
            assert "required" in schema, (
                f"Tool {tool['name']} inputSchema must have 'required'"
            )

    def test_tool_names_are_unique(self):
        names = [t["name"] for t in TOOLS]
        assert len(names) == len(set(names)), "Duplicate tool names found"

    def test_known_tool_names_present(self):
        """Every expected tool name is in the list."""
        expected = {
            "brain_query",
            "brain_search",
            "brain_think",
            "brain_learn",
            "brain_validate",
            "brain_stats",
            "brain_contradictions",
            "brain_provenance",
            "brain_communities",
            "brain_feedback",
            "brain_reason",
            "brain_pack",
            "brain_pack_templates",
            "brain_pack_export",
            "brain_pack_compose",
            "brain_observe_outcome",
            "brain_promotion_outcome",
            "brain_reinforce",
            "brain_prediction_outcome",
            "brain_mine_code",
        }
        actual = {t["name"] for t in TOOLS}
        assert expected == actual, (
            f"Tool name mismatch.\n"
            f"  Missing: {expected - actual}\n"
            f"  Extra:   {actual - expected}"
        )

    def test_descriptions_are_nonempty_strings(self):
        for tool in TOOLS:
            desc = tool["description"]
            assert isinstance(desc, str) and len(desc) > 20, (
                f"Tool {tool['name']} has too-short or non-string description"
            )


# ---------------------------------------------------------------------------
# 2. RESOURCES list has exactly 5 resources
# ---------------------------------------------------------------------------


class TestResourceDefinitions:
    """Verify the RESOURCES list structure and completeness."""

    def test_resources_count_is_5(self):
        assert len(RESOURCES) == 5, f"Expected 5 resources, got {len(RESOURCES)}"

    def test_every_resource_has_required_keys(self):
        required_keys = {"uri", "name", "description", "mimeType"}
        for res in RESOURCES:
            missing = required_keys - set(res.keys())
            assert not missing, (
                f"Resource {res.get('name', '???')} is missing keys: {missing}"
            )

    def test_resource_uris_are_unique(self):
        uris = [r["uri"] for r in RESOURCES]
        assert len(uris) == len(set(uris)), "Duplicate resource URIs found"

    def test_known_resource_uris_present(self):
        expected_uris = {
            "brain://stats",
            "brain://health",
            "brain://layers",
            "brain://gaps",
            "brain://version",
        }
        actual_uris = {r["uri"] for r in RESOURCES}
        assert expected_uris == actual_uris, (
            f"Resource URI mismatch.\n"
            f"  Missing: {expected_uris - actual_uris}\n"
            f"  Extra:   {actual_uris - expected_uris}"
        )

    def test_mime_types_are_valid(self):
        valid_mimes = {"application/json", "text/plain"}
        for res in RESOURCES:
            assert res["mimeType"] in valid_mimes, (
                f"Resource {res['name']} has unexpected mimeType: {res['mimeType']}"
            )


# ---------------------------------------------------------------------------
# 3. _handle_request for "initialize" returns capabilities
# ---------------------------------------------------------------------------


class TestHandleInitialize:
    """Test the initialize handshake."""

    def test_initialize_returns_capabilities(self):
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        response = _handle_request(request)

        assert response is not None
        assert response["id"] == 1
        assert "result" in response
        result = response["result"]
        assert "capabilities" in result
        assert "serverInfo" in result
        assert "protocolVersion" in result

    def test_initialize_server_info(self):
        request = {"jsonrpc": "2.0", "id": 42, "method": "initialize", "params": {}}
        response = _handle_request(request)
        result = response["result"]

        assert result["serverInfo"]["name"] == "engineering-brain"
        assert result["serverInfo"]["version"] == "2.0.0"

    def test_initialize_capabilities_has_tools_and_resources(self):
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        response = _handle_request(request)
        caps = response["result"]["capabilities"]

        assert "tools" in caps
        assert "resources" in caps

    def test_initialize_protocol_version(self):
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        response = _handle_request(request)
        assert response["result"]["protocolVersion"] == "2024-11-05"


# ---------------------------------------------------------------------------
# 4. _handle_request for "tools/list" returns all tools
# ---------------------------------------------------------------------------


class TestHandleToolsList:
    """Test the tools/list method."""

    def test_tools_list_returns_all_tools(self):
        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        response = _handle_request(request)

        assert response is not None
        assert response["id"] == 2
        assert "result" in response
        result = response["result"]
        assert "tools" in result
        assert len(result["tools"]) == 20

    def test_tools_list_is_same_as_module_constant(self):
        request = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
        response = _handle_request(request)
        assert response["result"]["tools"] is TOOLS


# ---------------------------------------------------------------------------
# 5. _handle_request for "resources/list" returns all resources
# ---------------------------------------------------------------------------


class TestHandleResourcesList:
    """Test the resources/list method."""

    def test_resources_list_returns_all_resources(self):
        request = {"jsonrpc": "2.0", "id": 4, "method": "resources/list", "params": {}}
        response = _handle_request(request)

        assert response is not None
        assert response["id"] == 4
        assert "result" in response
        result = response["result"]
        assert "resources" in result
        assert len(result["resources"]) == 5

    def test_resources_list_is_same_as_module_constant(self):
        request = {"jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {}}
        response = _handle_request(request)
        assert response["result"]["resources"] is RESOURCES


# ---------------------------------------------------------------------------
# 6. _handle_request for unknown method returns error
# ---------------------------------------------------------------------------


class TestHandleUnknownMethod:
    """Test that unrecognized methods produce proper JSON-RPC errors."""

    def test_unknown_method_returns_error(self):
        request = {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "nonexistent/method",
            "params": {},
        }
        response = _handle_request(request)

        assert response is not None
        assert response["id"] == 99
        assert "error" in response
        assert "result" not in response
        assert response["error"]["code"] == -32601
        assert "nonexistent/method" in response["error"]["message"]

    def test_unknown_method_error_message_contains_method_name(self):
        request = {
            "jsonrpc": "2.0",
            "id": 100,
            "method": "foo/bar",
            "params": {},
        }
        response = _handle_request(request)
        assert "foo/bar" in response["error"]["message"]

    def test_notification_without_id_returns_none(self):
        """Notifications (no id) that are not recognized should return None."""
        request = {"jsonrpc": "2.0", "method": "unknown/notification", "params": {}}
        response = _handle_request(request)
        assert response is None

    def test_initialized_notification_returns_none(self):
        """notifications/initialized is a no-id notification, returns None."""
        request = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        response = _handle_request(request)
        assert response is None

    def test_unknown_tool_in_tools_call_returns_error(self):
        """tools/call with an unknown tool name returns an error."""
        request = {
            "jsonrpc": "2.0",
            "id": 101,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        }
        response = _handle_request(request)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32601
        assert "nonexistent_tool" in response["error"]["message"]

    def test_unknown_resource_uri_returns_error(self):
        """resources/read with an unknown URI returns an error."""
        request = {
            "jsonrpc": "2.0",
            "id": 102,
            "method": "resources/read",
            "params": {"uri": "brain://nonexistent"},
        }
        response = _handle_request(request)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32602
        assert "nonexistent" in response["error"]["message"]


# ---------------------------------------------------------------------------
# 7. _make_response and _make_error format
# ---------------------------------------------------------------------------


class TestResponseFormatting:
    """Test the JSON-RPC response envelope helpers."""

    def test_make_response_structure(self):
        resp = _make_response(1, {"foo": "bar"})
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"] == {"foo": "bar"}
        assert "error" not in resp

    def test_make_response_with_none_id(self):
        resp = _make_response(None, "ok")
        assert resp["id"] is None
        assert resp["result"] == "ok"

    def test_make_response_with_string_id(self):
        resp = _make_response("abc-123", [1, 2, 3])
        assert resp["id"] == "abc-123"
        assert resp["result"] == [1, 2, 3]

    def test_make_error_structure(self):
        resp = _make_error(42, -32600, "Invalid Request")
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 42
        assert "error" in resp
        assert resp["error"]["code"] == -32600
        assert resp["error"]["message"] == "Invalid Request"
        assert "result" not in resp

    def test_make_error_with_none_id(self):
        resp = _make_error(None, -32700, "Parse error")
        assert resp["id"] is None
        assert resp["error"]["code"] == -32700

    def test_make_error_preserves_exact_message(self):
        msg = "Something went wrong: details here"
        resp = _make_error(7, -32603, msg)
        assert resp["error"]["message"] == msg


# ---------------------------------------------------------------------------
# 8. Every tool in TOOLS has a handler in _TOOL_HANDLERS
# ---------------------------------------------------------------------------


class TestToolHandlersDict:
    """Verify that _TOOL_HANDLERS is complete and consistent."""

    def test_every_tool_has_handler(self):
        """Each tool defined in TOOLS must have a corresponding handler."""
        for tool in TOOLS:
            name = tool["name"]
            assert name in _TOOL_HANDLERS, (
                f"Tool {name!r} is defined in TOOLS but missing from _TOOL_HANDLERS"
            )

    def test_no_extra_handlers_beyond_tools(self):
        """_TOOL_HANDLERS should not contain handlers for undefined tools."""
        tool_names = {t["name"] for t in TOOLS}
        handler_names = set(_TOOL_HANDLERS.keys())
        extra = handler_names - tool_names
        assert not extra, (
            f"_TOOL_HANDLERS has handlers not in TOOLS: {extra}"
        )

    def test_handler_count_matches_tools_count(self):
        assert len(_TOOL_HANDLERS) == len(TOOLS)

    def test_all_handlers_are_callable(self):
        for name, handler in _TOOL_HANDLERS.items():
            assert callable(handler), (
                f"Handler for {name!r} is not callable: {type(handler)}"
            )

    @pytest.mark.parametrize("tool_name", [
        "brain_query",
        "brain_search",
        "brain_think",
        "brain_learn",
        "brain_validate",
        "brain_stats",
        "brain_contradictions",
        "brain_provenance",
        "brain_communities",
        "brain_feedback",
        "brain_reason",
        "brain_pack",
        "brain_pack_templates",
        "brain_pack_export",
        "brain_pack_compose",
        "brain_observe_outcome",
        "brain_promotion_outcome",
        "brain_reinforce",
        "brain_prediction_outcome",
        "brain_mine_code",
    ])
    def test_handler_exists_for_each_tool(self, tool_name: str):
        """Parametrized check: each known tool name has a handler function."""
        assert tool_name in _TOOL_HANDLERS
        assert callable(_TOOL_HANDLERS[tool_name])


# ---------------------------------------------------------------------------
# 9. Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Verify server metadata constants."""

    def test_server_info_name(self):
        assert _SERVER_INFO["name"] == "engineering-brain"

    def test_server_info_version(self):
        assert _SERVER_INFO["version"] == "2.0.0"

    def test_capabilities_has_tools(self):
        assert "tools" in _CAPABILITIES

    def test_capabilities_has_resources(self):
        assert "resources" in _CAPABILITIES


# ---------------------------------------------------------------------------
# 10. Request routing edge cases
# ---------------------------------------------------------------------------


class TestRequestRoutingEdgeCases:
    """Additional edge cases for _handle_request routing."""

    def test_missing_method_key_returns_error(self):
        """A request with no 'method' key and a valid id should return error."""
        request = {"jsonrpc": "2.0", "id": 200, "params": {}}
        response = _handle_request(request)
        # method defaults to "" which is unknown
        assert response is not None
        assert "error" in response

    def test_missing_params_key_defaults_to_empty_dict(self):
        """Requests without 'params' should still work for methods that
        don't require params (like initialize)."""
        request = {"jsonrpc": "2.0", "id": 201, "method": "initialize"}
        response = _handle_request(request)
        assert response is not None
        assert "result" in response

    def test_tools_list_with_no_params(self):
        request = {"jsonrpc": "2.0", "id": 202, "method": "tools/list"}
        response = _handle_request(request)
        assert "result" in response
        assert len(response["result"]["tools"]) == 20

    def test_resources_list_with_no_params(self):
        request = {"jsonrpc": "2.0", "id": 203, "method": "resources/list"}
        response = _handle_request(request)
        assert "result" in response
        assert len(response["result"]["resources"]) == 5

    def test_tools_call_missing_name_param(self):
        """tools/call with no 'name' in params should return unknown tool error."""
        request = {
            "jsonrpc": "2.0",
            "id": 204,
            "method": "tools/call",
            "params": {"arguments": {}},
        }
        response = _handle_request(request)
        assert "error" in response

    def test_response_always_has_jsonrpc_field(self):
        """Every non-None response from _handle_request must have 'jsonrpc': '2.0'."""
        requests = [
            {"jsonrpc": "2.0", "id": 300, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 301, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 302, "method": "resources/list", "params": {}},
            {"jsonrpc": "2.0", "id": 303, "method": "bogus", "params": {}},
        ]
        for req in requests:
            resp = _handle_request(req)
            assert resp is not None
            assert resp["jsonrpc"] == "2.0", (
                f"Response for {req['method']} missing jsonrpc field"
            )

    def test_response_id_matches_request_id(self):
        """Response id must always match the request id."""
        for req_id in [1, "abc", 999, 0]:
            request = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/list",
                "params": {},
            }
            response = _handle_request(request)
            assert response["id"] == req_id
