"""GET /api/edges — filtered edge list."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/edges", tags=["edges"])


@router.get("")
async def get_edges(
    request: Request,
    node_id: str | None = Query(None, alias="node"),
    edge_type: str | None = Query(None, alias="type"),
) -> list[dict]:
    """Filtered edges — by node ID and/or edge type."""
    bridge = request.app.state.bridge
    return await bridge.edges(node_id=node_id, edge_type=edge_type)
