"""Injects adversarial knowledge into a Brain copy for robustness testing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ADVERSARIAL_PATH = Path(__file__).parent.parent / "datasets" / "adversarial_v1.yaml"


class KnowledgeInjector:
    """Injects conflicting, obsolete, or biased rules into a Brain."""

    def __init__(self, adversarial_path: str | None = None) -> None:
        path = Path(adversarial_path) if adversarial_path else _ADVERSARIAL_PATH
        with open(path) as f:
            self._data = yaml.safe_load(f)

    def inject(self, brain: Any, scenario: str) -> list[str]:
        """Inject adversarial rules for a given scenario.

        Returns IDs of injected rules.
        """
        rules = self._data.get(scenario, [])
        if not rules:
            logger.warning("No adversarial rules for scenario: %s", scenario)
            return []

        injected_ids: list[str] = []
        for rule in rules:
            rid = rule["id"]
            # Add directly to the brain's graph as L3 rules
            brain._graph.add_node(
                rid,
                {
                    "id": rid,
                    "text": rule["text"],
                    "why": rule.get("why", ""),
                    "how_to_do_right": rule.get("how_to_do_right", ""),
                    "technologies": rule.get("technologies", []),
                    "domains": rule.get("domains", []),
                    "severity": rule.get("severity", "medium"),
                    "layer": "L3_RULES",
                    "node_type": "Rule",
                    "reinforcement_count": rule.get("reinforcement_count", 1),
                    "validation_status": rule.get("validation_status", "unverified"),
                    "_adversarial": True,
                    "_scenario": scenario,
                },
            )
            injected_ids.append(rid)

        logger.info("Injected %d %s rules", len(injected_ids), scenario)
        return injected_ids

    def get_scenarios(self) -> list[str]:
        """Return available adversarial scenarios."""
        return [k for k in self._data if k != "version"]
