"""Robustness charts: degradation and resilience."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from ..results import RobustnessScenarioResult
from .theme import apply_hugr_theme, fig_to_base64, HUGR_BLUE, HUGR_RED, HUGR_GREEN, HUGR_AMBER


def degradation_chart(robustness_results: list[RobustnessScenarioResult], dark: bool = False) -> str:
    """Bar chart showing quality degradation per adversarial scenario."""
    apply_hugr_theme(dark)

    scenarios = [r.scenario.replace("_", " ").title() for r in robustness_results]
    baseline_ndcg = [r.baseline_ndcg for r in robustness_results]
    degraded_ndcg = [r.degraded_ndcg for r in robustness_results]
    resilience = [r.resilience_score for r in robustness_results]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Left: NDCG before/after
    x = np.arange(len(scenarios))
    width = 0.35
    ax1.bar(x - width / 2, baseline_ndcg, width, label="Clean Baseline", color=HUGR_GREEN, edgecolor="white", linewidth=0.5, zorder=3)
    ax1.bar(x + width / 2, degraded_ndcg, width, label="After Injection", color=HUGR_RED, edgecolor="white", linewidth=0.5, zorder=3)
    ax1.set_xticks(x)
    ax1.set_xticklabels(scenarios, fontweight="medium")
    ax1.set_ylabel("NDCG@10")
    ax1.set_title("Quality Under Adversarial Injection", fontweight="bold", pad=12)
    ax1.set_ylim(0, 1.15)
    ax1.legend(framealpha=0.9)
    ax1.grid(axis="y", alpha=0.3, zorder=0)
    ax1.grid(axis="x", visible=False)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    # Right: Resilience scores
    colors = [HUGR_GREEN if r >= 0.8 else HUGR_AMBER if r >= 0.6 else HUGR_RED for r in resilience]
    bars = ax2.bar(x, resilience, color=colors, edgecolor="white", linewidth=0.5, zorder=3)
    for bar, val in zip(bars, resilience):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02, f"{val:.3f}", ha="center", va="bottom", fontsize=11, fontweight="medium")
    ax2.set_xticks(x)
    ax2.set_xticklabels(scenarios, fontweight="medium")
    ax2.set_ylabel("Resilience Score")
    ax2.set_title("Resilience per Scenario", fontweight="bold", pad=12)
    ax2.set_ylim(0, 1.15)
    ax2.grid(axis="y", alpha=0.3, zorder=0)
    ax2.grid(axis="x", visible=False)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    fig.tight_layout(w_pad=4)
    return fig_to_base64(fig)
