"""Cluster-based additive crystallization for the Engineering Knowledge Brain.

Clusters similar L3 rules and extracts shared L2 patterns WITHOUT removing
the original rules. This is additive compression — we abstract upward while
preserving all originals.

Algorithm:
1. Gather eligible rules (min reinforcements + confidence)
2. Compute pairwise similarity (Jaccard on tech/domain + term overlap on text)
3. Cluster via Union-Find (single-linkage agglomerative)
4. Extract shared L2 pattern from each cluster
5. Link via INSTANTIATES edges (pattern → each member rule)

Properties:
- ZERO information loss: original rules remain untouched
- Idempotent: deterministic pattern IDs from sorted member rule IDs
- No external dependencies: pure Python, O(n^2) on ~2K rules
"""

from __future__ import annotations

import hashlib
import logging
import random
import os
import re
from collections import Counter, defaultdict
from typing import Any

from engineering_brain.adapters.base import GraphAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import EdgeType, NodeType

logger = logging.getLogger(__name__)

# Stop words for term overlap computation
_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "up",
    "about", "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "over", "under", "again", "further",
    "then", "once", "and", "but", "or", "nor", "not", "no", "so", "if",
    "this", "that", "these", "those", "it", "its", "used", "using",
    "use", "don", "always", "never", "ensure", "make", "sure",
})


def _extract_terms(text: str) -> set[str]:
    """Extract significant terms from text (lowercased, min 3 chars)."""
    words = re.findall(r"\b\w{3,}\b", text.lower())
    return {w for w in words if w not in _STOP_WORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two sets."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _text_term_overlap(text_a: str, text_b: str) -> float:
    """Compute term overlap between two texts using Jaccard on extracted terms."""
    terms_a = _extract_terms(text_a)
    terms_b = _extract_terms(text_b)
    return _jaccard(terms_a, terms_b)


class _MinHashLSH:
    """MinHash with LSH banding for O(n log n) approximate candidate pair detection.

    Replaces O(n^2) brute-force pairwise comparison when n >= 1000 nodes.
    Uses permutation hashing with LSH banding to find candidate similar pairs
    in sub-quadratic time.
    """

    def __init__(self, num_hashes: int = 128, num_bands: int = 16, seed: int = 42) -> None:
        self.num_hashes = num_hashes
        self.num_bands = num_bands
        self.rows_per_band = num_hashes // num_bands
        rng = random.Random(seed)
        self._a = [rng.randint(1, (1 << 31) - 2) for _ in range(num_hashes)]
        self._b = [rng.randint(0, (1 << 31) - 2) for _ in range(num_hashes)]
        self._prime = (1 << 31) - 1  # Mersenne prime

    def fingerprint(self, terms: set[str]) -> list[int]:
        """Compute MinHash fingerprint for a set of terms."""
        if not terms:
            return [self._prime] * self.num_hashes
        hashes = [self._prime] * self.num_hashes
        for term in terms:
            h = hash(term) & 0x7FFFFFFF
            for i in range(self.num_hashes):
                val = (self._a[i] * h + self._b[i]) % self._prime
                if val < hashes[i]:
                    hashes[i] = val
        return hashes

    def find_candidates(self, fingerprints: list[list[int]]) -> set[tuple[int, int]]:
        """Use LSH banding to find candidate similar pairs in O(n * bands)."""
        candidates: set[tuple[int, int]] = set()
        for band_idx in range(self.num_bands):
            start = band_idx * self.rows_per_band
            end = start + self.rows_per_band
            buckets: dict[tuple[int, ...], list[int]] = defaultdict(list)
            for idx, fp in enumerate(fingerprints):
                band_sig = tuple(fp[start:end])
                buckets[band_sig].append(idx)
            for members in buckets.values():
                if len(members) < 2:
                    continue
                for i in range(len(members)):
                    for j in range(i + 1, min(i + 50, len(members))):
                        candidates.add((members[i], members[j]))
        return candidates


class ClusterPromoter:
    """Clusters similar L3 rules into shared L2 patterns (additive)."""

    def __init__(self, graph: GraphAdapter, config: BrainConfig | None = None) -> None:
        self._graph = graph
        self._config = config or BrainConfig()
        self._embedder = None
        self._embedding_cache: dict[str, list[float]] = {}
        if self._config.embedding_enabled:
            try:
                from engineering_brain.retrieval.embedder import get_embedder
                self._embedder = get_embedder()
            except Exception:
                pass

    def crystallize(self) -> list[str]:
        """Run cluster crystallization. Returns list of created pattern IDs."""
        # 1. Gather eligible rules
        rules = self._gather_eligible_rules()
        min_cluster = self._config.crystallize_min_cluster_size
        if len(rules) < min_cluster:
            return []

        # 2. Compute pairwise similarity
        sim_edges = self._compute_pairwise_similarity(rules)

        # 3. Cluster via Union-Find
        clusters = self._find_clusters(rules, sim_edges)

        # 3b. Validate cluster coherence via embedding centroid (if available)
        if self._embedder:
            clusters = self._validate_cluster_coherence(clusters)

        # 4. Extract patterns from qualifying clusters
        created: list[str] = []
        for cluster in clusters:
            if len(cluster) < min_cluster:
                continue
            pattern_id = self._create_pattern_from_cluster(cluster)
            if pattern_id:
                created.append(pattern_id)

        if created:
            logger.info(
                "Cluster crystallization: %d patterns from %d eligible rules",
                len(created), len(rules),
            )

        return created

    def _gather_eligible_rules(self) -> list[dict[str, Any]]:
        """Gather rules meeting minimum reinforcement and confidence thresholds."""
        rules = self._graph.query(label=NodeType.RULE.value, limit=2000)
        eligible: list[dict[str, Any]] = []
        min_r = self._config.crystallize_min_reinforcements
        min_c = self._config.crystallize_min_confidence

        for rule in rules:
            if rule.get("deprecated"):
                continue
            rc = int(rule.get("reinforcement_count", 0))
            ep_b = rule.get("ep_b")
            if ep_b is not None:
                ep_u = float(rule.get("ep_u", 1.0))
                ep_a = float(rule.get("ep_a", 0.5))
                projected = float(ep_b) + ep_a * ep_u
                if rc >= min_r and projected >= min_c and ep_u <= 0.5:
                    eligible.append(rule)
            else:
                conf = float(rule.get("confidence", 0))
                if rc >= min_r and conf >= min_c:
                    eligible.append(rule)

        return eligible

    def _get_node_embedding(self, node: dict[str, Any]) -> list[float] | None:
        """Get or compute embedding for a node. Returns None if unavailable."""
        if not self._embedder:
            return None
        nid = node.get("id", "")
        if nid in self._embedding_cache:
            return self._embedding_cache[nid]
        vec = self._embedder.embed_text(self._embedder.node_to_text(node))
        if vec:
            self._embedding_cache[nid] = vec
        return vec or None

    def _rule_similarity(self, a: dict[str, Any], b: dict[str, Any]) -> float:
        """Compute composite similarity between two rules.

        Uses embedding cosine similarity when available (0.60 weight),
        falls back to Jaccard text overlap (0.35 weight) when not.

        Structural guard: when both rules have technologies or domains
        specified but share zero overlap in both, they are structurally
        disjoint and return 0.0 regardless of text/embedding similarity.
        This prevents small embedding models from merging unrelated clusters.
        """
        tech_a = {t.lower() for t in (a.get("technologies") or [])}
        tech_b = {t.lower() for t in (b.get("technologies") or [])}
        tech_sim = _jaccard(tech_a, tech_b)

        dom_a = {d.lower() for d in (a.get("domains") or [])}
        dom_b = {d.lower() for d in (b.get("domains") or [])}
        domain_sim = _jaccard(dom_a, dom_b)

        # Structural guard: if both rules specify technologies or domains
        # and they share zero overlap in both, they are disjoint topics.
        # Embedding similarity alone should not override structural signals.
        has_structural_a = bool(tech_a or dom_a)
        has_structural_b = bool(tech_b or dom_b)
        if has_structural_a and has_structural_b and tech_sim == 0.0 and domain_sim == 0.0:
            return 0.0

        # Embedding-based semantic similarity (replaces Jaccard text overlap)
        vec_a = self._get_node_embedding(a)
        vec_b = self._get_node_embedding(b)
        if vec_a and vec_b:
            from engineering_brain.retrieval.embedder import cosine_similarity
            embed_sim = cosine_similarity(vec_a, vec_b)
            return 0.25 * tech_sim + 0.15 * domain_sim + 0.60 * embed_sim

        # Fallback: original Jaccard text overlap
        text_a = f"{a.get('text', '')} {a.get('why', '')}"
        text_b = f"{b.get('text', '')} {b.get('why', '')}"
        text_sim = _text_term_overlap(text_a, text_b)

        return 0.40 * tech_sim + 0.25 * domain_sim + 0.35 * text_sim

    def _compute_pairwise_similarity(
        self, rules: list[dict[str, Any]]
    ) -> list[tuple[int, int]]:
        """Compute pairwise similarity and return edges above threshold.

        Uses MinHash/LSH for O(n * bands) candidate detection when n >= 1000,
        falling back to O(n^2) brute force for smaller sets.
        """
        n = len(rules)
        threshold = self._config.crystallize_min_similarity
        edges: list[tuple[int, int]] = []

        if n >= 1000:
            # Approximate: MinHash/LSH candidate pairs then verify
            lsh = _MinHashLSH(num_hashes=128, num_bands=16)
            fingerprints: list[list[int]] = []
            for rule in rules:
                terms = _extract_terms(
                    f"{rule.get('text', '')} {rule.get('why', '')}"
                )
                techs = {t.lower() for t in (rule.get("technologies") or [])}
                domains = {d.lower() for d in (rule.get("domains") or [])}
                fingerprints.append(lsh.fingerprint(terms | techs | domains))

            candidates = lsh.find_candidates(fingerprints)
            logger.info(
                "MinHash/LSH: %d candidates from %d rules (vs %d brute force)",
                len(candidates), n, n * (n - 1) // 2,
            )

            for i, j in candidates:
                if self._rule_similarity(rules[i], rules[j]) >= threshold:
                    edges.append((i, j))
        else:
            # Brute force for small sets
            for i in range(n):
                for j in range(i + 1, n):
                    if self._rule_similarity(rules[i], rules[j]) >= threshold:
                        edges.append((i, j))

        return edges

    def _find_clusters(
        self,
        rules: list[dict[str, Any]],
        edges: list[tuple[int, int]],
    ) -> list[list[dict[str, Any]]]:
        """Cluster rules using Union-Find on similarity edges."""
        n = len(rules)
        parent = list(range(n))
        rank = [0] * n

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # path compression
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            rx, ry = find(x), find(y)
            if rx == ry:
                return
            if rank[rx] < rank[ry]:
                rx, ry = ry, rx
            parent[ry] = rx
            if rank[rx] == rank[ry]:
                rank[rx] += 1

        for i, j in edges:
            union(i, j)

        groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for i in range(n):
            groups[find(i)].append(rules[i])

        return list(groups.values())

    def _create_pattern_from_cluster(
        self, cluster: list[dict[str, Any]]
    ) -> str | None:
        """Create an L2 pattern from a cluster of similar L3 rules."""
        # Deterministic ID from sorted member rule IDs
        member_ids = sorted(r.get("id", "") for r in cluster)
        fingerprint = "|".join(member_ids)
        h = hashlib.sha256(fingerprint.encode()).hexdigest()[:10]
        pattern_id = f"CPAT-{h}"

        # Idempotent check
        if self._graph.get_node(pattern_id):
            return pattern_id

        # Extract pattern fields
        pattern_data = self._extract_pattern_fields(cluster, pattern_id, member_ids)

        # Add pattern node
        success = self._graph.add_node(
            NodeType.PATTERN.value, pattern_id, pattern_data
        )
        if not success:
            return None

        # Add INSTANTIATES edges (pattern → each member rule)
        for rule in cluster:
            rid = rule.get("id", "")
            if rid:
                self._graph.add_edge(pattern_id, rid, EdgeType.INSTANTIATES.value)

        # Add technology edges
        for tech in pattern_data.get("languages", []):
            tid = f"tech:{tech.lower()}"
            self._graph.add_edge(pattern_id, tid, EdgeType.USED_IN.value)

        # Add domain edges
        for domain in pattern_data.get("_domains", []):
            did = f"domain:{domain.lower()}"
            self._graph.add_edge(pattern_id, did, EdgeType.IN_DOMAIN.value)

        logger.info(
            "Crystallized %d rules into pattern %s: %s",
            len(cluster), pattern_id, pattern_data.get("name", ""),
        )
        return pattern_id

    def _extract_pattern_fields(
        self,
        cluster: list[dict[str, Any]],
        pattern_id: str,
        member_ids: list[str],
    ) -> dict[str, Any]:
        """Extract shared pattern fields from a cluster of rules."""
        # Sort by confidence descending for "best representative"
        by_conf = sorted(
            cluster,
            key=lambda r: float(r.get("confidence", 0)),
            reverse=True,
        )
        best = by_conf[0]

        # Shared technologies (intersection, fallback to >50% occurrence)
        tech_sets = [
            {t.lower() for t in (r.get("technologies") or [])} for r in cluster
        ]
        shared_techs = tech_sets[0].copy() if tech_sets else set()
        for ts in tech_sets[1:]:
            shared_techs &= ts

        if not shared_techs and tech_sets:
            tech_counts: Counter[str] = Counter()
            for ts in tech_sets:
                tech_counts.update(ts)
            threshold = len(cluster) / 2
            shared_techs = {t for t, c in tech_counts.items() if c > threshold}

        # All domains (union)
        all_domains: set[str] = set()
        for r in cluster:
            for d in (r.get("domains") or []):
                all_domains.add(d.lower())

        # Synthesize name from common terms
        name = self._synthesize_name(cluster)

        # Merge fields (LLM intent if enabled, else merge)
        llm_intent = None
        if self._config.llm_concept_naming_enabled:
            llm_intent = self._llm_synthesize_intent(cluster)
        intent = llm_intent or self._merge_field(cluster, "why", max_chars=500)
        when_to_use = self._merge_field(cluster, "when_applies", max_chars=300)
        when_not_to_use = self._merge_field(cluster, "when_not_applies", max_chars=300)

        # Epistemic aggregation
        ep_fields = self._aggregate_epistemic(cluster)

        # Weighted average confidence
        total_weight = max(
            sum(int(r.get("reinforcement_count", 1)) for r in cluster), 1
        )
        weighted_conf = sum(
            float(r.get("confidence", 0)) * int(r.get("reinforcement_count", 1))
            for r in cluster
        ) / total_weight

        return {
            "id": pattern_id,
            "name": name,
            "category": "crystallized",
            "intent": intent,
            "when_to_use": when_to_use,
            "when_not_to_use": when_not_to_use,
            "languages": sorted(shared_techs),
            "example_good": str(best.get("example_good", "")),
            "example_bad": str(best.get("example_bad", "")),
            "related_principles": [],
            "_crystallized_from": member_ids,
            "_cluster_size": len(cluster),
            "_crystallization_confidence": weighted_conf,
            "_domains": sorted(all_domains),
            **ep_fields,
        }

    def _synthesize_name(self, cluster: list[dict[str, Any]]) -> str:
        """Synthesize pattern name — LLM-assisted or token-frequency fallback."""
        if self._config.llm_concept_naming_enabled:
            name = self._llm_synthesize_name(cluster)
            if name:
                return name
        return self._token_frequency_name(cluster)

    def _token_frequency_name(self, cluster: list[dict[str, Any]]) -> str:
        """Token-frequency pattern naming (original algorithm)."""
        all_terms: Counter[str] = Counter()
        for rule in cluster:
            text = f"{rule.get('text', '')} {rule.get('why', '')}"
            terms = _extract_terms(text)
            all_terms.update(terms)

        # Keep terms appearing in >50% of cluster members
        threshold = len(cluster) / 2
        common = [t for t, c in all_terms.most_common(10) if c > threshold]

        if common:
            return " ".join(common[:5]).title()

        # Fallback: highest-confidence rule's text
        best = max(cluster, key=lambda r: float(r.get("confidence", 0)))
        return str(best.get("text", ""))[:80]

    def _llm_synthesize_name(self, cluster: list[dict[str, Any]]) -> str | None:
        """Ask Claude to synthesize a meaningful pattern name."""
        try:
            import anthropic
            client = anthropic.Anthropic()

            rules_text = "\n".join(
                f"- {r.get('text', '')[:100]}" for r in cluster[:8]
            )
            prompt = (
                f"Given these {len(cluster)} engineering rules that were clustered together:\n"
                f"{rules_text}\n\n"
                "Synthesize a single abstract pattern name (3-7 words, Title Case) "
                "that captures the shared principle. Return ONLY the name, nothing else."
            )

            response = client.messages.create(
                model=os.getenv("CLUSTER_PROMOTER_MODEL", "claude-opus-4-6"),
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )
            name = response.content[0].text.strip()
            if 2 <= len(name.split()) <= 10:
                return name
            return None
        except Exception:
            return None

    def _llm_synthesize_intent(self, cluster: list[dict[str, Any]]) -> str | None:
        """Ask Claude for a one-sentence pattern intent."""
        try:
            import anthropic
            client = anthropic.Anthropic()

            rules_text = "\n".join(
                f"- {r.get('text', '')[:80]}. WHY: {r.get('why', '')[:80]}"
                for r in cluster[:8]
            )
            prompt = (
                f"These {len(cluster)} engineering rules share a common pattern:\n"
                f"{rules_text}\n\n"
                "Write ONE sentence describing the shared intent/principle. "
                "Be specific and actionable. Return ONLY the sentence."
            )

            response = client.messages.create(
                model=os.getenv("CLUSTER_PROMOTER_MODEL", "claude-opus-4-6"),
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception:
            return None

    def _merge_field(
        self,
        cluster: list[dict[str, Any]],
        field: str,
        max_chars: int = 500,
    ) -> str:
        """Merge a text field from all cluster members, deduplicating."""
        seen_terms: set[str] = set()
        parts: list[str] = []

        for rule in cluster:
            value = str(rule.get(field, "")).strip()
            if not value:
                continue
            # Dedup by checking term overlap with already-seen content
            terms = _extract_terms(value)
            overlap = len(terms & seen_terms) / max(len(terms), 1)
            if overlap < 0.7:  # Less than 70% overlap → add it
                parts.append(value)
                seen_terms |= terms

        merged = " | ".join(parts)
        return merged[:max_chars] if len(merged) > max_chars else merged

    def _aggregate_epistemic(self, cluster: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate epistemic opinions from cluster members."""
        members_with_ep = [
            r for r in cluster if r.get("ep_b") is not None
        ]
        if not members_with_ep:
            return {}

        # Weighted mean (weight = reinforcement_count)
        total_weight = 0.0
        sum_b = 0.0
        sum_d = 0.0
        max_u = 0.0

        for r in members_with_ep:
            w = max(int(r.get("reinforcement_count", 1)), 1)
            total_weight += w
            sum_b += float(r["ep_b"]) * w
            sum_d += float(r.get("ep_d", 0.0)) * w
            max_u = max(max_u, float(r.get("ep_u", 0.5)))

        avg_b = sum_b / total_weight
        avg_d = sum_d / total_weight
        # Conservative uncertainty: take the worst case
        # Normalize to ensure b + d + u = 1
        remaining = 1.0 - avg_b - avg_d
        ep_u = max(max_u, remaining)
        # Renormalize if needed
        total = avg_b + avg_d + ep_u
        if total > 0:
            avg_b /= total
            avg_d /= total
            ep_u /= total

        return {
            "ep_b": avg_b,
            "ep_d": avg_d,
            "ep_u": ep_u,
            "ep_a": 0.5,
        }

    def _validate_cluster_coherence(
        self,
        clusters: list[list[dict[str, Any]]],
        min_sim: float = 0.3,
    ) -> list[list[dict[str, Any]]]:
        """Remove outlier members too far from cluster centroid.

        Post-clustering quality gate: for each cluster, compute the
        centroid embedding and filter out members below min_sim.
        Falls back to keeping the cluster as-is when embeddings fail.
        """
        from engineering_brain.retrieval.embedder import cosine_similarity

        validated: list[list[dict[str, Any]]] = []
        min_cluster = self._config.crystallize_min_cluster_size

        for cluster in clusters:
            embeddings = [self._get_node_embedding(r) for r in cluster]
            valid_pairs = [(r, e) for r, e in zip(cluster, embeddings) if e]

            if len(valid_pairs) < 2:
                validated.append(cluster)  # Can't validate, keep as-is
                continue

            # Compute centroid
            dim = len(valid_pairs[0][1])
            centroid = [
                sum(e[d] for _, e in valid_pairs) / len(valid_pairs)
                for d in range(dim)
            ]

            # Filter members below similarity threshold
            filtered = [
                r for r, e in valid_pairs
                if cosine_similarity(e, centroid) >= min_sim
            ]

            if len(filtered) >= min_cluster:
                validated.append(filtered)

        return validated
