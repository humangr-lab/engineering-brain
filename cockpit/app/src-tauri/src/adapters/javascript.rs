//! JavaScript/TypeScript Adapter — extracts modules, exports, imports, components.
//! Regex-based heuristics. Handles .js, .ts, .jsx, .tsx.

use std::collections::HashMap;
use std::path::Path;
use std::sync::LazyLock;

use rayon::prelude::*;
use regex::Regex;

use super::{AdapterConfig, AdapterError, ImportAdapter, RawEdge, RawGraph, RawNode};

// Pre-compiled regexes (compiled once, reused across all files)
static ES_IMPORT_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"(?m)^import\s+(?:(?:[\w*{}\s,]+)\s+from\s+)?['"]([^'"]+)['"]"#).unwrap()
});
static REQUIRE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"(?m)require\s*\(\s*['"]([^'"]+)['"]\s*\)"#).unwrap()
});
static EXPORT_FN_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?m)^export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)").unwrap()
});
static COMPONENT_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?m)^(?:export\s+(?:default\s+)?)?function\s+([A-Z]\w+)").unwrap()
});
static HOOK_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?m)^(?:export\s+)?function\s+(use[A-Z]\w*)").unwrap()
});

pub struct JavaScriptAdapter;

impl ImportAdapter for JavaScriptAdapter {
    fn name(&self) -> &str {
        "javascript"
    }

    fn detect(&self, project_path: &Path) -> bool {
        project_path.join("package.json").exists()
            || project_path.join("tsconfig.json").exists()
            || has_js_files(project_path)
    }

    fn extract(
        &self,
        project_path: &Path,
        config: &AdapterConfig,
    ) -> Result<RawGraph, AdapterError> {
        let files = collect_js_files(project_path, config)?;
        log::info!(
            "JSAdapter: found {} JS/TS files in {:?}",
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
                Some(parse_js_file(&rel_str, &content))
            })
            .collect();

        let mut graph = RawGraph::default();
        for (nodes, edges) in results {
            graph.nodes.extend(nodes);
            graph.edges.extend(edges);
        }

        log::info!(
            "JSAdapter: extracted {} nodes, {} edges",
            graph.nodes.len(),
            graph.edges.len()
        );

        Ok(graph)
    }

    fn supported_extensions(&self) -> &[&str] {
        &["js", "ts", "jsx", "tsx", "mjs"]
    }
}

fn has_js_files(path: &Path) -> bool {
    let extensions = ["js", "ts", "jsx", "tsx"];
    walkdir::WalkDir::new(path)
        .max_depth(3)
        .into_iter()
        .filter_map(|e| e.ok())
        .any(|e| {
            e.path()
                .extension()
                .is_some_and(|ext| extensions.iter().any(|x| ext == *x))
        })
}

fn collect_js_files(
    project_path: &Path,
    config: &AdapterConfig,
) -> Result<Vec<std::path::PathBuf>, AdapterError> {
    let ignore_dirs = [
        "node_modules",
        ".git",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "coverage",
        ".turbo",
    ];
    let extensions = ["js", "ts", "jsx", "tsx", "mjs"];

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
            && entry
                .path()
                .extension()
                .is_some_and(|ext| extensions.iter().any(|x| ext == *x))
        {
            files.push(entry.into_path());
            if files.len() >= config.max_files {
                break;
            }
        }
    }

    Ok(files)
}

fn parse_js_file(rel_path: &str, content: &str) -> (Vec<RawNode>, Vec<RawEdge>) {
    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    // Module ID
    let module_id = format!(
        "js:{}",
        rel_path
            .trim_end_matches(".tsx")
            .trim_end_matches(".ts")
            .trim_end_matches(".jsx")
            .trim_end_matches(".js")
            .trim_end_matches(".mjs")
    );

    let file_label = rel_path.rsplit('/').next().unwrap_or(rel_path);
    let is_react = content.contains("React") || content.contains("jsx") || rel_path.ends_with("tsx") || rel_path.ends_with("jsx");

    // Module node
    nodes.push(RawNode {
        id: module_id.clone(),
        label: file_label.to_string(),
        node_type: if is_react { "component" } else { "module" }.to_string(),
        file_path: rel_path.to_string(),
        line_number: Some(1),
        adapter: "javascript".to_string(),
        metadata: HashMap::new(),
    });

    // Parse imports (ES modules)
    for cap in ES_IMPORT_RE.captures_iter(content) {
        let source = cap.get(1).unwrap().as_str();
        if source.starts_with('.') {
            // Relative import → resolve
            let target_id = resolve_relative_import(rel_path, source);
            edges.push(RawEdge {
                from_id: module_id.clone(),
                to_id: target_id,
                edge_type: "IMPORTS".to_string(),
            });
        }
        // Skip node_modules imports — they're external
    }

    // Parse require() imports (CommonJS)
    for cap in REQUIRE_RE.captures_iter(content) {
        let source = cap.get(1).unwrap().as_str();
        if source.starts_with('.') {
            let target_id = resolve_relative_import(rel_path, source);
            edges.push(RawEdge {
                from_id: module_id.clone(),
                to_id: target_id,
                edge_type: "IMPORTS".to_string(),
            });
        }
    }

    // Parse exports (function/class/const)
    for (line_num, line) in content.lines().enumerate() {
        if let Some(cap) = EXPORT_FN_RE.captures(line) {
            let fn_name = cap.get(1).unwrap().as_str();
            let fn_id = format!("{}:{}", module_id, fn_name);
            nodes.push(RawNode {
                id: fn_id.clone(),
                label: fn_name.to_string(),
                node_type: "function".to_string(),
                file_path: rel_path.to_string(),
                line_number: Some((line_num + 1) as u32),
                adapter: "javascript".to_string(),
                metadata: HashMap::new(),
            });
            edges.push(RawEdge {
                from_id: module_id.clone(),
                to_id: fn_id,
                edge_type: "EXPORTS".to_string(),
            });
        }
    }

    // Detect React components (PascalCase function returning JSX)
    for (line_num, line) in content.lines().enumerate() {
        if let Some(cap) = COMPONENT_RE.captures(line) {
            let name = cap.get(1).unwrap().as_str();
            let comp_id = format!("{}:{}", module_id, name);
            // Avoid duplicating nodes already created as exports
            if !nodes.iter().any(|n| n.id == comp_id) {
                nodes.push(RawNode {
                    id: comp_id.clone(),
                    label: name.to_string(),
                    node_type: "component".to_string(),
                    file_path: rel_path.to_string(),
                    line_number: Some((line_num + 1) as u32),
                    adapter: "javascript".to_string(),
                    metadata: HashMap::new(),
                });
                edges.push(RawEdge {
                    from_id: module_id.clone(),
                    to_id: comp_id,
                    edge_type: "CONTAINS".to_string(),
                });
            }
        }
    }

    // Detect hooks (use* functions)
    for (line_num, line) in content.lines().enumerate() {
        if let Some(cap) = HOOK_RE.captures(line) {
            let name = cap.get(1).unwrap().as_str();
            let hook_id = format!("{}:{}", module_id, name);
            if !nodes.iter().any(|n| n.id == hook_id) {
                nodes.push(RawNode {
                    id: hook_id.clone(),
                    label: name.to_string(),
                    node_type: "hook".to_string(),
                    file_path: rel_path.to_string(),
                    line_number: Some((line_num + 1) as u32),
                    adapter: "javascript".to_string(),
                    metadata: HashMap::new(),
                });
                edges.push(RawEdge {
                    from_id: module_id.clone(),
                    to_id: hook_id,
                    edge_type: "CONTAINS".to_string(),
                });
            }
        }
    }

    (nodes, edges)
}

fn resolve_relative_import(from_path: &str, import_path: &str) -> String {
    // Resolve relative import path against the current file's directory
    let dir = from_path.rsplit_once('/').map(|(d, _)| d).unwrap_or("");
    let parts: Vec<&str> = import_path.split('/').collect();
    let mut resolved_parts: Vec<&str> = if dir.is_empty() {
        vec![]
    } else {
        dir.split('/').collect()
    };

    for part in &parts {
        match *part {
            "." => {}
            ".." => {
                resolved_parts.pop();
            }
            _ => resolved_parts.push(part),
        }
    }

    let resolved = resolved_parts.join("/");
    format!("js:{}", resolved)
}
