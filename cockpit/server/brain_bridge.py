"""Thin wrapper around Engineering Brain — exposes JSON-serializable data."""

from __future__ import annotations

import asyncio
import logging

import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Layer derivation from node ID prefix ──────────────────────────────────────

_PREFIX_TO_LAYER: list[tuple[str, int, str, str]] = [
    ("AX-",  0, "Axiom",       "L0 — Axioms"),
    ("P-",   1, "Principle",   "L1 — Principles"),
    ("PAT-", 2, "Pattern",     "L2 — Patterns"),
    ("R-",   3, "Rule",        "L3 — Rules"),
    ("CR-",  3, "Rule",        "L3 — Rules"),
    ("F-",   4, "Finding",     "L4 — Evidence"),
    ("CE-",  4, "CodeExample", "L4 — Evidence"),
    ("TR-",  4, "TestResult",  "L4 — Evidence"),
    ("CPAT-",2, "CommunityPattern", "L2 — Patterns"),
    ("TC-",  5, "Task",        "L5 — Context"),
]

_TAXONOMY_PREFIXES = ("tech:", "domain:", "filetype:", "human_layer:", "sprint:")


def _layer_info(node_id: str) -> tuple[int, str, str]:
    """Return (layer_num, type_name, layer_label) from node ID prefix."""
    for prefix, layer, ntype, label in _PREFIX_TO_LAYER:
        if node_id.startswith(prefix):
            return layer, ntype, label
    # Taxonomy nodes
    for tp in _TAXONOMY_PREFIXES:
        if node_id.startswith(tp):
            kind = tp.rstrip(":")
            return -1, kind.title(), "Taxonomy"
    return 3, "Rule", "L3 — Rules"  # fallback


class BrainBridge:
    """Thin wrapper: loads Brain, exposes JSON-serializable data for the cockpit.

    Thread-safety: all public read methods acquire _brain_lock to capture
    a local reference to _brain, then read from it outside the lock.
    ReloadManager swaps _brain under the same lock (copy-on-write).
    """

    def __init__(
        self,
        brain_json_path: str | None = None,
        seeds_dir: str | None = None,
    ) -> None:
        self._brain = None
        self._version = 0
        self._brain_lock = asyncio.Lock()
        self._reload_version = 0
        self._load(brain_json_path, seeds_dir)

    # ── Loading ───────────────────────────────────────────────────────────

    def _load(
        self,
        brain_json_path: str | None,
        seeds_dir: str | None,
    ) -> None:
        """Load brain from JSON snapshot or seeds directory."""
        # Try importing engineering_brain (install via: pip install engineering-brain)
        try:
            from engineering_brain import Brain
        except ImportError:
            log.warning("engineering_brain not importable — running in static mode")
            self._brain = None
            return

        t0 = time.monotonic()

        if brain_json_path and Path(brain_json_path).exists():
            log.info("Loading brain from JSON: %s", brain_json_path)
            self._brain = Brain.load(brain_json_path)
        elif seeds_dir and Path(seeds_dir).is_dir():
            log.info("Loading brain from seeds: %s", seeds_dir)
            brain = Brain()
            brain.ingest_directory(seeds_dir)
            self._brain = brain
        else:
            log.info("Loading brain with default seeds")
            brain = Brain()
            brain.seed()
            self._brain = brain

        elapsed = time.monotonic() - t0
        log.info("Brain loaded in %.1fs — %d nodes", elapsed, len(self._all_nodes_raw(self._brain)))

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _infer_knowledge_type(node: dict[str, Any]) -> str:
        """Infer knowledge_type from node content when not explicitly stored."""
        node_id = str(node.get("id") or node.get("_id", ""))
        text = str(node.get("text") or node.get("statement") or "").lower()

        # Heuristic inference based on content and ID prefix
        if node_id.startswith("AX-"):
            return "axiomatic"
        if node.get("example_good") or node.get("example_bad"):
            return "procedural"
        if "version" in text or "api" in text or "library" in text:
            return "version_specific"
        if "security" in text or "vulnerability" in text:
            return "security_advisory"
        if node.get("how_to_apply") or node.get("how_to_do_right"):
            return "procedural"
        return "best_practice"

    # ── Raw data access ───────────────────────────────────────────────────

    @staticmethod
    def _all_nodes_raw(brain: Any) -> list[dict[str, Any]]:
        if not brain:
            return []
        return brain.graph.get_all_nodes()

    @staticmethod
    def _all_edges_raw(brain: Any) -> list[dict[str, Any]]:
        if not brain:
            return []
        return brain.graph.get_edges()

    # ── Cockpit node transformation ───────────────────────────────────────

    @staticmethod
    def _transform_node(raw: dict[str, Any], in_edges: list[dict], out_edges: list[dict]) -> dict[str, Any]:
        """Transform a raw Brain node into the cockpit format."""
        node_id = raw.get("id") or raw.get("_id", "")
        layer, ntype, layer_name = _layer_info(node_id)

        # Build opinion dict from ep_ fields
        opinion = None
        if raw.get("ep_b") is not None:
            opinion = {
                "b": raw.get("ep_b", 0),
                "d": raw.get("ep_d", 0),
                "u": raw.get("ep_u", 0),
                "a": raw.get("ep_a", 0.5),
            }

        # Derive display text (different node types have different primary fields)
        text = (
            raw.get("text")
            or raw.get("statement")
            or raw.get("name")
            or raw.get("description")
            or raw.get("intent")
            or node_id
        )

        result: dict[str, Any] = {
            "id": node_id,
            "type": ntype,
            "layer": layer,
            "layerName": layer_name,
            "text": text,
            "severity": raw.get("severity", "info"),
            "confidence": raw.get("confidence", 0.5),
            "technologies": raw.get("technologies", []),
            "domains": raw.get("domains", []) or ([raw["domain"]] if raw.get("domain") else []),
            "outEdges": [
                {"to": e.get("to_id", ""), "type": e.get("edge_type", "RELATES_TO")}
                for e in out_edges
            ],
            "inEdges": [
                {"from": e.get("from_id", ""), "type": e.get("edge_type", "RELATES_TO")}
                for e in in_edges
            ],
        }

        # Optional fields — only include if present
        if raw.get("why"):
            result["why"] = raw["why"]
        if raw.get("how_to_do_right"):
            result["howTo"] = raw["how_to_do_right"]
        if raw.get("how_to_apply"):
            result["howTo"] = raw["how_to_apply"]
        if raw.get("when_to_use"):
            result["whenToUse"] = raw["when_to_use"]
        if raw.get("when_not_to_use"):
            result["whenNotToUse"] = raw["when_not_to_use"]
        if raw.get("example_good"):
            result["exampleGood"] = raw["example_good"]
        if raw.get("example_bad"):
            result["exampleBad"] = raw["example_bad"]
        if raw.get("mental_model"):
            result["mentalModel"] = raw["mental_model"]
        if opinion:
            result["opinion"] = opinion
        if raw.get("reinforcement_count"):
            result["reinforcements"] = raw["reinforcement_count"]
        if raw.get("file_types"):
            result["fileTypes"] = raw["file_types"]

        # Wave 1: Epistemic status (E0-E5 ladder)
        if raw.get("epistemic_status"):
            result["epistemicStatus"] = raw["epistemic_status"]
        # Wave 1: Predictive decay freshness
        if raw.get("freshness") is not None:
            result["freshness"] = raw["freshness"]
        if raw.get("knowledge_type"):
            result["decayProfile"] = raw["knowledge_type"]

        return result

    # ── Public API (async — copy-on-write reads) ──────────────────────────

    async def snapshot(self) -> dict[str, Any]:
        """Full graph snapshot for initial client load."""
        async with self._brain_lock:
            brain = self._brain

        raw_nodes = self._all_nodes_raw(brain)
        raw_edges = self._all_edges_raw(brain)

        # Compute freshness and knowledge_type at snapshot time
        decay_engine = None
        try:
            from engineering_brain.epistemic.predictive_decay import PredictiveDecayEngine
            decay_engine = PredictiveDecayEngine()
        except Exception:
            pass

        for n in raw_nodes:
            if decay_engine and n.get("freshness") is None:
                try:
                    n["freshness"] = decay_engine.compute_freshness(n)
                except Exception:
                    pass
            if not n.get("knowledge_type"):
                n["knowledge_type"] = self._infer_knowledge_type(n)

        # Build edge indices for backlinks
        out_idx: dict[str, list[dict]] = {}
        in_idx: dict[str, list[dict]] = {}
        for e in raw_edges:
            fid = e.get("from_id", "")
            tid = e.get("to_id", "")
            out_idx.setdefault(fid, []).append(e)
            in_idx.setdefault(tid, []).append(e)

        nodes = [
            self._transform_node(
                n,
                in_edges=in_idx.get(n.get("id") or n.get("_id", ""), []),
                out_edges=out_idx.get(n.get("id") or n.get("_id", ""), []),
            )
            for n in raw_nodes
        ]

        edges = []
        for e in raw_edges:
            edge_dict: dict[str, Any] = {
                "from": e.get("from_id", ""),
                "to": e.get("to_id", ""),
                "type": e.get("edge_type", "RELATES_TO"),
            }
            # Wave 1: Bayesian edge fields
            if e.get("edge_alpha") is not None:
                edge_dict["edgeAlpha"] = e["edge_alpha"]
                edge_dict["edgeBeta"] = e.get("edge_beta", 1.0)
                edge_dict["edgeConfidence"] = e.get("edge_confidence", 0.5)
            if e.get("reinforcement_count"):
                edge_dict["reinforcements"] = e["reinforcement_count"]
            edges.append(edge_dict)

        return {
            "version": self.version,
            "stats": await self.stats(),
            "nodes": nodes,
            "edges": edges,
        }

    async def nodes(
        self,
        layer: int | None = None,
        severity: str | None = None,
        technology: str | None = None,
        domain: str | None = None,
        search: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Paginated, filtered nodes."""
        async with self._brain_lock:
            brain = self._brain

        raw_nodes = self._all_nodes_raw(brain)
        raw_edges = self._all_edges_raw(brain)

        # Build edge indices
        out_idx: dict[str, list[dict]] = {}
        in_idx: dict[str, list[dict]] = {}
        for e in raw_edges:
            out_idx.setdefault(e.get("from_id", ""), []).append(e)
            in_idx.setdefault(e.get("to_id", ""), []).append(e)

        result = []
        for n in raw_nodes:
            nid = n.get("id") or n.get("_id", "")
            node = self._transform_node(
                n,
                in_edges=in_idx.get(nid, []),
                out_edges=out_idx.get(nid, []),
            )

            # Apply filters
            if layer is not None and node["layer"] != layer:
                continue
            if severity and node.get("severity", "").lower() != severity.lower():
                continue
            if technology and technology.lower() not in [t.lower() for t in node.get("technologies", [])]:
                continue
            if domain and domain.lower() not in [d.lower() for d in node.get("domains", [])]:
                continue
            if search:
                search_lower = search.lower()
                searchable = f"{node['id']} {node['text']} {node.get('why', '')} {node.get('howTo', '')}".lower()
                if search_lower not in searchable:
                    continue

            result.append(node)

        return result[offset : offset + limit]

    async def node(self, node_id: str) -> dict[str, Any] | None:
        """Single node with computed backlinks."""
        async with self._brain_lock:
            brain = self._brain

        raw_nodes = self._all_nodes_raw(brain)
        raw_edges = self._all_edges_raw(brain)

        # Find the node
        raw = None
        for n in raw_nodes:
            if (n.get("id") or n.get("_id", "")) == node_id:
                raw = n
                break
        if not raw:
            return None

        out_idx: dict[str, list[dict]] = {}
        in_idx: dict[str, list[dict]] = {}
        for e in raw_edges:
            out_idx.setdefault(e.get("from_id", ""), []).append(e)
            in_idx.setdefault(e.get("to_id", ""), []).append(e)

        return self._transform_node(
            raw,
            in_edges=in_idx.get(node_id, []),
            out_edges=out_idx.get(node_id, []),
        )

    async def edges(
        self,
        node_id: str | None = None,
        edge_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filtered edges."""
        async with self._brain_lock:
            brain = self._brain

        raw_edges = self._all_edges_raw(brain)
        result = []
        for e in raw_edges:
            if node_id:
                if e.get("from_id") != node_id and e.get("to_id") != node_id:
                    continue
            if edge_type:
                if e.get("edge_type", "").upper() != edge_type.upper():
                    continue
            edge_dict = {
                "from": e.get("from_id", ""),
                "to": e.get("to_id", ""),
                "type": e.get("edge_type", "RELATES_TO"),
                "properties": e.get("properties", {}),
            }
            # Wave 1: Bayesian edge fields
            if e.get("edge_alpha") is not None:
                edge_dict["edgeAlpha"] = e["edge_alpha"]
                edge_dict["edgeBeta"] = e.get("edge_beta", 1.0)
                edge_dict["edgeConfidence"] = e.get("edge_confidence", 0.5)
            if e.get("reinforcement_count"):
                edge_dict["reinforcements"] = e["reinforcement_count"]
            result.append(edge_dict)
        return result

    async def stats(self) -> dict[str, Any]:
        """Aggregate statistics for the dashboard."""
        async with self._brain_lock:
            brain = self._brain

        raw_nodes = self._all_nodes_raw(brain)
        raw_edges = self._all_edges_raw(brain)

        by_layer: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        by_technology: dict[str, int] = {}
        by_domain: dict[str, int] = {}
        by_edge_type: dict[str, int] = {}

        for n in raw_nodes:
            nid = n.get("id") or n.get("_id", "")
            _, _, layer_name = _layer_info(nid)
            by_layer[layer_name] = by_layer.get(layer_name, 0) + 1

            sev = n.get("severity", "info").upper()
            by_severity[sev] = by_severity.get(sev, 0) + 1

            for tech in n.get("technologies", []):
                by_technology[tech] = by_technology.get(tech, 0) + 1

            domains = n.get("domains", []) or ([n["domain"]] if n.get("domain") else [])
            for dom in domains:
                by_domain[dom] = by_domain.get(dom, 0) + 1

        for e in raw_edges:
            et = e.get("edge_type", "RELATES_TO")
            by_edge_type[et] = by_edge_type.get(et, 0) + 1

        # Count seed files if brain has seeds path
        seed_count = 0
        try:
            if brain:
                from engineering_brain.core.config import BrainConfig
                cfg = BrainConfig()
                seeds_dir = Path(cfg.seeds_directory)
                if seeds_dir.is_dir():
                    seed_count = sum(1 for _ in seeds_dir.rglob("*.yaml"))
        except Exception:
            pass

        return {
            "total_nodes": len(raw_nodes),
            "total_edges": len(raw_edges),
            "total_edge_types": len(by_edge_type),
            "total_technologies": len(by_technology),
            "total_domains": len(by_domain),
            "seed_count": seed_count,
            "by_layer": by_layer,
            "by_severity": by_severity,
            "by_edge_type": by_edge_type,
            "by_technology": by_technology,
            "by_domain": by_domain,
            "version": self.version,
        }

    # ── Pack API ─────────────────────────────────────────────────────────

    async def create_pack(
        self,
        description: str,
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
        max_nodes: int = 80,
    ) -> dict[str, Any]:
        """Create a knowledge pack from description. Returns pack as dict."""
        async with self._brain_lock:
            brain = self._brain

        if not brain:
            return {"error": "Brain not loaded"}

        try:
            pack = brain.create_pack(
                description,
                technologies=technologies,
                domains=domains,
                max_nodes=max_nodes,
            )
            return {
                "id": pack.id,
                "description": pack.description,
                "node_ids": pack.node_ids,
                "node_count": pack.node_count,
                "technologies": pack.technologies,
                "domains": pack.domains,
                "layers_present": pack.layers_present,
                "quality_score": pack.quality_score,
                "reasoning_edges": pack.reasoning_edges,
            }
        except Exception as e:
            log.error("create_pack failed: %s", e)
            return {"error": str(e)}

    async def preview_pack(
        self,
        description: str,
        technologies: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Preview pack composition without full materialization.

        Creates a small pack (max 20 nodes) and returns lightweight summary.
        """
        async with self._brain_lock:
            brain = self._brain

        if not brain:
            return {"error": "Brain not loaded"}

        try:
            pack = brain.create_pack(
                description,
                technologies=technologies,
                domains=domains,
                max_nodes=20,
                min_score=0.2,
            )
            # Compute tech/domain overlap with request
            req_techs = set(t.lower() for t in (technologies or []))
            pack_techs = set(t.lower() for t in pack.technologies)
            tech_overlap = len(req_techs & pack_techs) / max(len(req_techs | pack_techs), 1) if req_techs else 0.0

            req_doms = set(d.lower() for d in (domains or []))
            pack_doms = set(d.lower() for d in pack.domains)
            domain_overlap = len(req_doms & pack_doms) / max(len(req_doms | pack_doms), 1) if req_doms else 0.0

            return {
                "id": pack.id,
                "node_count": pack.node_count,
                "layers_present": pack.layers_present,
                "quality_score": pack.quality_score,
                "technologies": pack.technologies,
                "domains": pack.domains,
                "tech_overlap": round(tech_overlap, 3),
                "domain_overlap": round(domain_overlap, 3),
            }
        except Exception as e:
            log.error("preview_pack failed: %s", e)
            return {"error": str(e)}

    # ── Epistemic API (Wave 1 SOTA) ──────────────────────────────────────

    async def epistemic_stats(self) -> dict[str, Any]:
        """E0-E5 distribution, average freshness, decay at-risk count, contradictions."""
        async with self._brain_lock:
            brain = self._brain

        raw_nodes = self._all_nodes_raw(brain)

        # ── E0-E5 distribution ────────────────────────────────────────────
        e_distribution: dict[str, int] = {
            "E0": 0, "E1": 0, "E2": 0, "E3": 0, "E4": 0, "E5": 0,
        }
        ladder = None
        try:
            from engineering_brain.epistemic.epistemic_ladder import EpistemicLadder
            ladder = EpistemicLadder()
        except Exception:
            pass

        for n in raw_nodes:
            es = n.get("epistemic_status")
            if es and es in e_distribution:
                e_distribution[es] += 1
            elif ladder:
                try:
                    status = ladder.classify(n)
                    key = status.value if hasattr(status, "value") else str(status)
                    if key in e_distribution:
                        e_distribution[key] += 1
                except Exception:
                    pass

        # ── Freshness stats via PredictiveDecayEngine ─────────────────────
        avg_freshness = 0.0
        decay_at_risk = 0
        decay_engine = None
        try:
            from engineering_brain.epistemic.predictive_decay import PredictiveDecayEngine
            decay_engine = PredictiveDecayEngine()
        except Exception:
            pass

        if decay_engine and raw_nodes:
            total_freshness = 0.0
            counted = 0
            for n in raw_nodes:
                try:
                    f = decay_engine.compute_freshness(n)
                    total_freshness += f
                    counted += 1
                except Exception:
                    pass
            avg_freshness = round(total_freshness / max(counted, 1), 4)

            try:
                at_risk = decay_engine.get_at_risk_nodes(raw_nodes, horizon_days=30)
                decay_at_risk = len(at_risk)
            except Exception:
                pass

        # ── Contradiction count ───────────────────────────────────────────
        contradiction_total = 0
        contradiction_unresolved = 0
        try:
            if brain and hasattr(brain, "detect_contradictions"):
                contradictions = brain.detect_contradictions()
                contradiction_total = len(contradictions)
                contradiction_unresolved = sum(
                    1 for c in contradictions
                    if c.get("resolution_method") in (None, "unresolved", "")
                )
        except Exception:
            pass

        return {
            "e_distribution": e_distribution,
            "avg_freshness": avg_freshness,
            "decay_at_risk": decay_at_risk,
            "contradiction_total": contradiction_total,
            "contradiction_unresolved": contradiction_unresolved,
            "total_nodes": len(raw_nodes),
        }

    async def contradictions(self) -> list[dict[str, Any]]:
        """Return all detected contradictions via Brain.detect_contradictions()."""
        async with self._brain_lock:
            brain = self._brain

        if not brain:
            return []

        try:
            if hasattr(brain, "detect_contradictions"):
                return brain.detect_contradictions()
        except Exception as e:
            log.warning("contradictions() failed: %s", e)

        return []

    async def at_risk_nodes(self, horizon_days: int = 30) -> list[dict[str, Any]]:
        """Return nodes predicted to go stale within the horizon."""
        async with self._brain_lock:
            brain = self._brain

        raw_nodes = self._all_nodes_raw(brain)
        if not raw_nodes:
            return []

        try:
            from engineering_brain.epistemic.predictive_decay import PredictiveDecayEngine
            engine = PredictiveDecayEngine()
            predictions = engine.get_at_risk_nodes(raw_nodes, horizon_days=horizon_days)
            return [p.to_dict() for p in predictions]
        except Exception as e:
            log.warning("at_risk_nodes() failed: %s", e)
            return []

    @property
    def version(self) -> int:
        """Monotonic write counter for change detection.

        Reload version is multiplied by 100_000 so it always dominates
        the Brain's internal version counter, ensuring SSE detects reloads.
        """
        brain_v = 0
        if self._brain and hasattr(self._brain, "version"):
            brain_v = self._brain.version
        return brain_v + self._reload_version * 100_000
