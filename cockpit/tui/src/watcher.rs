//! File watcher — live reload detection with debouncing.
//!
//! Watches the project directory for file changes and emits events
//! that trigger pulse animations on affected nodes.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::mpsc;
use std::time::{Duration, Instant};

use notify::{Event, EventKind, RecommendedWatcher, RecursiveMode, Watcher};

/// A debounced file change event.
#[derive(Debug, Clone)]
pub struct WatchEvent {
    /// Path relative to the project root.
    pub rel_path: String,
}

/// File watcher with built-in debouncing.
pub struct FileWatcher {
    rx: mpsc::Receiver<Result<Event, notify::Error>>,
    _watcher: RecommendedWatcher,
    last_events: HashMap<PathBuf, Instant>,
    debounce: Duration,
    project_root: PathBuf,
}

impl FileWatcher {
    /// Create a new file watcher for the given project path.
    pub fn new(path: &Path) -> anyhow::Result<Self> {
        let (tx, rx) = mpsc::channel();

        let mut watcher = RecommendedWatcher::new(tx, notify::Config::default())?;
        watcher.watch(path, RecursiveMode::Recursive)?;

        Ok(FileWatcher {
            rx,
            _watcher: watcher,
            last_events: HashMap::new(),
            debounce: Duration::from_millis(500),
            project_root: path.to_path_buf(),
        })
    }

    /// Poll for new watch events (non-blocking). Returns debounced file changes.
    pub fn poll(&mut self) -> Vec<WatchEvent> {
        let mut events = Vec::new();
        let now = Instant::now();

        while let Ok(result) = self.rx.try_recv() {
            let event = match result {
                Ok(e) => e,
                Err(_) => continue,
            };

            match event.kind {
                EventKind::Modify(_) | EventKind::Create(_) => {
                    for path in event.paths {
                        // Skip .git directory
                        if path.components().any(|c| c.as_os_str() == ".git") {
                            continue;
                        }

                        // Skip non-source files
                        if !is_source_file(&path) {
                            continue;
                        }

                        // Debounce: skip if we saw this file recently
                        if let Some(last) = self.last_events.get(&path) {
                            if now.duration_since(*last) < self.debounce {
                                continue;
                            }
                        }

                        self.last_events.insert(path.clone(), now);

                        // Compute relative path
                        let rel_path = path
                            .strip_prefix(&self.project_root)
                            .unwrap_or(&path)
                            .to_string_lossy()
                            .to_string();

                        events.push(WatchEvent { rel_path });
                    }
                }
                _ => {}
            }
        }

        events
    }
}

/// Check if a file is a source file we care about.
fn is_source_file(path: &Path) -> bool {
    matches!(
        path.extension().and_then(|e| e.to_str()),
        Some(
            "py" | "js"
                | "jsx"
                | "ts"
                | "tsx"
                | "mjs"
                | "cjs"
                | "go"
                | "rs"
                | "java"
                | "cs"
                | "yml"
                | "yaml"
        )
    )
}
