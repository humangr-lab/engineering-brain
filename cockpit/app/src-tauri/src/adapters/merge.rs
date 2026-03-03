//! Graph Merge — deduplicates and merges graphs from multiple adapters.
//! Cross-adapter edges: docker service name matches directory name.

use std::collections::{HashMap, HashSet};

use super::{RawEdge, RawGraph, RawNode};
use crate::brain::node::Edge;
use crate::brain::node::Node;
use crate::brain::graph::GraphSnapshot;
use crate::brain::bridge::compute_stats;

/// Merge multiple raw graphs into a single GraphSnapshot.
pub fn merge_raw_graphs(graphs: Vec<(&str, RawGraph)>) -> GraphSnapshot {
    let mut all_nodes: HashMap<String, RawNode> = HashMap::new();
    let mut all_edges: Vec<RawEdge> = Vec::new();
    let mut service_names: Vec<String> = Vec::new();
    let mut dir_names: HashSet<String> = HashSet::new();

    for (_adapter_name, graph) in &graphs {
        for node in &graph.nodes {
            all_nodes.entry(node.id.clone()).or_insert_with(|| node.clone());
            if node.node_type == "service" {
                service_names.push(node.label.clone());
            }
            if node.node_type == "module" {
                // Extract directory name from file path
                if let Some(dir) = node.file_path.split('/').next() {
                    dir_names.insert(dir.to_string());
                }
            }
        }
        all_edges.extend(graph.edges.iter().cloned());
    }

    // Cross-adapter edges: docker service → directory
    for service_name in &service_names {
        let service_lower = service_name.to_lowercase();
        for dir in &dir_names {
            let dir_lower = dir.to_lowercase();
            if dir_lower.contains(&service_lower) || service_lower.contains(&dir_lower) {
                // Find a module in that directory
                let matching_module = all_nodes.values().find(|n| {
                    n.node_type == "module" && n.file_path.starts_with(dir.as_str())
                });
                if let Some(module) = matching_module {
                    let service_id = format!("docker:{}", service_name);
                    all_edges.push(RawEdge {
                        from_id: service_id,
                        to_id: module.id.clone(),
                        edge_type: "CONTAINS_CODE".to_string(),
                    });
                }
            }
        }
    }

    // Transform to brain graph format
    let nodes: Vec<Node> = all_nodes
        .values()
        .map(|raw| {
            let (layer, ntype, layer_name) = infer_layer(&raw.node_type, &raw.adapter);

            Node {
                id: raw.id.clone(),
                node_type: ntype,
                layer,
                layer_name,
                text: raw.label.clone(),
                severity: "info".to_string(),
                confidence: 0.8,
                technologies: vec![raw.adapter.clone()],
                domains: vec![],
                out_edges: vec![],
                in_edges: vec![],
                why: None,
                how_to: None,
                when_to_use: None,
                opinion: None,
                epistemic_status: None,
                freshness: None,
                metadata: raw
                    .metadata
                    .iter()
                    .map(|(k, v)| (k.clone(), serde_json::Value::String(v.clone())))
                    .collect(),
            }
        })
        .collect();

    let edges: Vec<Edge> = all_edges
        .iter()
        .map(|raw| Edge {
            from: raw.from_id.clone(),
            to: raw.to_id.clone(),
            edge_type: raw.edge_type.clone(),
            weight: None,
            edge_alpha: None,
            edge_beta: None,
            edge_confidence: None,
        })
        .collect();

    let stats = compute_stats(&nodes, &edges, 0);

    GraphSnapshot {
        nodes,
        edges,
        version: 0,
        stats,
    }
}

/// Infer brain layer from adapter node type.
fn infer_layer(node_type: &str, _adapter: &str) -> (i32, String, String) {
    match node_type {
        "service" | "network" | "volume" => (0, "infrastructure".into(), "L0: Infrastructure".into()),
        "module" => (1, "module".into(), "L1: Module".into()),
        "component" => (2, "component".into(), "L2: Component".into()),
        "class" => (2, "class".into(), "L2: Class".into()),
        "function" => (3, "function".into(), "L3: Function".into()),
        "hook" => (3, "hook".into(), "L3: Hook".into()),
        _ => (1, node_type.into(), format!("L1: {}", node_type)),
    }
}
