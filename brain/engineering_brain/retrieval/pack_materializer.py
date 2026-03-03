"""PackMaterializer — transforms template + params into a MaterializedPack.

Thin layer over PackManager v1/v2 that translates template specs into
create_pack() calls + post-processing (severity filter, confidence filter,
full node hydration, edge collection).

Usage:
    materializer = PackMaterializer(graph, vector, config, query_router, embedder)
    pack = materializer.materialize(template, technologies=["flask"])
    composed = materializer.compose([pack1, pack2])
"""

from __future__ import annotations

import fnmatch
import logging
import time
from typing import Any

from engineering_brain.adapters.base import GraphAdapter, VectorAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.types import MaterializedPack, PackTemplate
from engineering_brain.retrieval.pack_manager import PackManager, _infer_layer

logger = logging.getLogger(__name__)


class PackMaterializer:
    """Transforms PackTemplate + user params into a MaterializedPack."""

    def __init__(
        self,
        graph: GraphAdapter,
        vector: VectorAdapter | None,
        config: BrainConfig,
        query_router: Any = None,
        embedder: Any = None,
    ) -> None:
        self._graph = graph
        self._vector = vector
        self._config = config
        self._query_router = query_router
        self._embedder = embedder

    def materialize(
        self,
        template: PackTemplate,
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
        **kwargs: Any,
    ) -> MaterializedPack:
        """Create a MaterializedPack from a template + user overrides.

        Args:
            template: The pack template to use
            technologies: Override template technologies
            domains: Override template domains
            **kwargs: Additional overrides for template parameters

        Returns:
            MaterializedPack with full node data, ready for export
        """
        t0 = time.time()

        # 1. Merge template filters with user overrides
        techs = technologies or template.technologies or []
        doms = domains or template.domains or []
        max_nodes = kwargs.get("max_nodes", template.max_nodes)
        min_score = kwargs.get("min_score", template.min_quality)

        # 2. Build description from template + params
        desc_parts = [template.description or template.name or template.id]
        if techs:
            desc_parts.append(f"Technologies: {', '.join(techs)}")
        if doms:
            desc_parts.append(f"Domains: {', '.join(doms)}")
        description = ". ".join(desc_parts)

        # 3. Delegate to PackManager v1/v2 for retrieval
        pack = self._create_base_pack(description, techs, doms, min_score, max_nodes)

        # 4. Apply template constraints (severity filter, min_confidence, layer filter)
        filtered_ids = self._apply_template_filters(pack.node_ids, template)

        # 5. Hydrate full node data from graph
        nodes, node_map = self._hydrate_nodes(filtered_ids)

        # 6. Collect graph edges between pack nodes
        edges = self._collect_edges(filtered_ids)

        # 7. Filter reasoning edges to only include filtered nodes
        node_id_set = set(filtered_ids)
        reasoning_edges = [
            e for e in pack.reasoning_edges
            if e.get("from_id") in node_id_set and e.get("to_id") in node_id_set
        ]

        # Compute layers present
        layers_present = sorted({_infer_layer(nid) for nid in filtered_ids})

        # Compute technologies and domains from actual nodes
        all_techs: set[str] = set()
        all_doms: set[str] = set()
        for n in nodes:
            for t in (n.get("technologies") or n.get("languages") or []):
                all_techs.add(t)
            for d in (n.get("domains") or []):
                all_doms.add(d)

        materialized = MaterializedPack(
            id=f"pack-{template.id}-{int(t0)}",
            description=description,
            node_ids=filtered_ids,
            reasoning_edges=reasoning_edges,
            technologies=sorted(all_techs) or techs,
            domains=sorted(all_doms) or doms,
            layers_present=layers_present,
            quality_score=pack.quality_score,
            node_count=len(nodes),
            nodes=nodes,
            edges=edges,
            template_id=template.id,
            template_version=template.version,
        )
        # Attach template reference for serve()/export() to use
        materialized._template = template

        elapsed = (time.time() - t0) * 1000
        logger.info(
            "Materialized pack %s: %d nodes, %d edges, quality=%.2f (%.0fms)",
            template.id, len(nodes), len(edges), materialized.quality_score, elapsed,
        )
        return materialized

    def compose(self, packs: list[MaterializedPack]) -> MaterializedPack:
        """Compose multiple packs into one, deduplicating nodes.

        Args:
            packs: List of MaterializedPacks to merge

        Returns:
            Single merged MaterializedPack
        """
        if not packs:
            raise ValueError("Cannot compose empty pack list")
        if len(packs) == 1:
            return packs[0]

        # Merge nodes (deduplicate by ID)
        seen_ids: set[str] = set()
        merged_nodes: list[dict[str, Any]] = []
        merged_node_ids: list[str] = []
        all_techs: set[str] = set()
        all_doms: set[str] = set()
        all_layers: set[str] = set()
        merged_edges: list[dict[str, Any]] = []
        merged_reasoning: list[dict[str, Any]] = []
        template_ids: list[str] = []

        for pack in packs:
            if pack.template_id:
                template_ids.append(pack.template_id)
            for node in pack.nodes:
                nid = node.get("id", "")
                if nid and nid not in seen_ids:
                    seen_ids.add(nid)
                    merged_nodes.append(node)
                    merged_node_ids.append(nid)
            merged_edges.extend(pack.edges)
            merged_reasoning.extend(pack.reasoning_edges)
            all_techs.update(pack.technologies)
            all_doms.update(pack.domains)
            all_layers.update(pack.layers_present)

        # Deduplicate graph edges
        seen_edge_keys: set[tuple[str, str, str]] = set()
        deduped_edges: list[dict[str, Any]] = []
        for e in merged_edges:
            key = (e.get("from_id", ""), e.get("to_id", ""), e.get("edge_type", ""))
            if key not in seen_edge_keys:
                seen_edge_keys.add(key)
                deduped_edges.append(e)

        # Deduplicate reasoning edges
        seen_reasoning_keys: set[tuple[str, str, str]] = set()
        deduped_reasoning: list[dict[str, Any]] = []
        for e in merged_reasoning:
            key = (e.get("from_id", ""), e.get("to_id", ""), e.get("edge_type", ""))
            if key not in seen_reasoning_keys:
                seen_reasoning_keys.add(key)
                deduped_reasoning.append(e)

        # Recompute quality
        avg_quality = sum(p.quality_score for p in packs) / len(packs)

        return MaterializedPack(
            id=f"composed-{'-'.join(template_ids) or 'pack'}-{int(time.time())}",
            description=f"Composed pack from: {', '.join(template_ids)}",
            node_ids=merged_node_ids,
            reasoning_edges=deduped_reasoning,
            technologies=sorted(all_techs),
            domains=sorted(all_doms),
            layers_present=sorted(all_layers),
            quality_score=round(avg_quality, 3),
            node_count=len(merged_nodes),
            nodes=merged_nodes,
            edges=deduped_edges,
            template_id="+".join(template_ids),
            template_version="composed",
        )

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _create_base_pack(
        self,
        description: str,
        technologies: list[str],
        domains: list[str],
        min_score: float,
        max_nodes: int,
    ) -> Any:
        """Delegate pack creation to PackManager v1/v2."""
        if self._config.pack_v2_enabled:
            from engineering_brain.retrieval.pack_manager_v2 import ScalablePackManager
            mgr = ScalablePackManager(
                self._graph, self._vector, self._config,
                query_router=self._query_router,
                embedder=self._embedder,
            )
        else:
            mgr = PackManager(self._graph, self._vector, self._config, self._query_router)
        return mgr.create_pack(
            description,
            technologies=technologies or None,
            domains=domains or None,
            min_score=min_score,
            max_nodes=max_nodes,
        )

    def _apply_template_filters(
        self,
        node_ids: list[str],
        template: PackTemplate,
    ) -> list[str]:
        """Filter node_ids based on template constraints."""
        filtered: list[str] = []

        for nid in node_ids:
            node = self._graph.get_node(nid)
            if node is None:
                continue

            # Exclude deprecated
            if template.exclude_deprecated and node.get("deprecated"):
                continue

            # Layer filter
            if template.layers:
                node_layer = _infer_layer(nid)
                if node_layer not in template.layers:
                    continue

            # Severity filter
            if template.severities:
                node_severity = node.get("severity", "medium")
                if node_severity not in template.severities:
                    continue

            # Confidence filter
            if template.min_confidence > 0:
                node_confidence = float(node.get("confidence", 0.5))
                if node_confidence < template.min_confidence:
                    continue

            # Technology filter (glob matching)
            if template.technologies:
                node_techs = node.get("technologies") or node.get("languages") or []
                if node_techs:
                    match = any(
                        fnmatch.fnmatch(nt.lower(), tp.lower())
                        for nt in node_techs
                        for tp in template.technologies
                    )
                    if not match:
                        # Filter out nodes whose technologies don't match
                        # Nodes without technologies pass through
                        continue

            # Domain filter (glob matching)
            if template.domains:
                node_doms = node.get("domains") or []
                # Don't filter — domains are used for scoring not hard filtering

            filtered.append(nid)

        # Sort by severity if preferred
        if template.prefer_high_severity:
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            filtered.sort(key=lambda nid: severity_order.get(
                (self._graph.get_node(nid) or {}).get("severity", "medium"), 2,
            ))

        # Enforce max_nodes
        if template.max_nodes and len(filtered) > template.max_nodes:
            filtered = filtered[:template.max_nodes]

        return filtered

    def _hydrate_nodes(
        self,
        node_ids: list[str],
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        """Fetch full node data from the graph.

        Returns:
            (nodes_list, node_map_by_id)
        """
        nodes: list[dict[str, Any]] = []
        node_map: dict[str, dict[str, Any]] = {}

        for nid in node_ids:
            node = self._graph.get_node(nid)
            if node is not None:
                nodes.append(node)
                node_map[nid] = node

        return nodes, node_map

    def _collect_edges(self, node_ids: list[str]) -> list[dict[str, Any]]:
        """Collect all graph edges between pack nodes."""
        node_id_set = set(node_ids)
        edges: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for nid in node_ids:
            try:
                node_edges = self._graph.get_edges(node_id=nid)
            except Exception:
                continue
            for edge in node_edges:
                from_id = edge.get("from_id", "")
                to_id = edge.get("to_id", "")
                if from_id in node_id_set and to_id in node_id_set:
                    key = (from_id, to_id)
                    if key not in seen:
                        seen.add(key)
                        edges.append(edge)

        return edges
