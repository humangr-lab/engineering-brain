"""Engineering Knowledge Brain — Industrial-scale knowledge graph for AI agents.

The Brain teaches agents to THINK, not memorize. Every piece of knowledge
carries WHY it matters and HOW to do it right.

Usage:
    from engineering_brain import Brain

    brain = Brain()          # In-memory by default
    brain.seed()             # Load built-in knowledge
    result = brain.query("Write Flask server with WebSocket")
    print(result.formatted_text)

    # Or with full infrastructure:
    brain = Brain(adapter="falkordb")  # FalkorDB + Qdrant + Redis
"""

from __future__ import annotations

from engineering_brain.core.brain import Brain
from engineering_brain.core.config import BrainConfig, get_brain_config
from engineering_brain.core.schema import EdgeType, Layer, NodeType
from engineering_brain.core.types import (
    Axiom,
    CodeExample,
    Domain,
    FileType,
    Finding,
    HumanLayer,
    KnowledgeQuery,
    KnowledgeResult,
    Pattern,
    Principle,
    Rule,
    SeedEntry,
    SeedFile,
    Source,
    SourceType,
    TaskContext,
    Technology,
    TestResult,
    ValidationStatus,
)

__all__ = [
    # Main entry point
    "Brain",
    # Configuration
    "BrainConfig",
    "get_brain_config",
    # Schema
    "Layer",
    "NodeType",
    "EdgeType",
    # Types — Knowledge nodes
    "Axiom",
    "Principle",
    "Pattern",
    "Rule",
    "Finding",
    "CodeExample",
    "TestResult",
    "TaskContext",
    # Types — Taxonomy
    "Technology",
    "FileType",
    "Domain",
    "HumanLayer",
    # Types — Query/Result
    "KnowledgeQuery",
    "KnowledgeResult",
    # Types — Seed
    "SeedEntry",
    "SeedFile",
    # Types — Source attribution
    "Source",
    "SourceType",
    "ValidationStatus",
]

__version__ = "1.0.0"
