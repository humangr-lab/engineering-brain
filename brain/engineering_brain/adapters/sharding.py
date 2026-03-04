"""Shard router for the Engineering Knowledge Brain.

Implements domain × layer partitioning for industrial-scale graph operations.
Routes queries to relevant shards and merges results transparently.

Sharding strategy:
- Graph: Separate FalkorDB graphs per domain (security, testing, ui, etc.)
- Vector: Separate Qdrant collections per layer (rules, patterns, evidence)
- Cache: Key prefix includes domain + technology + phase

At Tier 4, each shard can live on a separate instance. Currently all shards
are on the same FalkorDB/Qdrant instance — the routing logic is identical,
only the connection changes.
"""

from __future__ import annotations

import logging

from engineering_brain.core.schema import SHARD_DOMAINS, Layer, shard_key

logger = logging.getLogger(__name__)


class ShardRouter:
    """Routes queries to the correct graph/vector shards based on context."""

    def __init__(self, enabled: bool = True, max_parallel: int = 5) -> None:
        self._enabled = enabled
        self._max_parallel = max_parallel

    def route_query(
        self,
        domains: list[str],
        layers: list[Layer],
        technologies: list[str] | None = None,
    ) -> list[ShardTarget]:
        """Determine which shards to query based on context.

        Returns a list of ShardTarget objects, each specifying a
        graph shard and/or vector collection to query.
        """
        if not self._enabled:
            return [
                ShardTarget(
                    graph_shard="general",
                    vector_collections=["brain_rules", "brain_patterns"],
                    shard_key="general:all",
                )
            ]

        targets: list[ShardTarget] = []
        seen_keys: set[str] = set()

        resolved_domains = self._resolve_domains(domains)

        for domain in resolved_domains:
            for layer in layers:
                key = shard_key(domain, layer)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                target = ShardTarget(
                    graph_shard=domain,
                    vector_collections=self._collections_for_layer(layer),
                    shard_key=key,
                    domain=domain,
                    layer=layer,
                )
                targets.append(target)

                if len(targets) >= self._max_parallel:
                    break
            if len(targets) >= self._max_parallel:
                break

        if not targets:
            targets.append(
                ShardTarget(
                    graph_shard="general",
                    vector_collections=["brain_rules"],
                    shard_key="general:L3",
                    domain="general",
                    layer=Layer.L3_RULES,
                )
            )

        return targets

    def route_write(self, domain: str, layer: Layer) -> ShardTarget:
        """Determine which shard to write to for a given domain + layer."""
        d = domain.lower().strip()
        if d not in SHARD_DOMAINS:
            d = "general"
        return ShardTarget(
            graph_shard=d,
            vector_collections=self._collections_for_layer(layer),
            shard_key=shard_key(d, layer),
            domain=d,
            layer=layer,
        )

    def _resolve_domains(self, domains: list[str]) -> list[str]:
        """Resolve domain names to valid shard domains."""
        resolved = []
        for d in domains:
            dl = d.lower().strip()
            if dl in SHARD_DOMAINS:
                resolved.append(dl)
            else:
                # Try to map common aliases
                alias_map = {
                    "web": "api",
                    "frontend": "ui",
                    "backend": "api",
                    "infra": "devops",
                    "infrastructure": "devops",
                    "test": "testing",
                    "tests": "testing",
                    "sec": "security",
                    "auth": "security",
                    "perf": "performance",
                    "db": "database",
                    "data": "database",
                    "design": "architecture",
                    "arch": "architecture",
                }
                mapped = alias_map.get(dl, "general")
                if mapped not in resolved:
                    resolved.append(mapped)
        if not resolved:
            resolved.append("general")
        return resolved

    @staticmethod
    def _collections_for_layer(layer: Layer) -> list[str]:
        """Get Qdrant collection names for a given layer."""
        from engineering_brain.core.schema import VECTOR_COLLECTIONS

        coll = VECTOR_COLLECTIONS.get(layer.value)
        if coll:
            return [coll]
        # For layers without dedicated collections, query rules + patterns
        return ["brain_rules", "brain_patterns"]


class ShardTarget:
    """Describes a single shard target for a query or write operation."""

    __slots__ = ("graph_shard", "vector_collections", "shard_key", "domain", "layer")

    def __init__(
        self,
        graph_shard: str,
        vector_collections: list[str],
        shard_key: str,
        domain: str = "general",
        layer: Layer | None = None,
    ) -> None:
        self.graph_shard = graph_shard
        self.vector_collections = vector_collections
        self.shard_key = shard_key
        self.domain = domain
        self.layer = layer

    def __repr__(self) -> str:
        return f"ShardTarget(shard={self.graph_shard}, collections={self.vector_collections}, key={self.shard_key})"
