"""Cost/benefit analysis across benchmark systems."""

from __future__ import annotations

import logging
import resource
import statistics
import time

from ..baselines.brain_system import BrainSystem
from ..baselines.graph_rag import GraphRAGSystem
from ..baselines.naive_rag import NaiveRAGSystem
from ..datasets.loader import DatasetLoader
from ..results import CostProfile
from .profiler import BenchmarkProfiler, QueryProfile

logger = logging.getLogger(__name__)


class CostAnalyzer:
    """Runs cost/benefit analysis across systems."""

    def __init__(self, dataset_path: str | None = None) -> None:
        self._dataset_path = dataset_path

    def run(self) -> list[CostProfile]:
        """Profile all local systems (no API key required)."""
        systems = [
            BrainSystem(),
            NaiveRAGSystem(),
            GraphRAGSystem(),
        ]

        loader = DatasetLoader(self._dataset_path)
        queries = loader.load()
        profiler = BenchmarkProfiler()
        results: list[CostProfile] = []

        for system in systems:
            logger.info("Profiling: %s", system.name)

            # Measure setup time
            setup_start = time.monotonic()
            system.setup()
            setup_time = time.monotonic() - setup_start

            # Measure peak memory before queries
            mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

            try:
                profiles: list[QueryProfile] = []
                for q in queries:
                    _, profile = profiler.profile_query(system, q)
                    profiles.append(profile)

                mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                latencies = sorted(p.latency_ms for p in profiles)
                total_tokens = sum(p.token_count for p in profiles)
                n = len(profiles) or 1

                results.append(
                    CostProfile(
                        system_name=system.name,
                        avg_latency_ms=sum(latencies) / n,
                        median_latency_ms=statistics.median(latencies) if latencies else 0.0,
                        p95_latency_ms=latencies[min(int(0.95 * len(latencies)), len(latencies) - 1)]
                        if latencies
                        else 0.0,
                        p99_latency_ms=latencies[min(int(0.99 * len(latencies)), len(latencies) - 1)]
                        if latencies
                        else 0.0,
                        total_tokens=total_tokens,
                        avg_tokens_per_query=total_tokens / n,
                        peak_memory_mb=max(0, mem_after - mem_before) / 1024,
                        setup_time_s=setup_time,
                    )
                )

                logger.info(
                    "  %s: p50=%.1fms p95=%.1fms tokens=%d setup=%.1fs",
                    system.name,
                    results[-1].median_latency_ms,
                    results[-1].p95_latency_ms,
                    total_tokens,
                    setup_time,
                )
            finally:
                system.teardown()

        return results
