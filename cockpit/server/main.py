"""FastAPI application — Ontology Cockpit data server."""

from __future__ import annotations

import argparse
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.brain_bridge import BrainBridge
from server.config import Config
from server.reload_manager import ReloadManager
from server.routes import admin, edges, epistemic, graph, nodes, packs, stats, stream

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _create_app(cfg: Config) -> FastAPI:
    """Build and configure the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup — load brain
        log.info("Loading Engineering Brain...")
        bridge = BrainBridge(
            brain_json_path=cfg.brain_json_path or None,
            seeds_dir=cfg.brain_seeds_dir or None,
        )
        app.state.bridge = bridge
        app.state.config = cfg
        st = await bridge.stats()
        log.info(
            "Ready — %d nodes, %d edges, version %d",
            st["total_nodes"],
            st["total_edges"],
            bridge.version,
        )

        # Start live-reload manager
        reload_manager = None
        if cfg.reload_enabled:
            reload_manager = ReloadManager(
                bridge=bridge,
                seeds_dir=cfg.brain_seeds_dir or None,
                brain_json_path=cfg.brain_json_path or None,
                poll_interval=cfg.reload_poll_interval,
                debounce_seconds=cfg.reload_debounce_seconds,
            )
            reload_manager.start()
        app.state.reload_manager = reload_manager

        yield

        # Shutdown
        if reload_manager:
            await reload_manager.stop()
        log.info("Shutting down")

    app = FastAPI(
        title="Ontology Cockpit",
        description="Real-time 3D viewer for Engineering Brain knowledge graph",
        version="0.2.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(graph.router)
    app.include_router(nodes.router)
    app.include_router(edges.router)
    app.include_router(stats.router)
    app.include_router(stream.router)
    app.include_router(packs.router)
    app.include_router(admin.router)
    app.include_router(epistemic.router)

    # Health check
    @app.get("/api/health", tags=["health"])
    async def health():
        return {"status": "ok", "version": app.state.bridge.version}

    # No-cache headers for JS/CSS during development
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request

    class NoCacheMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            path = request.url.path
            if path.endswith(('.js', '.css', '.html')) or path == '/':
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
            return response

    app.add_middleware(NoCacheMiddleware)

    # Static files — serve client/ at root (must be last)
    import pathlib
    client_dir = pathlib.Path(__file__).parent.parent / "client"
    if client_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(client_dir), html=True), name="client")

    return app


def main():
    parser = argparse.ArgumentParser(description="Ontology Cockpit server")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--seeds", dest="seeds_dir", default=None,
                        help="Path to brain seeds directory")
    parser.add_argument("--brain-json", dest="brain_json", default=None,
                        help="Path to brain JSON snapshot")
    args = parser.parse_args()

    cfg = Config.from_env()
    # CLI overrides
    if args.host:
        cfg = Config(**{**cfg.__dict__, "host": args.host})
    if args.port:
        cfg = Config(**{**cfg.__dict__, "port": args.port})
    if args.seeds_dir:
        cfg = Config(**{**cfg.__dict__, "brain_seeds_dir": args.seeds_dir})
    if args.brain_json:
        cfg = Config(**{**cfg.__dict__, "brain_json_path": args.brain_json})

    app = _create_app(cfg)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")


# Support: python -m server.main
if __name__ == "__main__":
    main()
