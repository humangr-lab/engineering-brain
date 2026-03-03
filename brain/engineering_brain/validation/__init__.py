"""Knowledge Validation Pipeline — Cross-check brain knowledge against official sources.

Usage:
    # CLI
    PYTHONPATH=src python -m engineering_brain validate --all

    # Programmatic
    from engineering_brain.validation import validate_all, validate_node
    report = await validate_all(dry_run=True)
"""

from engineering_brain.validation.orchestrator import validate_all, validate_node

__all__ = ["validate_all", "validate_node"]
