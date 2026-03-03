//! File watcher — uses notify crate with debounce.
//! Port of Python server/reload_manager.py.

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use log::{info, warn};
use notify::{RecommendedWatcher, RecursiveMode, Watcher};
use notify_debouncer_mini::{new_debouncer, Debouncer, DebouncedEventKind};
use tauri::{AppHandle, Emitter};

use crate::brain::bridge::load_from_seeds_dir;
use crate::brain::BrainState;

/// Start watching a seeds directory for changes.
/// Emits "brain_version_changed" event on reload.
/// Returns the debouncer — caller MUST keep it alive for watching to continue.
pub fn start_watching(
    app_handle: AppHandle,
    seeds_dir: PathBuf,
    state: Arc<BrainState>,
) -> Result<Debouncer<RecommendedWatcher>, String> {
    info!("FileWatcher: starting to watch {:?}", seeds_dir);

    let seeds_dir_clone = seeds_dir.clone();
    let (tx, rx) = std::sync::mpsc::channel();

    // Debounce: 500ms (collapses rapid saves into one reload)
    let mut debouncer = new_debouncer(Duration::from_millis(500), tx)
        .map_err(|e| format!("Failed to create debouncer: {}", e))?;

    debouncer
        .watcher()
        .watch(&seeds_dir, RecursiveMode::Recursive)
        .map_err(|e| format!("Failed to watch {:?}: {}", seeds_dir, e))?;

    // Spawn reload thread
    std::thread::spawn(move || {
        while let Ok(result) = rx.recv() {
            match result {
                Ok(events) => {
                    let has_yaml = events.iter().any(|e| {
                        e.kind == DebouncedEventKind::Any
                            && e.path
                                .extension()
                                .map(|ext| ext == "yaml" || ext == "yml")
                                .unwrap_or(false)
                    });
                    if has_yaml {
                        info!("FileWatcher: YAML change detected, reloading...");
                        do_reload(&app_handle, &seeds_dir_clone, &state);
                    }
                }
                Err(errors) => {
                    warn!("FileWatcher: watch error: {:?}", errors);
                }
            }
        }
    });

    info!("FileWatcher: watching {:?}", seeds_dir);
    Ok(debouncer)
}

/// Lightweight watcher that only emits "brain_version_changed" events
/// without performing the reload itself. Used in setup() when we don't
/// have an Arc<BrainState> available.
pub fn start_event_watcher(
    app_handle: AppHandle,
    watch_dir: PathBuf,
) -> Result<Debouncer<RecommendedWatcher>, String> {
    info!("EventWatcher: starting to watch {:?}", watch_dir);

    let (tx, rx) = std::sync::mpsc::channel();

    let mut debouncer = new_debouncer(Duration::from_millis(500), tx)
        .map_err(|e| format!("Failed to create debouncer: {}", e))?;

    debouncer
        .watcher()
        .watch(&watch_dir, RecursiveMode::Recursive)
        .map_err(|e| format!("Failed to watch {:?}: {}", watch_dir, e))?;

    std::thread::spawn(move || {
        while let Ok(result) = rx.recv() {
            match result {
                Ok(events) => {
                    let has_relevant = events.iter().any(|e| {
                        e.kind == DebouncedEventKind::Any
                            && e.path
                                .extension()
                                .map(|ext| {
                                    let s = ext.to_string_lossy();
                                    ["yaml", "yml", "py", "rs", "ts", "js", "go"]
                                        .contains(&s.as_ref())
                                })
                                .unwrap_or(false)
                    });
                    if has_relevant {
                        info!("EventWatcher: file change detected, emitting event");
                        let _ = app_handle.emit("brain_version_changed", 0u32);
                    }
                }
                Err(errors) => {
                    warn!("EventWatcher: watch error: {:?}", errors);
                }
            }
        }
    });

    info!("EventWatcher: watching {:?}", watch_dir);
    Ok(debouncer)
}

fn do_reload(app_handle: &AppHandle, seeds_dir: &PathBuf, state: &BrainState) {
    let t0 = std::time::Instant::now();

    // Mark as reloading
    if let Ok(mut status) = state.reload_status.lock() {
        status.is_reloading = true;
    }

    match load_from_seeds_dir(seeds_dir) {
        Ok(mut snapshot) => {
            let elapsed = t0.elapsed();
            let node_count = snapshot.nodes.len();

            // Atomic swap
            if let Ok(mut version) = state.version.lock() {
                *version += 1;
                snapshot.version = *version;
                snapshot.stats.version = *version;
            }
            if let Ok(mut graph) = state.graph.lock() {
                *graph = snapshot;
            }
            if let Ok(mut status) = state.reload_status.lock() {
                status.is_reloading = false;
                status.reload_count += 1;
                status.last_error = None;
                status.last_duration_ms = Some(elapsed.as_millis() as u64);
            }

            info!(
                "FileWatcher: reloaded in {:.1}s — {} nodes",
                elapsed.as_secs_f64(),
                node_count
            );

            // Emit event to frontend
            let _ = app_handle.emit("brain_version_changed", node_count);
        }
        Err(e) => {
            warn!("FileWatcher: reload failed: {}", e);
            if let Ok(mut status) = state.reload_status.lock() {
                status.is_reloading = false;
                status.last_error = Some(e);
            }
        }
    }
}
