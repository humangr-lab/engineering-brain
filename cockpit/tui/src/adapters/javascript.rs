//! JavaScript / TypeScript adapter — tree-sitter AST extraction.
//!
//! Extracts: modules, exports, components, hooks, imports, function calls.

use std::path::Path;

use tree_sitter::{Node, Parser};

use crate::graph::{GraphEdge, GraphNode};

use super::{node_text, rel_path};

/// Parse a JavaScript file.
pub fn parse_js_file(
    path: &Path,
    source: &str,
    root: &Path,
) -> (Vec<GraphNode>, Vec<GraphEdge>) {
    parse_with_language(path, source, root, &tree_sitter_javascript::LANGUAGE.into())
}

/// Parse a TypeScript file.
pub fn parse_ts_file(
    path: &Path,
    source: &str,
    root: &Path,
) -> (Vec<GraphNode>, Vec<GraphEdge>) {
    let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
    let lang: tree_sitter::Language = if ext == "tsx" {
        tree_sitter_typescript::LANGUAGE_TSX.into()
    } else {
        tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into()
    };
    parse_with_language(path, source, root, &lang)
}

fn parse_with_language(
    path: &Path,
    source: &str,
    root: &Path,
    language: &tree_sitter::Language,
) -> (Vec<GraphNode>, Vec<GraphEdge>) {
    let mut parser = Parser::new();
    if parser.set_language(language).is_err() {
        return (Vec::new(), Vec::new());
    }

    let tree = match parser.parse(source, None) {
        Some(t) => t,
        None => return (Vec::new(), Vec::new()),
    };

    let rel = rel_path(path, root);
    let module = js_module_name(path, root);
    let mod_id = format!("js:{module}");
    let src = source.as_bytes();
    let is_jsx = rel.ends_with(".tsx") || rel.ends_with(".jsx");

    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    // Module node
    nodes.push(GraphNode {
        id: mod_id.clone(),
        label: path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown")
            .to_string(),
        node_type: "module".to_string(),
        file_path: Some(rel),
        line_count: Some(source.lines().count()),
        layer: Some("module".to_string()),
    });

    walk_js(
        tree.root_node(),
        src,
        &mut nodes,
        &mut edges,
        &mod_id,
        &module,
        is_jsx,
        false,
    );

    (nodes, edges)
}

#[allow(clippy::too_many_arguments)]
fn walk_js(
    node: Node,
    source: &[u8],
    nodes: &mut Vec<GraphNode>,
    edges: &mut Vec<GraphEdge>,
    mod_id: &str,
    module: &str,
    is_jsx: bool,
    inside_export: bool,
) {
    match node.kind() {
        // Export statement — mark children as exported
        "export_statement" => {
            let mut cursor = node.walk();
            for child in node.children(&mut cursor) {
                walk_js(child, source, nodes, edges, mod_id, module, is_jsx, true);
            }
            return;
        }

        // Function declaration
        "function_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let func_id = format!("js:{module}.{name}");

                let has_jsx = is_jsx || contains_jsx(node);
                let (node_type, layer) = if is_component_name(name) && has_jsx {
                    ("component", "component")
                } else if name.starts_with("use") && name.len() > 3 {
                    ("hook", "hook")
                } else if inside_export {
                    ("export", "export")
                } else {
                    ("function", "function")
                };

                nodes.push(GraphNode {
                    id: func_id.clone(),
                    label: name.to_string(),
                    node_type: node_type.to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some(layer.to_string()),
                });

                edges.push(GraphEdge {
                    from: mod_id.to_string(),
                    to: func_id,
                    edge_type: if inside_export {
                        "exports".to_string()
                    } else {
                        "contains".to_string()
                    },
                });
            }
        }

        // Class declaration
        "class_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let class_id = format!("js:{module}.{name}");

                nodes.push(GraphNode {
                    id: class_id.clone(),
                    label: name.to_string(),
                    node_type: "class".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("class".to_string()),
                });

                edges.push(GraphEdge {
                    from: mod_id.to_string(),
                    to: class_id,
                    edge_type: if inside_export {
                        "exports".to_string()
                    } else {
                        "contains".to_string()
                    },
                });
            }
        }

        // Variable declarations (const Foo = ..., const useFoo = ...)
        "lexical_declaration" | "variable_declaration" => {
            let mut cursor = node.walk();
            for child in node.children(&mut cursor) {
                if child.kind() == "variable_declarator" {
                    if let Some(name_node) = child.child_by_field_name("name") {
                        let name = node_text(name_node, source);
                        if name.is_empty() {
                            continue;
                        }

                        // Check if the value is an arrow function or function expression
                        let is_func = child
                            .child_by_field_name("value")
                            .is_some_and(|v| {
                                v.kind() == "arrow_function"
                                    || v.kind() == "function"
                                    || v.kind() == "function_expression"
                            });

                        if !is_func && !inside_export {
                            continue;
                        }

                        let has_jsx = is_jsx || child
                            .child_by_field_name("value")
                            .is_some_and(|v| contains_jsx(v));
                        let (node_type, layer) = if is_component_name(name) && has_jsx {
                            ("component", "component")
                        } else if name.starts_with("use") && name.len() > 3 {
                            ("hook", "hook")
                        } else if inside_export {
                            ("export", "export")
                        } else {
                            ("function", "function")
                        };

                        let var_id = format!("js:{module}.{name}");
                        if !nodes.iter().any(|n| n.id == var_id) {
                            nodes.push(GraphNode {
                                id: var_id.clone(),
                                label: name.to_string(),
                                node_type: node_type.to_string(),
                                file_path: None,
                                line_count: None,
                                layer: Some(layer.to_string()),
                            });

                            edges.push(GraphEdge {
                                from: mod_id.to_string(),
                                to: var_id,
                                edge_type: if inside_export {
                                    "exports".to_string()
                                } else {
                                    "contains".to_string()
                                },
                            });
                        }
                    }
                }
            }
        }

        // TypeScript-specific: interface, type alias, enum
        "interface_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let iface_id = format!("js:{module}.{name}");
                nodes.push(GraphNode {
                    id: iface_id.clone(),
                    label: name.to_string(),
                    node_type: "interface".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("type".to_string()),
                });
                edges.push(GraphEdge {
                    from: mod_id.to_string(),
                    to: iface_id,
                    edge_type: if inside_export {
                        "exports".to_string()
                    } else {
                        "contains".to_string()
                    },
                });
            }
        }

        "type_alias_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let type_id = format!("js:{module}.{name}");
                nodes.push(GraphNode {
                    id: type_id.clone(),
                    label: name.to_string(),
                    node_type: "type".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("type".to_string()),
                });
                edges.push(GraphEdge {
                    from: mod_id.to_string(),
                    to: type_id,
                    edge_type: if inside_export {
                        "exports".to_string()
                    } else {
                        "contains".to_string()
                    },
                });
            }
        }

        "enum_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let enum_id = format!("js:{module}.{name}");
                nodes.push(GraphNode {
                    id: enum_id.clone(),
                    label: name.to_string(),
                    node_type: "enum".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("type".to_string()),
                });
                edges.push(GraphEdge {
                    from: mod_id.to_string(),
                    to: enum_id,
                    edge_type: if inside_export {
                        "exports".to_string()
                    } else {
                        "contains".to_string()
                    },
                });
            }
        }

        // Import statement
        "import_statement" => {
            if let Some(source_node) = node.child_by_field_name("source") {
                let raw = node_text(source_node, source);
                let target = raw.trim_matches(|c| c == '\'' || c == '"');
                if target.starts_with('.') {
                    // Relative import — resolve path
                    let dir = std::path::Path::new(module)
                        .parent()
                        .unwrap_or(std::path::Path::new(""));
                    let resolved = dir.join(target);
                    let resolved_mod = resolved
                        .to_string_lossy()
                        .replace(['/', '\\'], ".");
                    let clean = resolved_mod
                        .trim_start_matches('.')
                        .to_string();
                    edges.push(GraphEdge {
                        from: mod_id.to_string(),
                        to: format!("js:{clean}"),
                        edge_type: "imports".to_string(),
                    });
                }
            }
            return;
        }

        _ => {}
    }

    // Recurse into children (unless we already returned above)
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        walk_js(
            child,
            source,
            nodes,
            edges,
            mod_id,
            module,
            is_jsx,
            inside_export,
        );
    }
}

/// Check if a name looks like a React component (PascalCase).
fn is_component_name(name: &str) -> bool {
    name.starts_with(|c: char| c.is_ascii_uppercase())
        && name.chars().any(|c| c.is_ascii_lowercase())
}

/// Check if a subtree contains JSX elements (works regardless of file extension).
fn contains_jsx(node: Node) -> bool {
    match node.kind() {
        "jsx_element" | "jsx_self_closing_element" | "jsx_fragment" => return true,
        _ => {}
    }
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        if contains_jsx(child) {
            return true;
        }
    }
    false
}

/// Module name from a JS/TS file path.
fn js_module_name(file: &Path, root: &Path) -> String {
    file.strip_prefix(root)
        .unwrap_or(file)
        .with_extension("")
        .to_string_lossy()
        .replace(['/', '\\'], ".")
}
