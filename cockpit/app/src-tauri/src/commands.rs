//! Tauri commands — 14 IPC endpoints replacing FastAPI.

use tauri::State;

use crate::brain::graph::{Contradiction, EpistemicStats, GraphSnapshot, Stats, StatusCount};
use crate::brain::node::{Edge, Node};
use crate::brain::BrainState;

// ── Graph queries ────────────────────────────────────────────────────────

#[tauri::command]
pub fn get_graph(state: State<BrainState>) -> GraphSnapshot {
    state.graph.lock().unwrap_or_else(|e| e.into_inner()).clone()
}

#[tauri::command]
pub fn get_graph_version(state: State<BrainState>) -> u64 {
    *state.version.lock().unwrap_or_else(|e| e.into_inner())
}

#[tauri::command]
pub fn get_stats(state: State<BrainState>) -> Stats {
    state.graph.lock().unwrap_or_else(|e| e.into_inner()).stats.clone()
}

// ── Node queries ─────────────────────────────────────────────────────────

#[tauri::command]
pub fn get_nodes(
    state: State<BrainState>,
    layer: Option<i32>,
    severity: Option<String>,
    search: Option<String>,
    limit: Option<usize>,
    offset: Option<usize>,
) -> Vec<Node> {
    let graph = state.graph.lock().unwrap_or_else(|e| e.into_inner());
    let limit = limit.unwrap_or(500);
    let offset = offset.unwrap_or(0);

    let filtered: Vec<Node> = graph
        .nodes
        .iter()
        .filter(|n| {
            if let Some(l) = layer {
                if n.layer != l {
                    return false;
                }
            }
            if let Some(ref sev) = severity {
                if !n.severity.eq_ignore_ascii_case(sev) {
                    return false;
                }
            }
            if let Some(ref q) = search {
                let q_lower = q.to_lowercase();
                let searchable = format!("{} {} {}", n.id, n.text, n.why.as_deref().unwrap_or(""))
                    .to_lowercase();
                if !searchable.contains(&q_lower) {
                    return false;
                }
            }
            true
        })
        .skip(offset)
        .take(limit)
        .cloned()
        .collect();

    filtered
}

#[tauri::command]
pub fn get_node(state: State<BrainState>, id: String) -> Option<Node> {
    let graph = state.graph.lock().unwrap_or_else(|e| e.into_inner());
    graph.nodes.iter().find(|n| n.id == id).cloned()
}

// ── Edge queries ─────────────────────────────────────────────────────────

#[tauri::command]
pub fn get_edges(
    state: State<BrainState>,
    node_id: Option<String>,
    edge_type: Option<String>,
) -> Vec<Edge> {
    let graph = state.graph.lock().unwrap_or_else(|e| e.into_inner());
    graph
        .edges
        .iter()
        .filter(|e| {
            if let Some(ref nid) = node_id {
                if e.from != *nid && e.to != *nid {
                    return false;
                }
            }
            if let Some(ref et) = edge_type {
                if !e.edge_type.eq_ignore_ascii_case(et) {
                    return false;
                }
            }
            true
        })
        .cloned()
        .collect()
}

// ── Epistemic queries ────────────────────────────────────────────────────

#[tauri::command]
pub fn get_epistemic_stats(state: State<BrainState>) -> EpistemicStats {
    let graph = state.graph.lock().unwrap_or_else(|e| e.into_inner());
    let total = graph.nodes.len();

    // Count by epistemic status
    let mut status_map: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    let mut conf_sum = 0.0f64;

    for n in &graph.nodes {
        let status = n
            .epistemic_status
            .as_deref()
            .unwrap_or("unknown")
            .to_string();
        *status_map.entry(status).or_insert(0) += 1;
        conf_sum += n.confidence;
    }

    let by_status: Vec<StatusCount> = status_map
        .into_iter()
        .map(|(status, count)| StatusCount { status, count })
        .collect();

    let avg_confidence = if total > 0 {
        conf_sum / total as f64
    } else {
        0.0
    };

    EpistemicStats {
        total_nodes: total,
        by_status,
        avg_confidence,
        at_risk_count: 0, // TODO: compute from freshness
    }
}

#[tauri::command]
pub fn get_contradictions(_state: State<BrainState>) -> Vec<Contradiction> {
    // TODO: implement contradiction detection
    Vec::new()
}

#[tauri::command]
pub fn get_at_risk_nodes(
    state: State<BrainState>,
    _horizon_days: Option<u32>,
) -> Vec<Node> {
    let graph = state.graph.lock().unwrap_or_else(|e| e.into_inner());
    // Return nodes with low freshness
    graph
        .nodes
        .iter()
        .filter(|n| n.freshness.map(|f| f < 0.3).unwrap_or(false))
        .cloned()
        .collect()
}

// ── Admin commands ───────────────────────────────────────────────────────

#[tauri::command]
pub fn trigger_reload(state: State<BrainState>) -> Result<String, String> {
    let mut version = state.version.lock().unwrap_or_else(|e| e.into_inner());
    *version += 1;
    Ok(format!("Reloaded. Version: {}", *version))
}

#[tauri::command]
pub fn get_reload_status(state: State<BrainState>) -> crate::brain::ReloadStatus {
    state.reload_status.lock().unwrap_or_else(|e| e.into_inner()).clone()
}

// ── Git commands ────────────────────────────────────────────────────────

#[tauri::command]
pub fn get_git_log(
    path: String,
    max_commits: Option<usize>,
) -> Result<Vec<crate::git::GitCommit>, String> {
    let p = std::path::Path::new(&path);
    crate::git::get_git_log(p, max_commits.unwrap_or(50))
}

#[tauri::command]
pub fn get_changed_files(path: String) -> Result<Vec<String>, String> {
    let p = std::path::Path::new(&path);
    crate::git::get_recently_modified(p, 300) // last 5 minutes
}

// ── Health score ─────────────────────────────────────────────────────────

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HealthScoreResult {
    pub node_count: usize,
    pub edge_count: usize,
    pub avg_confidence: f64,
    pub layer_count: usize,
    pub connectivity_ratio: f64,
}

#[tauri::command]
pub fn get_health_score(state: State<BrainState>) -> HealthScoreResult {
    let graph = state.graph.lock().unwrap_or_else(|e| e.into_inner());
    let n = graph.nodes.len();
    let e = graph.edges.len();
    let layers: std::collections::HashSet<i32> = graph.nodes.iter().map(|node| node.layer).collect();

    let avg_conf = if n > 0 {
        graph.nodes.iter().map(|node| node.confidence).sum::<f64>() / n as f64
    } else {
        0.0
    };

    // Connectivity: ratio of nodes that have at least one edge
    let mut connected = std::collections::HashSet::new();
    for edge in &graph.edges {
        connected.insert(edge.from.clone());
        connected.insert(edge.to.clone());
    }
    let connectivity = if n > 0 { connected.len() as f64 / n as f64 } else { 0.0 };

    HealthScoreResult {
        node_count: n,
        edge_count: e,
        avg_confidence: avg_conf,
        layer_count: layers.len(),
        connectivity_ratio: connectivity,
    }
}

// ── Analyze project (cockpit graph_data.json format) ────────────────────

/// Analyze a project and return graph_data.json compatible output
/// for the inference engine (not the brain format).
#[tauri::command]
pub fn analyze_project(path: String) -> Result<serde_json::Value, String> {
    let p = std::path::Path::new(&path);
    if !p.is_dir() {
        return Err(format!("Not a directory: {}", path));
    }

    let config = crate::adapters::AdapterConfig::default();
    let adapters = crate::adapters::all_adapters();

    let applicable: Vec<_> = adapters.iter().filter(|a| a.detect(p)).collect();
    if applicable.is_empty() {
        return Err(format!("No supported files found in {:?}", p));
    }

    // Extract in parallel
    let results: Vec<_> = applicable
        .iter()
        .filter_map(|adapter| {
            adapter.extract(p, &config).ok().map(|g| (adapter.name(), g))
        })
        .collect();

    if results.is_empty() {
        return Err("All adapters failed".to_string());
    }

    // Convert to graph_data.json format
    let project_name = p
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("unknown")
        .to_string();

    let mut nodes: Vec<serde_json::Value> = Vec::new();
    let mut edges: Vec<serde_json::Value> = Vec::new();
    let mut seen_ids = std::collections::HashSet::new();

    for (adapter_name, graph) in &results {
        for raw_node in &graph.nodes {
            // Sanitize ID: replace ':' with '.' for cockpit regex compatibility
            let id = raw_node.id.replace(':', ".");
            if !seen_ids.insert(id.clone()) {
                continue; // deduplicate
            }

            let mut properties = serde_json::Map::new();
            if !raw_node.file_path.is_empty() {
                properties.insert("path".into(), serde_json::Value::String(raw_node.file_path.clone()));
            }
            if let Some(loc) = raw_node.metadata.get("line_count") {
                if let Ok(n) = loc.parse::<u64>() {
                    properties.insert("loc".into(), serde_json::Value::Number(n.into()));
                }
            }
            properties.insert("language".into(), serde_json::Value::String(adapter_name.to_string()));

            let mut node_obj = serde_json::Map::new();
            node_obj.insert("id".into(), serde_json::Value::String(id));
            node_obj.insert("label".into(), serde_json::Value::String(raw_node.label.clone()));
            node_obj.insert("type".into(), serde_json::Value::String(raw_node.node_type.clone()));
            if !properties.is_empty() {
                node_obj.insert("properties".into(), serde_json::Value::Object(properties));
            }

            nodes.push(serde_json::Value::Object(node_obj));
        }

        for raw_edge in &graph.edges {
            let mut edge_obj = serde_json::Map::new();
            edge_obj.insert("from".into(), serde_json::Value::String(raw_edge.from_id.replace(':', ".")));
            edge_obj.insert("to".into(), serde_json::Value::String(raw_edge.to_id.replace(':', ".")));
            edge_obj.insert("type".into(), serde_json::Value::String(raw_edge.edge_type.clone()));
            edges.push(serde_json::Value::Object(edge_obj));
        }
    }

    let now = chrono::Utc::now().to_rfc3339();

    let mut metadata = serde_json::Map::new();
    metadata.insert("name".into(), serde_json::Value::String(project_name));
    metadata.insert("generator".into(), serde_json::Value::String("ontology-map".into()));
    metadata.insert("generated_at".into(), serde_json::Value::String(now));

    let mut result = serde_json::Map::new();
    result.insert("nodes".into(), serde_json::Value::Array(nodes));
    result.insert("edges".into(), serde_json::Value::Array(edges));
    result.insert("metadata".into(), serde_json::Value::Object(metadata));

    Ok(serde_json::Value::Object(result))
}

// ── Project commands ─────────────────────────────────────────────────────

#[tauri::command]
pub fn open_project(
    state: State<BrainState>,
    path: String,
) -> Result<GraphSnapshot, String> {
    let p = std::path::Path::new(&path);
    if !p.is_dir() {
        return Err(format!("Not a directory: {}", path));
    }

    // Run import adapters (detect → extract in parallel → merge)
    let snapshot = crate::adapters::pipeline::run_adapters(p)?;

    // Update shared state
    let mut graph = state.graph.lock().unwrap_or_else(|e| e.into_inner());
    *graph = snapshot.clone();
    let mut version = state.version.lock().unwrap_or_else(|e| e.into_inner());
    *version += 1;

    log::info!(
        "open_project: loaded {} nodes, {} edges from {:?}",
        snapshot.nodes.len(),
        snapshot.edges.len(),
        path
    );

    Ok(snapshot)
}
