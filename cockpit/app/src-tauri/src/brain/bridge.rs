//! BrainBridge — loads YAML/JSON seed files and builds the graph.
//! Port of Python server/brain_bridge.py.

use std::collections::HashMap;
use std::path::Path;

use log::{info, warn};
use rayon::prelude::*;

use super::graph::{GraphSnapshot, LayerCount, Stats};
use super::node::{layer_info, Edge, EdgeRef, Node, Opinion};

/// Raw YAML seed node — matches the engineering brain seed format.
#[derive(Debug, Clone, serde::Deserialize)]
struct RawSeedNode {
    id: Option<String>,
    #[serde(alias = "_id")]
    _id: Option<String>,
    text: Option<String>,
    statement: Option<String>,
    name: Option<String>,
    description: Option<String>,
    intent: Option<String>,
    severity: Option<String>,
    confidence: Option<f64>,
    technologies: Option<Vec<String>>,
    domains: Option<Vec<String>>,
    domain: Option<String>,
    why: Option<String>,
    how_to_do_right: Option<String>,
    how_to_apply: Option<String>,
    when_to_use: Option<String>,
    // Epistemic
    ep_b: Option<f64>,
    ep_d: Option<f64>,
    ep_u: Option<f64>,
    ep_a: Option<f64>,
    epistemic_status: Option<String>,
    freshness: Option<f64>,
}

/// Raw YAML seed edge.
#[derive(Debug, Clone, serde::Deserialize)]
struct RawSeedEdge {
    from_id: Option<String>,
    to_id: Option<String>,
    edge_type: Option<String>,
    edge_alpha: Option<f64>,
    edge_beta: Option<f64>,
    edge_confidence: Option<f64>,
}

/// A YAML seed file's top-level structure.
#[derive(Debug, Clone, serde::Deserialize)]
struct SeedFile {
    #[serde(default)]
    nodes: Vec<serde_yaml::Value>,
    #[serde(default)]
    edges: Vec<serde_yaml::Value>,
}

/// Load all YAML seed files from a directory and build a GraphSnapshot.
pub fn load_from_seeds_dir(seeds_dir: &Path) -> Result<GraphSnapshot, String> {
    if !seeds_dir.is_dir() {
        return Err(format!("Seeds directory not found: {:?}", seeds_dir));
    }

    let yaml_files: Vec<_> = walkdir::WalkDir::new(seeds_dir)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| {
            let p = e.path();
            p.is_file()
                && matches!(
                    p.extension().and_then(|e| e.to_str()),
                    Some("yaml") | Some("yml")
                )
        })
        .map(|e| e.into_path())
        .collect();

    info!(
        "BrainBridge: loading {} YAML files from {:?}",
        yaml_files.len(),
        seeds_dir
    );

    // Parse files in parallel with Rayon
    let parsed: Vec<(Vec<serde_yaml::Value>, Vec<serde_yaml::Value>)> = yaml_files
        .par_iter()
        .filter_map(|path| {
            let content = match std::fs::read_to_string(path) {
                Ok(c) => c,
                Err(e) => {
                    warn!("BrainBridge: failed to read {:?}: {}", path, e);
                    return None;
                }
            };
            match serde_yaml::from_str::<SeedFile>(&content) {
                Ok(seed) => Some((seed.nodes, seed.edges)),
                Err(_) => {
                    // Try as a list of nodes (some seed files are just node arrays)
                    match serde_yaml::from_str::<Vec<serde_yaml::Value>>(&content) {
                        Ok(nodes) => Some((nodes, Vec::new())),
                        Err(e) => {
                            warn!("BrainBridge: failed to parse {:?}: {}", path, e);
                            None
                        }
                    }
                }
            }
        })
        .collect();

    let mut all_raw_nodes: Vec<serde_yaml::Value> = Vec::new();
    let mut all_raw_edges: Vec<serde_yaml::Value> = Vec::new();
    for (nodes, edges) in parsed {
        all_raw_nodes.extend(nodes);
        all_raw_edges.extend(edges);
    }

    info!(
        "BrainBridge: parsed {} raw nodes, {} raw edges",
        all_raw_nodes.len(),
        all_raw_edges.len()
    );

    // Build edge index
    let raw_edges: Vec<RawSeedEdge> = all_raw_edges
        .iter()
        .filter_map(|v| serde_yaml::from_value(v.clone()).ok())
        .collect();

    let mut out_idx: HashMap<String, Vec<&RawSeedEdge>> = HashMap::new();
    let mut in_idx: HashMap<String, Vec<&RawSeedEdge>> = HashMap::new();
    for e in &raw_edges {
        if let Some(fid) = &e.from_id {
            out_idx.entry(fid.clone()).or_default().push(e);
        }
        if let Some(tid) = &e.to_id {
            in_idx.entry(tid.clone()).or_default().push(e);
        }
    }

    // Transform nodes
    let nodes: Vec<Node> = all_raw_nodes
        .iter()
        .filter_map(|v| {
            let raw: RawSeedNode = serde_yaml::from_value(v.clone()).ok()?;
            let node_id = raw.id.clone().or_else(|| raw._id.clone())?;
            if node_id.is_empty() {
                return None;
            }
            Some(transform_node(&raw, &node_id, &out_idx, &in_idx))
        })
        .collect();

    // Transform edges
    let edges: Vec<Edge> = raw_edges
        .iter()
        .filter_map(|e| {
            Some(Edge {
                from: e.from_id.clone()?,
                to: e.to_id.clone()?,
                edge_type: e.edge_type.clone().unwrap_or("RELATES_TO".to_string()),
                weight: None,
                edge_alpha: e.edge_alpha,
                edge_beta: e.edge_beta,
                edge_confidence: e.edge_confidence,
            })
        })
        .collect();

    // Compute stats
    let stats = compute_stats(&nodes, &edges, 0);

    Ok(GraphSnapshot {
        nodes,
        edges,
        version: 0,
        stats,
    })
}

fn transform_node(
    raw: &RawSeedNode,
    node_id: &str,
    out_idx: &HashMap<String, Vec<&RawSeedEdge>>,
    in_idx: &HashMap<String, Vec<&RawSeedEdge>>,
) -> Node {
    let (layer, ntype, layer_name) = layer_info(node_id);

    let text = raw
        .text
        .as_deref()
        .or(raw.statement.as_deref())
        .or(raw.name.as_deref())
        .or(raw.description.as_deref())
        .or(raw.intent.as_deref())
        .unwrap_or(node_id)
        .to_string();

    let out_edges = out_idx
        .get(node_id)
        .map(|edges| {
            edges
                .iter()
                .map(|e| EdgeRef {
                    node_id: e.to_id.clone().unwrap_or_default(),
                    edge_type: e.edge_type.clone().unwrap_or("RELATES_TO".to_string()),
                })
                .collect()
        })
        .unwrap_or_default();

    let in_edges = in_idx
        .get(node_id)
        .map(|edges| {
            edges
                .iter()
                .map(|e| EdgeRef {
                    node_id: e.from_id.clone().unwrap_or_default(),
                    edge_type: e.edge_type.clone().unwrap_or("RELATES_TO".to_string()),
                })
                .collect()
        })
        .unwrap_or_default();

    let domains = raw.domains.clone().unwrap_or_else(|| {
        raw.domain
            .as_ref()
            .map(|d| vec![d.clone()])
            .unwrap_or_default()
    });

    let opinion = if raw.ep_b.is_some() {
        Some(Opinion {
            b: raw.ep_b.unwrap_or(0.0),
            d: raw.ep_d.unwrap_or(0.0),
            u: raw.ep_u.unwrap_or(0.0),
            a: raw.ep_a.unwrap_or(0.5),
        })
    } else {
        None
    };

    let how_to = raw
        .how_to_do_right
        .clone()
        .or_else(|| raw.how_to_apply.clone());

    Node {
        id: node_id.to_string(),
        node_type: ntype,
        layer,
        layer_name,
        text,
        severity: raw.severity.clone().unwrap_or("info".to_string()),
        confidence: raw.confidence.unwrap_or(0.5),
        technologies: raw.technologies.clone().unwrap_or_default(),
        domains,
        out_edges,
        in_edges,
        why: raw.why.clone(),
        how_to,
        when_to_use: raw.when_to_use.clone(),
        opinion,
        epistemic_status: raw.epistemic_status.clone(),
        freshness: raw.freshness,
        metadata: HashMap::new(),
    }
}

pub fn compute_stats(nodes: &[Node], edges: &[Edge], version: u64) -> Stats {
    let mut layer_map: HashMap<(i32, String), usize> = HashMap::new();
    let mut tech_set: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut domain_set: std::collections::HashSet<String> = std::collections::HashSet::new();

    for n in nodes {
        *layer_map
            .entry((n.layer, n.layer_name.clone()))
            .or_insert(0) += 1;
        for t in &n.technologies {
            tech_set.insert(t.clone());
        }
        for d in &n.domains {
            domain_set.insert(d.clone());
        }
    }

    let mut layer_counts: Vec<LayerCount> = layer_map
        .into_iter()
        .map(|((layer, name), count)| LayerCount {
            layer,
            name,
            count,
        })
        .collect();
    layer_counts.sort_by_key(|lc| lc.layer);

    let mut technologies: Vec<String> = tech_set.into_iter().collect();
    technologies.sort();
    let mut domains: Vec<String> = domain_set.into_iter().collect();
    domains.sort();

    Stats {
        node_count: nodes.len(),
        edge_count: edges.len(),
        layer_counts,
        version,
        technologies,
        domains,
    }
}
