"""Agent configuration facade.

Reads agent-specific settings from BrainConfig and validates
preconditions (API key, feature flag).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from engineering_brain.core.config import BrainConfig, get_brain_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentConfig:
    """Validated, immutable snapshot of agent configuration."""

    enabled: bool
    api_key: str = field(repr=False)  # Never leak API key in repr/logs
    model: str
    orchestrator_model: str
    max_workers: int
    max_tokens: int
    timeout: int
    cards_dir: str

    def __post_init__(self) -> None:
        if self.max_workers < 1:
            object.__setattr__(self, "max_workers", 1)
        if self.max_tokens < 1:
            object.__setattr__(self, "max_tokens", 1)
        if self.timeout < 1:
            object.__setattr__(self, "timeout", 1)

    @property
    def is_configured(self) -> bool:
        """True when the agent system has a valid API key and is enabled."""
        return self.enabled and bool(self.api_key)


def get_agent_config(config: BrainConfig | None = None) -> AgentConfig:
    """Build AgentConfig from BrainConfig (reads current env)."""
    cfg = config or get_brain_config()
    return AgentConfig(
        enabled=cfg.agent_enabled,
        api_key=cfg.agent_api_key,
        model=cfg.agent_model,
        orchestrator_model=cfg.agent_orchestrator_model,
        max_workers=cfg.agent_max_workers,
        max_tokens=cfg.agent_max_tokens,
        timeout=cfg.agent_timeout,
        cards_dir=cfg.agent_cards_dir,
    )
