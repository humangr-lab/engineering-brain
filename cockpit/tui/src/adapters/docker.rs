//! Docker Compose adapter — YAML-based extraction.
//!
//! Extracts: services, depends_on, networks, volumes.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

use crate::graph::{GraphEdge, GraphNode};

/// Parse Docker Compose files (not parallelized — typically only 1-2 files).
pub fn parse_files(files: &[PathBuf], _root: &Path) -> (Vec<GraphNode>, Vec<GraphEdge>) {
    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    for file in files {
        let content = match fs::read_to_string(file) {
            Ok(c) => c,
            Err(_) => continue,
        };

        let doc: serde_yaml::Value = match serde_yaml::from_str(&content) {
            Ok(v) => v,
            Err(_) => continue,
        };

        // Extract services
        if let Some(services) = doc.get("services").and_then(|s| s.as_mapping()) {
            for (name, config) in services {
                let svc_name = name.as_str().unwrap_or("unknown");
                let svc_id = format!("docker:{svc_name}");

                let image = config
                    .get("image")
                    .and_then(|v| v.as_str())
                    .unwrap_or(svc_name);

                let ports: Vec<String> = config
                    .get("ports")
                    .and_then(|v| v.as_sequence())
                    .map(|seq| {
                        seq.iter()
                            .filter_map(|p| p.as_str().map(std::string::ToString::to_string))
                            .collect()
                    })
                    .unwrap_or_default();

                let label = if !ports.is_empty() {
                    format!("{svc_name} ({})", ports.join(", "))
                } else if image != svc_name {
                    format!("{svc_name} [{image}]")
                } else {
                    svc_name.to_string()
                };

                nodes.push(GraphNode {
                    id: svc_id.clone(),
                    label,
                    node_type: "service".to_string(),
                    file_path: Some(
                        file.file_name()
                            .and_then(|n| n.to_str())
                            .unwrap_or("docker-compose.yml")
                            .to_string(),
                    ),
                    line_count: None,
                    layer: Some("infrastructure".to_string()),
                });

                // depends_on
                if let Some(deps) = config.get("depends_on") {
                    let dep_names: Vec<String> = match deps {
                        serde_yaml::Value::Sequence(seq) => seq
                            .iter()
                            .filter_map(|v| v.as_str().map(std::string::ToString::to_string))
                            .collect(),
                        serde_yaml::Value::Mapping(map) => map
                            .keys()
                            .filter_map(|k| k.as_str().map(std::string::ToString::to_string))
                            .collect(),
                        _ => Vec::new(),
                    };

                    for dep in dep_names {
                        edges.push(GraphEdge {
                            from: svc_id.clone(),
                            to: format!("docker:{dep}"),
                            edge_type: "depends_on".to_string(),
                        });
                    }
                }

                // networks
                if let Some(networks) = config.get("networks") {
                    if let Some(nets) = networks.as_sequence() {
                        for net in nets {
                            if let Some(net_name) = net.as_str() {
                                edges.push(GraphEdge {
                                    from: svc_id.clone(),
                                    to: format!("docker:net:{net_name}"),
                                    edge_type: "network".to_string(),
                                });
                            }
                        }
                    }
                }

                // volumes
                if let Some(volumes) = config.get("volumes") {
                    if let Some(vols) = volumes.as_sequence() {
                        for vol in vols {
                            if let Some(vol_str) = vol.as_str() {
                                if !vol_str.starts_with('.') && !vol_str.starts_with('/') {
                                    let vol_name =
                                        vol_str.split(':').next().unwrap_or(vol_str);
                                    edges.push(GraphEdge {
                                        from: svc_id.clone(),
                                        to: format!("docker:vol:{vol_name}"),
                                        edge_type: "volume".to_string(),
                                    });
                                }
                            }
                        }
                    }
                }
            }
        }

        // Network nodes
        if let Some(networks) = doc.get("networks").and_then(|n| n.as_mapping()) {
            for name in networks.keys() {
                let net_name = name.as_str().unwrap_or("default");
                nodes.push(GraphNode {
                    id: format!("docker:net:{net_name}"),
                    label: format!("net:{net_name}"),
                    node_type: "network".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("infrastructure".to_string()),
                });
            }
        }

        // Volume nodes
        if let Some(volumes) = doc.get("volumes").and_then(|v| v.as_mapping()) {
            for name in volumes.keys() {
                let vol_name = name.as_str().unwrap_or("data");
                nodes.push(GraphNode {
                    id: format!("docker:vol:{vol_name}"),
                    label: format!("vol:{vol_name}"),
                    node_type: "volume".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("infrastructure".to_string()),
                });
            }
        }
    }

    // Filter edges to existing nodes
    let node_ids: HashSet<&str> = nodes.iter().map(|n| n.id.as_str()).collect();
    edges.retain(|e| node_ids.contains(e.to.as_str()));

    (nodes, edges)
}
