//! Graph data model for the Ontology Map TUI.

use serde::{Deserialize, Serialize};

/// A node in the code architecture graph.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphNode {
    pub id: String,
    pub label: String,
    pub node_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line_count: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub layer: Option<String>,
}

/// An edge (dependency) between two nodes.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphEdge {
    pub from: String,
    pub to: String,
    pub edge_type: String,
}

/// The complete application graph produced by adapters.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppGraph {
    pub nodes: Vec<GraphNode>,
    pub edges: Vec<GraphEdge>,
    pub adapters_used: Vec<String>,
}
