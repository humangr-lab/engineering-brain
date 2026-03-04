"""Matplotlib theme matching the HuGR design system.

Colors derived from cockpit/client/css/tokens.css OKLCH values.
"""

from __future__ import annotations

import base64
from io import BytesIO

import matplotlib as mpl
import matplotlib.pyplot as plt

# -- HuGR Brand Colors (hex equivalents of OKLCH tokens) --
HUGR_BLUE = "#6b8fff"
HUGR_PURPLE = "#9b7cff"
HUGR_GREEN = "#5cb870"
HUGR_TEAL = "#3db8b8"
HUGR_AMBER = "#c4a232"
HUGR_RED = "#d4586a"
HUGR_ORANGE = "#cc8033"
HUGR_INDIGO = "#7b7aff"

# -- Surface Colors (dark theme) --
SURFACE_0 = "#0f1117"
SURFACE_1 = "#161922"
SURFACE_2 = "#1f2330"

# -- Text Colors --
TEXT_PRIMARY = "#e0e4ed"
TEXT_SECONDARY = "#8b92a8"

# -- Palettes --
PALETTE = [HUGR_BLUE, HUGR_PURPLE, HUGR_GREEN, HUGR_AMBER, HUGR_TEAL, HUGR_RED, HUGR_ORANGE, HUGR_INDIGO]
PALETTE_LIGHT = ["#4a6fdf", "#7b5cdf", "#2e8b57", "#b8920e", "#1a8b8b", "#c9374e", "#b06820", "#5b5adf"]

# -- System names to colors (consistent across all charts) --
SYSTEM_COLORS = {
    "Engineering Brain": HUGR_BLUE,
    "Naive RAG": HUGR_AMBER,
    "GraphRAG": HUGR_TEAL,
    "Raw LLM (sonnet)": HUGR_RED,
}


def apply_hugr_theme(dark: bool = False) -> None:
    """Apply HuGR design system to matplotlib."""
    if dark:
        plt.style.use("dark_background")
        bg_color = SURFACE_0
        text_color = TEXT_PRIMARY
        grid_color = SURFACE_2
        palette = PALETTE
    else:
        bg_color = "#ffffff"
        text_color = "#1a1a2e"
        grid_color = "#e2e4ed"
        palette = PALETTE_LIGHT

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Inter", "Helvetica Neue", "Arial", "sans-serif"],
            "font.size": 11,
            "axes.titlesize": 14,
            "axes.titleweight": "bold",
            "axes.labelsize": 12,
            "axes.facecolor": bg_color,
            "axes.edgecolor": grid_color,
            "axes.grid": True,
            "axes.prop_cycle": mpl.cycler(color=palette),
            "figure.facecolor": bg_color,
            "figure.dpi": 150,
            "figure.figsize": (10, 6),
            "text.color": text_color,
            "axes.labelcolor": text_color,
            "xtick.color": text_color,
            "ytick.color": text_color,
            "grid.color": grid_color,
            "grid.alpha": 0.3,
            "grid.linewidth": 0.5,
            "legend.framealpha": 0.9,
            "legend.edgecolor": grid_color,
            "legend.fontsize": 10,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.15,
        }
    )


def get_system_color(system_name: str) -> str:
    """Get consistent color for a system name."""
    if system_name in SYSTEM_COLORS:
        return SYSTEM_COLORS[system_name]
    # Fallback: cycle through palette
    idx = hash(system_name) % len(PALETTE_LIGHT)
    return PALETTE_LIGHT[idx]


def fig_to_base64(fig: plt.Figure) -> str:
    """Convert a matplotlib figure to base64-encoded PNG string."""
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")
