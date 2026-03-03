//! Integration tests for language adapters.

use std::fs;
use std::path::Path;

/// Helper: run ontology-map --json on a temp directory and parse the JSON.
fn analyze_dir(dir: &Path) -> serde_json::Value {
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_ontology-map"))
        .args(["--json", "--no-git", "--no-watch"])
        .arg(dir)
        .output()
        .expect("failed to run binary");

    assert!(
        output.status.success(),
        "binary failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    serde_json::from_slice(&output.stdout).expect("invalid JSON output")
}

/// Helper: create a temp dir with files and analyze.
fn analyze_source(ext: &str, source: &str) -> serde_json::Value {
    let dir = tempfile::tempdir().unwrap();
    let file_path = dir.path().join(format!("test.{ext}"));
    fs::write(&file_path, source).unwrap();
    analyze_dir(dir.path())
}

fn nodes_of_type(data: &serde_json::Value, node_type: &str) -> Vec<serde_json::Value> {
    data["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|n| n["node_type"].as_str() == Some(node_type))
        .cloned()
        .collect()
}

fn has_node(data: &serde_json::Value, label: &str, node_type: &str) -> bool {
    data["nodes"].as_array().unwrap().iter().any(|n| {
        n["label"].as_str().map_or(false, |l| l.contains(label))
            && n["node_type"].as_str() == Some(node_type)
    })
}

fn edge_count(data: &serde_json::Value, edge_type: &str) -> usize {
    data["edges"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|e| e["edge_type"].as_str() == Some(edge_type))
        .count()
}

// ─── Python ────────────────────────────────────────────────────────

#[test]
fn python_class_and_methods() {
    let data = analyze_source(
        "py",
        r#"
class User:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello {self.name}"

def create_user(name):
    return User(name)
"#,
    );

    assert!(has_node(&data, "User", "class"));
    assert!(has_node(&data, "__init__", "method"));
    assert!(has_node(&data, "greet", "method"));
    assert!(has_node(&data, "create_user", "function"));
}

#[test]
fn python_calls_extracted() {
    let data = analyze_source(
        "py",
        r#"
def helper():
    pass

def main():
    helper()
"#,
    );

    assert!(has_node(&data, "helper", "function"));
    assert!(has_node(&data, "main", "function"));
    assert!(edge_count(&data, "calls") >= 1, "should have call edges");
}

#[test]
fn python_decorated_function() {
    let data = analyze_source(
        "py",
        r#"
def decorator(f):
    return f

@decorator
def decorated_func():
    pass

class Service:
    @staticmethod
    def static_method():
        pass
"#,
    );

    assert!(has_node(&data, "decorated_func", "function"));
    assert!(has_node(&data, "static_method", "method"));
}

#[test]
fn python_empty_file() {
    let data = analyze_source("py", "");
    let modules = nodes_of_type(&data, "module");
    assert_eq!(modules.len(), 1, "empty file should still create module node");
}

#[test]
fn python_syntax_error_graceful() {
    let data = analyze_source("py", "def broken(\n  class invalid syntax {{{}}}");
    // Should not crash — tree-sitter handles errors gracefully
    let modules = nodes_of_type(&data, "module");
    assert_eq!(modules.len(), 1);
}

// ─── JavaScript ────────────────────────────────────────────────────

#[test]
fn js_component_detection() {
    let data = analyze_source(
        "js",
        r#"
export function App() {
    return <div>Hello</div>;
}

export const HomePage = () => {
    return <h1>Home</h1>;
}
"#,
    );

    assert!(has_node(&data, "App", "component"), "App should be component");
    assert!(
        has_node(&data, "HomePage", "component"),
        "HomePage should be component"
    );
}

#[test]
fn js_hooks_and_classes() {
    let data = analyze_source(
        "js",
        r#"
function useAuth() {
    return { user: null };
}

class UserService {
    constructor() {}
}

export const [user, setUser] = useState(null);
"#,
    );

    assert!(has_node(&data, "useAuth", "hook"));
    assert!(has_node(&data, "UserService", "class"));
}

#[test]
fn js_import_edges() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("utils.js"), "export function helper() {}").unwrap();
    fs::write(
        dir.path().join("main.js"),
        "import { helper } from './utils';\nhelper();",
    )
    .unwrap();

    let data = analyze_dir(dir.path());
    assert!(
        edge_count(&data, "imports") >= 1,
        "should have import edge for relative import"
    );
}

// ─── TypeScript ────────────────────────────────────────────────────

#[test]
fn ts_interfaces_and_types() {
    let data = analyze_source(
        "ts",
        r#"
interface User {
    id: string;
    name: string;
}

type Config = {
    host: string;
    port: number;
};

enum Role {
    Admin,
    User,
}
"#,
    );

    assert!(has_node(&data, "User", "interface"));
    assert!(has_node(&data, "Config", "type"));
    assert!(has_node(&data, "Role", "enum"));
}

#[test]
fn tsx_component_detection() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("App.tsx"),
        r#"
export function App() {
    return <div>Hello</div>;
}

export const Header = () => <header>Nav</header>;
"#,
    )
    .unwrap();

    let data = analyze_dir(dir.path());
    assert!(has_node(&data, "App", "component"));
    assert!(has_node(&data, "Header", "component"));
}

// ─── Go ────────────────────────────────────────────────────────────

#[test]
fn go_structs_and_interfaces() {
    let data = analyze_source(
        "go",
        r#"
package main

type Server struct {
    Port int
    Host string
}

type Handler interface {
    Handle()
}

func NewServer(port int) *Server {
    return &Server{Port: port}
}

func (s *Server) Start() error {
    return nil
}
"#,
    );

    assert!(has_node(&data, "Server", "struct"));
    assert!(has_node(&data, "Handler", "interface"));
    assert!(has_node(&data, "NewServer", "function"));
    assert!(has_node(&data, "Start", "method"));
}

// ─── Rust ──────────────────────────────────────────────────────────

#[test]
fn rust_traits_and_enums() {
    let data = analyze_source(
        "rs",
        r#"
pub trait Repository {
    fn find(&self, id: &str) -> Option<String>;
}

pub struct InMemory {
    items: Vec<String>,
}

pub enum Status {
    Active,
    Inactive,
}

pub fn create() -> InMemory {
    InMemory { items: vec![] }
}
"#,
    );

    assert!(has_node(&data, "Repository", "trait"));
    assert!(has_node(&data, "InMemory", "struct"));
    assert!(has_node(&data, "Status", "enum"));
    assert!(has_node(&data, "create", "function"));
}

// ─── Java ──────────────────────────────────────────────────────────

#[test]
fn java_classes_and_interfaces() {
    let data = analyze_source(
        "java",
        r#"
package com.example;

public class UserService {
    public String find(String id) {
        return id;
    }

    private void validate() {}
}

interface Repository {
    String find(String id);
}
"#,
    );

    assert!(has_node(&data, "UserService", "class"));
    assert!(has_node(&data, "Repository", "interface"));
    assert!(has_node(&data, "find", "method"));
    assert!(has_node(&data, "validate", "method"));
}

// ─── C# ────────────────────────────────────────────────────────────

#[test]
fn csharp_namespaces_and_structs() {
    let data = analyze_source(
        "cs",
        r#"
namespace MyApp.Controllers
{
    public class UserController
    {
        public void GetUser(string id) {}
    }

    public interface IService
    {
        void Execute();
    }

    public struct Config
    {
        public string Name;
    }
}
"#,
    );

    assert!(has_node(&data, "MyApp.Controllers", "namespace"));
    assert!(has_node(&data, "UserController", "class"));
    assert!(has_node(&data, "IService", "interface"));
    assert!(has_node(&data, "Config", "struct"));
    assert!(has_node(&data, "GetUser", "method"));
}

// ─── Docker Compose ────────────────────────────────────────────────

#[test]
fn docker_compose_services() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("docker-compose.yml"),
        r#"
version: "3.8"
services:
  web:
    build: .
    ports:
      - "8080:8080"
    depends_on:
      - db
  db:
    image: postgres:15
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - backend

volumes:
  pgdata:

networks:
  backend:
    driver: bridge
"#,
    )
    .unwrap();

    let data = analyze_dir(dir.path());
    assert!(has_node(&data, "web", "service"));
    assert!(has_node(&data, "db", "service"));
    assert!(edge_count(&data, "depends_on") >= 1);
}

// ─── Multi-language integration ────────────────────────────────────

#[test]
fn multi_language_project() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("main.py"), "class App: pass").unwrap();
    fs::write(dir.path().join("index.js"), "export function render() {}").unwrap();
    fs::write(dir.path().join("server.go"), "package main\ntype Server struct {}").unwrap();
    fs::write(dir.path().join("lib.rs"), "pub struct Engine {}").unwrap();

    let data = analyze_dir(dir.path());
    let adapters = data["adapters_used"]
        .as_array()
        .unwrap()
        .iter()
        .map(|a| a.as_str().unwrap().to_string())
        .collect::<Vec<_>>();

    assert!(adapters.iter().any(|a| a.contains("python")));
    assert!(adapters.iter().any(|a| a.contains("javascript")));
    assert!(adapters.iter().any(|a| a.contains("go")));
    assert!(adapters.iter().any(|a| a.contains("rust")));
}

#[test]
fn empty_directory() {
    let dir = tempfile::tempdir().unwrap();
    let data = analyze_dir(dir.path());
    assert_eq!(data["nodes"].as_array().unwrap().len(), 0);
    assert_eq!(data["edges"].as_array().unwrap().len(), 0);
}

#[test]
fn json_output_schema() {
    let data = analyze_source("py", "def hello(): pass");

    // Verify top-level schema
    assert!(data["nodes"].is_array());
    assert!(data["edges"].is_array());
    assert!(data["adapters_used"].is_array());

    // Verify node schema
    let node = &data["nodes"].as_array().unwrap()[0];
    assert!(node["id"].is_string());
    assert!(node["label"].is_string());
    assert!(node["node_type"].is_string());

    // Verify edge schema
    if let Some(edge) = data["edges"].as_array().unwrap().first() {
        assert!(edge["from"].is_string());
        assert!(edge["to"].is_string());
        assert!(edge["edge_type"].is_string());
    }
}

// ─── Unicode and special characters ────────────────────────────────

#[test]
fn unicode_identifiers() {
    let data = analyze_source(
        "py",
        r#"
class Configuração:
    def calcular_preço(self):
        pass
"#,
    );

    assert!(has_node(&data, "Configuração", "class"));
    assert!(has_node(&data, "calcular_preço", "method"));
}
