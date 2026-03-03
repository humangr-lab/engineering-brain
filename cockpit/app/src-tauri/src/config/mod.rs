use serde::{Deserialize, Serialize};

/// Application configuration loaded from TOML + env fallback.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub seeds_dir: Option<String>,
    pub watch_enabled: bool,
    pub watch_debounce_ms: u64,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            seeds_dir: None,
            watch_enabled: true,
            watch_debounce_ms: 500,
        }
    }
}
