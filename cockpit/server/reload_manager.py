"""Live-reload manager — polls seeds directory, rebuilds Brain on changes."""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class ReloadManager:
    """Watches seeds directory for changes and hot-swaps the Brain.

    Safety pattern: Copy-On-Write atomic swap.
    1. Build NEW Brain in thread pool executor (isolated, no shared state)
    2. Acquire asyncio.Lock (microseconds — just for pointer swap)
    3. self._bridge._brain = new_brain  ← atomic reference swap
    4. Release lock, increment _reload_version
    5. Old Brain stays alive via Python refcount until in-flight readers finish
    """

    def __init__(
        self,
        bridge: Any,
        seeds_dir: str | None = None,
        brain_json_path: str | None = None,
        poll_interval: float = 1.0,
        debounce_seconds: float = 3.0,
    ) -> None:
        self._bridge = bridge
        self._seeds_dir = Path(seeds_dir) if seeds_dir else None
        self._brain_json_path = brain_json_path
        self._poll_interval = poll_interval
        self._debounce_seconds = debounce_seconds

        # State
        self._fingerprints: dict[str, tuple[int, int]] = {}  # {path: (mtime_ns, size)}
        self._pending_reload_at: float | None = None
        self._is_reloading = False
        self._reload_count = 0
        self._last_reload_error: str | None = None
        self._last_reload_time: float | None = None
        self._last_reload_duration: float | None = None
        self._last_reload_source: str | None = None

        # Asyncio
        self._task: asyncio.Task | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="brain-reload")

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the polling loop (call from async context)."""
        if not self._seeds_dir:
            log.info("ReloadManager: no seeds_dir configured, live-reload disabled")
            return
        if not self._seeds_dir.is_dir():
            log.warning("ReloadManager: seeds_dir %s is not a directory", self._seeds_dir)
            return
        # Take initial fingerprint
        self._fingerprints = self._scan_fingerprints()
        log.info(
            "ReloadManager: watching %s (%d files, poll=%.1fs, debounce=%.1fs)",
            self._seeds_dir,
            len(self._fingerprints),
            self._poll_interval,
            self._debounce_seconds,
        )
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Cancel the polling loop and shut down executor."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._executor.shutdown(wait=False)
        log.info("ReloadManager: stopped")

    # ── Polling ────────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Main async loop — scans fingerprints every poll_interval."""
        while True:
            try:
                await asyncio.sleep(self._poll_interval)
                self._check_for_changes()

                # Fire debounced reload if timer expired
                if (
                    self._pending_reload_at is not None
                    and time.monotonic() >= self._pending_reload_at
                    and not self._is_reloading
                ):
                    await self._trigger_reload("file_change")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("ReloadManager: error in poll loop")

    def _scan_fingerprints(self) -> dict[str, tuple[int, int]]:
        """Stat all *.yaml files in seeds dir + optional JSON snapshot."""
        fps: dict[str, tuple[int, int]] = {}
        if self._seeds_dir and self._seeds_dir.is_dir():
            for p in self._seeds_dir.rglob("*.yaml"):
                try:
                    st = p.stat()
                    fps[str(p)] = (st.st_mtime_ns, st.st_size)
                except OSError:
                    pass
            for p in self._seeds_dir.rglob("*.yml"):
                try:
                    st = p.stat()
                    fps[str(p)] = (st.st_mtime_ns, st.st_size)
                except OSError:
                    pass
        if self._brain_json_path:
            jp = Path(self._brain_json_path)
            if jp.exists():
                try:
                    st = jp.stat()
                    fps[str(jp)] = (st.st_mtime_ns, st.st_size)
                except OSError:
                    pass
        return fps

    def _check_for_changes(self) -> None:
        """Compare current fingerprints with last known — set debounce timer on change."""
        current = self._scan_fingerprints()
        if current != self._fingerprints:
            added = set(current) - set(self._fingerprints)
            removed = set(self._fingerprints) - set(current)
            modified = {
                k for k in set(current) & set(self._fingerprints)
                if current[k] != self._fingerprints[k]
            }
            log.info(
                "ReloadManager: changes detected — %d added, %d removed, %d modified",
                len(added),
                len(removed),
                len(modified),
            )
            self._fingerprints = current
            # Reset debounce timer (collapses rapid writes into one reload)
            self._pending_reload_at = time.monotonic() + self._debounce_seconds

    # ── Reload ─────────────────────────────────────────────────────────────

    async def _trigger_reload(self, source: str) -> dict[str, Any]:
        """Build new Brain in executor, swap under lock."""
        if self._is_reloading:
            msg = "Reload already in progress, skipping"
            log.info("ReloadManager: %s", msg)
            return {"status": "skipped", "reason": msg}

        self._is_reloading = True
        self._pending_reload_at = None
        self._last_reload_error = None
        t0 = time.monotonic()
        log.info("ReloadManager: reloading Brain (source=%s)...", source)

        try:
            loop = asyncio.get_running_loop()
            new_brain = await loop.run_in_executor(
                self._executor, self._build_brain_sync
            )
            # Atomic swap under lock
            async with self._bridge._brain_lock:
                old_brain = self._bridge._brain
                self._bridge._brain = new_brain
                self._bridge._reload_version += 1

            elapsed = time.monotonic() - t0
            self._reload_count += 1
            self._last_reload_time = time.monotonic()
            self._last_reload_duration = elapsed
            self._last_reload_source = source

            # Count nodes for logging
            node_count = len(new_brain.graph.get_all_nodes()) if new_brain else 0
            log.info(
                "ReloadManager: Brain reloaded in %.1fs — %d nodes (version=%d, source=%s)",
                elapsed,
                node_count,
                self._bridge._reload_version,
                source,
            )
            return {
                "status": "ok",
                "nodes": node_count,
                "duration_s": round(elapsed, 2),
                "reload_version": self._bridge._reload_version,
            }

        except Exception as exc:
            elapsed = time.monotonic() - t0
            self._last_reload_error = f"{type(exc).__name__}: {exc}"
            log.exception("ReloadManager: reload failed after %.1fs — old Brain preserved", elapsed)
            return {
                "status": "error",
                "error": self._last_reload_error,
                "duration_s": round(elapsed, 2),
            }
        finally:
            self._is_reloading = False

    def _build_brain_sync(self) -> Any:
        """Build a fresh Brain — runs in ThreadPoolExecutor (isolated, no shared state)."""
        from pathlib import Path as P
        try:
            from engineering_brain import Brain
        except ImportError:
            log.warning("engineering_brain not installed — reload skipped")
            return None


        if self._brain_json_path and P(self._brain_json_path).exists():
            return Brain.load(self._brain_json_path)

        if self._seeds_dir and self._seeds_dir.is_dir():
            brain = Brain()
            brain.ingest_directory(str(self._seeds_dir))
            return brain

        brain = Brain()
        brain.seed()
        return brain

    # ── Public API ─────────────────────────────────────────────────────────

    async def manual_reload(self) -> dict[str, Any]:
        """Trigger immediate reload, bypassing debounce."""
        # Refresh fingerprints so next poll doesn't re-trigger
        self._fingerprints = self._scan_fingerprints()
        return await self._trigger_reload("manual")

    def status(self) -> dict[str, Any]:
        """Return current reload manager status."""
        pending_in = None
        if self._pending_reload_at is not None:
            remaining = self._pending_reload_at - time.monotonic()
            pending_in = round(max(0, remaining), 1)

        return {
            "enabled": self._seeds_dir is not None,
            "seeds_dir": str(self._seeds_dir) if self._seeds_dir else None,
            "watched_files": len(self._fingerprints),
            "is_reloading": self._is_reloading,
            "reload_count": self._reload_count,
            "last_reload_error": self._last_reload_error,
            "last_reload_duration_s": (
                round(self._last_reload_duration, 2) if self._last_reload_duration else None
            ),
            "last_reload_source": self._last_reload_source,
            "pending_reload_in_s": pending_in,
            "poll_interval_s": self._poll_interval,
            "debounce_s": self._debounce_seconds,
        }
