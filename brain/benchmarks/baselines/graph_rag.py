"""GraphRAG baseline — graph traversal + embedding, minimal scoring.

Uses the same seed data and enables graph expansion and embedding, but
disables adaptive scoring, LLM enhancements, and advanced features.
"""

from __future__ import annotations

from .brain_system import BrainSystem

_GRAPH_RAG_OVERRIDES = {
    # Keep graph + embedding
    "BRAIN_GRAPH_EXPANSION_ENABLED": "true",
    "BRAIN_EMBEDDING_ENABLED": "true",
    # Disable advanced scoring and intelligence
    "BRAIN_ADAPTIVE_WEIGHTS": "false",
    "BRAIN_CROSS_LAYER_INFERENCE": "false",
    "BRAIN_LINK_PREDICTION": "false",
    "BRAIN_ONTOLOGY_ALIGNMENT": "false",
    "BRAIN_ADAPTIVE_PROMOTION": "false",
    "BRAIN_CODE_MINING": "false",
    "BRAIN_GUARDRAILS": "false",
    "BRAIN_RERANKER_ENABLED": "false",
    "BRAIN_QUERY_EXPANSION_ENABLED": "false",
    # Disable all LLM enhancements
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


class GraphRAGSystem(BrainSystem):
    """Graph-structured RAG — graph traversal + embedding, no advanced scoring."""

    def __init__(self) -> None:
        super().__init__(config_overrides=_GRAPH_RAG_OVERRIDES)

    @property
    def name(self) -> str:
        return "GraphRAG"

    @property
    def description(self) -> str:
        return (
            "Graph-structured retrieval with embedding similarity and multi-hop "
            "graph expansion. No adaptive scoring, LLM enhancements, or advanced "
            "features like cross-layer inference or ontology alignment."
        )
