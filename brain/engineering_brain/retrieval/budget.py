"""Context budget enforcement for the Engineering Knowledge Brain.

Ensures knowledge injection stays within token/character limits.
Prevents prompt bloating while maximizing knowledge density.
"""

from __future__ import annotations

from typing import Any

from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import Layer


# Default per-layer character budgets (proportional allocation)
_DEFAULT_LAYER_BUDGETS: dict[str, float] = {
    "L1": 0.07,   # ~200 chars of 3000
    "L2": 0.20,   # ~600 chars
    "L3": 0.50,   # ~1500 chars
    "L4": 0.23,   # ~700 chars
}

# Markup overhead multiplier per layer — accounts for markdown headers,
# bullets, labels, and formatting that _estimate_chars doesn't count.
_MARKUP_OVERHEAD: dict[str, float] = {
    "L0": 1.3,   # Axioms: short text + formal notation
    "L1": 1.4,   # Principles: mental_model + when_applies + teaching_example
    "L2": 1.3,   # Patterns: intent + when_to_use + examples
    "L3": 1.2,   # Rules: why + how (already counted) + prediction
    "L4": 1.1,   # Evidence: compact
}


def enforce_budget(
    results_by_layer: dict[str, list[dict[str, Any]]],
    config: BrainConfig | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Enforce context budget across all layers.

    Trims results per layer to stay within character budget.
    Higher-scored results are kept first.
    """
    cfg = config or BrainConfig()
    total_budget = cfg.context_budget_chars
    trimmed: dict[str, list[dict[str, Any]]] = {}

    for layer_key, results in results_by_layer.items():
        layer_fraction = _DEFAULT_LAYER_BUDGETS.get(layer_key, 0.25)
        layer_budget = int(total_budget * layer_fraction)

        # Sort by relevance score (highest first)
        sorted_results = sorted(
            results,
            key=lambda n: n.get("_relevance_score", 0.0),
            reverse=True,
        )

        kept: list[dict[str, Any]] = []
        chars_used = 0

        overhead = _MARKUP_OVERHEAD.get(layer_key, 1.2)
        for node in sorted_results:
            node_chars = int(_estimate_chars(node) * overhead)
            if chars_used + node_chars <= layer_budget:
                kept.append(node)
                chars_used += node_chars
            elif not kept:
                # Always keep at least one result per layer
                kept.append(node)
                break

        trimmed[layer_key] = kept

    return trimmed


def estimate_total_chars(results_by_layer: dict[str, list[dict[str, Any]]]) -> int:
    """Estimate total character count for formatted output."""
    total = 0
    for results in results_by_layer.values():
        for node in results:
            total += _estimate_chars(node)
    return total


def _estimate_chars(node: dict[str, Any]) -> int:
    """Estimate character count for a single knowledge node when formatted."""
    chars = 0
    # Primary text
    text = node.get("text") or node.get("name") or node.get("statement") or node.get("description", "")
    chars += len(str(text))
    # WHY field
    why = node.get("why", "")
    chars += len(str(why))
    # HOW field
    how = node.get("how_to_do_right") or node.get("how_to_apply", "")
    chars += len(str(how))
    # Example (only good example, not bad)
    example = node.get("example_good", "")
    chars += len(str(example))
    # Prediction text
    pred_if = node.get("prediction_if", "")
    pred_then = node.get("prediction_then", "")
    if pred_if and pred_then:
        chars += len(str(pred_if)) + len(str(pred_then)) + 40
    # Overhead for formatting (markdown, labels, etc.)
    chars += 50
    return chars
