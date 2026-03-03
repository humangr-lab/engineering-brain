//! C# adapter — tree-sitter AST extraction.
//!
//! Extracts: namespaces, classes, interfaces, structs, methods, using directives.

use std::path::Path;

use tree_sitter::{Node, Parser};

use crate::graph::{GraphEdge, GraphNode};

use super::{node_text, rel_path};

/// Parse a C# file and extract graph nodes + edges.
pub fn parse_file(path: &Path, source: &str, root: &Path) -> (Vec<GraphNode>, Vec<GraphEdge>) {
    let mut parser = Parser::new();
    if parser
        .set_language(&tree_sitter_c_sharp::LANGUAGE.into())
        .is_err()
    {
        return (Vec::new(), Vec::new());
    }

    let tree = match parser.parse(source, None) {
        Some(t) => t,
        None => return (Vec::new(), Vec::new()),
    };

    let rel = rel_path(path, root);
    let src = source.as_bytes();

    let file_stem = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("Unknown");

    // Extract namespace or use filename
    let namespace =
        extract_namespace(tree.root_node(), src).unwrap_or_else(|| file_stem.to_string());
    let mod_id = format!("cs:{namespace}");

    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    // Module/file node
    nodes.push(GraphNode {
        id: mod_id.clone(),
        label: namespace.clone(),
        node_type: "namespace".to_string(),
        file_path: Some(rel),
        line_count: Some(source.lines().count()),
        layer: Some("module".to_string()),
    });

    walk_csharp(
        tree.root_node(),
        src,
        &mut nodes,
        &mut edges,
        &mod_id,
        &namespace,
    );

    (nodes, edges)
}

fn extract_namespace(root: Node, source: &[u8]) -> Option<String> {
    let mut cursor = root.walk();
    for child in root.children(&mut cursor) {
        if child.kind() == "namespace_declaration"
            || child.kind() == "file_scoped_namespace_declaration"
        {
            if let Some(name_node) = child.child_by_field_name("name") {
                return Some(node_text(name_node, source).to_string());
            }
        }
    }
    None
}

fn walk_csharp(
    node: Node,
    source: &[u8],
    nodes: &mut Vec<GraphNode>,
    edges: &mut Vec<GraphEdge>,
    parent_id: &str,
    namespace: &str,
) {
    match node.kind() {
        // Namespace declaration (nested)
        "namespace_declaration" | "file_scoped_namespace_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let ns_id = format!("cs:{name}");

                if ns_id != *parent_id {
                    nodes.push(GraphNode {
                        id: ns_id.clone(),
                        label: name.to_string(),
                        node_type: "namespace".to_string(),
                        file_path: None,
                        line_count: None,
                        layer: Some("module".to_string()),
                    });

                    edges.push(GraphEdge {
                        from: parent_id.to_string(),
                        to: ns_id.clone(),
                        edge_type: "contains".to_string(),
                    });
                }

                // Recurse with new namespace as parent
                if let Some(body) = node.child_by_field_name("body") {
                    walk_csharp(body, source, nodes, edges, &ns_id, name);
                } else {
                    // File-scoped namespace — siblings are the body
                    let mut cursor = node.walk();
                    for child in node.children(&mut cursor) {
                        walk_csharp(child, source, nodes, edges, &ns_id, name);
                    }
                }
                return;
            }
        }

        // Class declaration
        "class_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let class_id = format!("cs:{namespace}.{name}");

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

                // Check base_list for inheritance
                if let Some(base_list) = node.child_by_field_name("bases") {
                    let mut cursor = base_list.walk();
                    for child in base_list.children(&mut cursor) {
                        if child.kind() == "identifier"
                            || child.kind() == "generic_name"
                            || child.kind() == "qualified_name"
                        {
                            let base_name = node_text(child, source);
                            edges.push(GraphEdge {
                                from: class_id.clone(),
                                to: format!("cs:{namespace}.{base_name}"),
                                edge_type: "extends".to_string(),
                            });
                        }
                    }
                }

                // Recurse into class body
                if let Some(body) = node.child_by_field_name("body") {
                    walk_csharp(body, source, nodes, edges, &class_id, namespace);
                }
                return;
            }
        }

        // Interface
        "interface_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let iface_id = format!("cs:{namespace}.{name}");

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

                // Recurse
                if let Some(body) = node.child_by_field_name("body") {
                    walk_csharp(body, source, nodes, edges, &iface_id, namespace);
                }
                return;
            }
        }

        // Struct
        "struct_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let struct_id = format!("cs:{namespace}.{name}");

                nodes.push(GraphNode {
                    id: struct_id.clone(),
                    label: name.to_string(),
                    node_type: "struct".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("struct".to_string()),
                });

                edges.push(GraphEdge {
                    from: parent_id.to_string(),
                    to: struct_id.clone(),
                    edge_type: "contains".to_string(),
                });

                if let Some(body) = node.child_by_field_name("body") {
                    walk_csharp(body, source, nodes, edges, &struct_id, namespace);
                }
                return;
            }
        }

        // Enum
        "enum_declaration" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let enum_id = format!("cs:{namespace}.{name}");

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

        // Method
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

        // Using directive
        "using_directive" => {
            let mut cursor = node.walk();
            for child in node.children(&mut cursor) {
                if child.kind() == "qualified_name" || child.kind() == "identifier" {
                    let using_path = node_text(child, source);
                    if !using_path.starts_with("System") {
                        edges.push(GraphEdge {
                            from: parent_id.to_string(),
                            to: format!("cs:{using_path}"),
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
        walk_csharp(child, source, nodes, edges, parent_id, namespace);
    }
}
