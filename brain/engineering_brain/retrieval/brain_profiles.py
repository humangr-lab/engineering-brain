"""Brain Profiles — role-specific reasoning preferences for ERG.

Profiles control pack boost/suppress, confidence thresholds, and
contradiction sensitivity. Loaded from YAML configs.
"""

from __future__ import annotations

import logging
import os

import yaml

from engineering_brain.core.types import BrainProfile

logger = logging.getLogger(__name__)

# Default directory for profile YAML files
_PROFILES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "profiles",
)

# Cache loaded profiles
_profile_cache: dict[str, BrainProfile] = {}


def load_profile(profile_id: str, profiles_dir: str | None = None) -> BrainProfile | None:
    """Load a brain profile from YAML.

    Args:
        profile_id: Profile name (e.g. "data_engineer", "security_engineer").
        profiles_dir: Override directory to load from.

    Returns:
        BrainProfile or None if not found.
    """
    if profile_id in _profile_cache:
        return _profile_cache[profile_id]

    directory = profiles_dir or _PROFILES_DIR
    path = os.path.join(directory, f"{profile_id}.yaml")

    if not os.path.isfile(path):
        logger.debug("Profile %r not found at %s", profile_id, path)
        return None

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return None
        profile = BrainProfile(**data)
        _profile_cache[profile_id] = profile
        return profile
    except Exception as e:
        logger.warning("Failed to load profile %r: %s", profile_id, e)
        return None


def get_available_profiles(profiles_dir: str | None = None) -> list[str]:
    """List available profile IDs."""
    directory = profiles_dir or _PROFILES_DIR
    if not os.path.isdir(directory):
        return []
    return [
        f[:-5]  # strip .yaml
        for f in sorted(os.listdir(directory))
        if f.endswith(".yaml") and not f.startswith(".")
    ]


def clear_profile_cache() -> None:
    """Clear the profile cache (for testing)."""
    _profile_cache.clear()
