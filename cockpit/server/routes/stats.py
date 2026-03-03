"""GET /api/stats — aggregate dashboard statistics."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
async def get_stats(request: Request) -> dict:
    """Aggregate stats: counts by layer, severity, edge type, tech, domain."""
    bridge = request.app.state.bridge
    return await bridge.stats()
