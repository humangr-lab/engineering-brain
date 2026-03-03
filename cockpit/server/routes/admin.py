"""Admin routes — manual reload trigger and status."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/reload")
async def trigger_reload(request: Request) -> dict:
    """Trigger an immediate Brain reload, bypassing debounce."""
    rm = request.app.state.reload_manager
    if rm is None:
        return {"status": "error", "error": "ReloadManager not configured"}
    return await rm.manual_reload()


@router.get("/reload/status")
async def reload_status(request: Request) -> dict:
    """Return current ReloadManager status."""
    rm = request.app.state.reload_manager
    if rm is None:
        return {"enabled": False}
    return rm.status()
