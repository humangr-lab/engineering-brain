"""Synonym dictionary for query expansion in the Engineering Knowledge Brain.

Maps ~60 common engineering terms to their synonyms/aliases. Applied
during context extraction to catch knowledge that uses alternate
terminology. Also supports graph-based expansion via 1-hop traversal.

Example:
    "CORS" → also search "cross-origin"
    "auth" → also search "authentication", "authorization"
    "XSS"  → also search "cross-site scripting"
"""

from __future__ import annotations

from typing import Any


# Curated synonym dictionary: canonical term → list of aliases
_SYNONYMS: dict[str, list[str]] = {
    # Security
    "cors": ["cross-origin", "cross origin resource sharing", "access-control-allow-origin"],
    "xss": ["cross-site scripting", "script injection", "html injection"],
    "csrf": ["cross-site request forgery", "xsrf", "session riding"],
    "auth": ["authentication", "authorization", "authn", "authz"],
    "jwt": ["json web token", "bearer token"],
    "oauth": ["oauth2", "open authorization"],
    "sql injection": ["sqli", "sql attack", "parameterized query"],
    "path traversal": ["directory traversal", "dot-dot-slash", "../"],
    "command injection": ["os command injection", "shell injection"],
    "ssrf": ["server-side request forgery"],
    "idor": ["insecure direct object reference"],
    # Architecture
    "dry": ["don't repeat yourself", "single source of truth", "deduplication"],
    "solid": ["single responsibility", "open closed", "liskov", "interface segregation", "dependency inversion"],
    "srp": ["single responsibility", "single responsibility principle"],
    "microservice": ["microservices", "service-oriented", "soa"],
    "monolith": ["monolithic", "single-deployment"],
    "cqrs": ["command query responsibility segregation"],
    "event sourcing": ["event-driven", "event store"],
    "saga": ["saga pattern", "distributed transaction"],
    # API
    "rest": ["restful", "rest api", "http api"],
    "graphql": ["gql", "graph query language"],
    "grpc": ["remote procedure call", "protobuf"],
    "websocket": ["ws", "web socket", "socketio", "socket.io", "real-time"],
    "idempotent": ["idempotency", "retry-safe"],
    # Database
    "orm": ["object-relational mapping", "sqlalchemy", "active record"],
    "nosql": ["document store", "key-value store", "non-relational"],
    "index": ["database index", "b-tree index", "composite index"],
    "migration": ["schema migration", "database migration", "alembic"],
    # DevOps
    "ci": ["continuous integration", "ci/cd", "build pipeline"],
    "cd": ["continuous deployment", "continuous delivery"],
    "container": ["docker container", "containerized", "oci"],
    "k8s": ["kubernetes", "kube"],
    "iac": ["infrastructure as code", "terraform", "pulumi"],
    # Performance
    "cache": ["caching", "memoize", "memoization", "lru"],
    "async": ["asynchronous", "non-blocking", "concurrent", "asyncio"],
    "lazy load": ["lazy loading", "deferred loading", "on-demand"],
    "rate limit": ["rate limiting", "throttle", "throttling", "backpressure"],
    # Testing
    "unit test": ["unittest", "unit testing", "isolated test"],
    "integration test": ["integration testing", "e2e", "end-to-end"],
    "mock": ["mocking", "stub", "fake", "test double"],
    "fixture": ["test fixture", "setup", "teardown"],
    "tdd": ["test-driven development", "test first"],
    # Observability
    "logging": ["log", "logger", "structured logging"],
    "tracing": ["distributed tracing", "trace", "opentelemetry", "otel"],
    "metrics": ["metric", "prometheus", "counter", "gauge", "histogram"],
    # Error Handling
    "error handling": ["exception handling", "error recovery", "fault tolerance"],
    "circuit breaker": ["circuit-breaker", "bulkhead", "resilience"],
    "retry": ["retrying", "backoff", "exponential backoff"],
    "fallback": ["graceful degradation", "default value", "failover"],
}

# Build reverse index for fast lookup
_REVERSE_INDEX: dict[str, str] = {}
for _canonical, _aliases in _SYNONYMS.items():
    for _alias in _aliases:
        _REVERSE_INDEX[_alias.lower()] = _canonical


def expand_query_terms(terms: list[str]) -> list[str]:
    """Expand query terms with synonyms. Additive — never removes terms.

    Args:
        terms: List of query terms (technologies, domains, keywords).

    Returns:
        Expanded list with synonyms appended.
    """
    expanded = list(terms)
    seen = {t.lower() for t in terms}

    for term in terms:
        term_lower = term.lower()

        # Forward lookup: canonical → aliases
        aliases = _SYNONYMS.get(term_lower, [])
        for alias in aliases:
            if alias.lower() not in seen:
                expanded.append(alias)
                seen.add(alias.lower())

        # Reverse lookup: alias → canonical
        canonical = _REVERSE_INDEX.get(term_lower)
        if canonical and canonical not in seen:
            expanded.append(canonical)
            seen.add(canonical)
            # Also add other aliases of the canonical
            for alias in _SYNONYMS.get(canonical, []):
                if alias.lower() not in seen:
                    expanded.append(alias)
                    seen.add(alias.lower())

    return expanded


def expand_from_graph(
    graph: Any,
    terms: list[str],
    max_hops: int = 1,
) -> list[str]:
    """Expand terms via 1-hop graph traversal (semantic neighbors).

    For each term, find matching technology/domain nodes and collect
    their neighbors' names as additional query terms.

    Args:
        graph: GraphAdapter instance.
        terms: List of terms to expand.
        max_hops: Maximum graph hops (default 1).

    Returns:
        Additional terms from graph neighbors.
    """
    if not graph or max_hops < 1:
        return []

    additional: list[str] = []
    seen = {t.lower() for t in terms}

    for term in terms:
        term_lower = term.lower()
        # Try to find as technology node
        tech_id = f"tech:{term_lower}"
        node = graph.get_node(tech_id)
        if not node:
            # Try domain node
            tech_id = f"domain:{term_lower}"
            node = graph.get_node(tech_id)
        if not node:
            continue

        # Get 1-hop neighbors
        try:
            edges = graph.get_edges(node_id=tech_id)
            for edge in edges:
                neighbor_id = edge["to_id"] if edge["from_id"] == tech_id else edge["from_id"]
                neighbor = graph.get_node(neighbor_id)
                if not neighbor:
                    continue
                name = (
                    neighbor.get("name", "")
                    or neighbor.get("text", "")
                    or ""
                ).strip()
                if name and name.lower() not in seen and len(name) < 50:
                    additional.append(name)
                    seen.add(name.lower())
        except Exception:
            pass

    return additional
