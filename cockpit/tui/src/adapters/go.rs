//! Go adapter — tree-sitter AST extraction.
//!
//! Extracts: packages, structs, interfaces, functions, methods, imports.

use std::path::Path;

use tree_sitter::{Node, Parser};

use crate::graph::{GraphEdge, GraphNode};

use super::{node_text, rel_path};

/// Parse a Go file and extract graph nodes + edges.
pub fn parse_file(path: &Path, source: &str, root: &Path) -> (Vec<GraphNode>, Vec<GraphEdge>) {
    let mut parser = Parser::new();
    if parser.set_language(&tree_sitter_go::LANGUAGE.into()).is_err() {
        return (Vec::new(), Vec::new());
    }

    let tree = match parser.parse(source, None) {
        Some(t) => t,
        None => return (Vec::new(), Vec::new()),
    };

    let rel = rel_path(path, root);
    let src = source.as_bytes();

    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    // Extract package name from AST
    let package = extract_package(tree.root_node(), src).unwrap_or_else(|| "main".to_string());

    // Compute a file-based module ID (package + filename without ext)
    let file_stem = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown");
    let module = format!("{package}/{file_stem}");
    let mod_id = format!("go:{module}");

    // Module/file node
    nodes.push(GraphNode {
        id: mod_id.clone(),
        label: format!("{package}/{file_stem}"),
        node_type: "module".to_string(),
        file_path: Some(rel),
        line_count: Some(source.lines().count()),
        layer: Some("module".to_string()),
    });

    // Walk AST
    walk_go(tree.root_node(), src, &mut nodes, &mut edges, &mod_id, &module);

    (nodes, edges)
}

fn extract_package(root: Node, source: &[u8]) -> Option<String> {
    let mut cursor = root.walk();
    for child in root.children(&mut cursor) {
        if child.kind() == "package_clause" {
            let mut inner = child.walk();
            for pkg_child in child.children(&mut inner) {
                if pkg_child.kind() == "package_identifier" {
                    return Some(node_text(pkg_child, source).to_string());
                }
            }
        }
    }
    None
}

fn walk_go(
    node: Node,
    source: &[u8],
    nodes: &mut Vec<GraphNode>,
    edges: &mut Vec<GraphEdge>,
    mod_id: &str,
    module: &str,
) {
    match node.kind() {
        // Function declaration
        "function_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let func_id = format!("go:{module}.{name}");

                nodes.push(GraphNode {
                    id: func_id.clone(),
                    label: name.to_string(),
                    node_type: "function".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("function".to_string()),
                });

                edges.push(GraphEdge {
                    from: mod_id.to_string(),
                    to: func_id,
                    edge_type: "contains".to_string(),
                });
            }
        }

        // Method declaration (func (r Receiver) Name(...) ...)
        "method_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let receiver_type = extract_receiver_type(node, source);

                let method_id = if receiver_type.is_empty() {
                    format!("go:{module}.{name}")
                } else {
                    format!("go:{module}.{receiver_type}.{name}")
                };

                nodes.push(GraphNode {
                    id: method_id.clone(),
                    label: format!("{receiver_type}.{name}"),
                    node_type: "method".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("method".to_string()),
                });

                // Link to struct if it exists
                if receiver_type.is_empty() {
                    edges.push(GraphEdge {
                        from: mod_id.to_string(),
                        to: method_id,
                        edge_type: "contains".to_string(),
                    });
                } else {
                    edges.push(GraphEdge {
                        from: format!("go:{module}.{receiver_type}"),
                        to: method_id,
                        edge_type: "contains".to_string(),
                    });
                }
            }
        }

        // Type declarations (struct, interface)
        "type_declaration" => {
            let mut cursor = node.walk();
            for child in node.children(&mut cursor) {
                if child.kind() == "type_spec" {
                    if let Some(name_node) = child.child_by_field_name("name") {
                        let name = node_text(name_node, source);
                        let type_node = child.child_by_field_name("type");
                        let kind = type_node
                            .map_or("type", |t| match t.kind() {
                                "struct_type" => "struct",
                                "interface_type" => "interface",
                                _ => "type",
                            });

                        let type_id = format!("go:{module}.{name}");

                        nodes.push(GraphNode {
                            id: type_id.clone(),
                            label: name.to_string(),
                            node_type: kind.to_string(),
                            file_path: None,
                            line_count: None,
                            layer: Some(kind.to_string()),
                        });

                        edges.push(GraphEdge {
                            from: mod_id.to_string(),
                            to: type_id,
                            edge_type: "contains".to_string(),
                        });
                    }
                }
            }
            return;
        }

        // Import declarations
        "import_declaration" => {
            let mut cursor = node.walk();
            for child in node.children(&mut cursor) {
                extract_go_imports(child, source, mod_id, edges);
            }
            return;
        }

        _ => {}
    }

    // Recurse into children
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        walk_go(child, source, nodes, edges, mod_id, module);
    }
}

fn extract_receiver_type(node: Node, source: &[u8]) -> String {
    if let Some(receiver) = node.child_by_field_name("receiver") {
        let mut cursor = receiver.walk();
        for child in receiver.children(&mut cursor) {
            if child.kind() == "parameter_declaration" {
                if let Some(type_node) = child.child_by_field_name("type") {
                    let text = node_text(type_node, source);
                    return text.trim_start_matches('*').to_string();
                }
            }
        }
    }
    String::new()
}

fn extract_go_imports(
    node: Node,
    source: &[u8],
    mod_id: &str,
    edges: &mut Vec<GraphEdge>,
) {
    match node.kind() {
        "import_spec" | "interpreted_string_literal" => {
            let raw = node_text(node, source);
            let import_path = raw.trim_matches('"');
            if !import_path.is_empty() {
                edges.push(GraphEdge {
                    from: mod_id.to_string(),
                    to: format!("go:{import_path}"),
                    edge_type: "imports".to_string(),
                });
            }
        }
        "import_spec_list" => {
            let mut cursor = node.walk();
            for child in node.children(&mut cursor) {
                extract_go_imports(child, source, mod_id, edges);
            }
        }
        _ => {}
    }
}
