"""Ablation study charts: waterfall and heatmap."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from ..results import AblationResult
from .theme import apply_hugr_theme, fig_to_base64, HUGR_BLUE, HUGR_RED, HUGR_GREEN


def waterfall_impact(ablation_results: list[AblationResult], dark: bool = False) -> str:
    """Sorted waterfall chart showing each flag's impact on NDCG@10."""
    apply_hugr_theme(dark)

    # Sort by delta magnitude (most impactful first)
    sorted_results = sorted(ablation_results, key=lambda r: r.delta_ndcg)

    names = [r.flag_name.replace("_enabled", "").replace("llm_", "LLM:") for r in sorted_results]
    deltas = [r.delta_ndcg for r in sorted_results]

    fig, ax = plt.subplots(figsize=(12, max(6, len(names) * 0.4)))

    colors = [HUGR_RED if d < -0.001 else HUGR_GREEN if d > 0.001 else "#888888" for d in deltas]
    y_pos = np.arange(len(names))

    bars = ax.barh(y_pos, deltas, color=colors, edgecolor="white", linewidth=0.5, height=0.7, zorder=3)

    # Value labels
    for bar, delta in zip(bars, deltas):
        x = bar.get_width()
        sign = "+" if delta >= 0 else ""
        ha = "left" if x >= 0 else "right"
        offset = 0.001 if x >= 0 else -0.001
        ax.text(x + offset, bar.get_y() + bar.get_height() / 2, f"{sign}{delta:.4f}", va="center", ha=ha, fontsize=9)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=10)
    ax.set_xlabel("NDCG@10 Delta (negative = feature helps when ON)")
    ax.set_title("Ablation Study: Feature Impact on Retrieval Quality", fontweight="bold", pad=16)
    ax.axvline(x=0, color="#666666", linewidth=1, zorder=2)
    ax.grid(axis="x", alpha=0.3, zorder=0)
    ax.grid(axis="y", visible=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.invert_yaxis()

    fig.tight_layout()
    return fig_to_base64(fig)


def heatmap_flags(ablation_results: list[AblationResult], dark: bool = False) -> str:
    """Heatmap: flag x metric delta matrix."""
    apply_hugr_theme(dark)

    # Sort by group, then by name
    sorted_results = sorted(ablation_results, key=lambda r: (r.group, r.flag_name))

    names = [r.flag_name.replace("_enabled", "").replace("llm_", "LLM:") for r in sorted_results]
    metrics = ["NDCG", "MRR", "Recall", "Latency"]

    data = []
    for r in sorted_results:
        data.append([r.delta_ndcg, r.delta_mrr, r.delta_recall, r.delta_latency_ms / 100])

    fig, ax = plt.subplots(figsize=(8, max(6, len(names) * 0.45)))
    arr = np.array(data)

    # Diverging colormap centered at 0
    vmax = max(abs(arr[:, :3].min()), abs(arr[:, :3].max()), 0.01)
    im = ax.imshow(arr[:, :3], cmap="RdYlGn_r", aspect="auto", vmin=-vmax, vmax=vmax)

    ax.set_xticks(np.arange(3))
    ax.set_yticks(np.arange(len(names)))
    ax.set_xticklabels(metrics[:3], fontweight="medium")
    ax.set_yticklabels(names, fontsize=9)

    # Annotate cells
    for i in range(len(names)):
        for j in range(3):
            val = arr[i, j]
            sign = "+" if val >= 0 else ""
            text_color = "white" if abs(val) > vmax * 0.6 else "black"
            ax.text(j, i, f"{sign}{val:.4f}", ha="center", va="center", fontsize=8, color=text_color)

    ax.set_title("Ablation Impact Matrix (delta when toggled OFF)", fontweight="bold", pad=16)
    fig.colorbar(im, ax=ax, label="Delta", shrink=0.8)

    fig.tight_layout()
    return fig_to_base64(fig)
