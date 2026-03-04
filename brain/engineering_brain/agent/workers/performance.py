"""Performance domain worker."""

from __future__ import annotations

from engineering_brain.agent.worker import WorkerAgent


class PerformanceWorker(WorkerAgent):
    """Worker specializing in performance analysis."""

    domain = "performance"
    card_id = "performance_worker"

    def _get_domains(self) -> list[str]:
        return ["performance", "scalability", "optimization"]
