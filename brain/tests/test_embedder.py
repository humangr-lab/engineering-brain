"""Tests for the BrainEmbedder module.

Verifies:
- node_to_text extracts correct fields in priority order
- cosine_similarity is mathematically correct
- embed_text/embed_batch return [] when provider unavailable
- embed_and_store fast-exits when provider failed
- embed_all_nodes fast-exits when no provider
- get_embedder singleton respects embedding_enabled config
- reset_embedder clears singleton
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from engineering_brain.adapters.memory import MemoryGraphAdapter, MemoryVectorAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import NodeType
from engineering_brain.retrieval.embedder import (
    BrainEmbedder,
    cosine_similarity,
    get_embedder,
    reset_embedder,
)


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_partial_similarity(self):
        sim = cosine_similarity([1, 1, 0], [1, 0, 0])
        assert 0.5 < sim < 1.0

    def test_empty_vectors(self):
        assert cosine_similarity([], []) == 0.0

    def test_mismatched_lengths(self):
        assert cosine_similarity([1, 2], [1, 2, 3]) == 0.0

    def test_zero_vector(self):
        assert cosine_similarity([0, 0], [1, 1]) == 0.0


# ---------------------------------------------------------------------------
# node_to_text
# ---------------------------------------------------------------------------

class TestNodeToText:
    def setup_method(self):
        self.embedder = BrainEmbedder(MemoryVectorAdapter())

    def test_rule_fields(self):
        text = self.embedder.node_to_text({
            "text": "Validate CORS origins",
            "why": "Prevent XSS",
            "how_to_do_right": "Use allowlist",
        })
        assert "Validate CORS origins" in text
        assert "Prevent XSS" in text
        assert "Use allowlist" in text

    def test_pattern_fields(self):
        text = self.embedder.node_to_text({
            "name": "Deny By Default",
            "intent": "Block unknown input",
        })
        assert "Deny By Default" in text
        assert "Block unknown input" in text

    def test_axiom_fields(self):
        text = self.embedder.node_to_text({"statement": "All input is hostile"})
        assert "All input is hostile" in text

    def test_finding_fields(self):
        text = self.embedder.node_to_text({
            "description": "CORS wildcard found",
            "resolution": "Restrict origins",
        })
        assert "CORS wildcard found" in text
        assert "Restrict origins" in text

    def test_empty_node(self):
        assert self.embedder.node_to_text({}) == ""

    def test_text_capped_at_500(self):
        text = self.embedder.node_to_text({"text": "x" * 1000})
        assert len(text) <= 500

    def test_primary_field_priority(self):
        """'text' has priority over 'name' over 'statement'."""
        text = self.embedder.node_to_text({
            "text": "TEXT_FIELD",
            "name": "NAME_FIELD",
            "statement": "STATEMENT_FIELD",
        })
        assert "TEXT_FIELD" in text
        # Only first non-empty primary field is used
        assert "NAME_FIELD" not in text


# ---------------------------------------------------------------------------
# Graceful degradation (no provider)
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_embed_text_no_provider(self):
        embedder = BrainEmbedder(MemoryVectorAdapter())
        embedder._provider_attempted = True  # Simulate failed import
        assert embedder.embed_text("test") == []

    def test_embed_batch_no_provider(self):
        embedder = BrainEmbedder(MemoryVectorAdapter())
        embedder._provider_attempted = True
        assert embedder.embed_batch(["test1", "test2"]) == []

    def test_embed_and_store_fast_exit(self):
        embedder = BrainEmbedder(MemoryVectorAdapter())
        embedder._provider_attempted = True
        assert embedder.embed_and_store({"id": "R-1", "text": "test"}, "coll") is False

    def test_embed_all_nodes_fast_exit(self):
        graph = MemoryGraphAdapter()
        graph.add_node(NodeType.RULE.value, "CR-001", {
            "id": "CR-001", "text": "test",
        })
        embedder = BrainEmbedder(MemoryVectorAdapter())
        embedder._provider_attempted = True
        stats = embedder.embed_all_nodes(graph)
        assert stats["embedded"] == 0
        assert stats["failed"] == 0


# ---------------------------------------------------------------------------
# embed_all_nodes with mock provider
# ---------------------------------------------------------------------------

class TestEmbedAllNodes:
    def test_embeds_and_stores_nodes(self):
        graph = MemoryGraphAdapter()
        vector = MemoryVectorAdapter()

        # Add rules (CR- prefix → L3 → brain_rules collection)
        for i in range(3):
            graph.add_node(NodeType.RULE.value, f"CR-TEST-{i:03d}", {
                "id": f"CR-TEST-{i:03d}",
                "text": f"Test rule {i}",
                "technologies": ["python"],
            })

        embedder = BrainEmbedder(vector)
        # Mock the provider to return fake embeddings
        mock_provider = MagicMock()
        mock_provider.embed_batch.return_value = [[0.1, 0.2, 0.3]] * 3
        embedder._provider = mock_provider
        embedder._provider_attempted = True

        stats = embedder.embed_all_nodes(graph, batch_size=10)
        assert stats["embedded"] == 3
        assert stats["failed"] == 0

    def test_skips_deprecated_nodes(self):
        graph = MemoryGraphAdapter()
        vector = MemoryVectorAdapter()

        graph.add_node(NodeType.RULE.value, "CR-ACTIVE", {
            "id": "CR-ACTIVE", "text": "Active rule",
        })
        graph.add_node(NodeType.RULE.value, "CR-DEP", {
            "id": "CR-DEP", "text": "Deprecated rule", "deprecated": True,
        })

        embedder = BrainEmbedder(vector)
        mock_provider = MagicMock()
        mock_provider.embed_batch.return_value = [[0.1, 0.2]]
        embedder._provider = mock_provider
        embedder._provider_attempted = True

        stats = embedder.embed_all_nodes(graph, batch_size=10)
        assert stats["embedded"] == 1
        assert stats["skipped"] >= 1

    def test_skips_unknown_prefix(self):
        graph = MemoryGraphAdapter()
        vector = MemoryVectorAdapter()

        graph.add_node("Unknown", "UNKNOWN-001", {
            "id": "UNKNOWN-001", "text": "Unknown type",
        })

        embedder = BrainEmbedder(vector)
        mock_provider = MagicMock()
        embedder._provider = mock_provider
        embedder._provider_attempted = True

        stats = embedder.embed_all_nodes(graph, batch_size=10)
        assert stats["embedded"] == 0
        assert stats["skipped"] >= 1


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def setup_method(self):
        reset_embedder()

    def teardown_method(self):
        reset_embedder()

    def test_get_embedder_returns_none_when_disabled(self):
        cfg = BrainConfig()
        cfg.embedding_enabled = False
        assert get_embedder(config=cfg) is None

    def test_get_embedder_returns_instance_when_enabled(self):
        cfg = BrainConfig()
        cfg.embedding_enabled = True
        embedder = get_embedder(config=cfg)
        assert isinstance(embedder, BrainEmbedder)

    def test_singleton_returns_same_instance(self):
        cfg = BrainConfig()
        cfg.embedding_enabled = True
        e1 = get_embedder(config=cfg)
        e2 = get_embedder(config=cfg)
        assert e1 is e2

    def test_reset_clears_singleton(self):
        cfg = BrainConfig()
        cfg.embedding_enabled = True
        e1 = get_embedder(config=cfg)
        reset_embedder()
        e2 = get_embedder(config=cfg)
        assert e1 is not e2
