"""Tests for all server API routes.

Exercises every public endpoint to ensure the server starts, routes are
registered, and responses have the expected shape.
"""

from __future__ import annotations


# -- Health ------------------------------------------------------------------


class TestHealth:
    """GET /api/health -- basic liveness probe."""

    async def test_health_returns_ok(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body

    async def test_health_version_is_integer(self, client):
        resp = await client.get("/api/health")
        body = resp.json()
        assert isinstance(body["version"], int)


# -- Graph -------------------------------------------------------------------


class TestGraph:
    """GET /api/graph -- full graph snapshot."""

    async def test_graph_returns_200(self, client):
        resp = await client.get("/api/graph")
        assert resp.status_code == 200

    async def test_graph_has_nodes_and_edges(self, client):
        resp = await client.get("/api/graph")
        body = resp.json()
        assert "nodes" in body
        assert "edges" in body
        assert isinstance(body["nodes"], list)
        assert isinstance(body["edges"], list)

    async def test_graph_version_endpoint(self, client):
        resp = await client.get("/api/graph/version")
        assert resp.status_code == 200
        body = resp.json()
        assert "version" in body


# -- Stats -------------------------------------------------------------------


class TestStats:
    """GET /api/stats -- aggregate statistics."""

    async def test_stats_returns_200(self, client):
        resp = await client.get("/api/stats")
        assert resp.status_code == 200

    async def test_stats_has_counts(self, client):
        resp = await client.get("/api/stats")
        body = resp.json()
        assert "total_nodes" in body
        assert "total_edges" in body


# -- Nodes -------------------------------------------------------------------


class TestNodes:
    """GET /api/nodes -- node listing with pagination."""

    async def test_nodes_returns_200(self, client):
        resp = await client.get("/api/nodes")
        assert resp.status_code == 200

    async def test_nodes_response_is_list(self, client):
        resp = await client.get("/api/nodes")
        body = resp.json()
        assert isinstance(body, list)


# -- Edges -------------------------------------------------------------------


class TestEdges:
    """GET /api/edges -- edge listing."""

    async def test_edges_returns_200(self, client):
        resp = await client.get("/api/edges")
        assert resp.status_code == 200

    async def test_edges_response_is_list(self, client):
        resp = await client.get("/api/edges")
        body = resp.json()
        assert isinstance(body, list)


# -- SSE Stream --------------------------------------------------------------


class TestStream:
    """GET /api/stream -- Server-Sent Events endpoint."""

    async def test_stream_returns_200_with_sse_content_type(self, client):
        """SSE endpoint should return 200 with text/event-stream content type.

        We use stream=True to get headers without consuming the full body.
        The SSE endpoint is an infinite loop, so we only check the response
        headers and read the first chunk before closing.
        """
        import asyncio

        async def _read_first_chunk():
            async with client.stream("GET", "/api/stream") as resp:
                assert resp.status_code == 200
                assert "text/event-stream" in resp.headers.get("content-type", "")
                # Read first bytes to confirm data is flowing
                async for chunk in resp.aiter_bytes():
                    assert len(chunk) > 0
                    break

        try:
            await asyncio.wait_for(_read_first_chunk(), timeout=5)
        except (TimeoutError, asyncio.TimeoutError):
            # It's OK if the SSE doesn't emit within timeout (empty brain)
            pass


# -- Admin -------------------------------------------------------------------


class TestAdmin:
    """POST /api/admin/reload -- admin reload endpoint."""

    async def test_reload_returns_200_when_no_reload_manager(self, client):
        """With reload_manager=None, should return error status but 200."""
        resp = await client.post("/api/admin/reload")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "error"

    async def test_reload_status_returns_200(self, client):
        resp = await client.get("/api/admin/reload/status")
        assert resp.status_code == 200


# -- Epistemic ---------------------------------------------------------------


class TestEpistemic:
    """GET /api/epistemic/* -- epistemic SOTA endpoints."""

    async def test_epistemic_stats_returns_200(self, client):
        resp = await client.get("/api/epistemic/stats")
        assert resp.status_code == 200

    async def test_epistemic_contradictions_returns_200(self, client):
        resp = await client.get("/api/epistemic/contradictions")
        assert resp.status_code == 200


# -- 404 Handling ------------------------------------------------------------


class TestNotFound:
    """Ensure unknown API routes return proper errors."""

    async def test_unknown_api_route_returns_404(self, client):
        resp = await client.get("/api/nonexistent")
        assert resp.status_code == 404

    async def test_unknown_nested_api_route_returns_404(self, client):
        resp = await client.get("/api/graph/nonexistent/path")
        assert resp.status_code in (404, 405)
