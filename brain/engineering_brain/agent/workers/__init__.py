"""Worker registry — maps domain names to WorkerAgent subclasses."""

from __future__ import annotations

__all__ = [
    "ArchitectureWorker",
    "DebuggingWorker",
    "GeneralWorker",
    "PerformanceWorker",
    "SecurityWorker",
    "WORKER_REGISTRY",
    "resolve_domain",
    "get_worker_class",
]

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engineering_brain.agent.worker import WorkerAgent

from engineering_brain.agent.workers.architecture import ArchitectureWorker
from engineering_brain.agent.workers.debugging import DebuggingWorker
from engineering_brain.agent.workers.general import GeneralWorker
from engineering_brain.agent.workers.performance import PerformanceWorker
from engineering_brain.agent.workers.security import SecurityWorker

# Domain string -> WorkerAgent subclass
WORKER_REGISTRY: dict[str, type[WorkerAgent]] = {
    "architecture": ArchitectureWorker,
    "security": SecurityWorker,
    "performance": PerformanceWorker,
    "debugging": DebuggingWorker,
    "general": GeneralWorker,
}

# Aliases for common domain names the orchestrator might emit
_DOMAIN_ALIASES: dict[str, str] = {
    "arch": "architecture",
    "design": "architecture",
    "system_design": "architecture",
    "sec": "security",
    "auth": "security",
    "perf": "performance",
    "optimization": "performance",
    "scalability": "performance",
    "debug": "debugging",
    "incident": "debugging",
    "troubleshooting": "debugging",
}


def resolve_domain(domain: str) -> str:
    """Normalize a domain string to a registry key."""
    key = domain.lower().strip()
    return _DOMAIN_ALIASES.get(key, key)


def get_worker_class(domain: str) -> type[WorkerAgent]:
    """Get the worker class for a domain, falling back to GeneralWorker."""
    resolved = resolve_domain(domain)
    return WORKER_REGISTRY.get(resolved, GeneralWorker)
