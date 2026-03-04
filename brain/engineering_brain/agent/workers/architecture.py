"""Architecture domain worker."""

from __future__ import annotations

from engineering_brain.agent.worker import WorkerAgent


class ArchitectureWorker(WorkerAgent):
    """Worker specializing in software architecture analysis."""

    domain = "architecture"
    card_id = "architecture_worker"

    def _get_domains(self) -> list[str]:
        return ["architecture", "api", "design"]
