"""Shared fixtures for engineering_brain tests.

Resets module-level global state between test modules to prevent
cross-contamination (see audit finding C5).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_global_state() -> None:  # noqa: PT004
    """Reset module-level singletons before each test function.

    Addresses global state pollution from:
    - context_extractor._dynamic_tech_index
    - context_extractor._dynamic_domain_index
    - taxonomy._global_registry
    - brain_factory singleton
    """
    # Reset context extractor indices
    try:
        from engineering_brain.retrieval import context_extractor

        context_extractor._dynamic_tech_index = {}
        context_extractor._dynamic_domain_index = {}
    except (ImportError, AttributeError):
        pass

    # Reset taxonomy registry
    try:
        from engineering_brain.core import taxonomy

        taxonomy._global_registry = None
    except (ImportError, AttributeError):
        pass

    # Reset brain factory singleton
    try:
        from engineering_brain.core.brain_factory import reset_brain

        reset_brain()
    except (ImportError, AttributeError):
        pass

    # Reset agent card cache
    try:
        from engineering_brain.agent.runtime_cards import clear_card_cache

        clear_card_cache()
    except (ImportError, AttributeError):
        pass
