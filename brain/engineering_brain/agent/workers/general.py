"""General-purpose domain worker."""

from __future__ import annotations

from engineering_brain.agent.worker import WorkerAgent


class GeneralWorker(WorkerAgent):
    """Fallback worker for topics not covered by specialist workers."""

    domain = "general"
    card_id = "general_worker"

    def _get_domains(self) -> list[str]:
        return []  # No domain filter — search entire brain
