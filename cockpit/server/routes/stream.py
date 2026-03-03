"""GET /api/stream — Server-Sent Events for version changes."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/stream", tags=["stream"])


@router.get("")
async def stream_events(request: Request) -> StreamingResponse:
    """SSE endpoint — emits version change events."""
    bridge = request.app.state.bridge
    poll_interval = request.app.state.config.sse_poll_interval

    async def event_generator():
        last_version = -1
        while True:
            if await request.is_disconnected():
                break
            current_version = bridge.version
            if current_version != last_version:
                last_version = current_version
                stats = await bridge.stats()
                data = json.dumps({
                    "version": current_version,
                    "node_count": stats["total_nodes"],
                    "edge_count": stats["total_edges"],
                })
                yield f"event: version\ndata: {data}\n\n"
            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
