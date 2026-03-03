"""Server configuration — all tunables in one place."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    """Immutable server configuration loaded from env vars or defaults."""

    host: str = "0.0.0.0"
    port: int = 8420

    # Brain data source — one of these must be set
    brain_seeds_dir: str = ""  # Load from YAML seeds (full boot)
    brain_json_path: str = ""  # Load from saved JSON snapshot (fast)

    cors_origins: list[str] = field(default_factory=lambda: ["*"])

    # SSE polling interval (seconds)
    sse_poll_interval: float = 2.0

    # Pagination defaults
    default_page_size: int = 500
    max_page_size: int = 5000

    # Live-reload settings
    reload_enabled: bool = True
    reload_poll_interval: float = 1.0
    reload_debounce_seconds: float = 3.0

    @classmethod
    def from_env(cls) -> Config:
        origins_raw = os.getenv("CORS_ORIGINS", "*")
        origins = [o.strip() for o in origins_raw.split(",")]
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8420")),
            brain_seeds_dir=os.getenv("BRAIN_SEEDS_DIR", ""),
            brain_json_path=os.getenv("BRAIN_JSON_PATH", ""),
            cors_origins=origins,
            sse_poll_interval=float(os.getenv("SSE_POLL_INTERVAL", "2.0")),
            default_page_size=int(os.getenv("DEFAULT_PAGE_SIZE", "500")),
            max_page_size=int(os.getenv("MAX_PAGE_SIZE", "5000")),
            reload_enabled=os.getenv("RELOAD_ENABLED", "true").lower() in ("1", "true", "yes"),
            reload_poll_interval=float(os.getenv("RELOAD_POLL_INTERVAL", "1.0")),
            reload_debounce_seconds=float(os.getenv("RELOAD_DEBOUNCE_SECONDS", "3.0")),
        )
