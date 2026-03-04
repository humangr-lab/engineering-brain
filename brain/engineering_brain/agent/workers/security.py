"""Security domain worker."""

from __future__ import annotations

from engineering_brain.agent.worker import WorkerAgent


class SecurityWorker(WorkerAgent):
    """Worker specializing in security analysis."""

    domain = "security"
    card_id = "security_worker"

    def _get_domains(self) -> list[str]:
        return ["security", "auth", "crypto"]
