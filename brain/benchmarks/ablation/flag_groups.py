"""Logical groupings for feature flags."""

from __future__ import annotations

FLAG_GROUPS: dict[str, list[str]] = {
    "retrieval": [
        "embedding_enabled",
        "graph_expansion_enabled",
        "query_expansion_enabled",
        "reranker_enabled",
        "sharding_enabled",
    ],
    "gaps": [
        "cross_layer_inference_enabled",
        "code_mining_enabled",
        "adaptive_weights_enabled",
        "link_prediction_enabled",
        "ontology_alignment_enabled",
        "adaptive_promotion_enabled",
    ],
    "epistemic": [
        "epistemic_ladder_enabled",
        "bayesian_edges_enabled",
        "predictive_decay_enabled",
        "contradiction_tensor_enabled",
        "dst_evidence_enabled",
    ],
    "llm": [
        "llm_context_extraction",
        "llm_task_tagging",
        "llm_crystallization",
        "llm_code_mining_description",
        "llm_proactive_push",
        "llm_metacognition",
        "llm_synonyms",
        "llm_epistemic_suggestion",
        "llm_promotion_assessment",
        "llm_knowledge_assembly",
        "llm_concept_naming_enabled",
    ],
    "maintenance": [
        "maintenance_enabled",
        "maintenance_crystallize",
        "maintenance_promote",
        "maintenance_prune",
    ],
    "other": [
        "enabled",
        "guardrails_enabled",
        "crystallize_enabled",
        "observation_log_enabled",
        "auto_expand_enabled",
        "hake_enabled",
        "relationship_learning_enabled",
        "agent_enabled",
        "pack_v2_enabled",
    ],
}

# Reverse lookup: field_name -> group
_FIELD_TO_GROUP: dict[str, str] = {}
for group, fields in FLAG_GROUPS.items():
    for field_name in fields:
        _FIELD_TO_GROUP[field_name] = group


def get_flag_group(field_name: str) -> str:
    """Return the logical group for a flag field name."""
    return _FIELD_TO_GROUP.get(field_name, "other")


def get_group_flags(group: str) -> list[str]:
    """Return all flag field names in a group."""
    return FLAG_GROUPS.get(group, [])
