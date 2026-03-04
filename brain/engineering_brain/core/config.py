"""Configuration for the Engineering Knowledge Brain.

All settings use lazy environment variable loading — no module-level side effects.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _env_float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


def _env_bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


@dataclass
class BrainConfig:
    """Central configuration for the Engineering Brain."""

    # --- Feature flags ---
    enabled: bool = field(default_factory=lambda: _env_bool("ENGINEERING_BRAIN_ENABLED", True))
    adapter: str = field(default_factory=lambda: _env("BRAIN_ADAPTER", "memory"))

    # --- FalkorDB ---
    falkordb_host: str = field(default_factory=lambda: _env("BRAIN_FALKORDB_HOST", "localhost"))
    falkordb_port: int = field(default_factory=lambda: _env_int("BRAIN_FALKORDB_PORT", 6380))
    falkordb_database: str = field(
        default_factory=lambda: _env("BRAIN_FALKORDB_DATABASE", "engineering_brain")
    )

    # --- Neo4j ---
    neo4j_uri: str = field(default_factory=lambda: _env("BRAIN_NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: _env("BRAIN_NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: _env("BRAIN_NEO4J_PASSWORD", ""))
    neo4j_database: str = field(default_factory=lambda: _env("BRAIN_NEO4J_DATABASE", "neo4j"))

    # --- Qdrant ---
    qdrant_host: str = field(default_factory=lambda: _env("BRAIN_QDRANT_HOST", "localhost"))
    qdrant_port: int = field(default_factory=lambda: _env_int("BRAIN_QDRANT_PORT", 6333))
    qdrant_collection_prefix: str = field(
        default_factory=lambda: _env("BRAIN_QDRANT_PREFIX", "brain_")
    )
    embedding_dimension: int = field(default_factory=lambda: _env_int("BRAIN_EMBEDDING_DIM", 1024))

    # --- Redis (L2 cache) ---
    redis_host: str = field(default_factory=lambda: _env("BRAIN_REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: _env_int("BRAIN_REDIS_PORT", 6379))
    redis_db: int = field(default_factory=lambda: _env_int("BRAIN_REDIS_DB", 3))
    redis_cache_ttl: int = field(default_factory=lambda: _env_int("BRAIN_REDIS_CACHE_TTL", 300))
    redis_max_entries: int = field(
        default_factory=lambda: _env_int("BRAIN_REDIS_MAX_ENTRIES", 10000)
    )

    # --- Memory cache (L1) ---
    memory_cache_size: int = field(
        default_factory=lambda: _env_int("BRAIN_MEMORY_CACHE_SIZE", 1000)
    )
    memory_cache_ttl: int = field(default_factory=lambda: _env_int("BRAIN_MEMORY_CACHE_TTL", 60))

    # --- Retrieval ---
    context_budget_chars: int = field(
        default_factory=lambda: _env_int("BRAIN_CONTEXT_BUDGET", 50000)
    )
    enhanced_context_budget_chars: int = field(
        default_factory=lambda: _env_int("BRAIN_ENHANCED_BUDGET", 80000)
    )
    top_k_principles: int = field(default_factory=lambda: _env_int("BRAIN_TOP_K_L1", 5))
    top_k_patterns: int = field(default_factory=lambda: _env_int("BRAIN_TOP_K_L2", 8))
    top_k_rules: int = field(default_factory=lambda: _env_int("BRAIN_TOP_K_L3", 20))
    top_k_evidence: int = field(default_factory=lambda: _env_int("BRAIN_TOP_K_L4", 3))

    # --- Scoring weights (6 signals, sum = 1.0) ---
    weight_tech_match: float = field(default_factory=lambda: _env_float("BRAIN_W_TECH", 0.28))
    weight_domain_match: float = field(default_factory=lambda: _env_float("BRAIN_W_DOMAIN", 0.18))
    weight_severity: float = field(default_factory=lambda: _env_float("BRAIN_W_SEVERITY", 0.18))
    weight_reinforcement: float = field(
        default_factory=lambda: _env_float("BRAIN_W_REINFORCE", 0.13)
    )
    weight_recency: float = field(default_factory=lambda: _env_float("BRAIN_W_RECENCY", 0.13))
    weight_confidence: float = field(default_factory=lambda: _env_float("BRAIN_W_CONFIDENCE", 0.10))

    # --- Learning ---
    promote_l4_to_l3_threshold: int = field(
        default_factory=lambda: _env_int("BRAIN_PROMOTE_L4_L3", 5)
    )
    promote_l3_to_l2_threshold: int = field(
        default_factory=lambda: _env_int("BRAIN_PROMOTE_L3_L2", 20)
    )
    prune_after_days: int = field(default_factory=lambda: _env_int("BRAIN_PRUNE_DAYS", 60))
    prune_min_reinforcements: int = field(
        default_factory=lambda: _env_int("BRAIN_PRUNE_MIN_REINFORCE", 0)
    )

    # --- Sharding ---
    sharding_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_SHARDING_ENABLED", True)
    )
    max_parallel_shard_queries: int = field(
        default_factory=lambda: _env_int("BRAIN_MAX_SHARD_QUERIES", 5)
    )

    # --- Validation ---
    validation_cache_dir: str = field(
        default_factory=lambda: _env(
            "BRAIN_VALIDATION_CACHE_DIR",
            os.path.join(os.path.expanduser("~"), ".engineering_brain"),
        )
    )
    validation_cache_ttl_days: int = field(
        default_factory=lambda: _env_int("BRAIN_VALIDATION_CACHE_TTL_DAYS", 30)
    )
    so_api_key: str = field(default_factory=lambda: _env("STACKOVERFLOW_API_KEY", ""))
    nvd_api_key: str = field(default_factory=lambda: _env("NVD_API_KEY", ""))
    github_token: str = field(default_factory=lambda: _env("GITHUB_TOKEN", ""))
    validation_rate_pypi: float = field(
        default_factory=lambda: _env_float("VALIDATION_RATE_LIMIT_PYPI", 1.0)
    )
    validation_rate_npm: float = field(
        default_factory=lambda: _env_float("VALIDATION_RATE_LIMIT_NPM", 1.0)
    )
    validation_rate_so: float = field(
        default_factory=lambda: _env_float("VALIDATION_RATE_LIMIT_SO", 0.5)
    )
    validation_rate_nvd: float = field(
        default_factory=lambda: _env_float("VALIDATION_RATE_LIMIT_NVD", 0.15)
    )

    # --- Observation log ---
    observation_log_path: str = field(
        default_factory=lambda: _env(
            "BRAIN_OBSERVATION_LOG",
            os.path.join(os.path.expanduser("~"), ".engineering_brain", "observations.jsonl"),
        )
    )
    observation_log_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_OBSERVATION_LOG_ENABLED", True)
    )

    # --- Cluster crystallization ---
    crystallize_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_CRYSTALLIZE_ENABLED", True)
    )
    crystallize_min_similarity: float = field(
        default_factory=lambda: _env_float("BRAIN_CRYSTALLIZE_MIN_SIM", 0.35)
    )
    crystallize_min_cluster_size: int = field(
        default_factory=lambda: _env_int("BRAIN_CRYSTALLIZE_MIN_CLUSTER", 3)
    )
    crystallize_min_reinforcements: int = field(
        default_factory=lambda: _env_int("BRAIN_CRYSTALLIZE_MIN_REINFORCE", 5)
    )
    crystallize_min_confidence: float = field(
        default_factory=lambda: _env_float("BRAIN_CRYSTALLIZE_MIN_CONF", 0.5)
    )

    # --- Embedding & vector search ---
    embedding_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_EMBEDDING_ENABLED", True)
    )
    embedding_batch_size: int = field(
        default_factory=lambda: _env_int("BRAIN_EMBEDDING_BATCH_SIZE", 50)
    )
    vector_score_weight: float = field(
        default_factory=lambda: _env_float("BRAIN_VECTOR_SCORE_WEIGHT", 0.15)
    )

    # --- Multi-hop graph expansion ---
    graph_expansion_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_GRAPH_EXPANSION_ENABLED", True)
    )
    graph_expansion_max_expand: int = field(
        default_factory=lambda: _env_int("BRAIN_GRAPH_EXPANSION_MAX_EXPAND", 5)
    )
    graph_expansion_max_hops: int = field(
        default_factory=lambda: _env_int("BRAIN_GRAPH_EXPANSION_HOPS", 1)
    )
    graph_expansion_discount: float = field(
        default_factory=lambda: _env_float("BRAIN_GRAPH_EXPANSION_DISCOUNT", 0.4)
    )

    # --- Query expansion ---
    query_expansion_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_QUERY_EXPANSION_ENABLED", True)
    )

    # --- Cross-encoder reranking (optional, improves precision) ---
    reranker_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_RERANKER_ENABLED", False)
    )

    # --- LLM concept naming ---
    llm_concept_naming_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_LLM_CONCEPT_NAMING", True)
    )

    # --- LLM model for brain module enhancements ---
    llm_model: str = field(
        default_factory=lambda: _env("BRAIN_LLM_MODEL", "claude-sonnet-4-20250514")
    )

    # --- LLM enhancements (all default ON, opt-out per module) ---
    llm_context_extraction: bool = field(
        default_factory=lambda: _env_bool("BRAIN_LLM_CONTEXT_EXTRACTION", True)
    )
    llm_task_tagging: bool = field(
        default_factory=lambda: _env_bool("BRAIN_LLM_TASK_TAGGING", True)
    )
    llm_crystallization: bool = field(
        default_factory=lambda: _env_bool("BRAIN_LLM_CRYSTALLIZATION", True)
    )
    llm_code_mining_description: bool = field(
        default_factory=lambda: _env_bool("BRAIN_LLM_CODE_MINING_DESCRIPTION", True)
    )
    llm_proactive_push: bool = field(
        default_factory=lambda: _env_bool("BRAIN_LLM_PROACTIVE_PUSH", True)
    )
    llm_metacognition: bool = field(
        default_factory=lambda: _env_bool("BRAIN_LLM_METACOGNITION", True)
    )
    llm_synonyms: bool = field(default_factory=lambda: _env_bool("BRAIN_LLM_SYNONYMS", True))
    llm_epistemic_suggestion: bool = field(
        default_factory=lambda: _env_bool("BRAIN_LLM_EPISTEMIC_SUGGESTION", True)
    )
    llm_promotion_assessment: bool = field(
        default_factory=lambda: _env_bool("BRAIN_LLM_PROMOTION_ASSESSMENT", True)
    )

    # --- LLM knowledge assembly (curated packs per query) ---
    llm_knowledge_assembly: bool = field(
        default_factory=lambda: _env_bool("BRAIN_LLM_KNOWLEDGE_ASSEMBLY", True)
    )

    # --- Agent guardrails (obligation derivation + applicability checking) ---
    guardrails_enabled: bool = field(default_factory=lambda: _env_bool("BRAIN_GUARDRAILS", True))

    # --- Brain maintenance (post-run crystallize/promote/prune) ---
    maintenance_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_MAINTENANCE_ENABLED", True)
    )
    maintenance_crystallize: bool = field(
        default_factory=lambda: _env_bool("BRAIN_MAINTENANCE_CRYSTALLIZE", True)
    )
    maintenance_promote: bool = field(
        default_factory=lambda: _env_bool("BRAIN_MAINTENANCE_PROMOTE", True)
    )
    maintenance_prune: bool = field(
        default_factory=lambda: _env_bool("BRAIN_MAINTENANCE_PRUNE", True)
    )

    # --- Scaling ---
    batch_write_size: int = field(default_factory=lambda: _env_int("BRAIN_BATCH_WRITE_SIZE", 100))
    query_timeout_ms: int = field(default_factory=lambda: _env_int("BRAIN_QUERY_TIMEOUT_MS", 5000))
    # Hawkes process: exponential decay rate λ for temporal recency scoring.
    # Score contribution decays as exp(-λ * Δt_days). 0.001 ≈ half-life ~693 days.
    hawkes_decay_rate: float = field(
        default_factory=lambda: _env_float("BRAIN_HAWKES_DECAY", 0.001)
    )
    similarity_threshold: float = field(
        default_factory=lambda: _env_float("BRAIN_SIMILARITY_THRESHOLD", 0.35)
    )
    min_cluster_size: int = field(default_factory=lambda: _env_int("BRAIN_MIN_CLUSTER_SIZE", 3))
    confidence_update_factor: float = field(
        default_factory=lambda: _env_float("BRAIN_CONFIDENCE_UPDATE", 0.1)
    )

    # --- ERG Reasoning ---
    reasoning_max_chains: int = field(
        default_factory=lambda: _env_int("BRAIN_REASONING_MAX_CHAINS", 3)
    )
    reasoning_max_steps_per_chain: int = field(
        default_factory=lambda: _env_int("BRAIN_REASONING_MAX_STEPS", 5)
    )
    reasoning_max_nodes_per_step: int = field(
        default_factory=lambda: _env_int("BRAIN_REASONING_MAX_NODES_STEP", 8)
    )

    # --- Taxonomy auto-expansion (Tier 2) ---
    auto_expand_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_AUTO_EXPAND_ENABLED", False)
    )
    auto_expand_similarity_threshold: float = field(
        default_factory=lambda: _env_float("BRAIN_AUTO_EXPAND_SIM", 0.75)
    )
    auto_expand_min_confidence: float = field(
        default_factory=lambda: _env_float("BRAIN_AUTO_EXPAND_CONF", 0.80)
    )

    # --- Taxonomy HAKE + relationship learning (Tier 3) ---
    hake_enabled: bool = field(default_factory=lambda: _env_bool("BRAIN_HAKE_ENABLED", False))
    relationship_learning_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_RELATIONSHIP_LEARNING", False)
    )

    # --- Graph improvement gaps ---
    # Gap 1: Cross-layer edge inference via embeddings (ON — runs in background thread)
    cross_layer_inference_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_CROSS_LAYER_INFERENCE", True)
    )
    cross_layer_similarity_threshold: float = field(
        default_factory=lambda: _env_float("BRAIN_CROSS_LAYER_SIM", 0.40)
    )
    # Gap 3: Code pattern mining from AST (ON — on-demand, requires explicit codebase path)
    code_mining_enabled: bool = field(default_factory=lambda: _env_bool("BRAIN_CODE_MINING", True))
    # Gap 4: Adaptive scoring weights via Thompson Sampling (ON — safe cold start with default priors)
    adaptive_weights_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_ADAPTIVE_WEIGHTS", True)
    )
    # Gap 5: Link prediction (HAKE + type constraints) (ON — runs in background thread)
    link_prediction_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_LINK_PREDICTION", True)
    )
    link_prediction_threshold: float = field(
        default_factory=lambda: _env_float("BRAIN_LINK_PRED_THRESHOLD", 0.45)
    )
    # Gap 6: Ontology alignment via SKOS (ON — on-demand, uses SKOS alignment data)
    ontology_alignment_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_ONTOLOGY_ALIGNMENT", True)
    )
    # Gap 7: Adaptive promotion thresholds via Bayesian Beta priors (ON — safe cold start with Jeffreys prior)
    adaptive_promotion_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_ADAPTIVE_PROMOTION", True)
    )

    # --- SOTA Scoring: cosine normalization + per-layer thresholds ---
    # Cross-layer per-transition thresholds (used when BRAIN_CROSS_LAYER_SIM env not explicitly set)
    cross_layer_grounds_threshold: float = field(
        default_factory=lambda: _env_float("BRAIN_CROSS_LAYER_GROUNDS_THRESH", 0.35)
    )
    cross_layer_informs_threshold: float = field(
        default_factory=lambda: _env_float("BRAIN_CROSS_LAYER_INFORMS_THRESH", 0.35)
    )
    cross_layer_instantiates_threshold: float = field(
        default_factory=lambda: _env_float("BRAIN_CROSS_LAYER_INSTANTIATES_THRESH", 0.40)
    )
    # Top-K per transition (rank-based selection, 0 = threshold-only)
    cross_layer_top_k_per_transition: int = field(
        default_factory=lambda: _env_int("BRAIN_CROSS_LAYER_TOP_K", 50)
    )
    # Cosine normalization parameters (empirical bounds for bge embeddings)
    cross_layer_cosine_floor: float = field(
        default_factory=lambda: _env_float("BRAIN_CROSS_LAYER_COS_FLOOR", 0.25)
    )
    cross_layer_cosine_min: float = field(
        default_factory=lambda: _env_float("BRAIN_CROSS_LAYER_COS_MIN", 0.25)
    )
    cross_layer_cosine_max: float = field(
        default_factory=lambda: _env_float("BRAIN_CROSS_LAYER_COS_MAX", 0.80)
    )
    # Link prediction scoring
    link_prediction_cosine_floor: float = field(
        default_factory=lambda: _env_float("BRAIN_LINK_PRED_COS_FLOOR", 0.20)
    )
    link_prediction_cosine_min: float = field(
        default_factory=lambda: _env_float("BRAIN_LINK_PRED_COS_MIN", 0.20)
    )
    link_prediction_cosine_max: float = field(
        default_factory=lambda: _env_float("BRAIN_LINK_PRED_COS_MAX", 0.85)
    )
    link_prediction_top_k_per_type: int = field(
        default_factory=lambda: _env_int("BRAIN_LINK_PRED_TOP_K_TYPE", 20)
    )

    # --- Wave 1: Epistemic SOTA (all default OFF, opt-in) ---
    # 1A: Epistemic status ladder (E0-E5 classification)
    epistemic_ladder_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_EPISTEMIC_LADDER", False)
    )
    # 1B: Bayesian edge weights (Beta distribution learning)
    bayesian_edges_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_BAYESIAN_EDGES", False)
    )
    # 1C: Predictive decay (staleness forecasting)
    predictive_decay_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_PREDICTIVE_DECAY", False)
    )
    # 1D: Contradiction tensor (first-class contradiction entities)
    contradiction_tensor_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_CONTRADICTION_TENSOR", False)
    )
    # 1E: DST evidence combiner (adaptive fusion strategy)
    dst_evidence_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAIN_DST_EVIDENCE", False)
    )

    # --- Agent system (BYOK Opus reasoning over brain knowledge) ---
    agent_enabled: bool = field(default_factory=lambda: _env_bool("BRAIN_AGENT_ENABLED", False))
    agent_api_key: str = field(default_factory=lambda: _env("BRAIN_AGENT_API_KEY", ""))
    agent_model: str = field(
        default_factory=lambda: _env("BRAIN_AGENT_MODEL", "claude-opus-4-20250514")
    )
    agent_orchestrator_model: str = field(
        default_factory=lambda: _env("BRAIN_AGENT_ORCHESTRATOR_MODEL", "claude-opus-4-20250514")
    )
    agent_max_workers: int = field(default_factory=lambda: _env_int("BRAIN_AGENT_MAX_WORKERS", 3))
    agent_max_tokens: int = field(default_factory=lambda: _env_int("BRAIN_AGENT_MAX_TOKENS", 4096))
    agent_timeout: int = field(default_factory=lambda: _env_int("BRAIN_AGENT_TIMEOUT", 60))
    agent_cards_dir: str = field(default_factory=lambda: _env("BRAIN_AGENT_CARDS_DIR", ""))

    # --- Pack Manager v2 (O(log N) scalable retrieval) ---
    pack_v2_enabled: bool = field(default_factory=lambda: _env_bool("BRAIN_PACK_V2_ENABLED", False))
    pack_v2_vector_top_k: int = field(
        default_factory=lambda: _env_int("BRAIN_PACK_V2_VECTOR_TOP_K", 50)
    )
    pack_v2_max_sub_queries: int = field(
        default_factory=lambda: _env_int("BRAIN_PACK_V2_MAX_SUB_QUERIES", 5)
    )
    pack_v2_graph_filter_limit: int = field(
        default_factory=lambda: _env_int("BRAIN_PACK_V2_GRAPH_FILTER_LIMIT", 30)
    )

    # --- Pack Factory ---
    pack_templates_directory: str = field(
        default_factory=lambda: _env(
            "BRAIN_PACK_TEMPLATES_DIR",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "pack_templates"),
        )
    )
    pack_export_format: str = field(
        default_factory=lambda: _env("BRAIN_PACK_EXPORT_FORMAT", "directory")
    )

    # --- Seeds ---
    seeds_directory: str = field(
        default_factory=lambda: _env(
            "BRAIN_SEEDS_DIR",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "seeds"),
        )
    )


def get_brain_config() -> BrainConfig:
    """Get brain configuration (creates fresh instance reading current env)."""
    return BrainConfig()
