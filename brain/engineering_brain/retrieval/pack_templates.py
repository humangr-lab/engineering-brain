"""PackTemplateRegistry — loads YAML templates, resolves inheritance, provides discovery.

Templates are YAML files in configs/engineering_brain/pack_templates/ that define
reusable recipes for pack creation. Templates support inheritance via `extends`.

Usage:
    registry = get_template_registry()
    template = registry.get("security-review")
    all_templates = registry.list_templates()
    matches = registry.search(tags=["security"])
"""

from __future__ import annotations

import fnmatch
import logging
from pathlib import Path
from typing import Any

import yaml

from engineering_brain.core.config import BrainConfig, get_brain_config
from engineering_brain.core.types import MCPToolSpec, PackTemplate

logger = logging.getLogger(__name__)

# Module-level singleton
_registry: PackTemplateRegistry | None = None


class PackTemplateRegistry:
    """Loads, caches, and provides discovery for pack templates."""

    def __init__(self, templates_dir: str | None = None, config: BrainConfig | None = None) -> None:
        cfg = config or get_brain_config()
        self._templates_dir = templates_dir or cfg.pack_templates_directory
        self._templates: dict[str, PackTemplate] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load templates on first access."""
        if self._loaded:
            return
        self._load_all()
        self._resolve_inheritance()
        self._loaded = True

    def _load_all(self) -> None:
        """Load all YAML template files from the templates directory."""
        templates_path = Path(self._templates_dir)
        if not templates_path.is_dir():
            logger.warning("Pack templates directory not found: %s", self._templates_dir)
            return

        for yaml_file in sorted(templates_path.glob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    raw = yaml.safe_load(f)
                if not raw or not isinstance(raw, dict):
                    continue
                # Convert mcp_tools from dicts to MCPToolSpec objects
                if "mcp_tools" in raw and isinstance(raw["mcp_tools"], list):
                    raw["mcp_tools"] = [
                        MCPToolSpec(**t) if isinstance(t, dict) else t for t in raw["mcp_tools"]
                    ]
                template = PackTemplate(**raw)
                self._templates[template.id] = template
                logger.debug("Loaded pack template: %s from %s", template.id, yaml_file.name)
            except Exception as e:
                logger.warning("Failed to load template %s: %s", yaml_file.name, e)

        logger.info("Loaded %d pack templates from %s", len(self._templates), self._templates_dir)

    def _resolve_inheritance(self) -> None:
        """Resolve `extends` inheritance — shallow merge (child overrides parent)."""
        resolved: set[str] = set()

        def _resolve(template_id: str) -> PackTemplate:
            if template_id in resolved:
                return self._templates[template_id]

            template = self._templates.get(template_id)
            if template is None:
                raise KeyError(f"Template not found: {template_id}")

            if not template.extends:
                resolved.add(template_id)
                return template

            # Build merged data from parents (left to right)
            merged: dict[str, Any] = {}
            for parent_id in template.extends:
                if parent_id not in self._templates:
                    logger.warning("Template %s extends unknown parent %s", template_id, parent_id)
                    continue
                parent = _resolve(parent_id)
                parent_data = parent.model_dump()
                # Merge parent fields into merged (later parents override earlier)
                for key, value in parent_data.items():
                    if key in ("id", "name", "description", "extends", "version"):
                        continue  # Never inherit identity fields
                    if isinstance(value, list) and value:
                        # Lists: merge parent into merged
                        existing = merged.get(key, [])
                        if isinstance(existing, list):
                            merged[key] = existing + [v for v in value if v not in existing]
                        else:
                            merged[key] = value
                    elif isinstance(value, dict) and value:
                        existing = merged.get(key, {})
                        if isinstance(existing, dict):
                            merged[key] = {**existing, **value}
                        else:
                            merged[key] = value
                    elif value and not (isinstance(value, (int, float)) and value == 0):
                        merged[key] = value

            # Child overrides everything it explicitly sets
            # Compare against Pydantic defaults to detect explicit overrides
            defaults = PackTemplate(id="__defaults__").model_dump()
            child_data = template.model_dump()
            for key, value in child_data.items():
                if key in ("extends",):
                    continue
                # Only override if the child actually set a non-default value
                if (
                    isinstance(value, list)
                    and value
                    or isinstance(value, dict)
                    and value
                    or isinstance(value, str)
                    and value
                    or isinstance(value, bool)
                    and value != defaults.get(key)
                ):
                    merged[key] = value
                elif isinstance(value, (int, float)) and value != defaults.get(key):
                    # Only override if child explicitly changed from default
                    merged[key] = value

            # Ensure identity fields come from child
            merged["id"] = template.id
            merged["name"] = template.name or merged.get("name", "")
            merged["description"] = template.description or merged.get("description", "")
            merged["version"] = template.version

            # Convert mcp_tools back
            if "mcp_tools" in merged and isinstance(merged["mcp_tools"], list):
                merged["mcp_tools"] = [
                    MCPToolSpec(**t) if isinstance(t, dict) else t for t in merged["mcp_tools"]
                ]

            self._templates[template_id] = PackTemplate(**merged)
            resolved.add(template_id)
            return self._templates[template_id]

        for tid in list(self._templates.keys()):
            try:
                _resolve(tid)
            except Exception as e:
                logger.warning("Failed to resolve inheritance for %s: %s", tid, e)

    def get(self, template_id: str) -> PackTemplate:
        """Get a template by ID. Raises KeyError if not found."""
        self._ensure_loaded()
        if template_id not in self._templates:
            raise KeyError(
                f"Pack template not found: {template_id!r}. Available: {sorted(self._templates.keys())}"
            )
        return self._templates[template_id]

    def list_templates(self) -> list[PackTemplate]:
        """List all available templates."""
        self._ensure_loaded()
        return sorted(self._templates.values(), key=lambda t: t.id)

    def search(
        self, tags: list[str] | None = None, domain: str = "", technology: str = ""
    ) -> list[PackTemplate]:
        """Search templates by tags, domain, or technology."""
        self._ensure_loaded()
        results: list[PackTemplate] = []

        for template in self._templates.values():
            # Tag match
            if tags:
                if any(t.lower() in [x.lower() for x in template.tags] for t in tags):
                    results.append(template)
                    continue

            # Domain match (glob)
            if domain:
                if any(fnmatch.fnmatch(domain.lower(), d.lower()) for d in template.domains):
                    results.append(template)
                    continue

            # Technology match (glob)
            if technology:
                if any(
                    fnmatch.fnmatch(technology.lower(), t.lower()) for t in template.technologies
                ):
                    results.append(template)
                    continue

        return sorted(results, key=lambda t: t.id)

    @property
    def size(self) -> int:
        """Number of loaded templates."""
        self._ensure_loaded()
        return len(self._templates)


def get_template_registry(config: BrainConfig | None = None) -> PackTemplateRegistry:
    """Get the module-level singleton template registry."""
    global _registry  # noqa: PLW0603
    if _registry is None:
        _registry = PackTemplateRegistry(config=config)
    return _registry


def reset_template_registry() -> None:
    """Reset the singleton (for testing)."""
    global _registry  # noqa: PLW0603
    _registry = None
