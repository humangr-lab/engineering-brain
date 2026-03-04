"""Validation Router — maps knowledge nodes to appropriate checkers.

Routes each node to the right checker(s) based on its technologies,
domains, and severity. This ensures we don't waste API calls on
irrelevant checks.
"""

from __future__ import annotations

import logging
from typing import Any

from engineering_brain.validation.checkers import SourceChecker

logger = logging.getLogger(__name__)


class ValidationRouter:
    """Routes knowledge nodes to appropriate validation checkers."""

    def __init__(self, checkers: dict[str, SourceChecker]) -> None:
        self._checkers = checkers

    def route(self, node: dict[str, Any]) -> list[SourceChecker]:
        """Determine which checkers should validate this node.

        Args:
            node: Knowledge node dict with technologies, domains, severity, etc.

        Returns:
            Ordered list of checkers to run (most relevant first).
        """
        selected: list[SourceChecker] = []
        technologies = node.get("technologies", [])
        domains = [d.lower() for d in node.get("domains", [])]
        severity = node.get("severity", "medium").lower()
        layer = node.get("layer", "L3")
        techs_lower = [t.lower() for t in technologies]

        # L0 axioms are auto-verified (no API calls)
        if layer == "L0":
            return []

        # Security domain → NVD + GitHub Advisory + OWASP
        if "security" in domains or "auth" in domains:
            if "nvd_cve" in self._checkers:
                selected.append(self._checkers["nvd_cve"])
            if "github_advisory" in self._checkers:
                selected.append(self._checkers["github_advisory"])
            if "owasp" in self._checkers:
                selected.append(self._checkers["owasp"])

        # Web technologies → MDN
        web_techs = {
            "html",
            "css",
            "javascript",
            "react",
            "vue",
            "angular",
            "svelte",
            "typescript",
            "next.js",
            "htmx",
            "alpine.js",
        }
        web_domains = {"web", "frontend", "css", "html", "javascript", "browser"}
        if any(t in web_techs for t in techs_lower) or (set(domains) & web_domains):
            if "mdn" in self._checkers:
                selected.append(self._checkers["mdn"])

        # Any recognized technology → official docs
        if technologies and "official_docs" in self._checkers:
            selected.append(self._checkers["official_docs"])

        # Package-based technologies → package registry
        if technologies and "package_registry" in self._checkers:
            selected.append(self._checkers["package_registry"])

        # High-severity or high-reinforcement → also SO for community validation
        reinforcement = node.get("reinforcement_count", 0)
        if severity in ("critical", "high") or reinforcement >= 3:
            if (
                "stackoverflow" in self._checkers
                and self._checkers["stackoverflow"] not in selected
            ):
                selected.append(self._checkers["stackoverflow"])

        # Architecture/design patterns checker — for nodes without technologies
        pattern_domains = {
            "architecture",
            "design",
            "patterns",
            "agile",
            "project_management",
            "product_management",
            "planning",
            "strategy",
            "spec_writing",
            "devops",
            "testing",
            "performance",
            "metrics",
            "risk",
            "ui",
            "ux",
            "code_quality",
            "research",
        }
        if "architecture_patterns" in self._checkers:
            if not technologies or (set(domains) & pattern_domains):
                selected.append(self._checkers["architecture_patterns"])

        # If nothing matched, fall back to SO + official_docs
        if not selected:
            for name in ("official_docs", "stackoverflow"):
                if name in self._checkers:
                    selected.append(self._checkers[name])

        return selected
