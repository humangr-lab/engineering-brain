"""Shared pytest fixtures for the Ontology Map Toolkit test suite."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


# -- Path fixtures -----------------------------------------------------------


@pytest.fixture()
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture()
def schemas_dir(project_root: Path) -> Path:
    """Return the schemas/ directory."""
    return project_root / "schemas"


@pytest.fixture()
def examples_dir(project_root: Path) -> Path:
    """Return the examples/ directory."""
    return project_root / "examples"


@pytest.fixture()
def client_dir(project_root: Path) -> Path:
    """Return the client/ directory."""
    return project_root / "client"


# -- FastAPI test client -----------------------------------------------------


@pytest.fixture()
def anyio_backend():
    """Use asyncio as the async backend for pytest-asyncio."""
    return "asyncio"


@pytest.fixture()
async def client():
    """Async HTTPX test client for the FastAPI app.

    Patches BrainBridge._load to avoid loading real brain data (which is
    slow and requires engineering_brain). The bridge runs in "static mode"
    with no brain data — all endpoints return empty but valid responses.
    """
    from httpx import ASGITransport, AsyncClient

    from server.config import Config
    from server.main import _create_app

    cfg = Config(
        host="127.0.0.1",
        port=8420,
        brain_seeds_dir="",
        brain_json_path="",
        reload_enabled=False,
    )
    app = _create_app(cfg)

    # Patch BrainBridge._load to be a no-op so we don't load real brain data.
    with patch("server.brain_bridge.BrainBridge._load"):
        from server.brain_bridge import BrainBridge

        bridge = BrainBridge(brain_json_path=None, seeds_dir=None)

    # bridge._brain is None (static mode) — all methods return empty data
    app.state.bridge = bridge
    app.state.config = cfg
    app.state.reload_manager = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
