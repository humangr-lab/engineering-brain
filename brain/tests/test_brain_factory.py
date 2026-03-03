"""Tests for the consolidated Brain singleton factory."""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from engineering_brain.core.brain_factory import (
    get_brain,
    is_embed_ready,
    reset_brain,
    wait_for_embed,
)


class TestBrainFactory:
    """Test the singleton factory."""

    def setup_method(self):
        reset_brain()

    def teardown_method(self):
        reset_brain()

    def test_get_brain_returns_same_instance(self):
        b1 = get_brain(background_embed=False)
        b2 = get_brain(background_embed=False)
        assert b1 is b2

    def test_get_brain_seeds_nodes(self):
        b = get_brain(background_embed=False)
        assert b.stats()["total"] > 100

    def test_get_brain_is_thread_safe(self):
        """Concurrent calls should all get the same instance."""
        instances: list[int] = []
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()
            b = get_brain(background_embed=False)
            instances.append(id(b))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(set(instances)) == 1, f"Got {len(set(instances))} distinct instances"

    def test_reset_brain_clears_singleton(self):
        b1 = get_brain(background_embed=False)
        reset_brain()
        b2 = get_brain(background_embed=False)
        assert b1 is not b2

    def test_embedder_present_after_init(self):
        b = get_brain(background_embed=False)
        assert b._embedder is not None

    def test_skip_background_embed_env_var(self):
        """BRAIN_SKIP_BACKGROUND_EMBED disables background thread."""
        with patch.dict("os.environ", {"BRAIN_SKIP_BACKGROUND_EMBED": "1"}):
            get_brain(background_embed=True)
            assert not is_embed_ready()

    def test_no_background_embed_when_disabled(self):
        get_brain(background_embed=False)
        assert not is_embed_ready()

    @pytest.mark.slow
    def test_background_embed_sets_event(self):
        """Background embed should eventually set _embed_ready.

        Uses BRAIN_EMBEDDING_ENABLED=false so the embedder is None,
        causing the background worker to return immediately and set the
        event.  This validates the thread → event mechanism without the
        real ~200s embedding + tag-indexing run.
        """
        with patch.dict("os.environ", {"BRAIN_EMBEDDING_ENABLED": "false"}):
            get_brain(background_embed=True)
            assert wait_for_embed(timeout=30), "Background embed did not complete in 30s"
            assert is_embed_ready()
