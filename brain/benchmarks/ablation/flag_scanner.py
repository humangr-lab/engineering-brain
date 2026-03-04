"""Discovers all configurable flags from BrainConfig via introspection."""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, fields as dc_fields
from typing import Any

from .flag_groups import get_flag_group


@dataclass
class FlagInfo:
    """Metadata about a single feature flag."""

    field_name: str
    env_var: str
    field_type: str
    default_value: Any
    group: str


def scan_flags() -> list[FlagInfo]:
    """Introspect BrainConfig and extract all toggleable boolean fields."""
    from engineering_brain.core.config import BrainConfig

    flags: list[FlagInfo] = []

    for f in dc_fields(BrainConfig):
        if f.type != "bool" and f.type is not bool:
            continue

        # Extract env var name from default_factory source
        env_var = _extract_env_var(f)
        if not env_var:
            continue

        # Get default value
        default_value = True
        if f.default_factory is not None:  # type: ignore[arg-type]
            try:
                default_value = f.default_factory()  # type: ignore[misc]
            except Exception:
                pass

        group = get_flag_group(f.name)
        flags.append(
            FlagInfo(
                field_name=f.name,
                env_var=env_var,
                field_type="bool",
                default_value=default_value,
                group=group,
            )
        )

    return flags


def _extract_env_var(field: Any) -> str | None:
    """Extract environment variable name from a field's default_factory lambda."""
    if field.default_factory is None:
        return None

    try:
        source = inspect.getsource(field.default_factory)
    except (OSError, TypeError):
        return None

    # Match patterns like _env_bool("BRAIN_SOMETHING", ...)
    match = re.search(r'_env_bool\(\s*["\']([A-Z_]+)["\']', source)
    if match:
        return match.group(1)
    return None
