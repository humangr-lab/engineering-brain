"""Debugging domain worker."""

from __future__ import annotations

from engineering_brain.agent.worker import WorkerAgent


class DebuggingWorker(WorkerAgent):
    """Worker specializing in debugging and incident analysis."""

    domain = "debugging"
    card_id = "debugging_worker"

    def _get_domains(self) -> list[str]:
        return ["debugging", "testing", "operations"]
