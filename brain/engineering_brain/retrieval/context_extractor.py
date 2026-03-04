"""Context extractor for the Engineering Knowledge Brain.

Parses a task description to extract technologies, domains, file types,
and phase — enabling targeted shard routing and relevant knowledge retrieval.

SCALABILITY: Technology detection is auto-built from loaded brain nodes
at runtime — adding new seed files automatically expands detection
without code changes. Hardcoded patterns are kept as a fast bootstrap
fallback for when the brain hasn't been loaded yet.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Auto-populated registry (filled by build_tech_index_from_nodes)
# ──────────────────────────────────────────────────────────────────────
_dynamic_tech_index: dict[str, str] = {}  # lowercase keyword → canonical name
_dynamic_domain_index: set[str] = set()  # all known domains


def build_tech_index_from_nodes(nodes: list[dict[str, Any]]) -> None:
    """Build technology detection index from all loaded brain nodes.

    Called once after brain.seed() — auto-discovers every technology
    and domain from the actual knowledge base. This makes detection
    scale infinitely: add a new seed file, and its technologies are
    automatically detectable.
    """
    global _dynamic_tech_index, _dynamic_domain_index

    techs: dict[str, str] = {}
    domains: set[str] = set()

    for node in nodes:
        # Extract technologies (with hierarchical path decomposition)
        for t in node.get("technologies") or node.get("languages") or []:
            canonical = str(t).strip()
            if not canonical or len(canonical) < 2:
                continue
            key = canonical.lower()
            # Store full dotted path as key → canonical mapping
            if key not in techs:
                techs[key] = canonical
            # For dotted paths, also register the LEAF and each SEGMENT as keys
            # "language.python.web.flask" → register "flask", "web.flask",
            # "python.web.flask" etc. all pointing to the full path.
            if "." in key:
                parts = key.split(".")
                # Leaf name (e.g., "flask")
                leaf = parts[-1]
                if leaf not in techs and len(leaf) >= 2:
                    techs[leaf] = canonical
                # Register suffixes: "web.flask", "python.web.flask"
                for i in range(1, len(parts)):
                    suffix = ".".join(parts[i:])
                    if suffix not in techs and len(suffix) >= 3:
                        techs[suffix] = canonical
                # Register meaningful individual segments (>= 3 chars, not
                # generic like "web", "core") — "redis", "flask", "pytest" etc.
                _GENERIC_SEGMENTS = {"web", "core", "orm", "api", "cli", "sdk", "lib"}
                for part in parts[1:]:  # skip first (usually "language"/"database")
                    if len(part) >= 3 and part not in _GENERIC_SEGMENTS and part not in techs:
                        techs[part] = canonical
            else:
                # Flat tag — common variations
                key_underscore = key.replace(" ", "_")
                if key_underscore != key and key_underscore not in techs:
                    techs[key_underscore] = canonical
                key_hyphen = key.replace(" ", "-")
                if key_hyphen != key and key_hyphen not in techs:
                    techs[key_hyphen] = canonical

        # Extract domains (with hierarchical path decomposition)
        for d in node.get("domains") or []:
            domain = str(d).strip().lower()
            if domain and len(domain) >= 2:
                domains.add(domain)
            # For dotted paths, also register leaf and intermediate segments
            if "." in domain:
                parts = domain.split(".")
                for i in range(len(parts)):
                    segment = ".".join(parts[i:])
                    if segment and len(segment) >= 2:
                        domains.add(segment)
                    # Also add individual parts if they're meaningful (>= 4 chars)
                    if len(parts[i]) >= 4:
                        domains.add(parts[i])

    _dynamic_tech_index = techs
    _dynamic_domain_index = domains


# ──────────────────────────────────────────────────────────────────────
# Hardcoded fallback patterns (used before brain is loaded)
# These are a minimal bootstrap set — the dynamic index supersedes them
# ──────────────────────────────────────────────────────────────────────
_FALLBACK_TECH_PATTERNS: dict[str, str] = {
    "flask": "Flask",
    "fastapi": "FastAPI",
    "django": "Django",
    "express": "Express",
    "react": "React",
    "vue": "Vue",
    "angular": "Angular",
    "nextjs": "Next.js",
    "typescript": "TypeScript",
    "python": "Python",
    "javascript": "JavaScript",
    "websocket": "WebSocket",
    "cors": "CORS",
    "redis": "Redis",
    "postgresql": "PostgreSQL",
    "mongodb": "MongoDB",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "aws": "AWS",
    "graphql": "GraphQL",
    "kafka": "Kafka",
    "terraform": "Terraform",
    "rust": "Rust",
    "golang": "Go",
    "solidity": "Solidity",
}

# Domain detection keywords (always active — complements dynamic index)
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "security": [
        "auth",
        "security",
        "cors",
        "csrf",
        "xss",
        "injection",
        "encrypt",
        "token",
        "password",
        "vulnerability",
        "owasp",
    ],
    "testing": [
        "test",
        "pytest",
        "mock",
        "fixture",
        "assertion",
        "coverage",
        "e2e",
        "integration test",
        "unit test",
    ],
    "api": [
        "endpoint",
        "route",
        "api",
        "rest",
        "graphql",
        "http",
        "middleware",
        "handler",
        "grpc",
        "webhook",
    ],
    "ui": [
        "button",
        "form",
        "modal",
        "css",
        "html",
        "dom",
        "component",
        "layout",
        "responsive",
        "accessibility",
        "aria",
    ],
    "architecture": [
        "pattern",
        "microservice",
        "event-driven",
        "cqrs",
        "ddd",
        "clean architecture",
        "hexagonal",
        "saga",
    ],
    "database": [
        "query",
        "schema",
        "migration",
        "orm",
        "sql",
        "transaction",
        "index",
        "sharding",
        "replication",
        "nosql",
    ],
    "performance": [
        "cache",
        "optimize",
        "latency",
        "throughput",
        "async",
        "concurrent",
        "parallel",
        "lazy load",
        "cdn",
    ],
    "devops": [
        "deploy",
        "ci",
        "cd",
        "docker",
        "kubernetes",
        "container",
        "monitoring",
        "terraform",
        "helm",
    ],
    "reliability": [
        "retry",
        "circuit breaker",
        "timeout",
        "fallback",
        "resilience",
        "health check",
        "backoff",
        "idempotent",
    ],
    "observability": [
        "trace",
        "metric",
        "opentelemetry",
        "prometheus",
        "grafana",
        "datadog",
        "dashboard",
        "apm",
    ],
    "data_engineering": [
        "etl",
        "streaming",
        "batch",
        "warehouse",
        "lake",
        "kafka",
        "spark",
        "flink",
        "airflow",
    ],
    "blockchain": [
        "smart contract",
        "solidity",
        "ethereum",
        "web3",
        "defi",
        "consensus",
        "validator",
        "wallet",
    ],
    "mobile": [
        "ios",
        "android",
        "react native",
        "flutter",
        "swift",
        "kotlin",
        "mobile",
        "push notification",
    ],
    "ai_ml": [
        "llm",
        "embedding",
        "rag",
        "fine-tune",
        "prompt",
        "vector",
        "inference",
        "training",
        "agent",
    ],
    "compliance": ["gdpr", "hipaa", "sox", "pci", "compliance", "audit", "regulation", "privacy"],
}

# Domain hierarchy (parent → children sub-domains for query expansion)
_DOMAIN_HIERARCHY: dict[str, list[str]] = {}


def build_domain_hierarchy() -> None:
    """Build parent->children domain mapping from keyword lists.

    Called after brain.seed() to enable query expansion:
    "security" -> also search for "cors", "auth", "csrf" etc.
    """
    global _DOMAIN_HIERARCHY
    _DOMAIN_HIERARCHY = {}
    for parent, keywords in _DOMAIN_KEYWORDS.items():
        # Sub-domains are keywords that are also top-level domain names
        # (e.g., "cors" under "security" if "cors" is also a domain key)
        # OR keywords long enough to be meaningful sub-concepts (>= 4 chars)
        # but NOT the parent domain itself
        children = [k for k in keywords if k != parent and (k in _DOMAIN_KEYWORDS or len(k) >= 5)]
        _DOMAIN_HIERARCHY[parent] = children


def expand_domains(domains: list[str]) -> list[str]:
    """Expand domain list with sub-domains from hierarchy.

    Additive only — never removes domains, only adds related ones.
    Used by router.py when query_expansion_enabled is True.
    """
    if not _DOMAIN_HIERARCHY:
        build_domain_hierarchy()
    expanded = list(domains)
    for domain in domains:
        children = _DOMAIN_HIERARCHY.get(domain.lower(), [])
        for child in children:
            if child not in expanded:
                expanded.append(child)
    return expanded


# ──────────────────────────────────────────────────────────────────────
# Technology Implication Graph (TIG) — Layer 2 of KTP
# Static mapping: technology → implied knowledge domains
# ──────────────────────────────────────────────────────────────────────

_TIG_DATA: dict[str, dict[str, list[str]]] | None = None  # Loaded once


def _load_tig() -> dict[str, dict[str, list[str]]]:
    """Load Technology Implication Graph from YAML (cached).

    Falls back to inline minimal set if file is missing.
    """
    global _TIG_DATA
    if _TIG_DATA is not None:
        return _TIG_DATA

    try:
        import os

        import yaml

        tig_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "technology_implications.yaml",
        )
        if os.path.isfile(tig_path):
            with open(tig_path) as f:
                _TIG_DATA = yaml.safe_load(f) or {}
            return _TIG_DATA
    except Exception as exc:
        logger.debug("Failed to load technology_implications.yaml: %s", exc)

    # Fallback: inline minimal TIG
    _TIG_DATA = {
        "flask": {
            "always": ["cors", "error_handling", "input_validation", "http_status_codes"],
            "if_routes": ["auth_middleware", "rate_limiting", "path_traversal"],
            "if_database": ["sql_injection", "orm_patterns"],
            "if_websocket": ["websocket_auth", "message_validation"],
        },
        "fastapi": {
            "always": ["cors", "input_validation", "pydantic_validation", "http_status_codes"],
            "if_routes": ["auth_middleware", "rate_limiting"],
        },
        "subprocess": {
            "always": ["command_injection", "path_sanitization", "timeout", "shell_false"],
        },
        "websocket": {
            "always": ["auth", "message_validation", "connection_lifecycle", "reconnection"],
        },
        "docker": {
            "always": ["non_root_user", "secrets_management", "health_checks"],
        },
    }
    return _TIG_DATA


# Condition keyword detection for TIG conditional implications
_CONDITION_KEYWORDS: dict[str, list[str]] = {
    "if_routes": ["route", "endpoint", "@app.", "blueprint", "router", "api"],
    "if_database": ["database", "db", "sql", "orm", "model", "query", "session", "migration"],
    "if_websocket": ["websocket", "socket", "ws://", "socketio", "emit"],
    "if_template": ["template", "render_template", "jinja", "html"],
    "if_forms": ["form", "input", "submit", "<form"],
    "if_api": ["fetch", "axios", "api", "endpoint", "http"],
    "if_compose": ["docker-compose", "compose", "services:"],
    "if_orm": ["sqlalchemy", "orm", "model", "session"],
}


def apply_technology_implications(
    technologies: list[str],
    text_lower: str,
) -> list[str]:
    """Apply TIG to expand detected technologies into implied domains.

    For each detected technology:
    1. Add 'always' domains unconditionally
    2. Check conditional keys (if_routes, if_database, etc.) against text
    3. Add conditional domains when context keywords are found

    Args:
        technologies: List of detected technology names (e.g. ["Flask", "WebSocket"])
        text_lower: Lowercased task description text for condition matching

    Returns:
        List of additional domain names to include in the knowledge query.
    """
    tig = _load_tig()
    if not tig:
        return []

    additional: list[str] = []
    seen: set[str] = set()

    for tech in technologies:
        key = tech.lower()
        entry = tig.get(key)
        if not entry:
            continue

        # Always-needed domains
        for domain in entry.get("always", []):
            if domain not in seen:
                seen.add(domain)
                additional.append(domain)

        # Conditional domains — check if condition keywords appear in text
        for condition_key, condition_keywords in _CONDITION_KEYWORDS.items():
            if condition_key not in entry:
                continue
            # Check if any condition keyword appears in text
            if any(kw in text_lower for kw in condition_keywords):
                for domain in entry[condition_key]:
                    if domain not in seen:
                        seen.add(domain)
                        additional.append(domain)

    return additional


# ──────────────────────────────────────────────────────────────────────
# AST-based context extraction — Layer 3 of KTP
# ──────────────────────────────────────────────────────────────────────

# Maps Python import names to knowledge areas (technologies + domains)
_IMPORT_KNOWLEDGE_MAP: dict[str, tuple[list[str], list[str]]] = {
    # (technologies, domains)
    "flask": (["Flask"], ["cors", "api", "security"]),
    "fastapi": (["FastAPI"], ["cors", "api", "security"]),
    "django": (["Django"], ["cors", "security", "orm_patterns"]),
    "express": (["Express"], ["cors", "api", "middleware"]),
    "subprocess": ([], ["command_injection", "security"]),
    "sqlite3": ([], ["sql_injection", "database"]),
    "sqlalchemy": (["SQLAlchemy"], ["orm_patterns", "database", "sql_injection"]),
    "redis": (["Redis"], ["caching", "connection_pooling"]),
    "flask_socketio": (["WebSocket"], ["websocket_auth", "connection_lifecycle"]),
    "socketio": (["WebSocket"], ["websocket_auth", "connection_lifecycle"]),
    "pathlib": ([], ["path_traversal"]),
    "os.path": ([], ["path_traversal"]),
    "os": ([], ["path_traversal", "security"]),
    "cryptography": ([], ["security", "encryption"]),
    "jwt": ([], ["security", "auth"]),
    "bcrypt": ([], ["security", "auth"]),
    "requests": ([], ["api", "error_handling"]),
    "httpx": ([], ["api", "error_handling"]),
    "aiohttp": ([], ["api", "error_handling", "async"]),
    "celery": ([], ["async", "reliability"]),
    "pydantic": (["Pydantic"], ["input_validation"]),
    "pytest": ([], ["testing"]),
    "docker": (["Docker"], ["devops", "secrets_management"]),
    "kubernetes": (["Kubernetes"], ["devops", "secrets_management"]),
    "boto3": (["AWS"], ["security", "devops"]),
    "psycopg2": (["PostgreSQL"], ["sql_injection", "database", "connection_pooling"]),
    "pymongo": (["MongoDB"], ["nosql_injection", "database"]),
    "kafka": (["Kafka"], ["data_engineering", "reliability"]),
}


def extract_ast_context(file_paths: list[str]) -> tuple[list[str], list[str]]:
    """Extract technologies and domains from Python file imports via AST.

    Parses Python files, extracts import statements, maps to knowledge
    areas via _IMPORT_KNOWLEDGE_MAP.

    Args:
        file_paths: List of Python file paths to analyze.

    Returns:
        (technologies, domains) tuple. Empty lists on failure (graceful degradation).
    """
    import ast as _ast
    import os as _os

    technologies: set[str] = set()
    domains: set[str] = set()

    for path in file_paths:
        if not _os.path.isfile(path):
            continue
        try:
            with open(path) as f:
                source = f.read()
            tree = _ast.parse(source)
        except Exception as exc:
            logger.debug("Failed to parse file %s for AST context: %s", path, exc)
            continue  # Graceful degradation on parse error

        for node in _ast.walk(tree):
            module_names: list[str] = []
            if isinstance(node, _ast.Import):
                module_names = [alias.name for alias in node.names if alias.name]
            elif isinstance(node, _ast.ImportFrom) and node.module:
                module_names = [node.module]

            for mod in module_names:
                # Check full module name and first segment
                for check in (mod, mod.split(".")[0]):
                    knowledge = _IMPORT_KNOWLEDGE_MAP.get(check)
                    if knowledge:
                        techs, doms = knowledge
                        technologies.update(techs)
                        domains.update(doms)
                        break

    return sorted(technologies), sorted(domains)


# ──────────────────────────────────────────────────────────────────────
# Knowledge Shopping List — structured output with provenance
# ──────────────────────────────────────────────────────────────────────


@dataclass
class KnowledgeShoppingList:
    """What knowledge a task needs, with provenance per item.

    Provenance values:
    - "explicit": from task description keywords or explicit tags
    - "tig": from Technology Implication Graph (Layer 2)
    - "tig:<tech>.<condition>": from conditional TIG match
    - "ast": from AST analysis of existing code (Layer 3)
    - "ast:<import_name>": from specific import detection
    """

    technologies: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)

    def merge(self, other: KnowledgeShoppingList) -> KnowledgeShoppingList:
        """Merge two shopping lists, preserving highest-priority provenance.

        Priority: explicit > tig > ast
        """
        priority = {"explicit": 0, "tig": 1, "ast": 2}
        merged_techs = list(self.technologies)
        merged_domains = list(self.domains)
        merged_prov = dict(self.provenance)

        for t in other.technologies:
            if t not in merged_techs:
                merged_techs.append(t)
        for d in other.domains:
            if d not in merged_domains:
                merged_domains.append(d)

        for key, source in other.provenance.items():
            if key not in merged_prov:
                merged_prov[key] = source
            else:
                # Keep higher priority (lower number)
                existing_base = merged_prov[key].split(":")[0]
                new_base = source.split(":")[0]
                if priority.get(new_base, 99) < priority.get(existing_base, 99):
                    merged_prov[key] = source

        return KnowledgeShoppingList(
            technologies=merged_techs,
            domains=merged_domains,
            provenance=merged_prov,
        )


# ──────────────────────────────────────────────────────────────────────
# Contextual node embedding — Layer 4 of KTP (Anthropic Contextual Retrieval)
# Prepends structural preamble to node text before embedding for -35% failure
# ──────────────────────────────────────────────────────────────────────

_LAYER_NAMES: dict[str, str] = {
    "L0": "Axiom (immutable truth)",
    "L1": "Principle (stable wisdom)",
    "L2": "Pattern (established practice)",
    "L3": "Rule (learned constraint)",
    "L4": "Evidence (observation)",
}


def build_contextual_text(node: dict[str, Any]) -> str:
    """Build contextually-enriched text for embedding a knowledge node.

    Prepends structural preamble (layer, domain, technologies, severity)
    to the node's primary text. This makes embeddings encode both the
    content AND the structural context — improving retrieval by ~35%
    (per Anthropic Contextual Retrieval research).

    Args:
        node: Knowledge node dict with id, text/name/statement, etc.

    Returns:
        Context-enriched text ready for embedding.
    """
    parts: list[str] = []

    # 1. Layer identification
    node_id = str(node.get("id", ""))
    layer = _infer_node_layer(node_id)
    layer_desc = _LAYER_NAMES.get(layer, "Knowledge")
    parts.append(f"[{layer_desc}]")

    # 2. Domain context
    domains = node.get("domains") or []
    if isinstance(domains, str):
        domains = [domains]
    if domains:
        parts.append(f"Domain: {', '.join(domains[:3])}")

    # 3. Technology context
    techs = node.get("technologies") or node.get("languages") or []
    if isinstance(techs, str):
        techs = [techs]
    if techs:
        parts.append(f"Tech: {', '.join(techs[:5])}")

    # 4. Severity (for rules/findings)
    severity = node.get("severity")
    if severity:
        parts.append(f"Severity: {severity}")

    # 5. Primary content
    text = (
        node.get("text", "")
        or node.get("statement", "")
        or node.get("name", "")
        or node.get("description", "")
    )
    if text:
        parts.append(text)

    # 6. WHY (the understanding — critical for rules)
    why = node.get("why", "")
    if why:
        parts.append(f"Why: {why}")

    return " | ".join(parts)


def _infer_node_layer(node_id: str) -> str:
    """Infer cortical layer from node ID prefix."""
    if node_id.startswith("AX-"):
        return "L0"
    if node_id.startswith("P-"):
        return "L1"
    if node_id.startswith(("PAT-", "CPAT-")):
        return "L2"
    if node_id.startswith(("CR-", "CR_")):
        return "L3"
    if node_id.startswith("F-"):
        return "L4"
    return "L3"  # Default


# File type detection
_FILE_TYPE_PATTERNS: dict[str, str] = {
    r"\.py\b": ".py",
    r"\.js\b": ".js",
    r"\.ts\b": ".ts",
    r"\.tsx\b": ".tsx",
    r"\.jsx\b": ".jsx",
    r"\.html\b": ".html",
    r"\.css\b": ".css",
    r"\.scss\b": ".scss",
    r"\.yaml\b": ".yaml",
    r"\.yml\b": ".yaml",
    r"\.json\b": ".json",
    r"\.sql\b": ".sql",
    r"\.go\b": ".go",
    r"\.rs\b": ".rs",
    r"\.java\b": ".java",
    r"\.kt\b": ".kt",
    r"\.swift\b": ".swift",
    r"\.sol\b": ".sol",
    r"\.dart\b": ".dart",
    r"\.rb\b": ".rb",
    r"\.cs\b": ".cs",
    r"\.tf\b": ".tf",
    r"\.proto\b": ".proto",
    r"\.graphql\b": ".graphql",
    r"\.wasm\b": ".wasm",
    r"dockerfile": "Dockerfile",
    r"\.toml\b": ".toml",
    r"python|\.py": ".py",
    r"javascript|\.js": ".js",
    r"typescript|\.ts": ".ts",
    r"golang|\.go": ".go",
    r"rust|\.rs": ".rs",
    r"kotlin|\.kt": ".kt",
    r"swift|\.swift": ".swift",
    r"solidity|\.sol": ".sol",
    r"ruby|\.rb": ".rb",
}

# Phase keywords
_PHASE_KEYWORDS: dict[str, list[str]] = {
    "spec": ["spec", "specification", "design", "plan", "architecture", "requirement"],
    "exec": ["implement", "write", "create", "build", "code", "develop", "add"],
    "qa": ["test", "validate", "verify", "review", "check", "audit", "qa"],
    "init": ["init", "setup", "configure", "initialize", "bootstrap"],
}


@dataclass
class ExtractedContext:
    """Extracted context from a task description."""

    technologies: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    facet_tags: dict[str, list[str]] = field(default_factory=dict)
    file_types: list[str] = field(default_factory=list)
    phase: str = "exec"
    raw_text: str = ""


def build_embedding_preamble(node: dict[str, Any]) -> str:
    """Build a structural context preamble for a knowledge node before embedding.

    Prepending layer/domain/technology context before the node text reduces
    retrieval failure by ~35% (Anthropic contextual retrieval research).
    """
    parts: list[str] = []
    # Layer identification
    nid = str(node.get("id", ""))
    if nid.startswith("AX-"):
        parts.append("[L0 Axiom]")
    elif nid.startswith("P-"):
        parts.append("[L1 Principle]")
    elif nid.startswith("PAT-") or nid.startswith("CPAT-"):
        parts.append("[L2 Pattern]")
    elif nid.startswith("CR-") or nid.startswith("F-"):
        parts.append("[L3 Rule]" if nid.startswith("CR-") else "[L4 Finding]")
    # Technologies
    techs = node.get("technologies") or node.get("languages") or []
    if techs:
        parts.append(f"Technologies: {', '.join(techs[:5])}")
    # Domains
    doms = node.get("domains") or []
    if doms:
        parts.append(f"Domains: {', '.join(doms[:5])}")
    # Severity
    sev = node.get("severity")
    if sev:
        parts.append(f"Severity: {sev}")
    return " | ".join(parts)


def contextual_text_for_embedding(node: dict[str, Any]) -> str:
    """Get the full text for embedding, with structural context preamble.

    Format: "[Layer] Technologies: X | Domains: Y --- <node text>"
    """
    preamble = build_embedding_preamble(node)
    text = node.get("text") or node.get("name") or node.get("statement", "")
    why = node.get("why", "")
    body = f"{text} {why}".strip() if why else str(text)
    if preamble:
        return f"{preamble} --- {body}"
    return body


def _llm_extract_context(task_description: str) -> dict | None:
    """LLM-enhanced context extraction. Returns None on failure."""
    from engineering_brain.llm_helpers import brain_llm_call_json, is_llm_enabled

    if not is_llm_enabled("BRAIN_LLM_CONTEXT_EXTRACTION"):
        return None
    system = (
        "Extract structured context from an engineering task description. "
        'Return ONLY JSON: {"technologies": ["Flask"], "domains": ["security"], '
        '"file_type": ".py", "phase": "exec"}. '
        "domains from: security, api, database, testing, performance, architecture, "
        "devops, ui, general. Be precise — only include clearly mentioned or implied items."
    )
    return brain_llm_call_json(system, f"Task: {task_description[:1000]}", max_tokens=200)


def extract_context(
    task_description: str,
    technologies: list[str] | None = None,
    file_type: str = "",
    phase: str = "",
    domains: list[str] | None = None,
) -> ExtractedContext:
    """Extract technology, domain, file type, and phase from task description.

    Uses dynamic index (auto-built from brain nodes) when available,
    falls back to hardcoded patterns when brain hasn't been loaded.
    Explicit parameters always take precedence over auto-detection.
    """
    text_lower = task_description.lower()
    ctx = ExtractedContext(raw_text=task_description)

    # --- Technologies ---
    # Use dynamic index if available, fallback to hardcoded
    tech_index = _dynamic_tech_index if _dynamic_tech_index else _FALLBACK_TECH_PATTERNS
    detected_techs: set[str] = set()

    # Word-boundary-aware matching for short keywords (avoid false positives)
    # e.g., "go" shouldn't match "google" or "going"
    short_keywords = {k for k in tech_index if len(k) <= 3}
    long_keywords = {k for k in tech_index if len(k) > 3}

    # Long keywords: simple substring match (fast, low false positive rate)
    for keyword in long_keywords:
        if keyword in text_lower:
            detected_techs.add(tech_index[keyword])

    # Short keywords: word boundary match (prevents false positives)
    for keyword in short_keywords:
        if re.search(rf"\b{re.escape(keyword)}\b", text_lower):
            detected_techs.add(tech_index[keyword])

    if technologies:
        for t in technologies:
            detected_techs.add(t)
    ctx.technologies = sorted(detected_techs)

    # --- Domains ---
    detected_domains: set[str] = set()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score >= 1:
            detected_domains.add(domain)
    # Also add any domains from the dynamic index that appear in text
    for domain in _dynamic_domain_index:
        if domain in text_lower:
            detected_domains.add(domain)
    if domains:
        for d in domains:
            detected_domains.add(d.lower())
    if not detected_domains:
        detected_domains.add("general")
    ctx.domains = sorted(detected_domains)

    # --- File types ---
    detected_types: set[str] = set()
    for pattern, ext in _FILE_TYPE_PATTERNS.items():
        if re.search(pattern, text_lower):
            detected_types.add(ext)
    if file_type:
        ft = file_type if file_type.startswith(".") else f".{file_type}"
        detected_types.add(ft)
    ctx.file_types = sorted(detected_types)

    # --- Phase ---
    if phase:
        ctx.phase = phase
    else:
        phase_scores: dict[str, int] = {}
        for p, keywords in _PHASE_KEYWORDS.items():
            phase_scores[p] = sum(1 for kw in keywords if kw in text_lower)
        if phase_scores:
            best_phase = max(phase_scores, key=lambda p: phase_scores[p])
            if phase_scores[best_phase] > 0:
                ctx.phase = best_phase

    # --- Facet tags (from TagRegistry, graceful fallback) ---
    try:
        from engineering_brain.core.taxonomy import get_registry

        registry = get_registry()
        if registry.size > 0:
            for t in ctx.technologies:
                decomposed = registry.decompose_dotted_path(t)
                for facet, ids in decomposed.items():
                    ctx.facet_tags.setdefault(facet, []).extend(ids)
            for d in ctx.domains:
                decomposed = registry.decompose_dotted_path(d)
                for facet, ids in decomposed.items():
                    ctx.facet_tags.setdefault(facet, []).extend(ids)
            ctx.facet_tags = {f: list(dict.fromkeys(ids)) for f, ids in ctx.facet_tags.items()}
    except Exception as exc:
        logger.debug("Facet tag enrichment failed: %s", exc)

    # LLM augmentation (merges with keyword results, never replaces)
    llm_ctx = _llm_extract_context(task_description)
    if llm_ctx:
        for t in llm_ctx.get("technologies") or []:
            if isinstance(t, str) and t and t.lower() not in {x.lower() for x in ctx.technologies}:
                ctx.technologies.append(t)
        for d in llm_ctx.get("domains") or []:
            if isinstance(d, str) and d.lower() not in {x.lower() for x in ctx.domains}:
                ctx.domains.append(d.lower())

    return ctx
