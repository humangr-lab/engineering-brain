use serde::{Deserialize, Serialize};

use super::node::{Edge, Node};

/// Full snapshot of the knowledge graph, serializable over IPC.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct GraphSnapshot {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub version: u64,
    pub stats: Stats,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct Stats {
    pub node_count: usize,
    pub edge_count: usize,
    pub layer_counts: Vec<LayerCount>,
    pub version: u64,
    pub technologies: Vec<String>,
    pub domains: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LayerCount {
    pub layer: i32,
    pub name: String,
    pub count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct EpistemicStats {
    pub total_nodes: usize,
    pub by_status: Vec<StatusCount>,
    pub avg_confidence: f64,
    pub at_risk_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StatusCount {
    pub status: String,
    pub count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Contradiction {
    pub node_a: String,
    pub node_b: String,
    pub description: String,
    pub severity: String,
}
