"""Naive RAG baseline — embedding similarity only, no graph features.

Uses the same seed data as the Brain but retrieves only by basic graph query
with no multi-signal scoring, graph expansion, adaptive weights, or LLM enhancements.
"""

from __future__ import annotations

from .brain_system import BrainSystem

# Disable all advanced features — keep only basic graph query + embedding
_NAIVE_RAG_OVERRIDES = {
    "BRAIN_GRAPH_EXPANSION_ENABLED": "false",
    "BRAIN_QUERY_EXPANSION_ENABLED": "false",
    "BRAIN_RERANKER_ENABLED": "false",
    "BRAIN_ADAPTIVE_WEIGHTS": "false",
    "BRAIN_CROSS_LAYER_INFERENCE": "false",
    "BRAIN_LINK_PREDICTION": "false",
    "BRAIN_ONTOLOGY_ALIGNMENT": "false",
    "BRAIN_ADAPTIVE_PROMOTION": "false",
    "BRAIN_CODE_MINING": "false",
    "BRAIN_GUARDRAILS": "false",
    "BRAIN_LLM_CONTEXT_EXTRACTION": "false",
    "BRAIN_LLM_TASK_TAGGING": "false",
    "BRAIN_LLM_CRYSTALLIZATION": "false",
    "BRAIN_LLM_CODE_MINING_DESCRIPTION": "false",
    "BRAIN_LLM_PROACTIVE_PUSH": "false",
    "BRAIN_LLM_METACOGNITION": "false",
    "BRAIN_LLM_SYNONYMS": "false",
    "BRAIN_LLM_EPISTEMIC_SUGGESTION": "false",
    "BRAIN_LLM_PROMOTION_ASSESSMENT": "false",
    "BRAIN_LLM_KNOWLEDGE_ASSEMBLY": "false",
    "BRAIN_LLM_CONCEPT_NAMING": "false",
    "BRAIN_MAINTENANCE_ENABLED": "false",
    "BRAIN_CRYSTALLIZE_ENABLED": "false",
}


class NaiveRAGSystem(BrainSystem):
    """Embedding-only retrieval — no graph features, no scoring signals."""

    def __init__(self) -> None:
        super().__init__(config_overrides=_NAIVE_RAG_OVERRIDES)

    @property
    def name(self) -> str:
        return "Naive RAG"

    @property
    def description(self) -> str:
        return (
            "Embedding-based retrieval over the same knowledge base. "
            "No multi-signal scoring, graph expansion, adaptive weights, "
            "cross-layer inference, or LLM enhancements."
        )
