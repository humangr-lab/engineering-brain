"""Cost/benefit charts: latency distributions and tradeoffs."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from ..results import BenchmarkResults, CostProfile
from .theme import apply_hugr_theme, fig_to_base64, get_system_color


def latency_comparison(cost_profiles: list[CostProfile], dark: bool = False) -> str:
    """Bar chart comparing latency percentiles across systems."""
    apply_hugr_theme(dark)

    names = [p.system_name for p in cost_profiles]
    p50 = [p.median_latency_ms for p in cost_profiles]
    p95 = [p.p95_latency_ms for p in cost_profiles]
    p99 = [p.p99_latency_ms for p in cost_profiles]

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(names))
    width = 0.25

    ax.bar(
        x - width,
        p50,
        width,
        label="p50",
        color=[get_system_color(n) for n in names],
        edgecolor="white",
        linewidth=0.5,
        alpha=0.6,
        zorder=3,
    )
    ax.bar(
        x,
        p95,
        width,
        label="p95",
        color=[get_system_color(n) for n in names],
        edgecolor="white",
        linewidth=0.5,
        alpha=0.8,
        zorder=3,
    )
    ax.bar(
        x + width,
        p99,
        width,
        label="p99",
        color=[get_system_color(n) for n in names],
        edgecolor="white",
        linewidth=0.5,
        alpha=1.0,
        zorder=3,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(names, fontweight="medium")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Query Latency by System", fontweight="bold", pad=16)
    ax.legend(framealpha=0.9)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    ax.grid(axis="x", visible=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig_to_base64(fig)


def quality_vs_cost(
    results: BenchmarkResults, cost_profiles: list[CostProfile], dark: bool = False
) -> str:
    """Scatter plot: quality (NDCG) vs cost (latency)."""
    apply_hugr_theme(dark)

    fig, ax = plt.subplots(figsize=(10, 7))

    cost_lookup = {p.system_name: p for p in cost_profiles}

    for name, sr in results.systems.items():
        profile = cost_lookup.get(name)
        if not profile:
            continue
        color = get_system_color(name)
        ax.scatter(
            profile.median_latency_ms,
            sr.aggregate.avg_ndcg_at_10,
            s=200,
            c=color,
            label=name,
            edgecolors="white",
            linewidth=1.5,
            zorder=5,
        )
        ax.annotate(
            name,
            (profile.median_latency_ms, sr.aggregate.avg_ndcg_at_10),
            xytext=(10, 10),
            textcoords="offset points",
            fontsize=10,
            fontweight="medium",
        )

    ax.set_xlabel("Median Latency (ms)")
    ax.set_ylabel("NDCG@10")
    ax.set_title("Quality vs. Cost Tradeoff", fontweight="bold", pad=16)
    ax.grid(alpha=0.3, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig_to_base64(fig)
