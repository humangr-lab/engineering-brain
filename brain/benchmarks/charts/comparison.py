"""Comparison charts: Brain vs baselines."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from ..results import BenchmarkResults
from .theme import apply_hugr_theme, fig_to_base64, get_system_color


def bar_comparison(results: BenchmarkResults, dark: bool = False) -> str:
    """Grouped bar chart: systems x metrics (NDCG, MRR, Recall, MAP, F1)."""
    apply_hugr_theme(dark)

    metrics = ["NDCG@10", "MRR", "Recall@10", "MAP", "F1@10"]
    systems = list(results.systems.keys())
    n_metrics = len(metrics)
    n_systems = len(systems)

    data = []
    for name in systems:
        agg = results.systems[name].aggregate
        data.append([
            agg.avg_ndcg_at_10,
            agg.avg_mrr,
            agg.avg_recall_at_10,
            agg.avg_map,
            agg.avg_f1_at_10,
        ])

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(n_metrics)
    width = 0.8 / n_systems

    for i, (name, values) in enumerate(zip(systems, data, strict=False)):
        offset = (i - n_systems / 2 + 0.5) * width
        bars = ax.bar(
            x + offset,
            values,
            width,
            label=name,
            color=get_system_color(name),
            edgecolor="white",
            linewidth=0.5,
            zorder=3,
        )
        # Value labels on bars
        for bar, val in zip(bars, values, strict=False):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"{val:.3f}",
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="medium",
            )

    ax.set_xlabel("")
    ax.set_ylabel("Score")
    ax.set_title("Retrieval Quality: Engineering Brain vs Baselines", fontweight="bold", pad=16)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontweight="medium")
    ax.set_ylim(0, 1.15)
    ax.legend(loc="upper right", framealpha=0.9)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    ax.grid(axis="x", visible=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return fig_to_base64(fig)


def radar_comparison(results: BenchmarkResults, dark: bool = False) -> str:
    """Radar/spider chart: multi-dimensional system comparison."""
    apply_hugr_theme(dark)

    metrics = ["NDCG@10", "MRR", "Recall@10", "Precision@10", "MAP", "F1@10"]
    systems = list(results.systems.keys())

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection="polar"))

    angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
    angles += angles[:1]  # Close the polygon

    for name in systems:
        agg = results.systems[name].aggregate
        values = [
            agg.avg_ndcg_at_10,
            agg.avg_mrr,
            agg.avg_recall_at_10,
            agg.avg_precision_at_10,
            agg.avg_map,
            agg.avg_f1_at_10,
        ]
        values += values[:1]
        color = get_system_color(name)
        ax.plot(angles, values, "o-", linewidth=2, label=name, color=color, markersize=6)
        ax.fill(angles, values, alpha=0.1, color=color)

    ax.set_thetagrids(np.degrees(angles[:-1]), metrics, fontweight="medium")
    ax.set_ylim(0, 1.05)
    ax.set_title("Multi-Dimensional Quality Comparison", fontweight="bold", pad=24, fontsize=14)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), framealpha=0.9)

    fig.tight_layout()
    return fig_to_base64(fig)


def category_heatmap(results: BenchmarkResults, dark: bool = False) -> str:
    """Heatmap: system x category x NDCG@10."""
    apply_hugr_theme(dark)

    systems = list(results.systems.keys())
    # Collect all categories across systems
    all_cats: set[str] = set()
    for sr in results.systems.values():
        all_cats.update(sr.per_category.keys())
    categories = sorted(all_cats)

    data = []
    for name in systems:
        row = []
        for cat in categories:
            cat_metrics = results.systems[name].per_category.get(cat)
            row.append(cat_metrics.avg_ndcg_at_10 if cat_metrics else 0.0)
        data.append(row)

    fig, ax = plt.subplots(figsize=(12, max(4, len(systems) * 1.2)))
    arr = np.array(data)

    im = ax.imshow(arr, cmap="RdYlGn", aspect="auto", vmin=0.5, vmax=1.0)
    ax.set_xticks(np.arange(len(categories)))
    ax.set_yticks(np.arange(len(systems)))
    ax.set_xticklabels([c.replace("_", " ").title() for c in categories], fontweight="medium")
    ax.set_yticklabels(systems, fontweight="medium")

    # Annotate cells
    for i in range(len(systems)):
        for j in range(len(categories)):
            val = arr[i, j]
            text_color = "white" if val < 0.75 else "black"
            ax.text(j, i, f"{val:.3f}", ha="center", va="center", fontsize=10, color=text_color, fontweight="medium")

    ax.set_title("NDCG@10 by Category and System", fontweight="bold", pad=16)
    fig.colorbar(im, ax=ax, label="NDCG@10", shrink=0.8)

    fig.tight_layout()
    return fig_to_base64(fig)
