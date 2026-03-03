"""Tests for the Faceted Taxonomy DAG — Tag, TagRegistry, bootstrap, embeddings.

Tests cover:
- Tag creation and defaults
- TagRegistry registration, lookup, aliases
- Precomputed closure (ancestors, descendants)
- Facet-aware matching (match, match_flat, tag_matches)
- Overlap scoring (overlap_score, overlap_count)
- Dotted path decomposition (backward compat)
- Node tag normalization (old → new format)
- Bootstrap from TAXONOMY.yaml
- Polyhierarchy (multiple parents)
- Tag embeddings (Tier 1): indexing, semantic search, find similar
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
import yaml

_SRC = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src")
sys.path.insert(0, os.path.abspath(_SRC))

from engineering_brain.core.taxonomy import (
    DOMAIN_ROOTS,
    FACET_PREFIXES,
    FACET_WEIGHTS,
    Tag,
    TagRegistry,
    get_registry,
    set_registry,
)
from engineering_brain.core.taxonomy_bootstrap import (
    KNOWN_ALIASES,
    POLYHIERARCHY_LINKS,
    bootstrap_registry,
    discover_tags_from_nodes,
    load_taxonomy_yaml,
)


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture
def empty_registry() -> TagRegistry:
    return TagRegistry()


@pytest.fixture
def simple_registry() -> TagRegistry:
    """A small DAG for testing:

    python
    ├── flask (parents: [python, microframework])
    │   └── flask_cors (parents: [flask, cors])
    └── django (parents: [python])

    cors (facet: concern)
    microframework (facet: pattern)
    security (facet: domain)
    """
    r = TagRegistry()
    r.register_batch([
        Tag(id="python", facet="lang"),
        Tag(id="microframework", facet="pattern"),
        Tag(id="security", facet="domain"),
        Tag(id="cors", facet="concern", parents=["security"]),
        Tag(id="flask", facet="framework", parents=["python", "microframework"]),
        Tag(id="django", facet="framework", parents=["python"]),
        Tag(id="flask_cors", facet="concern", parents=["flask", "cors"]),
    ])
    r.ensure_closure()
    return r


@pytest.fixture
def taxonomy_dir() -> str:
    """Create a temp dir with a minimal TAXONOMY.yaml for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        taxonomy = {
            "domains": {
                "security": {
                    "authentication": {
                        "oauth": {},
                        "jwt": {},
                    },
                    "network": {
                        "cors": {},
                        "tls": {},
                    },
                },
                "reliability": {
                    "availability": {},
                    "fault_tolerance": {},
                },
            },
            "technologies": {
                "language": {
                    "python": {
                        "web": {
                            "flask": {},
                            "django": {},
                        },
                        "testing": {
                            "pytest": {},
                        },
                    },
                    "javascript": {
                        "react": {},
                    },
                },
                "database": {
                    "postgresql": {},
                    "redis": {},
                },
            },
        }
        path = os.path.join(tmpdir, "TAXONOMY.yaml")
        with open(path, "w") as f:
            yaml.dump(taxonomy, f)
        yield tmpdir


# =====================================================================
# Tag dataclass
# =====================================================================

class TestTag:
    def test_defaults(self):
        t = Tag(id="python", facet="lang")
        assert t.id == "python"
        assert t.facet == "lang"
        assert t.display_name == "python"  # defaults to id
        assert t.parents == []
        assert t.children == []
        assert t.aliases == []
        assert t.weight == 1.0

    def test_display_name_override(self):
        t = Tag(id="python", facet="lang", display_name="Python 3")
        assert t.display_name == "Python 3"

    def test_parents_and_aliases(self):
        t = Tag(id="flask", facet="framework", parents=["python"], aliases=["flask-app"])
        assert t.parents == ["python"]
        assert t.aliases == ["flask-app"]


# =====================================================================
# TagRegistry — Registration & Lookup
# =====================================================================

class TestRegistryRegistration:
    def test_register_single(self, empty_registry: TagRegistry):
        r = empty_registry
        r.register(Tag(id="Python", facet="lang"))
        assert r.size == 1
        assert r.get("python") is not None
        assert r.get("PYTHON") is not None  # case-insensitive

    def test_register_batch(self, empty_registry: TagRegistry):
        r = empty_registry
        r.register_batch([
            Tag(id="python", facet="lang"),
            Tag(id="flask", facet="framework"),
        ])
        assert r.size == 2

    def test_register_merges_parents(self, empty_registry: TagRegistry):
        r = empty_registry
        r.register(Tag(id="flask", facet="framework", parents=["python"]))
        r.register(Tag(id="flask", facet="framework", parents=["microframework"]))
        tag = r.get("flask")
        assert tag is not None
        assert "python" in tag.parents
        assert "microframework" in tag.parents

    def test_register_merges_aliases(self, empty_registry: TagRegistry):
        r = empty_registry
        r.register(Tag(id="python", facet="lang", aliases=["py"]))
        r.register(Tag(id="python", facet="lang", aliases=["python3"]))
        tag = r.get("python")
        assert "py" in tag.aliases
        assert "python3" in tag.aliases

    def test_resolve_by_id(self, simple_registry: TagRegistry):
        assert simple_registry.resolve("flask") is not None
        assert simple_registry.resolve("Flask") is not None

    def test_resolve_by_alias(self, empty_registry: TagRegistry):
        r = empty_registry
        r.register(Tag(id="python", facet="lang", aliases=["py", "python3"]))
        tag = r.resolve("py")
        assert tag is not None
        assert tag.id == "python"

    def test_resolve_display_name(self, empty_registry: TagRegistry):
        r = empty_registry
        r.register(Tag(id="python", facet="lang", display_name="Python"))
        assert r.resolve("Python") is not None

    def test_resolve_underscore_hyphen_variants(self, empty_registry: TagRegistry):
        r = empty_registry
        r.register(Tag(id="flask_cors", facet="concern"))
        assert r.resolve("flask-cors") is not None

    def test_resolve_nonexistent(self, simple_registry: TagRegistry):
        assert simple_registry.resolve("nonexistent_xyz") is None

    def test_tags_by_facet(self, simple_registry: TagRegistry):
        langs = simple_registry.tags_by_facet("lang")
        assert len(langs) == 1
        assert langs[0].id == "python"

        frameworks = simple_registry.tags_by_facet("framework")
        assert len(frameworks) == 2

    def test_all_tags(self, simple_registry: TagRegistry):
        assert len(simple_registry.all_tags()) == 7


# =====================================================================
# Precomputed Closure (ancestors, descendants)
# =====================================================================

class TestClosure:
    def test_ancestors_of_flask(self, simple_registry: TagRegistry):
        anc = simple_registry.ancestors("flask")
        assert "python" in anc
        assert "microframework" in anc
        assert "django" not in anc

    def test_ancestors_of_flask_cors(self, simple_registry: TagRegistry):
        anc = simple_registry.ancestors("flask_cors")
        assert "flask" in anc
        assert "cors" in anc
        assert "python" in anc       # transitive
        assert "security" in anc     # transitive (cors → security)
        assert "microframework" in anc  # transitive (flask → microframework)

    def test_descendants_of_python(self, simple_registry: TagRegistry):
        desc = simple_registry.descendants("python")
        assert "flask" in desc
        assert "django" in desc
        assert "flask_cors" in desc  # transitive

    def test_descendants_of_cors(self, simple_registry: TagRegistry):
        desc = simple_registry.descendants("cors")
        assert "flask_cors" in desc

    def test_descendants_of_security(self, simple_registry: TagRegistry):
        desc = simple_registry.descendants("security")
        assert "cors" in desc
        assert "flask_cors" in desc  # transitive

    def test_is_ancestor_of(self, simple_registry: TagRegistry):
        assert simple_registry.is_ancestor_of("python", "flask")
        assert simple_registry.is_ancestor_of("python", "flask_cors")
        assert not simple_registry.is_ancestor_of("flask", "python")
        assert not simple_registry.is_ancestor_of("django", "flask")

    def test_leaf_has_no_descendants(self, simple_registry: TagRegistry):
        desc = simple_registry.descendants("flask_cors")
        assert len(desc) == 0

    def test_root_has_no_ancestors(self, simple_registry: TagRegistry):
        anc = simple_registry.ancestors("python")
        assert len(anc) == 0

    def test_closure_auto_rebuilds(self, empty_registry: TagRegistry):
        r = empty_registry
        r.register(Tag(id="a", facet="lang"))
        r.register(Tag(id="b", facet="lang", parents=["a"]))
        assert "a" in r.ancestors("b")  # triggers ensure_closure
        # Add new tag — closure should be dirty
        r.register(Tag(id="c", facet="lang", parents=["b"]))
        assert "a" in r.ancestors("c")  # transitive
        assert "b" in r.ancestors("c")

    def test_children_are_computed(self, simple_registry: TagRegistry):
        python_tag = simple_registry.get("python")
        assert "flask" in python_tag.children
        assert "django" in python_tag.children


# =====================================================================
# Matching
# =====================================================================

class TestMatching:
    def test_tag_matches_exact(self, simple_registry: TagRegistry):
        assert simple_registry.tag_matches("flask", "flask")

    def test_tag_matches_ancestor(self, simple_registry: TagRegistry):
        # query "python" should match node tagged "flask" (python is ancestor)
        assert simple_registry.tag_matches("python", "flask")

    def test_tag_matches_descendant(self, simple_registry: TagRegistry):
        # query "flask" should match node tagged "python" (flask is descendant)
        assert simple_registry.tag_matches("flask", "python")

    def test_tag_matches_no_relation(self, simple_registry: TagRegistry):
        assert not simple_registry.tag_matches("django", "flask")

    def test_match_faceted(self, simple_registry: TagRegistry):
        query = {"lang": ["python"]}
        node = {"framework": ["flask"]}
        # Different facets, but flask has python as ancestor → match via tag_matches
        # However, match() only compares within same facet
        assert not simple_registry.match(query, node)

        # Same facet match
        query2 = {"framework": ["python"]}
        node2 = {"framework": ["flask"]}
        assert simple_registry.match(query2, node2)

    def test_match_flat(self, simple_registry: TagRegistry):
        assert simple_registry.match_flat(["python"], ["flask"])
        assert simple_registry.match_flat(["security"], ["flask_cors"])
        assert not simple_registry.match_flat(["django"], ["flask"])

    def test_match_cross_hierarchy(self, simple_registry: TagRegistry):
        # cors → security, flask_cors → cors AND flask
        assert simple_registry.match_flat(["cors"], ["flask_cors"])
        assert simple_registry.match_flat(["security"], ["flask_cors"])

    def test_overlap_count(self, simple_registry: TagRegistry):
        assert simple_registry.overlap_count(["python"], ["flask"]) == 1
        assert simple_registry.overlap_count(["python", "security"], ["flask_cors"]) == 2
        assert simple_registry.overlap_count(["django"], ["flask"]) == 0

    def test_overlap_count_no_double_count(self, simple_registry: TagRegistry):
        # "python" matches "flask" once, not twice
        assert simple_registry.overlap_count(["python"], ["flask", "django"]) == 1

    def test_overlap_score_basic(self, simple_registry: TagRegistry):
        query = {"lang": ["python"]}
        node = {"lang": ["python"]}
        score = simple_registry.overlap_score(query, node)
        assert score == pytest.approx(1.0)

    def test_overlap_score_no_match(self, simple_registry: TagRegistry):
        query = {"lang": ["python"]}
        node = {"domain": ["security"]}
        score = simple_registry.overlap_score(query, node)
        assert score == pytest.approx(0.0)

    def test_overlap_score_partial(self, simple_registry: TagRegistry):
        query = {"lang": ["python"], "domain": ["security"]}
        node = {"lang": ["python"]}  # matches lang but not domain
        score = simple_registry.overlap_score(query, node)
        assert 0.0 < score < 1.0


# =====================================================================
# Dotted path decomposition
# =====================================================================

class TestDecomposeDottedPath:
    def test_known_tag(self, simple_registry: TagRegistry):
        result = simple_registry.decompose_dotted_path("flask")
        assert result == {"framework": ["flask"]}

    def test_language_prefix(self, simple_registry: TagRegistry):
        # "language.python" → strips "language" prefix, resolves "python"
        result = simple_registry.decompose_dotted_path("language.python")
        assert "lang" in result
        assert "python" in result["lang"]

    def test_domain_root(self, simple_registry: TagRegistry):
        result = simple_registry.decompose_dotted_path("security")
        assert result == {"domain": ["security"]}

    def test_domain_path(self, simple_registry: TagRegistry):
        result = simple_registry.decompose_dotted_path("security.cors")
        assert "domain" in result
        assert "security" in result["domain"]
        # cors is a known tag in "concern" facet
        assert "concern" in result
        assert "cors" in result["concern"]

    def test_unknown_single(self, simple_registry: TagRegistry):
        result = simple_registry.decompose_dotted_path("unknown_thing_xyz")
        assert "unknown" in result

    def test_unknown_multi(self, simple_registry: TagRegistry):
        result = simple_registry.decompose_dotted_path("totally.unknown.path")
        # All segments unknown → all go to unknown facet
        assert "unknown" in result


# =====================================================================
# Node tag normalization
# =====================================================================

class TestNormalizeNodeTags:
    def test_new_format_passthrough(self, simple_registry: TagRegistry):
        node = {"tags": {"lang": ["python"], "domain": ["security"]}}
        result = simple_registry.normalize_node_tags(node)
        assert result == {"lang": ["python"], "domain": ["security"]}

    def test_new_format_string_values(self, simple_registry: TagRegistry):
        node = {"tags": {"lang": "python"}}
        result = simple_registry.normalize_node_tags(node)
        assert result == {"lang": ["python"]}

    def test_old_format_technologies(self, simple_registry: TagRegistry):
        node = {"technologies": ["flask"], "domains": ["security"]}
        result = simple_registry.normalize_node_tags(node)
        assert "framework" in result
        assert "flask" in result["framework"]
        assert "domain" in result
        assert "security" in result["domain"]

    def test_empty_node(self, simple_registry: TagRegistry):
        result = simple_registry.normalize_node_tags({})
        assert result == {}


# =====================================================================
# Bootstrap
# =====================================================================

class TestBootstrap:
    def test_load_taxonomy_yaml(self, taxonomy_dir: str):
        tags = load_taxonomy_yaml(taxonomy_dir)
        assert len(tags) > 0
        # Should have domain tags
        ids = {t.id for t in tags}
        assert "security" in ids
        assert "authentication" in ids
        assert "oauth" in ids
        assert "reliability" in ids
        # Should have technology tags
        assert "python" in ids
        assert "flask" in ids
        assert "postgresql" in ids

    def test_load_taxonomy_yaml_missing(self):
        tags = load_taxonomy_yaml("/nonexistent/path")
        assert tags == []

    def test_bootstrap_creates_registry(self, taxonomy_dir: str):
        registry = bootstrap_registry(taxonomy_dir)
        assert registry.size > 0
        assert registry.get("security") is not None
        assert registry.get("python") is not None

    def test_bootstrap_closure_works(self, taxonomy_dir: str):
        registry = bootstrap_registry(taxonomy_dir)
        # authentication → security (parent)
        assert registry.is_ancestor_of("security", "authentication")
        # oauth → authentication → security
        assert registry.is_ancestor_of("security", "oauth")

    def test_bootstrap_with_nodes(self, taxonomy_dir: str):
        nodes = [
            {"technologies": ["framework.python.fastapi"], "domains": ["security"]},
        ]
        registry = bootstrap_registry(taxonomy_dir, nodes)
        # fastapi should exist (discovered from node data)
        assert registry.get("fastapi") is not None

    def test_bootstrap_technology_facets(self, taxonomy_dir: str):
        registry = bootstrap_registry(taxonomy_dir)
        python = registry.get("python")
        assert python is not None
        assert python.facet == "lang"
        pg = registry.get("postgresql")
        assert pg is not None
        assert pg.facet == "platform"

    def test_bootstrap_stats(self, taxonomy_dir: str):
        registry = bootstrap_registry(taxonomy_dir)
        stats = registry.stats()
        assert stats["total_tags"] > 0
        assert stats["aliases"] >= 0
        assert stats["max_ancestor_depth"] >= 1


# =====================================================================
# Discover tags from nodes
# =====================================================================

class TestDiscoverFromNodes:
    def test_discover_creates_new_tags(self, simple_registry: TagRegistry):
        nodes = [
            {"technologies": ["language.python.web.starlette"]},
        ]
        new_tags = discover_tags_from_nodes(nodes, simple_registry)
        # Should have created tags for unknown segments
        ids = {t.id for t in new_tags}
        assert "starlette" in ids

    def test_discover_no_duplicates(self, simple_registry: TagRegistry):
        nodes = [
            {"technologies": ["flask"]},
            {"technologies": ["flask"]},
        ]
        new_tags = discover_tags_from_nodes(nodes, simple_registry)
        # flask already exists → should not create a new one
        flask_tags = [t for t in new_tags if t.id == "flask"]
        assert len(flask_tags) == 0

    def test_discover_processes_domains(self, simple_registry: TagRegistry):
        nodes = [
            {"domains": ["security.authentication.oauth"]},
        ]
        new_tags = discover_tags_from_nodes(nodes, simple_registry)
        ids = {t.id for t in new_tags}
        assert "authentication" in ids or "oauth" in ids


# =====================================================================
# Module-level singleton
# =====================================================================

class TestSingleton:
    def test_get_creates_empty(self):
        set_registry(None)
        r = get_registry()
        assert r is not None
        assert r.size == 0

    def test_set_and_get(self, simple_registry: TagRegistry):
        set_registry(simple_registry)
        r = get_registry()
        assert r.size == simple_registry.size
        # Cleanup
        set_registry(None)


# =====================================================================
# Edge cases
# =====================================================================

class TestEdgeCases:
    def test_cycle_detection(self, empty_registry: TagRegistry):
        """DAG should handle cycles gracefully (BFS terminates)."""
        r = empty_registry
        r.register(Tag(id="a", facet="lang", parents=["b"]))
        r.register(Tag(id="b", facet="lang", parents=["a"]))
        # Should not hang — BFS terminates because visited set prevents re-entry
        anc = r.ancestors("a")
        assert "b" in anc

    def test_missing_parent_reference(self, empty_registry: TagRegistry):
        """Tags referencing non-existent parents should work."""
        r = empty_registry
        r.register(Tag(id="child", facet="lang", parents=["nonexistent"]))
        r.ensure_closure()
        # Should have no ancestors (parent doesn't exist)
        assert len(r.ancestors("child")) == 0

    def test_empty_registry_operations(self, empty_registry: TagRegistry):
        r = empty_registry
        assert r.size == 0
        assert r.resolve("anything") is None
        assert r.ancestors("anything") == frozenset()
        assert r.descendants("anything") == frozenset()
        assert not r.match_flat(["a"], ["b"])
        assert r.overlap_count(["a"], ["b"]) == 0

    def test_case_insensitivity(self, empty_registry: TagRegistry):
        r = empty_registry
        r.register(Tag(id="Python", facet="lang"))
        assert r.get("python") is not None
        assert r.get("PYTHON") is not None
        assert r.resolve("python") is not None

    def test_large_dag_performance(self, empty_registry: TagRegistry):
        """Build a DAG with 1000 tags and verify closure finishes fast."""
        r = empty_registry
        tags = [Tag(id="root", facet="lang")]
        for i in range(999):
            tags.append(Tag(
                id=f"tag_{i}",
                facet="lang",
                parents=["root" if i < 50 else f"tag_{i % 50}"],
            ))
        r.register_batch(tags)
        r.ensure_closure()
        assert r.size == 1000
        # root should have many descendants
        desc = r.descendants("root")
        assert len(desc) > 50


# =====================================================================
# Constants
# =====================================================================

class TestConstants:
    def test_facet_weights_sum_to_one(self):
        total = sum(FACET_WEIGHTS.values())
        assert total == pytest.approx(1.0)

    def test_domain_roots_nonempty(self):
        assert len(DOMAIN_ROOTS) > 10

    def test_facet_prefixes_nonempty(self):
        assert len(FACET_PREFIXES) > 5

    def test_known_aliases_valid(self):
        for tag_id, aliases in KNOWN_ALIASES.items():
            assert isinstance(aliases, list)
            assert len(aliases) > 0


# =====================================================================
# Tier 1 — Tag Embeddings
# =====================================================================

class _MockVectorAdapter:
    """Mock Qdrant vector adapter for testing."""

    def __init__(self):
        self._collections: dict[str, dict] = {}

    def ensure_collection(self, name: str, dim: int) -> None:
        self._collections[name] = {"dim": dim, "points": {}}

    def upsert(self, collection: str, id: str, text: str, vec: list[float], metadata: dict) -> None:
        if collection not in self._collections:
            self._collections[collection] = {"dim": len(vec), "points": {}}
        self._collections[collection]["points"][id] = {
            "text": text, "vec": vec, "metadata": metadata,
        }

    def search(self, collection: str, vec: list[float], top_k: int = 5,
               filters: dict | None = None, score_threshold: float = 0.0) -> list[dict]:
        if collection not in self._collections:
            return []
        points = self._collections[collection]["points"]
        results = []
        for pid, pdata in points.items():
            # Simple dot product as mock similarity
            score = sum(a * b for a, b in zip(vec[:4], pdata["vec"][:4]))
            if filters:
                if not all(pdata["metadata"].get(k) == v for k, v in filters.items()):
                    continue
            if score >= score_threshold:
                results.append({"id": pid, "score": score, "text": pdata["text"]})
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]


class _MockConfig:
    embedding_dimension = 8


class _MockEmbedder:
    """Mock BrainEmbedder for testing tag embeddings."""

    def __init__(self, vector=None, fail_embed=False):
        self._vector = vector or _MockVectorAdapter()
        self._config = _MockConfig()
        self._fail_embed = fail_embed

    def embed_text(self, text: str) -> list[float] | None:
        if self._fail_embed:
            return None
        # Deterministic embedding from text hash
        h = hash(text) % 10000
        return [float((h >> i) & 1) for i in range(8)]

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        if self._fail_embed:
            raise RuntimeError("embed failed")
        return [self.embed_text(t) for t in texts]


class TestTagEmbeddingIndex:
    """Tests for TagEmbeddingIndex (Tier 1)."""

    def _make_registry(self) -> TagRegistry:
        """Build a small registry for embedding tests."""
        reg = TagRegistry()
        reg.register(Tag(id="python", facet="lang", display_name="Python"))
        reg.register(Tag(id="javascript", facet="lang", display_name="JavaScript"))
        reg.register(Tag(id="flask", facet="framework", display_name="Flask",
                         parents=["python"], description="Micro web framework"))
        reg.register(Tag(id="django", facet="framework", display_name="Django",
                         parents=["python"], description="Full-stack web framework"))
        reg.register(Tag(id="react", facet="framework", display_name="React",
                         parents=["javascript"], description="UI library"))
        reg.register(Tag(id="xss", facet="concern", display_name="XSS",
                         aliases=["cross-site scripting"]))
        reg.register(Tag(id="csrf", facet="concern", display_name="CSRF",
                         aliases=["cross-site request forgery"]))
        reg.register(Tag(id="cors", facet="concern", display_name="CORS"))
        reg.ensure_closure()
        return reg

    def test_index_all_creates_embeddings(self):
        from engineering_brain.retrieval.tag_embeddings import TagEmbeddingIndex

        reg = self._make_registry()
        vector = _MockVectorAdapter()
        embedder = _MockEmbedder(vector=vector)
        idx = TagEmbeddingIndex(embedder, reg)

        stats = idx.index_all(batch_size=3)

        assert stats["indexed"] == 8  # All 8 tags
        assert stats["skipped"] == 0
        assert stats["failed"] == 0
        assert idx.is_indexed
        assert "brain_tags" in vector._collections
        assert len(vector._collections["brain_tags"]["points"]) == 8

    def test_index_all_empty_registry(self):
        from engineering_brain.retrieval.tag_embeddings import TagEmbeddingIndex

        reg = TagRegistry()
        embedder = _MockEmbedder()
        idx = TagEmbeddingIndex(embedder, reg)

        stats = idx.index_all()

        assert stats["indexed"] == 0
        assert not idx.is_indexed

    def test_index_all_no_embedder(self):
        from engineering_brain.retrieval.tag_embeddings import TagEmbeddingIndex

        reg = self._make_registry()
        idx = TagEmbeddingIndex(None, reg)

        stats = idx.index_all()

        assert stats["indexed"] == 0
        assert not idx.is_indexed

    def test_index_all_embed_failure_graceful(self):
        from engineering_brain.retrieval.tag_embeddings import TagEmbeddingIndex

        reg = self._make_registry()
        embedder = _MockEmbedder(fail_embed=True)
        idx = TagEmbeddingIndex(embedder, reg)

        stats = idx.index_all(batch_size=5)

        assert stats["indexed"] == 0
        assert stats["failed"] == 8
        assert not idx.is_indexed

    def test_semantic_search_returns_tags(self):
        from engineering_brain.retrieval.tag_embeddings import TagEmbeddingIndex

        reg = self._make_registry()
        vector = _MockVectorAdapter()
        embedder = _MockEmbedder(vector=vector)
        idx = TagEmbeddingIndex(embedder, reg)
        idx.index_all(batch_size=20)

        results = idx.semantic_search("web framework", top_k=3)

        assert isinstance(results, list)
        assert all(isinstance(t, Tag) for t in results)
        assert len(results) <= 3

    def test_semantic_search_with_facet_filter(self):
        from engineering_brain.retrieval.tag_embeddings import TagEmbeddingIndex

        reg = self._make_registry()
        vector = _MockVectorAdapter()
        embedder = _MockEmbedder(vector=vector)
        idx = TagEmbeddingIndex(embedder, reg)
        idx.index_all(batch_size=20)

        results = idx.semantic_search("Python", facet="lang", top_k=5)

        # All results should be lang facet
        for tag in results:
            assert tag.facet == "lang"

    def test_semantic_search_not_indexed(self):
        from engineering_brain.retrieval.tag_embeddings import TagEmbeddingIndex

        reg = self._make_registry()
        embedder = _MockEmbedder()
        idx = TagEmbeddingIndex(embedder, reg)
        # Don't call index_all

        results = idx.semantic_search("anything")
        assert results == []

    def test_find_similar_tags(self):
        from engineering_brain.retrieval.tag_embeddings import TagEmbeddingIndex

        reg = self._make_registry()
        vector = _MockVectorAdapter()
        embedder = _MockEmbedder(vector=vector)
        idx = TagEmbeddingIndex(embedder, reg)
        idx.index_all(batch_size=20)

        results = idx.find_similar_tags("flask", top_k=3)

        assert isinstance(results, list)
        assert len(results) <= 3
        # Should not include flask itself
        for tag_id, score in results:
            assert tag_id != "flask"
            assert isinstance(score, (int, float))

    def test_find_similar_tags_unknown_tag(self):
        from engineering_brain.retrieval.tag_embeddings import TagEmbeddingIndex

        reg = self._make_registry()
        embedder = _MockEmbedder()
        idx = TagEmbeddingIndex(embedder, reg)
        idx.index_all(batch_size=20)

        results = idx.find_similar_tags("nonexistent")
        assert results == []

    def test_singleton_get_set(self):
        from engineering_brain.retrieval.tag_embeddings import (
            TagEmbeddingIndex, get_tag_index, set_tag_index,
        )

        reg = self._make_registry()
        embedder = _MockEmbedder()
        idx = TagEmbeddingIndex(embedder, reg)

        set_tag_index(idx)
        assert get_tag_index() is idx

        set_tag_index(None)
        assert get_tag_index() is None

    def test_tag_to_text_includes_facet_and_name(self):
        from engineering_brain.retrieval.tag_embeddings import _tag_to_text

        reg = self._make_registry()
        tag = reg.get("flask")
        text = _tag_to_text(tag, reg)

        assert "framework" in text
        assert "Flask" in text
        assert "Python" in text  # parent name
        assert "Micro web framework" in text  # description

    def test_tag_to_text_includes_aliases(self):
        from engineering_brain.retrieval.tag_embeddings import _tag_to_text

        reg = self._make_registry()
        tag = reg.get("xss")
        text = _tag_to_text(tag, reg)

        assert "cross-site scripting" in text
        assert "Also known as" in text

    def test_batch_processing_respects_batch_size(self):
        from engineering_brain.retrieval.tag_embeddings import TagEmbeddingIndex

        reg = self._make_registry()
        vector = _MockVectorAdapter()
        embedder = _MockEmbedder(vector=vector)
        idx = TagEmbeddingIndex(embedder, reg)

        # Batch size 2 should still index all 8 tags
        stats = idx.index_all(batch_size=2)
        assert stats["indexed"] == 8


# =====================================================================
# Tier 2 — Taxonomy Auto-Expansion
# =====================================================================

class TestTaxonomyExpander:
    """Tests for TaxonomyExpander (Tier 2)."""

    def _make_indexed_setup(self):
        """Build a registry + embedding index for expansion tests."""
        from engineering_brain.retrieval.tag_embeddings import TagEmbeddingIndex

        reg = TagRegistry()
        reg.register(Tag(id="python", facet="lang", display_name="Python"))
        reg.register(Tag(id="javascript", facet="lang", display_name="JavaScript"))
        reg.register(Tag(id="flask", facet="framework", display_name="Flask",
                         parents=["python"], description="Micro web framework"))
        reg.register(Tag(id="django", facet="framework", display_name="Django",
                         parents=["python"], description="Full-stack web framework"))
        reg.register(Tag(id="react", facet="framework", display_name="React",
                         parents=["javascript"], description="UI library"))
        reg.register(Tag(id="express", facet="framework", display_name="Express",
                         parents=["javascript"], description="Node.js web framework",
                         aliases=["expressjs"]))
        reg.register(Tag(id="web_security", facet="domain", display_name="Web Security"))
        reg.register(Tag(id="xss", facet="concern", display_name="XSS",
                         parents=["web_security"]))
        reg.ensure_closure()

        vector = _MockVectorAdapter()
        embedder = _MockEmbedder(vector=vector)
        idx = TagEmbeddingIndex(embedder, reg)
        idx.index_all(batch_size=20)
        return reg, idx

    def test_expand_resolves_alias_first(self):
        from engineering_brain.retrieval.taxonomy_expander import TaxonomyExpander

        reg, idx = self._make_indexed_setup()
        expander = TaxonomyExpander(reg, idx)

        # "expressjs" is an alias for "express"
        result = expander.expand_unknown("expressjs")

        assert result is not None
        assert result.id == "express"

    def test_expand_unknown_creates_tag(self):
        from engineering_brain.retrieval.taxonomy_expander import TaxonomyExpander

        reg, idx = self._make_indexed_setup()
        expander = TaxonomyExpander(reg, idx)
        original_size = reg.size

        result = expander.expand_unknown("svelte", facet_hint="framework")

        assert result is not None
        assert result.id == "svelte"
        assert result.facet == "framework"
        assert reg.size == original_size + 1
        assert reg.get("svelte") is not None

    def test_expand_unknown_without_embeddings(self):
        from engineering_brain.retrieval.taxonomy_expander import TaxonomyExpander

        reg = TagRegistry()
        reg.register(Tag(id="python", facet="lang", display_name="Python"))
        reg.ensure_closure()

        expander = TaxonomyExpander(reg, None)
        result = expander.expand_unknown("rust", facet_hint="lang")

        assert result is not None
        assert result.id == "rust"
        assert result.facet == "lang"
        assert result.weight == 0.3  # Orphan weight

    def test_expand_empty_text(self):
        from engineering_brain.retrieval.taxonomy_expander import TaxonomyExpander

        reg, idx = self._make_indexed_setup()
        expander = TaxonomyExpander(reg, idx)

        result = expander.expand_unknown("")
        assert result is None

        result = expander.expand_unknown("   ")
        assert result is None

    def test_expand_existing_tag_returns_existing(self):
        from engineering_brain.retrieval.taxonomy_expander import TaxonomyExpander

        reg, idx = self._make_indexed_setup()
        expander = TaxonomyExpander(reg, idx)

        result = expander.expand_unknown("python")

        assert result is not None
        assert result.id == "python"

    def test_suggest_polyhierarchy_links(self):
        from engineering_brain.retrieval.taxonomy_expander import TaxonomyExpander

        reg, idx = self._make_indexed_setup()
        expander = TaxonomyExpander(reg, idx)

        suggestions = expander.suggest_polyhierarchy_links(
            min_similarity=0.0,  # Low threshold to get some results
            batch_size=5,
        )

        assert isinstance(suggestions, list)
        for child_id, parent_id, score in suggestions:
            assert isinstance(child_id, str)
            assert isinstance(parent_id, str)
            assert isinstance(score, (int, float))
            assert child_id != parent_id

    def test_suggest_polyhierarchy_no_index(self):
        from engineering_brain.retrieval.taxonomy_expander import TaxonomyExpander

        reg = TagRegistry()
        expander = TaxonomyExpander(reg, None)

        suggestions = expander.suggest_polyhierarchy_links()
        assert suggestions == []

    def test_apply_suggestions_respects_threshold(self):
        from engineering_brain.retrieval.taxonomy_expander import TaxonomyExpander

        reg, idx = self._make_indexed_setup()
        expander = TaxonomyExpander(reg, idx)

        # Create suggestions with varying scores
        suggestions = [
            ("react", "python", 0.9),   # High confidence
            ("xss", "python", 0.5),     # Below threshold
        ]

        applied = expander.apply_suggestions(suggestions, min_confidence=0.8)

        # Only the high-confidence one should be applied
        assert applied == 1
        react = reg.get("react")
        assert "python" in react.parents

    def test_apply_suggestions_prevents_cycles(self):
        from engineering_brain.retrieval.taxonomy_expander import TaxonomyExpander

        reg, idx = self._make_indexed_setup()
        expander = TaxonomyExpander(reg, idx)

        # flask's ancestor is python — adding python as child of flask would cycle
        suggestions = [("python", "flask", 0.95)]

        applied = expander.apply_suggestions(suggestions, min_confidence=0.8)
        assert applied == 0

    def test_vote_facet(self):
        from engineering_brain.retrieval.taxonomy_expander import TaxonomyExpander

        reg, idx = self._make_indexed_setup()
        expander = TaxonomyExpander(reg, idx)

        neighbors = [
            Tag(id="a", facet="framework"),
            Tag(id="b", facet="framework"),
            Tag(id="c", facet="lang"),
        ]
        assert expander._vote_facet(neighbors) == "framework"

    def test_vote_parents(self):
        from engineering_brain.retrieval.taxonomy_expander import TaxonomyExpander

        reg, idx = self._make_indexed_setup()
        expander = TaxonomyExpander(reg, idx)

        neighbors = [
            Tag(id="a", facet="framework", parents=["python"]),
            Tag(id="b", facet="framework", parents=["python", "web"]),
            Tag(id="c", facet="framework", parents=["javascript"]),
        ]
        parents = expander._vote_parents(neighbors)
        assert "python" in parents  # Most common parent

    def test_singleton_get_set(self):
        from engineering_brain.retrieval.taxonomy_expander import (
            TaxonomyExpander, get_expander, set_expander,
        )

        reg, idx = self._make_indexed_setup()
        expander = TaxonomyExpander(reg, idx)

        set_expander(expander)
        assert get_expander() is expander

        set_expander(None)
        assert get_expander() is None


# =====================================================================
# Tier 3a — HAKE Hierarchy-Aware Embeddings
# =====================================================================

class TestHAKEEncoder:
    """Tests for HAKEEncoder (Tier 3a)."""

    def _make_registry(self) -> TagRegistry:
        reg = TagRegistry()
        reg.register(Tag(id="python", facet="lang", display_name="Python"))
        reg.register(Tag(id="flask", facet="framework", display_name="Flask",
                         parents=["python"]))
        reg.register(Tag(id="django", facet="framework", display_name="Django",
                         parents=["python"]))
        reg.register(Tag(id="flask_cors", facet="library", display_name="Flask-CORS",
                         parents=["flask"]))
        reg.ensure_closure()
        return reg

    def test_modulus_encodes_depth(self):
        from engineering_brain.retrieval.hake_embeddings import HAKEEncoder

        reg = self._make_registry()
        enc = HAKEEncoder(reg, base_dim=4)

        # Root tag (depth 0) should have highest modulus
        vec_root = enc.encode_tag("python", [1.0, 0.0, 0.0, 0.0])
        # Depth 1 tag
        vec_mid = enc.encode_tag("flask", [1.0, 0.0, 0.0, 0.0])
        # Depth 2 tag
        vec_deep = enc.encode_tag("flask_cors", [1.0, 0.0, 0.0, 0.0])

        # Last 4 elements: [modulus, sin(phase), cos(phase), depth_norm]
        modulus_root = vec_root[-4]
        modulus_mid = vec_mid[-4]
        modulus_deep = vec_deep[-4]

        assert modulus_root > modulus_mid > modulus_deep

    def test_phase_siblings_close(self):
        import math
        from engineering_brain.retrieval.hake_embeddings import HAKEEncoder

        reg = self._make_registry()
        enc = HAKEEncoder(reg, base_dim=4)

        # flask and django are siblings (both children of python)
        vec_flask = enc.encode_tag("flask", [0.0] * 4)
        vec_django = enc.encode_tag("django", [0.0] * 4)

        # Extract phase components (sin, cos)
        sin_f, cos_f = vec_flask[-3], vec_flask[-2]
        sin_d, cos_d = vec_django[-3], vec_django[-2]

        # Siblings should have different but structured phases
        # Phase distance should be finite (not inf)
        phase_dist = math.sqrt((sin_f - sin_d) ** 2 + (cos_f - cos_d) ** 2)
        assert phase_dist < 3.0  # Less than max possible (2*sqrt(2))

    def test_hierarchy_distance_parent_child(self):
        from engineering_brain.retrieval.hake_embeddings import HAKEEncoder

        reg = self._make_registry()
        enc = HAKEEncoder(reg, base_dim=4)

        # Use same semantic vectors — test hierarchy component only
        sem = [1.0, 0.5, 0.3, 0.1]
        vec_python = enc.encode_tag("python", sem)
        vec_flask = enc.encode_tag("flask", sem)
        vec_cors = enc.encode_tag("flask_cors", sem)

        # Modulus should strictly decrease with depth
        mod_python = vec_python[-4]
        mod_flask = vec_flask[-4]
        mod_cors = vec_cors[-4]
        assert mod_python > mod_flask > mod_cors

        # Depth norm should strictly increase with depth
        depth_python = vec_python[-1]
        depth_flask = vec_flask[-1]
        depth_cors = vec_cors[-1]
        assert depth_python < depth_flask < depth_cors

    def test_encode_unknown_tag(self):
        from engineering_brain.retrieval.hake_embeddings import HAKEEncoder

        reg = self._make_registry()
        enc = HAKEEncoder(reg, base_dim=4)

        vec = enc.encode_tag("nonexistent", [1.0, 2.0, 3.0, 4.0])

        # Should have 4 semantic + 4 HAKE = 8 dims
        assert len(vec) == 8
        # HAKE part should be zeros for unknown tag
        assert vec[-4:] == [0.0, 0.0, 0.0, 0.0]

    def test_encode_all_with_mock_embedder(self):
        from engineering_brain.retrieval.hake_embeddings import HAKEEncoder

        reg = self._make_registry()
        enc = HAKEEncoder(reg, base_dim=8)
        embedder = _MockEmbedder()

        stats = enc.encode_all(embedder, batch_size=2)

        assert stats["encoded"] == 4  # 4 tags in registry
        assert stats["skipped"] == 0
        assert stats["failed"] == 0

        # Should be able to retrieve HAKE vectors
        vec = enc.get_hake_vector("flask")
        assert vec is not None
        assert len(vec) == 12  # 8 semantic + 4 HAKE

    def test_encode_all_no_embedder(self):
        from engineering_brain.retrieval.hake_embeddings import HAKEEncoder

        reg = self._make_registry()
        enc = HAKEEncoder(reg, base_dim=8)

        stats = enc.encode_all(None)
        assert stats["encoded"] == 0

    def test_encode_all_embed_failure(self):
        from engineering_brain.retrieval.hake_embeddings import HAKEEncoder

        reg = self._make_registry()
        enc = HAKEEncoder(reg, base_dim=8)
        embedder = _MockEmbedder(fail_embed=True)

        stats = enc.encode_all(embedder, batch_size=2)
        assert stats["failed"] == 4

    def test_cosine_similarity(self):
        from engineering_brain.retrieval.hake_embeddings import HAKEEncoder

        # Identical vectors
        sim = HAKEEncoder._cosine_similarity([1.0, 0.0], [1.0, 0.0])
        assert sim == pytest.approx(1.0)

        # Orthogonal vectors
        sim = HAKEEncoder._cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert sim == pytest.approx(0.0)

        # Empty vectors
        sim = HAKEEncoder._cosine_similarity([], [])
        assert sim == 0.0

    def test_depth_norm_in_range(self):
        from engineering_brain.retrieval.hake_embeddings import HAKEEncoder

        reg = self._make_registry()
        enc = HAKEEncoder(reg, base_dim=4)

        for tag in reg.all_tags():
            vec = enc.encode_tag(tag.id, [0.0] * 4)
            depth_norm = vec[-1]
            assert 0.0 <= depth_norm <= 1.0


# =====================================================================
# Tier 3b — Relationship Learner
# =====================================================================

class TestRelationshipLearner:
    """Tests for RelationshipLearner (Tier 3b)."""

    def _make_registry(self) -> TagRegistry:
        reg = TagRegistry()
        reg.register(Tag(id="python", facet="lang", display_name="Python"))
        reg.register(Tag(id="flask", facet="framework", display_name="Flask",
                         parents=["python"]))
        reg.register(Tag(id="django", facet="framework", display_name="Django",
                         parents=["python"]))
        reg.register(Tag(id="security", facet="domain", display_name="Security"))
        reg.register(Tag(id="testing", facet="concern", display_name="Testing"))
        reg.ensure_closure()
        return reg

    def test_observe_node(self):
        from engineering_brain.learning.relationship_learner import RelationshipLearner

        reg = self._make_registry()
        learner = RelationshipLearner(reg)

        node = {
            "technologies": ["python", "flask"],
            "domains": ["security"],
        }
        learner.observe_node(node)

        assert learner.stats["nodes_observed"] == 1
        assert learner.stats["unique_tags_seen"] == 3

    def test_cooccurrence_tracking(self):
        from engineering_brain.learning.relationship_learner import RelationshipLearner

        reg = self._make_registry()
        learner = RelationshipLearner(reg)

        # Same pair appears in multiple nodes
        for _ in range(5):
            learner.observe_node({
                "technologies": ["python", "flask"],
                "domains": ["security"],
            })

        assert learner.stats["nodes_observed"] == 5
        # (flask, python), (flask, security), (python, security) = 3 pairs
        assert learner.stats["unique_cooccurrences"] == 3

    def test_observe_batch(self):
        from engineering_brain.learning.relationship_learner import RelationshipLearner

        reg = self._make_registry()
        learner = RelationshipLearner(reg)

        nodes = [
            {"technologies": ["python", "flask"], "domains": ["security"]},
            {"technologies": ["python", "django"], "domains": ["testing"]},
            {"technologies": ["flask"], "domains": ["security", "testing"]},
        ]
        learner.observe_batch(nodes, batch_size=2)

        assert learner.stats["nodes_observed"] == 3

    def test_suggest_relationships(self):
        from engineering_brain.learning.relationship_learner import RelationshipLearner

        reg = self._make_registry()
        learner = RelationshipLearner(reg)

        # security+testing co-occur 5 times but aren't connected
        for _ in range(5):
            learner.observe_node({
                "technologies": ["python"],
                "domains": ["security", "testing"],
            })

        suggestions = learner.suggest_relationships(min_cooccurrence=3)

        assert isinstance(suggestions, list)
        # Should suggest security-testing link
        pairs = [(s["child"], s["parent"]) for s in suggestions]
        assert any("security" in p and "testing" in p for p in pairs)

    def test_suggest_no_duplicates_with_existing_edges(self):
        from engineering_brain.learning.relationship_learner import RelationshipLearner

        reg = self._make_registry()
        learner = RelationshipLearner(reg)

        # flask-python already connected — should not be suggested
        for _ in range(10):
            learner.observe_node({
                "technologies": ["python", "flask"],
                "domains": [],
            })

        suggestions = learner.suggest_relationships(min_cooccurrence=3)

        for s in suggestions:
            assert not (s["child"] == "flask" and s["parent"] == "python")

    def test_update_weights(self):
        from engineering_brain.learning.relationship_learner import RelationshipLearner

        reg = self._make_registry()
        learner = RelationshipLearner(reg)

        # Set testing tag to a low weight so the blend changes it
        reg.get("testing").weight = 0.3
        old_weight = reg.get("testing").weight

        # Make testing very frequent alongside other tags
        for _ in range(20):
            learner.observe_node({
                "technologies": ["python", "flask"],
                "domains": ["security", "testing"],
            })

        updated = learner.update_weights()

        assert updated > 0
        new_weight = reg.get("testing").weight
        # Weight should increase (blended with high frequency)
        assert new_weight > old_weight

    def test_update_weights_empty(self):
        from engineering_brain.learning.relationship_learner import RelationshipLearner

        reg = self._make_registry()
        learner = RelationshipLearner(reg)

        # No observations
        updated = learner.update_weights()
        assert updated == 0

    def test_extract_tags_old_format(self):
        from engineering_brain.learning.relationship_learner import RelationshipLearner

        reg = self._make_registry()
        learner = RelationshipLearner(reg)

        node = {
            "technologies": ["python.flask.cors", "javascript.react"],
            "domains": ["web.security"],
        }
        tags = learner._extract_tags_from_node(node)

        assert "python" in tags
        assert "flask" in tags
        assert "cors" in tags
        assert "javascript" in tags
        assert "react" in tags
        assert "web" in tags
        assert "security" in tags

    def test_extract_tags_new_format(self):
        from engineering_brain.learning.relationship_learner import RelationshipLearner

        reg = self._make_registry()
        learner = RelationshipLearner(reg)

        node = {
            "technologies": {
                "lang": ["python"],
                "framework": ["flask", "django"],
            },
            "domains": {
                "domain": ["security"],
            },
        }
        tags = learner._extract_tags_from_node(node)

        assert "python" in tags
        assert "flask" in tags
        assert "django" in tags
        assert "security" in tags

    def test_single_tag_node_ignored(self):
        from engineering_brain.learning.relationship_learner import RelationshipLearner

        reg = self._make_registry()
        learner = RelationshipLearner(reg)

        # Only 1 tag — no co-occurrence possible
        learner.observe_node({"technologies": ["python"], "domains": []})

        assert learner.stats["nodes_observed"] == 0
        assert learner.stats["unique_cooccurrences"] == 0
