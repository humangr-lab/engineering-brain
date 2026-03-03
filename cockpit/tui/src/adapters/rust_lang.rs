//! Rust adapter — tree-sitter AST extraction.
//!
//! Extracts: modules, structs, enums, traits, functions, impl blocks, use statements.

use std::path::Path;

use tree_sitter::{Node, Parser};

use crate::graph::{GraphEdge, GraphNode};

use super::{node_text, rel_path};

/// Parse a Rust file and extract graph nodes + edges.
pub fn parse_file(path: &Path, source: &str, root: &Path) -> (Vec<GraphNode>, Vec<GraphEdge>) {
    let mut parser = Parser::new();
    if parser
        .set_language(&tree_sitter_rust::LANGUAGE.into())
        .is_err()
    {
        return (Vec::new(), Vec::new());
    }

    let tree = match parser.parse(source, None) {
        Some(t) => t,
        None => return (Vec::new(), Vec::new()),
    };

    let rel = rel_path(path, root);
    let module = rust_module_name(path, root);
    let mod_id = format!("rs:{module}");
    let src = source.as_bytes();

    let mut nodes = Vec::new();
    let mut edges = Vec::new();

    // Module node
    nodes.push(GraphNode {
        id: mod_id.clone(),
        label: module.clone(),
        node_type: "module".to_string(),
        file_path: Some(rel),
        line_count: Some(source.lines().count()),
        layer: Some("module".to_string()),
    });

    walk_rust(
        tree.root_node(),
        src,
        &mut nodes,
        &mut edges,
        &mod_id,
        &module,
    );

    (nodes, edges)
}

fn walk_rust(
    node: Node,
    source: &[u8],
    nodes: &mut Vec<GraphNode>,
    edges: &mut Vec<GraphEdge>,
    mod_id: &str,
    module: &str,
) {
    match node.kind() {
        // Function
        "function_item" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let func_id = format!("rs:{module}::{name}");

                // Check visibility
                let is_pub = has_visibility(node);

                nodes.push(GraphNode {
                    id: func_id.clone(),
                    label: if is_pub {
                        format!("pub {name}")
                    } else {
                        name.to_string()
                    },
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

        // Struct
        "struct_item" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let struct_id = format!("rs:{module}::{name}");

                nodes.push(GraphNode {
                    id: struct_id.clone(),
                    label: name.to_string(),
                    node_type: "struct".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("struct".to_string()),
                });

                edges.push(GraphEdge {
                    from: mod_id.to_string(),
                    to: struct_id,
                    edge_type: "contains".to_string(),
                });
            }
        }

        // Enum
        "enum_item" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let enum_id = format!("rs:{module}::{name}");

                nodes.push(GraphNode {
                    id: enum_id.clone(),
                    label: name.to_string(),
                    node_type: "enum".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("enum".to_string()),
                });

                edges.push(GraphEdge {
                    from: mod_id.to_string(),
                    to: enum_id,
                    edge_type: "contains".to_string(),
                });
            }
        }

        // Trait
        "trait_item" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let trait_id = format!("rs:{module}::{name}");

                nodes.push(GraphNode {
                    id: trait_id.clone(),
                    label: name.to_string(),
                    node_type: "trait".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("trait".to_string()),
                });

                edges.push(GraphEdge {
                    from: mod_id.to_string(),
                    to: trait_id,
                    edge_type: "contains".to_string(),
                });
            }
        }

        // Impl block — creates "implements" edges
        "impl_item" => {
            if let Some(type_node) = node.child_by_field_name("type") {
                let type_name = node_text(type_node, source);

                // Check for trait impl: impl Trait for Type
                if let Some(trait_node) = node.child_by_field_name("trait") {
                    let trait_name = node_text(trait_node, source);
                    edges.push(GraphEdge {
                        from: format!("rs:{module}::{type_name}"),
                        to: format!("rs:{module}::{trait_name}"),
                        edge_type: "implements".to_string(),
                    });
                }

                // Extract methods from impl body
                if let Some(body) = node.child_by_field_name("body") {
                    let mut cursor = body.walk();
                    for child in body.children(&mut cursor) {
                        if child.kind() == "function_item" {
                            if let Some(name_node) = child.child_by_field_name("name") {
                                let name = node_text(name_node, source);
                                let method_id =
                                    format!("rs:{module}::{type_name}::{name}");

                                nodes.push(GraphNode {
                                    id: method_id.clone(),
                                    label: format!("{type_name}::{name}"),
                                    node_type: "method".to_string(),
                                    file_path: None,
                                    line_count: None,
                                    layer: Some("method".to_string()),
                                });

                                edges.push(GraphEdge {
                                    from: format!("rs:{module}::{type_name}"),
                                    to: method_id,
                                    edge_type: "contains".to_string(),
                                });
                            }
                        }
                    }
                }
            }
            return;
        }

        // Mod declaration
        "mod_item" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let sub_mod_id = format!("rs:{module}::{name}");

                nodes.push(GraphNode {
                    id: sub_mod_id.clone(),
                    label: name.to_string(),
                    node_type: "module".to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some("module".to_string()),
                });

                edges.push(GraphEdge {
                    from: mod_id.to_string(),
                    to: sub_mod_id,
                    edge_type: "contains".to_string(),
                });
            }
        }

        // Use declarations → import edges
        "use_declaration" => {
            extract_rust_use(node, source, mod_id, module, edges);
            return;
        }

        _ => {}
    }

    // Recurse into children
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        walk_rust(child, source, nodes, edges, mod_id, module);
    }
}

fn extract_rust_use(
    node: Node,
    source: &[u8],
    mod_id: &str,
    _module: &str,
    edges: &mut Vec<GraphEdge>,
) {
    // Extract the use path text and create an import edge
    // use foo::bar::Baz → edge to rs:foo::bar
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        if child.kind() == "use_clause"
            || child.kind() == "scoped_identifier"
            || child.kind() == "use_as_clause"
            || child.kind() == "use_list"
            || child.kind() == "use_wildcard"
            || child.kind() == "identifier"
            || child.kind() == "scoped_use_list"
        {
            let path_text = node_text(child, source);
            // Normalize: take the first two path segments as the target module
            let segments: Vec<&str> = path_text.split("::").collect();
            if segments.len() >= 2 {
                let target = segments[..2.min(segments.len())].join("::");
                // Skip std/core/alloc imports
                if !matches!(segments[0], "std" | "core" | "alloc" | "self" | "super") {
                    edges.push(GraphEdge {
                        from: mod_id.to_string(),
                        to: format!("rs:{target}"),
                        edge_type: "imports".to_string(),
                    });
                }
            }
            break;
        }
    }
}

fn has_visibility(node: Node) -> bool {
    let mut cursor = node.walk();
    let result = node
        .children(&mut cursor)
        .any(|c| c.kind() == "visibility_modifier");
    result
}

/// Module name from a Rust file path (e.g., src/foo/bar.rs → foo::bar).
fn rust_module_name(file: &Path, root: &Path) -> String {
    let rel = file.strip_prefix(root).unwrap_or(file);
    let mut parts: Vec<&str> = rel
        .components()
        .filter_map(|c| c.as_os_str().to_str())
        .collect();

    // Remove .rs extension
    if let Some(last) = parts.last_mut() {
        if let Some(stripped) = last.strip_suffix(".rs") {
            *last = stripped;
        }
    }

    // Remove "mod" or "lib" at the end (they represent the parent module)
    if matches!(parts.last(), Some(&"mod") | Some(&"lib")) {
        parts.pop();
    }

    // Skip "src" prefix if present
    if parts.first() == Some(&"src") {
        parts.remove(0);
    }

    if parts.is_empty() {
        "crate".to_string()
    } else {
        parts.join("::")
    }
}
