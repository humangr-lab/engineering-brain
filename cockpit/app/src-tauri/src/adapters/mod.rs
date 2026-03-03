//! Import Adapter Framework
//! Detects project languages, extracts graph data from source files.
//! Each adapter implements the `ImportAdapter` trait.

pub mod merge;
pub mod pipeline;
pub mod python;
pub mod javascript;
pub mod docker_compose;

use std::path::Path;

/// Raw node extracted by an adapter.
#[derive(Debug, Clone, serde::Serialize)]
pub struct RawNode {
    pub id: String,
    pub label: String,
    pub node_type: String,      // "module", "class", "function", "service", etc.
    pub file_path: String,       // Relative path from project root
    pub line_number: Option<u32>,
    pub adapter: String,         // "python", "javascript", "docker-compose"
    pub metadata: std::collections::HashMap<String, String>,
}

/// Raw edge extracted by an adapter.
#[derive(Debug, Clone, serde::Serialize)]
pub struct RawEdge {
    pub from_id: String,
    pub to_id: String,
    pub edge_type: String, // "IMPORTS", "CALLS", "DEPENDS_ON", "CONTAINS", etc.
}

/// Raw graph output from a single adapter.
#[derive(Debug, Clone, Default)]
pub struct RawGraph {
    pub nodes: Vec<RawNode>,
    pub edges: Vec<RawEdge>,
}

/// Error during adapter execution.
#[derive(Debug, thiserror::Error)]
pub enum AdapterError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("Walk error: {0}")]
    Walk(#[from] walkdir::Error),
    #[error("Parse error in {path}: {message}")]
    Parse { path: String, message: String },
    #[error("Adapter error: {0}")]
    Other(String),
}

/// Configuration for adapter execution.
#[derive(Debug, Clone)]
pub struct AdapterConfig {
    pub respect_gitignore: bool,
    pub max_files: usize,
    pub max_file_size_bytes: u64,
}

impl Default for AdapterConfig {
    fn default() -> Self {
        Self {
            respect_gitignore: true,
            max_files: 50_000,
            max_file_size_bytes: 1_000_000, // 1MB
        }
    }
}

/// Trait that all import adapters must implement.
pub trait ImportAdapter: Send + Sync {
    /// Human-readable adapter name.
    fn name(&self) -> &str;

    /// Check if this adapter applies to the given project.
    fn detect(&self, project_path: &Path) -> bool;

    /// Extract graph data from the project.
    fn extract(
        &self,
        project_path: &Path,
        config: &AdapterConfig,
    ) -> Result<RawGraph, AdapterError>;

    /// File extensions this adapter handles.
    fn supported_extensions(&self) -> &[&str];
}

/// Get all available adapters in priority order.
pub fn all_adapters() -> Vec<Box<dyn ImportAdapter>> {
    vec![
        Box::new(python::PythonAdapter),
        Box::new(javascript::JavaScriptAdapter),
        Box::new(docker_compose::DockerComposeAdapter),
    ]
}
