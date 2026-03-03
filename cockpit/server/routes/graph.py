"""GET /api/graph — full snapshot, GET /api/graph/version — version only."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("")
async def get_graph(request: Request) -> dict:
    """Full graph snapshot for initial client load."""
    bridge = request.app.state.bridge
    return await bridge.snapshot()


@router.get("/version")
async def get_version(request: Request) -> dict:
    """Lightweight version check for polling."""
    bridge = request.app.state.bridge
    return {"version": bridge.version}
