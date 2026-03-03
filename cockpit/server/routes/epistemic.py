"""GET /api/epistemic — Wave 1 epistemic SOTA endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/epistemic", tags=["epistemic"])


@router.get("/stats")
async def get_epistemic_stats(request: Request) -> dict:
    """E0-E5 distribution, freshness, decay at-risk count, contradictions."""
    bridge = request.app.state.bridge
    return await bridge.epistemic_stats()


@router.get("/contradictions")
async def get_contradictions(request: Request) -> list[dict]:
    """All tracked contradiction tensors."""
    bridge = request.app.state.bridge
    return await bridge.contradictions()


@router.get("/at-risk")
async def get_at_risk_nodes(
    request: Request,
    horizon: int = Query(30, ge=1, le=365, description="Days to look ahead"),
) -> list[dict]:
    """Nodes predicted to go stale within the horizon."""
    bridge = request.app.state.bridge
    return await bridge.at_risk_nodes(horizon_days=horizon)
