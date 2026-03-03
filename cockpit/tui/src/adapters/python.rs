//! Python adapter — tree-sitter AST extraction.
//!
//! Extracts: modules, classes, functions, methods, imports, function calls.

use std::path::Path;

use tree_sitter::{Node, Parser};

use crate::graph::{GraphEdge, GraphNode};

use super::{node_text, rel_path};

/// Parse a Python file and extract graph nodes + edges.
pub fn parse_file(path: &Path, source: &str, root: &Path) -> (Vec<GraphNode>, Vec<GraphEdge>) {
    let mut parser = Parser::new();
    if parser
        .set_language(&tree_sitter_python::LANGUAGE.into())
        .is_err()
    {
        return (Vec::new(), Vec::new());
    }

    let tree = match parser.parse(source, None) {
        Some(t) => t,
        None => return (Vec::new(), Vec::new()),
    };

    let rel = rel_path(path, root);
    let module = py_module_name(path, root);
    let mod_id = format!("py:{module}");
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

    // Walk the AST
    walk_python(
        tree.root_node(),
        src,
        &mut nodes,
        &mut edges,
        &mod_id,
        &module,
        Scope::Module,
    );

    (nodes, edges)
}

#[derive(Clone)]
enum Scope {
    Module,
    Class(String), // class name for qualified IDs
}

fn walk_python(
    node: Node,
    source: &[u8],
    nodes: &mut Vec<GraphNode>,
    edges: &mut Vec<GraphEdge>,
    mod_id: &str,
    module: &str,
    scope: Scope,
) {
    match node.kind() {
        // Class definition
        "class_definition" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);
                let class_id = format!("py:{module}.{name}");

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
                    to: class_id.clone(),
                    edge_type: "contains".to_string(),
                });

                // Recurse into class body with Class scope
                if let Some(body) = node.child_by_field_name("body") {
                    walk_python(
                        body,
                        source,
                        nodes,
                        edges,
                        &class_id,
                        module,
                        Scope::Class(name.to_string()),
                    );
                }
                return; // Don't recurse again below
            }
        }

        // Function / method definition
        "function_definition" => {
            if let Some(name_node) = node.child_by_field_name("name") {
                let name = node_text(name_node, source);

                // Skip dunder methods
                if name.starts_with("__") && name.ends_with("__") && name != "__init__" {
                    return;
                }

                let (node_type, layer, func_id) = match &scope {
                    Scope::Module => {
                        let id = format!("py:{module}.{name}");
                        ("function", "function", id)
                    }
                    Scope::Class(class_name) => {
                        let id = format!("py:{module}.{class_name}.{name}");
                        ("method", "method", id)
                    }
                };

                nodes.push(GraphNode {
                    id: func_id.clone(),
                    label: name.to_string(),
                    node_type: node_type.to_string(),
                    file_path: None,
                    line_count: None,
                    layer: Some(layer.to_string()),
                });

                // Edge: parent contains function/method
                let parent_id = match &scope {
                    Scope::Module => mod_id.to_string(),
                    Scope::Class(_) => mod_id.to_string(), // mod_id is actually class_id here
                };
                edges.push(GraphEdge {
                    from: parent_id,
                    to: func_id.clone(),
                    edge_type: "contains".to_string(),
                });

                // Extract calls from function body
                if let Some(body) = node.child_by_field_name("body") {
                    extract_calls(body, source, &func_id, module, edges);
                }
                return;
            }
        }

        // Decorated definitions (unwrap to the actual definition)
        "decorated_definition" => {
            let mut cursor = node.walk();
            for child in node.children(&mut cursor) {
                if child.kind() == "class_definition" || child.kind() == "function_definition" {
                    walk_python(child, source, nodes, edges, mod_id, module, scope.clone());
                    return;
                }
            }
        }

        // Import statements
        "import_statement" => {
            // import foo, import foo.bar
            let mut cursor = node.walk();
            for child in node.children(&mut cursor) {
                if child.kind() == "dotted_name" {
                    let imported = node_text(child, source);
                    if !imported.is_empty() {
                        edges.push(GraphEdge {
                            from: mod_id.to_string(),
                            to: format!("py:{imported}"),
                            edge_type: "imports".to_string(),
                        });
                    }
                }
            }
            return;
        }

        "import_from_statement" => {
            // from foo import bar
            if let Some(module_node) = node.child_by_field_name("module_name") {
                let imported = node_text(module_node, source);
                if !imported.is_empty() && !imported.starts_with('.') {
                    edges.push(GraphEdge {
                        from: mod_id.to_string(),
                        to: format!("py:{imported}"),
                        edge_type: "imports".to_string(),
                    });
                }
            }
            return;
        }

        _ => {}
    }

    // Recurse into children
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        walk_python(child, source, nodes, edges, mod_id, module, scope.clone());
    }
}

/// Extract function calls from a subtree.
fn extract_calls(
    node: Node,
    source: &[u8],
    caller_id: &str,
    module: &str,
    edges: &mut Vec<GraphEdge>,
) {
    if node.kind() == "call" {
        if let Some(func) = node.child_by_field_name("function") {
            match func.kind() {
                "identifier" => {
                    let name = node_text(func, source);
                    // Resolve to same-module function
                    edges.push(GraphEdge {
                        from: caller_id.to_string(),
                        to: format!("py:{module}.{name}"),
                        edge_type: "calls".to_string(),
                    });
                }
                "attribute" => {
                    // obj.method() — extract the attribute name
                    if let Some(attr) = func.child_by_field_name("attribute") {
                        let method_name = node_text(attr, source);
                        if let Some(obj) = func.child_by_field_name("object") {
                            let obj_name = node_text(obj, source);
                            edges.push(GraphEdge {
                                from: caller_id.to_string(),
                                to: format!("py:{module}.{obj_name}.{method_name}"),
                                edge_type: "calls".to_string(),
                            });
                        }
                    }
                }
                _ => {}
            }
        }
    }

    // Recurse
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        extract_calls(child, source, caller_id, module, edges);
    }
}

/// Module name from a Python file path (e.g., src/foo/bar.py → src.foo.bar).
fn py_module_name(file: &Path, root: &Path) -> String {
    let rel = file.strip_prefix(root).unwrap_or(file);
    let mut parts: Vec<&str> = rel
        .components()
        .filter_map(|c| c.as_os_str().to_str())
        .collect();

    // Remove .py extension
    if let Some(last) = parts.last_mut() {
        if let Some(stripped) = last.strip_suffix(".py") {
            *last = stripped;
        }
    }

    // Remove __init__ (represents the package itself)
    if parts.last() == Some(&"__init__") {
        parts.pop();
    }

    parts.join(".")
}
