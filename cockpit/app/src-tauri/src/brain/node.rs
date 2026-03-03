use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Layer derivation from node ID prefix — port of Python _PREFIX_TO_LAYER.
static PREFIX_TO_LAYER: &[(&str, i32, &str, &str)] = &[
    ("AX-", 0, "Axiom", "L0 — Axioms"),
    ("P-", 1, "Principle", "L1 — Principles"),
    ("PAT-", 2, "Pattern", "L2 — Patterns"),
    ("R-", 3, "Rule", "L3 — Rules"),
    ("CR-", 3, "Rule", "L3 — Rules"),
    ("F-", 4, "Finding", "L4 — Evidence"),
    ("CE-", 4, "CodeExample", "L4 — Evidence"),
    ("TR-", 4, "TestResult", "L4 — Evidence"),
    ("TC-", 5, "Task", "L5 — Context"),
];

static TAXONOMY_PREFIXES: &[&str] = &[
    "tech:", "domain:", "filetype:", "human_layer:", "sprint:",
];

/// Derive (layer_num, type_name, layer_label) from node ID prefix.
pub fn layer_info(node_id: &str) -> (i32, String, String) {
    for &(prefix, layer, ntype, label) in PREFIX_TO_LAYER {
        if node_id.starts_with(prefix) {
            return (layer, ntype.to_string(), label.to_string());
        }
    }
    for &tp in TAXONOMY_PREFIXES {
        if node_id.starts_with(tp) {
            let kind = tp.trim_end_matches(':');
            let mut title = kind.to_string();
            if let Some(c) = title.get_mut(..1) {
                c.make_ascii_uppercase();
            }
            return (-1, title, "Taxonomy".to_string());
        }
    }
    (3, "Rule".to_string(), "L3 — Rules".to_string())
}

/// A node in the knowledge/code graph.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Node {
    pub id: String,
    #[serde(rename = "type")]
    pub node_type: String,
    pub layer: i32,
    pub layer_name: String,
    pub text: String,
    #[serde(default)]
    pub severity: String,
    #[serde(default)]
    pub confidence: f64,
    #[serde(default)]
    pub technologies: Vec<String>,
    #[serde(default)]
    pub domains: Vec<String>,
    #[serde(default)]
    pub out_edges: Vec<EdgeRef>,
    #[serde(default)]
    pub in_edges: Vec<EdgeRef>,
    // Optional fields
    #[serde(skip_serializing_if = "Option::is_none")]
    pub why: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub how_to: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub when_to_use: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub opinion: Option<Opinion>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub epistemic_status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub freshness: Option<f64>,
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EdgeRef {
    #[serde(alias = "from", alias = "to")]
    pub node_id: String,
    #[serde(rename = "type")]
    pub edge_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Opinion {
    pub b: f64,
    pub d: f64,
    pub u: f64,
    pub a: f64,
}

/// An edge connecting two nodes.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Edge {
    pub from: String,
    pub to: String,
    #[serde(rename = "type")]
    pub edge_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub weight: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub edge_alpha: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub edge_beta: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub edge_confidence: Option<f64>,
}
