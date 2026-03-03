//! Adapter Pipeline — detect → extract (parallel) → merge → validate → emit.

use std::path::Path;

use rayon::prelude::*;

use super::{all_adapters, AdapterConfig, RawGraph};
use super::merge::merge_raw_graphs;
use crate::brain::graph::GraphSnapshot;

/// Run all matching adapters on a project and return a merged graph.
pub fn run_adapters(project_path: &Path) -> Result<GraphSnapshot, String> {
    let config = AdapterConfig::default();
    let adapters = all_adapters();

    // Detect which adapters apply
    let applicable: Vec<_> = adapters
        .iter()
        .filter(|a| a.detect(project_path))
        .collect();

    if applicable.is_empty() {
        return Err(format!(
            "No supported files found in {:?}. Supported: Python, JavaScript/TypeScript, Docker Compose",
            project_path
        ));
    }

    log::info!(
        "Pipeline: {} adapter(s) detected for {:?}: {}",
        applicable.len(),
        project_path,
        applicable.iter().map(|a| a.name()).collect::<Vec<_>>().join(", ")
    );

    // Extract in parallel (Rayon)
    let results: Vec<(&str, RawGraph)> = applicable
        .par_iter()
        .filter_map(|adapter| {
            match adapter.extract(project_path, &config) {
                Ok(graph) => Some((adapter.name(), graph)),
                Err(e) => {
                    log::warn!("Adapter '{}' failed: {}", adapter.name(), e);
                    None
                }
            }
        })
        .collect();

    if results.is_empty() {
        return Err("All adapters failed. Check logs for details.".to_string());
    }

    let total_nodes: usize = results.iter().map(|(_, g)| g.nodes.len()).sum();
    let total_edges: usize = results.iter().map(|(_, g)| g.edges.len()).sum();
    log::info!(
        "Pipeline: extracted {} nodes, {} edges total (pre-merge)",
        total_nodes,
        total_edges
    );

    // Merge
    let snapshot = merge_raw_graphs(results);

    log::info!(
        "Pipeline: final graph: {} nodes, {} edges (post-merge)",
        snapshot.nodes.len(),
        snapshot.edges.len()
    );

    Ok(snapshot)
}
