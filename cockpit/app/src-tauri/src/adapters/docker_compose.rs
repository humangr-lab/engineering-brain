//! Docker Compose Adapter — extracts services, networks, volumes, dependencies.

use std::collections::HashMap;
use std::path::Path;

use super::{AdapterConfig, AdapterError, ImportAdapter, RawEdge, RawGraph, RawNode};

pub struct DockerComposeAdapter;

impl ImportAdapter for DockerComposeAdapter {
    fn name(&self) -> &str {
        "docker-compose"
    }

    fn detect(&self, project_path: &Path) -> bool {
        project_path.join("docker-compose.yml").exists()
            || project_path.join("docker-compose.yaml").exists()
            || project_path.join("compose.yml").exists()
            || project_path.join("compose.yaml").exists()
    }

    fn extract(
        &self,
        project_path: &Path,
        _config: &AdapterConfig,
    ) -> Result<RawGraph, AdapterError> {
        let compose_path = find_compose_file(project_path)
            .ok_or_else(|| AdapterError::Other("No docker-compose file found".into()))?;

        let content = std::fs::read_to_string(&compose_path)?;
        let yaml: serde_yaml::Value = serde_yaml::from_str(&content).map_err(|e| {
            AdapterError::Parse {
                path: compose_path.to_string_lossy().to_string(),
                message: e.to_string(),
            }
        })?;

        let rel_path = compose_path
            .strip_prefix(project_path)
            .unwrap_or(&compose_path)
            .to_string_lossy()
            .to_string();

        parse_compose(&yaml, &rel_path)
    }

    fn supported_extensions(&self) -> &[&str] {
        &["yml", "yaml"]
    }
}

fn find_compose_file(project_path: &Path) -> Option<std::path::PathBuf> {
    let candidates = [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ];
    for name in &candidates {
        let path = project_path.join(name);
        if path.exists() {
            return Some(path);
        }
    }
    None
}

fn parse_compose(yaml: &serde_yaml::Value, rel_path: &str) -> Result<RawGraph, AdapterError> {
    let mut graph = RawGraph::default();

    // Parse services
    if let Some(services) = yaml.get("services").and_then(|s| s.as_mapping()) {
        for (name, config) in services {
            let service_name = name.as_str().unwrap_or("unknown");
            let service_id = format!("docker:{}", service_name);

            let mut metadata = HashMap::new();

            // Extract image
            if let Some(image) = config.get("image").and_then(|v| v.as_str()) {
                metadata.insert("image".into(), image.into());
            }

            // Extract ports
            if let Some(ports) = config.get("ports").and_then(|v| v.as_sequence()) {
                let port_strs: Vec<String> = ports
                    .iter()
                    .filter_map(|p| p.as_str().map(|s| s.to_string()))
                    .collect();
                if !port_strs.is_empty() {
                    metadata.insert("ports".into(), port_strs.join(", "));
                }
            }

            // Extract build context
            if let Some(build) = config.get("build") {
                let context = if let Some(s) = build.as_str() {
                    s.to_string()
                } else if let Some(ctx) = build.get("context").and_then(|v| v.as_str()) {
                    ctx.to_string()
                } else {
                    ".".to_string()
                };
                metadata.insert("build_context".into(), context);
            }

            nodes_push(
                &mut graph,
                service_id.clone(),
                service_name.to_string(),
                "service",
                rel_path,
                metadata,
            );

            // depends_on edges
            if let Some(deps) = config.get("depends_on") {
                let dep_names: Vec<String> = if let Some(seq) = deps.as_sequence() {
                    seq.iter()
                        .filter_map(|v| v.as_str().map(|s| s.to_string()))
                        .collect()
                } else if let Some(map) = deps.as_mapping() {
                    map.keys()
                        .filter_map(|k| k.as_str().map(|s| s.to_string()))
                        .collect()
                } else {
                    vec![]
                };

                for dep in dep_names {
                    graph.edges.push(RawEdge {
                        from_id: service_id.clone(),
                        to_id: format!("docker:{}", dep),
                        edge_type: "DEPENDS_ON".to_string(),
                    });
                }
            }

            // volumes edges
            if let Some(volumes) = config.get("volumes").and_then(|v| v.as_sequence()) {
                for vol in volumes {
                    if let Some(vol_str) = vol.as_str() {
                        if let Some((host, _)) = vol_str.split_once(':') {
                            let vol_id = format!("docker:volume:{}", host.replace('/', "_"));
                            if !graph.nodes.iter().any(|n| n.id == vol_id) {
                                nodes_push(
                                    &mut graph,
                                    vol_id.clone(),
                                    host.to_string(),
                                    "volume",
                                    rel_path,
                                    HashMap::new(),
                                );
                            }
                            graph.edges.push(RawEdge {
                                from_id: service_id.clone(),
                                to_id: vol_id,
                                edge_type: "MOUNTS".to_string(),
                            });
                        }
                    }
                }
            }

            // network edges
            if let Some(networks) = config.get("networks").and_then(|v| v.as_sequence()) {
                for net in networks {
                    if let Some(net_name) = net.as_str() {
                        let net_id = format!("docker:network:{}", net_name);
                        if !graph.nodes.iter().any(|n| n.id == net_id) {
                            nodes_push(
                                &mut graph,
                                net_id.clone(),
                                net_name.to_string(),
                                "network",
                                rel_path,
                                HashMap::new(),
                            );
                        }
                        graph.edges.push(RawEdge {
                            from_id: service_id.clone(),
                            to_id: net_id,
                            edge_type: "CONNECTED_TO".to_string(),
                        });
                    }
                }
            }
        }
    }

    // Parse top-level networks
    if let Some(networks) = yaml.get("networks").and_then(|n| n.as_mapping()) {
        for (name, _config) in networks {
            let net_name = name.as_str().unwrap_or("unknown");
            let net_id = format!("docker:network:{}", net_name);
            if !graph.nodes.iter().any(|n| n.id == net_id) {
                nodes_push(
                    &mut graph,
                    net_id,
                    net_name.to_string(),
                    "network",
                    rel_path,
                    HashMap::new(),
                );
            }
        }
    }

    log::info!(
        "DockerComposeAdapter: extracted {} nodes, {} edges",
        graph.nodes.len(),
        graph.edges.len()
    );

    Ok(graph)
}

fn nodes_push(
    graph: &mut RawGraph,
    id: String,
    label: String,
    node_type: &str,
    file_path: &str,
    metadata: HashMap<String, String>,
) {
    graph.nodes.push(RawNode {
        id,
        label,
        node_type: node_type.to_string(),
        file_path: file_path.to_string(),
        line_number: None,
        adapter: "docker-compose".to_string(),
        metadata,
    });
}
