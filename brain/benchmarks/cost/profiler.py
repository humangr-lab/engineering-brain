"""Performance profiler for benchmark queries."""

from __future__ import annotations

import resource
import time
from dataclasses import dataclass

from ..baselines.base import BaselineSystem, SystemResult
from ..datasets.loader import EvalQuery


@dataclass
class QueryProfile:
    """Profile data for a single query execution."""

    query_id: str
    latency_ms: float
    memory_delta_kb: float
    token_count: int


class BenchmarkProfiler:
    """Profiles resource usage during benchmark runs."""

    def profile_query(
        self,
        system: BaselineSystem,
        query: EvalQuery,
    ) -> tuple[SystemResult, QueryProfile]:
        """Profile a single query execution."""
        mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        start = time.monotonic()

        result = system.query(
            task_description=query.query,
            technologies=query.expected_technologies,
            domains=query.expected_domains,
        )

        elapsed = (time.monotonic() - start) * 1000
        mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        profile = QueryProfile(
            query_id=query.id,
            latency_ms=elapsed,
            memory_delta_kb=max(0, mem_after - mem_before),
            token_count=result.token_count,
        )

        return result, profile
