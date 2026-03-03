"""POST /api/packs — knowledge pack creation and preview."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/packs", tags=["packs"])


class PackCreateRequest(BaseModel):
    description: str = Field(..., min_length=1, description="Natural language description")
    technologies: list[str] | None = Field(default=None, description="Technology filter")
    domains: list[str] | None = Field(default=None, description="Domain filter")
    max_nodes: int = Field(default=80, ge=1, le=500, description="Maximum nodes in pack")


class PackPreviewRequest(BaseModel):
    description: str = Field(..., min_length=1, description="Natural language description")
    technologies: list[str] | None = Field(default=None, description="Technology filter")
    domains: list[str] | None = Field(default=None, description="Domain filter")


@router.post("/create")
async def create_pack(request: Request, body: PackCreateRequest) -> dict:
    """Create a knowledge pack from description."""
    bridge = request.app.state.bridge
    return await bridge.create_pack(
        description=body.description,
        technologies=body.technologies,
        domains=body.domains,
        max_nodes=body.max_nodes,
    )


@router.post("/preview")
async def preview_pack(request: Request, body: PackPreviewRequest) -> dict:
    """Preview pack composition without full materialization."""
    bridge = request.app.state.bridge
    return await bridge.preview_pack(
        description=body.description,
        technologies=body.technologies,
        domains=body.domains,
    )
