"""GET /api/nodes — paginated + filtered, GET /api/nodes/{id} — single node."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("")
async def get_nodes(
    request: Request,
    layer: int | None = None,
    severity: str | None = None,
    technology: str | None = None,
    domain: str | None = None,
    search: str | None = Query(None, alias="q"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    """Paginated, filtered node list for KLIB."""
    bridge = request.app.state.bridge
    return await bridge.nodes(
        layer=layer,
        severity=severity,
        technology=technology,
        domain=domain,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/{node_id}")
async def get_node(request: Request, node_id: str) -> dict:
    """Single node with computed backlinks."""
    bridge = request.app.state.bridge
    node = await bridge.node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id!r} not found")
    return node
