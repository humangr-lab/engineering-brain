//! Language adapters — analyze project source code via tree-sitter AST parsing.
//!
//! Supported languages:
//! - Python (.py): modules, classes, functions, methods, imports, calls
//! - JavaScript/TypeScript (.js/.ts/.jsx/.tsx/.mjs/.cjs): modules, exports, components, imports
//! - Go (.go): packages, structs, interfaces, functions, methods, imports
//! - Rust (.rs): modules, structs, enums, traits, functions, use statements
//! - Java (.java): packages, classes, interfaces, methods, imports
//! - C# (.cs): namespaces, classes, interfaces, methods, using directives
//! - Docker Compose (docker-compose.yml): services, dependencies, networks, volumes

mod csharp;
mod docker;
mod go;
mod java;
mod javascript;
mod python;
mod rust_lang;

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::Result;
use rayon::prelude::*;

use crate::graph::{AppGraph, GraphEdge, GraphNode};

/// Detected language for a source file.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum Language {
    Python,
    JavaScript,
    TypeScript,
    Go,
    Rust,
    Java,
    CSharp,
    DockerCompose,
}

impl Language {
    /// Detect language from file path.
    fn detect(path: &Path) -> Option<Self> {
        // Docker Compose files (check filename first)
        if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
            if matches!(
                name,
                "docker-compose.yml"
                    | "docker-compose.yaml"
                    | "compose.yml"
                    | "compose.yaml"
            ) {
                return Some(Language::DockerCompose);
            }
        }

        // Detect by extension
        match path.extension().and_then(|e| e.to_str()) {
            Some("py") => Some(Language::Python),
            Some("js" | "jsx" | "mjs" | "cjs") => Some(Language::JavaScript),
            Some("ts" | "tsx") => Some(Language::TypeScript),
            Some("go") => Some(Language::Go),
            Some("rs") => Some(Language::Rust),
            Some("java") => Some(Language::Java),
            Some("cs") => Some(Language::CSharp),
            _ => None,
        }
    }

    fn name(&self) -> &'static str {
        match self {
            Language::Python => "python",
            Language::JavaScript => "javascript",
            Language::TypeScript => "typescript",
            Language::Go => "go",
            Language::Rust => "rust",
            Language::Java => "java",
            Language::CSharp => "csharp",
            Language::DockerCompose => "docker-compose",
        }
    }
}

/// Analyze a project directory and return the merged graph.
pub fn analyze_project(path: &Path, max_files: usize) -> Result<AppGraph> {
    let files = collect_files(path, max_files);

    // Group files by language
    let mut groups: std::collections::HashMap<Language, Vec<PathBuf>> =
        std::collections::HashMap::new();
    for file in &files {
        if let Some(lang) = Language::detect(file) {
            groups.entry(lang).or_default().push(file.clone());
        }
    }

    let mut all_nodes: Vec<GraphNode> = Vec::new();
    let mut all_edges: Vec<GraphEdge> = Vec::new();
    let mut adapters_used: Vec<String> = Vec::new();

    // Parse each language group
    for (lang, lang_files) in &groups {
        let (nodes, edges) = match lang {
            Language::Python => parse_parallel(lang_files, path, python::parse_file),
            Language::JavaScript => parse_parallel(lang_files, path, javascript::parse_js_file),
            Language::TypeScript => parse_parallel(lang_files, path, javascript::parse_ts_file),
            Language::Go => parse_parallel(lang_files, path, go::parse_file),
            Language::Rust => parse_parallel(lang_files, path, rust_lang::parse_file),
            Language::Java => parse_parallel(lang_files, path, java::parse_file),
            Language::CSharp => parse_parallel(lang_files, path, csharp::parse_file),
            Language::DockerCompose => docker::parse_files(lang_files, path),
        };

        if !nodes.is_empty() {
            all_nodes.extend(nodes);
            all_edges.extend(edges);
            adapters_used.push(lang.name().to_string());
        }
    }

    // Deduplicate nodes by ID
    let mut seen = HashSet::new();
    all_nodes.retain(|n| seen.insert(n.id.clone()));

    // Filter edges to only reference existing nodes
    let node_ids: HashSet<&str> = all_nodes.iter().map(|n| n.id.as_str()).collect();
    all_edges.retain(|e| node_ids.contains(e.to.as_str()));

    // Sort adapters for deterministic output
    adapters_used.sort();
    // Merge JS + TS into one adapter name
    if adapters_used.contains(&"javascript".to_string())
        && adapters_used.contains(&"typescript".to_string())
    {
        adapters_used.retain(|a| a != "typescript");
        if let Some(js) = adapters_used.iter_mut().find(|a| a.as_str() == "javascript") {
            *js = "javascript/typescript".to_string();
        }
    }

    Ok(AppGraph {
        nodes: all_nodes,
        edges: all_edges,
        adapters_used,
    })
}

/// Parse files in parallel using Rayon, with a per-file parse function.
fn parse_parallel<F>(
    files: &[PathBuf],
    root: &Path,
    parse_fn: F,
) -> (Vec<GraphNode>, Vec<GraphEdge>)
where
    F: Fn(&Path, &str, &Path) -> (Vec<GraphNode>, Vec<GraphEdge>) + Sync,
{
    let results: Vec<_> = files
        .par_iter()
        .filter_map(|file| {
            let source = fs::read_to_string(file).ok()?;
            Some(parse_fn(file, &source, root))
        })
        .collect();

    let mut all_nodes = Vec::new();
    let mut all_edges = Vec::new();
    for (nodes, edges) in results {
        all_nodes.extend(nodes);
        all_edges.extend(edges);
    }
    (all_nodes, all_edges)
}

/// Collect source files using the `ignore` crate (respects .gitignore).
fn collect_files(root: &Path, max_files: usize) -> Vec<PathBuf> {
    use ignore::WalkBuilder;

    let mut files = Vec::new();

    let walker = WalkBuilder::new(root)
        .hidden(true) // skip hidden dirs/files
        .git_ignore(true) // respect .gitignore
        .git_global(true)
        .git_exclude(true)
        .build();

    for entry in walker.flatten() {
        if entry.file_type().is_some_and(|ft| ft.is_file())
            && Language::detect(entry.path()).is_some() {
                files.push(entry.into_path());
                if files.len() >= max_files {
                    break;
                }
            }
    }
    files
}

/// Relative path string for display.
pub(crate) fn rel_path(file: &Path, root: &Path) -> String {
    file.strip_prefix(root)
        .unwrap_or(file)
        .to_string_lossy()
        .to_string()
}

/// Extract text from a tree-sitter node.
pub(crate) fn node_text<'a>(node: tree_sitter::Node, source: &'a [u8]) -> &'a str {
    std::str::from_utf8(&source[node.byte_range()]).unwrap_or("")
}
