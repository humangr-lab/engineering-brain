pub mod bridge;
pub mod graph;
pub mod node;

use std::sync::Mutex;

use graph::GraphSnapshot;

/// Shared application state managed by Tauri.
/// Thread-safety: Mutex for write access (reload), read access via clone.
pub struct BrainState {
    pub graph: Mutex<GraphSnapshot>,
    pub version: Mutex<u64>,
    pub reload_status: Mutex<ReloadStatus>,
    /// Holds the file watcher debouncer — dropping it stops watching.
    /// Box<dyn Send> avoids leaking notify types into the public API.
    pub watcher_handle: Mutex<Option<Box<dyn Send>>>,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct ReloadStatus {
    pub is_reloading: bool,
    pub reload_count: u32,
    pub last_error: Option<String>,
    pub last_duration_ms: Option<u64>,
    pub seeds_dir: Option<String>,
    pub watched_files: usize,
}

impl Default for ReloadStatus {
    fn default() -> Self {
        Self {
            is_reloading: false,
            reload_count: 0,
            last_error: None,
            last_duration_ms: None,
            seeds_dir: None,
            watched_files: 0,
        }
    }
}

impl Default for BrainState {
    fn default() -> Self {
        Self {
            graph: Mutex::new(GraphSnapshot::default()),
            version: Mutex::new(0),
            reload_status: Mutex::new(ReloadStatus::default()),
            watcher_handle: Mutex::new(None),
        }
    }
}
