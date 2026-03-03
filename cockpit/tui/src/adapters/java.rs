//! Java adapter — tree-sitter AST extraction.
//!
//! Extracts: packages, classes, interfaces, methods, imports.

use std::path::Path;

use tree_sitter::{Node, Parser};

use crate::graph::{GraphEdge, GraphNode};

use super::{node_text, rel_path};

/// Parse a Java file and extract graph nodes + edges.
pub fn parse_file(path: &Path, source: &str, root: &Path) -> (Vec<GraphNode>, Vec<GraphEdge>) {
    let mut parser = Parser::new();
    if parser.set_language(&tree_sitter_java::LANGUAGE.into()).is_err() {
        return (Vec::new(), Vec::new());
    }

    let tree = match parser.parse(source, None) {
        Some(t) => t,
        None => return (Vec::new(), Vec::new()),
    };

    let rel = rel_path(path, root);
    let src = source.as_bytes();

    // Extract package name
    let package = extract_package(tree.root_node(), src).unwrap_or_default();

    let file_stem = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("Unknown");
    let module = if package.is_empty() {
        file_stem.to_string()
    } else {
        format!("{package}.{file_stem}")
    };
    let mod_id = format!("java:{module}");

    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    // Module/file node
    nodes.push(GraphNode {
        id: mod_id.clone(),
        label: file_stem.to_string(),
        node_type: "module".to_string(),
        file_path: Some(rel),
        line_count: Some(source.lines().count()),
        layer: Some("module".to_string()),
    });

    walk_java(
        tree.root_node(),
        src,
        &mut nodes,
        &mut edges,
        &mod_id,
        &module,
    );

    (nodes, edges)
}

fn extract_package(root: Node, source: &[u8]) -> Option<String> {
    let mut cursor = root.walk();
    for child in root.children(&mut cursor) {
        if child.kind() == "package_declaration" {
            // The package name is a scoped_identifier or identifier child
            let mut inner = child.walk();
            for pkg_child in child.children(&mut inner) {
                if pkg_child.kind() == "scoped_identifier" || pkg_child.kind() == "identifier" {
                    return Some(node_text(pkg_child, source).to_string());
                }
            }
        }
    }
    None
}

fn walk_java(
    node: Node,
    source: &[u8],
    nodes: &mut Vec<GraphNode>,
    edges: &mut Vec<GraphEdge>,
    parent_id: &str,
    module: &str,
) {
    match node.kind() {
        // Class declaration
        "class_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let class_id = format!("java:{module}.{name}");

                nodes.push(GraphNode {
                    id: class_id.clone(),
                    label: name.to_string(),
                    node_type: "class".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("class".to_string()),
                });

                edges.push(GraphEdge {
                    from: parent_id.to_string(),
                    to: class_id.clone(),
                    edge_type: "contains".to_string(),
                });

                // Check for extends/implements
                if let Some(superclass) = node.child_by_field_name("superclass") {
                    let super_name = node_text(superclass, source);
                    edges.push(GraphEdge {
                        from: class_id.clone(),
                        to: format!("java:{module}.{super_name}"),
                        edge_type: "extends".to_string(),
                    });
                }

                if let Some(interfaces) = node.child_by_field_name("interfaces") {
                    let mut cursor = interfaces.walk();
                    for child in interfaces.children(&mut cursor) {
                        if child.kind() == "type_identifier" {
                            let iface_name = node_text(child, source);
                            edges.push(GraphEdge {
                                from: class_id.clone(),
                                to: format!("java:{module}.{iface_name}"),
                                edge_type: "implements".to_string(),
                            });
                        }
                    }
                }

                // Recurse into class body
                if let Some(body) = node.child_by_field_name("body") {
                    walk_java(body, source, nodes, edges, &class_id, module);
                }
                return;
            }
        }

        // Interface declaration
        "interface_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let iface_id = format!("java:{module}.{name}");

                nodes.push(GraphNode {
                    id: iface_id.clone(),
                    label: name.to_string(),
                    node_type: "interface".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("interface".to_string()),
                });

                edges.push(GraphEdge {
                    from: parent_id.to_string(),
                    to: iface_id.clone(),
                    edge_type: "contains".to_string(),
                });

                // Recurse into interface body
                if let Some(body) = node.child_by_field_name("body") {
                    walk_java(body, source, nodes, edges, &iface_id, module);
                }
                return;
            }
        }

        // Enum declaration
        "enum_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let enum_id = format!("java:{module}.{name}");

                nodes.push(GraphNode {
                    id: enum_id.clone(),
                    label: name.to_string(),
                    node_type: "enum".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("enum".to_string()),
                });

                edges.push(GraphEdge {
                    from: parent_id.to_string(),
                    to: enum_id,
                    edge_type: "contains".to_string(),
                });
            }
        }

        // Method declaration
        "method_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let method_id = format!("{parent_id}.{name}");

                nodes.push(GraphNode {
                    id: method_id.clone(),
                    label: name.to_string(),
                    node_type: "method".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("method".to_string()),
                });

                edges.push(GraphEdge {
                    from: parent_id.to_string(),
                    to: method_id,
                    edge_type: "contains".to_string(),
                });
            }
        }

        // Constructor
        "constructor_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let ctor_id = format!("{parent_id}.{name}");

                nodes.push(GraphNode {
                    id: ctor_id.clone(),
                    label: format!("{name}()"),
                    node_type: "constructor".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("method".to_string()),
                });

                edges.push(GraphEdge {
                    from: parent_id.to_string(),
                    to: ctor_id,
                    edge_type: "contains".to_string(),
                });
            }
        }

        // Import declaration
        "import_declaration" => {
            let mut cursor = node.walk();
            for child in node.children(&mut cursor) {
                if child.kind() == "scoped_identifier" || child.kind() == "identifier" {
                    let import_path = node_text(child, source);
                    // Take the package part (everything except the last segment)
                    let parts: Vec<&str> = import_path.split('.').collect();
                    if parts.len() >= 2 {
                        let target = parts[..parts.len() - 1].join(".");
                        edges.push(GraphEdge {
                            from: parent_id.to_string(),
                            to: format!("java:{target}"),
                            edge_type: "imports".to_string(),
                        });
                    }
                }
            }
            return;
        }

        _ => {}
    }

    // Recurse
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        walk_java(child, source, nodes, edges, parent_id, module);
    }
}
