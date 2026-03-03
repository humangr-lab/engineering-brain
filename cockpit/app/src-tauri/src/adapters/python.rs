//! Python Adapter — extracts modules, classes, functions, and imports.
//! Uses regex-based heuristics for speed. Can be upgraded to tree-sitter.

use std::collections::HashMap;
use std::path::Path;
use std::sync::LazyLock;

use rayon::prelude::*;
use regex::Regex;

use super::{AdapterConfig, AdapterError, ImportAdapter, RawEdge, RawGraph, RawNode};

// Pre-compiled regexes (compiled once, reused across all files)
static IMPORT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?m)^(?:from\s+([\w.]+)\s+)?import\s+([\w.,\s]+)").unwrap());
static CLASS_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?m)^class\s+(\w+)").unwrap());
static FN_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?m)^def\s+(\w+)").unwrap());

pub struct PythonAdapter;

impl ImportAdapter for PythonAdapter {
    fn name(&self) -> &str {
        "python"
    }

    fn detect(&self, project_path: &Path) -> bool {
        // Detect if project has Python files
        project_path.join("pyproject.toml").exists()
            || project_path.join("setup.py").exists()
            || project_path.join("requirements.txt").exists()
            || has_python_files(project_path)
    }

    fn extract(
        &self,
        project_path: &Path,
        config: &AdapterConfig,
    ) -> Result<RawGraph, AdapterError> {
        let files = collect_python_files(project_path, config)?;
        log::info!(
            "PythonAdapter: found {} Python files in {:?}",
            files.len(),
            project_path
        );

        let results: Vec<(Vec<RawNode>, Vec<RawEdge>)> = files
            .par_iter()
            .filter_map(|path| {
                let content = std::fs::read_to_string(path).ok()?;
                if content.len() as u64 > config.max_file_size_bytes {
                    return None;
                }
                let rel_path = path.strip_prefix(project_path).unwrap_or(path);
                let rel_str = rel_path.to_string_lossy().to_string();
                Some(parse_python_file(&rel_str, &content))
            })
            .collect();

        let mut graph = RawGraph::default();
        for (nodes, edges) in results {
            graph.nodes.extend(nodes);
            graph.edges.extend(edges);
        }

        log::info!(
            "PythonAdapter: extracted {} nodes, {} edges",
            graph.nodes.len(),
            graph.edges.len()
        );

        Ok(graph)
    }

    fn supported_extensions(&self) -> &[&str] {
        &["py"]
    }
}

fn has_python_files(path: &Path) -> bool {
    walkdir::WalkDir::new(path)
        .max_depth(3)
        .into_iter()
        .filter_map(|e| e.ok())
        .any(|e| e.path().extension().is_some_and(|ext| ext == "py"))
}

fn collect_python_files(
    project_path: &Path,
    config: &AdapterConfig,
) -> Result<Vec<std::path::PathBuf>, AdapterError> {
    let ignore_dirs = [
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".eggs",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
    ];

    let mut files = Vec::new();
    for entry in walkdir::WalkDir::new(project_path)
        .into_iter()
        .filter_entry(|e| {
            let name = e.file_name().to_string_lossy();
            !ignore_dirs.iter().any(|d| name == *d) && !name.starts_with('.')
        })
    {
        let entry = entry?;
        if entry.file_type().is_file()
            && entry.path().extension().is_some_and(|ext| ext == "py")
        {
            files.push(entry.into_path());
            if files.len() >= config.max_files {
                break;
            }
        }
    }

    Ok(files)
}

fn parse_python_file(rel_path: &str, content: &str) -> (Vec<RawNode>, Vec<RawEdge>) {
    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    // Module node ID: python:{relative_path}
    let module_id = format!("python:{}", rel_path.trim_end_matches(".py").replace('/', "."));

    // Module node
    nodes.push(RawNode {
        id: module_id.clone(),
        label: rel_path
            .rsplit('/')
            .next()
            .unwrap_or(rel_path)
            .trim_end_matches(".py")
            .to_string(),
        node_type: "module".to_string(),
        file_path: rel_path.to_string(),
        line_number: Some(1),
        adapter: "python".to_string(),
        metadata: HashMap::new(),
    });

    // Parse imports
    for cap in IMPORT_RE.captures_iter(content) {
        let from_module = cap.get(1).map(|m| m.as_str());
        let imports = cap.get(2).map(|m| m.as_str()).unwrap_or("");

        if let Some(base) = from_module {
            let target_id = format!("python:{}", base.replace('.', "/"));
            edges.push(RawEdge {
                from_id: module_id.clone(),
                to_id: target_id,
                edge_type: "IMPORTS".to_string(),
            });
        } else {
            for imp in imports.split(',') {
                let name = imp.trim().split_whitespace().next().unwrap_or("").trim();
                if !name.is_empty() {
                    let target_id = format!("python:{}", name.replace('.', "/"));
                    edges.push(RawEdge {
                        from_id: module_id.clone(),
                        to_id: target_id,
                        edge_type: "IMPORTS".to_string(),
                    });
                }
            }
        }
    }

    // Parse class definitions
    for (line_num, line) in content.lines().enumerate() {
        if let Some(cap) = CLASS_RE.captures(line) {
            let class_name = cap.get(1).unwrap().as_str();
            let class_id = format!("{}:{}", module_id, class_name);
            nodes.push(RawNode {
                id: class_id.clone(),
                label: class_name.to_string(),
                node_type: "class".to_string(),
                file_path: rel_path.to_string(),
                line_number: Some((line_num + 1) as u32),
                adapter: "python".to_string(),
                metadata: HashMap::new(),
            });
            edges.push(RawEdge {
                from_id: module_id.clone(),
                to_id: class_id,
                edge_type: "CONTAINS".to_string(),
            });
        }
    }

    // Parse top-level function definitions
    for (line_num, line) in content.lines().enumerate() {
        if let Some(cap) = FN_RE.captures(line) {
            let fn_name = cap.get(1).unwrap().as_str();
            if fn_name.starts_with('_') && fn_name != "__init__" {
                continue; // Skip private functions
            }
            let fn_id = format!("{}:{}", module_id, fn_name);
            nodes.push(RawNode {
                id: fn_id.clone(),
                label: fn_name.to_string(),
                node_type: "function".to_string(),
                file_path: rel_path.to_string(),
                line_number: Some((line_num + 1) as u32),
                adapter: "python".to_string(),
                metadata: HashMap::new(),
            });
            edges.push(RawEdge {
                from_id: module_id.clone(),
                to_id: fn_id,
                edge_type: "CONTAINS".to_string(),
            });
        }
    }

    (nodes, edges)
}
