//! Semantic search — fuzzy matching with ranked results.
//!
//! Scoring: exact match > prefix > word boundary > contains > subsequence > fuzzy.
//! Bonus points for: high-churn files, node importance (PageRank-ish), node type.

use std::collections::HashMap;

use crate::graph::AppGraph;

/// A scored search result.
#[derive(Debug, Clone)]
pub struct SearchResult {
    pub node_index: usize,
    pub score: f64,
    pub match_kind: MatchKind,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum MatchKind {
    Exact,
    Prefix,
    WordBoundary,
    Contains,
    Subsequence,
    FileMatch,
    TypeMatch,
}

impl MatchKind {
    pub fn label(self) -> &'static str {
        match self {
            MatchKind::Exact => "exact",
            MatchKind::Prefix => "prefix",
            MatchKind::WordBoundary => "word",
            MatchKind::Contains => "contains",
            MatchKind::Subsequence => "fuzzy",
            MatchKind::FileMatch => "file",
            MatchKind::TypeMatch => "type",
        }
    }
}

/// Node importance based on connection count (simplified PageRank).
pub fn compute_importance(graph: &AppGraph) -> HashMap<usize, f64> {
    let id_to_idx: HashMap<&str, usize> = graph
        .nodes
        .iter()
        .enumerate()
        .map(|(i, n)| (n.id.as_str(), i))
        .collect();

    let mut incoming = vec![0usize; graph.nodes.len()];
    let mut outgoing = vec![0usize; graph.nodes.len()];

    for edge in &graph.edges {
        if let Some(&from) = id_to_idx.get(edge.from.as_str()) {
            outgoing[from] += 1;
        }
        if let Some(&to) = id_to_idx.get(edge.to.as_str()) {
            incoming[to] += 1;
        }
    }

    let max_conn = incoming
        .iter()
        .zip(outgoing.iter())
        .map(|(i, o)| i + o)
        .max()
        .unwrap_or(1)
        .max(1) as f64;

    let mut importance = HashMap::new();
    for i in 0..graph.nodes.len() {
        let connections = (incoming[i] + outgoing[i]) as f64;
        importance.insert(i, connections / max_conn);
    }

    importance
}

/// Type priority for search result ranking.
fn type_priority(node_type: &str) -> f64 {
    match node_type {
        "module" | "namespace" => 1.0,
        "class" | "component" => 0.9,
        "service" => 0.85,
        "struct" | "interface" | "trait" => 0.8,
        "function" | "hook" => 0.6,
        "method" => 0.5,
        "export" | "enum" | "type" => 0.4,
        _ => 0.3,
    }
}

/// Run a ranked search across all nodes.
pub fn ranked_search(
    query: &str,
    graph: &AppGraph,
    importance: &HashMap<usize, f64>,
    churn: &HashMap<usize, f64>,
) -> Vec<SearchResult> {
    if query.is_empty() {
        return Vec::new();
    }

    let q = query.to_lowercase();
    let q_chars: Vec<char> = q.chars().collect();
    let mut results = Vec::new();

    for (i, node) in graph.nodes.iter().enumerate() {
        let label_lower = node.label.to_lowercase();
        let id_lower = node.id.to_lowercase();
        let type_lower = node.node_type.to_lowercase();
        let file_lower = node
            .file_path
            .as_deref()
            .unwrap_or("")
            .to_lowercase();

        // Try each match type in priority order
        let (base_score, match_kind) = if label_lower == q {
            (100.0, MatchKind::Exact)
        } else if label_lower.starts_with(&q) {
            (80.0, MatchKind::Prefix)
        } else if word_boundary_match(&label_lower, &q) {
            (70.0, MatchKind::WordBoundary)
        } else if label_lower.contains(&q) || id_lower.contains(&q) {
            (50.0, MatchKind::Contains)
        } else if file_lower.contains(&q) {
            (30.0, MatchKind::FileMatch)
        } else if type_lower == q {
            (25.0, MatchKind::TypeMatch)
        } else if is_subsequence(&q_chars, &label_lower) {
            let score = subsequence_score(&q_chars, &label_lower);
            (score, MatchKind::Subsequence)
        } else {
            continue;
        };

        // Apply bonuses
        let type_bonus = type_priority(&node.node_type) * 10.0;
        let importance_bonus = importance.get(&i).copied().unwrap_or(0.0) * 15.0;
        let churn_bonus = churn.get(&i).copied().unwrap_or(0.0) * 5.0;

        let score = base_score + type_bonus + importance_bonus + churn_bonus;

        results.push(SearchResult {
            node_index: i,
            score,
            match_kind,
        });
    }

    results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
    results.truncate(50); // Cap at 50 results
    results
}

/// Check if query appears at a word boundary in the target.
/// Word boundaries: start of string, after '.', '_', '-', case change (camelCase).
fn word_boundary_match(target: &str, query: &str) -> bool {
    let chars: Vec<char> = target.chars().collect();
    for (i, _) in target.match_indices(query) {
        if i == 0 {
            return true;
        }
        let prev = chars.get(i.saturating_sub(1).min(chars.len() - 1));
        if prev.is_some_and(|c| matches!(c, '.' | '_' | '-' | '/' | ':')) {
            return true;
        }
    }
    false
}

/// Check if chars is a subsequence of target.
fn is_subsequence(chars: &[char], target: &str) -> bool {
    let mut ci = 0;
    for tc in target.chars() {
        if ci < chars.len() && tc == chars[ci] {
            ci += 1;
        }
    }
    ci == chars.len()
}

/// Score a subsequence match (0-20) based on how tightly the chars cluster.
fn subsequence_score(chars: &[char], target: &str) -> f64 {
    let target_chars: Vec<char> = target.chars().collect();
    let mut positions = Vec::new();
    let mut ci = 0;

    for (ti, &tc) in target_chars.iter().enumerate() {
        if ci < chars.len() && tc == chars[ci] {
            positions.push(ti);
            ci += 1;
        }
    }

    if positions.len() < chars.len() {
        return 0.0;
    }

    // Score based on: gaps between matched positions (smaller gaps = better)
    let total_gap: usize = positions
        .windows(2)
        .map(|w| w[1] - w[0] - 1)
        .sum();

    let max_gap = target_chars.len().saturating_sub(chars.len());
    if max_gap == 0 {
        return 20.0;
    }

    let tightness = 1.0 - (total_gap as f64 / max_gap as f64);
    tightness * 20.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_subsequence() {
        assert!(is_subsequence(&['u', 's', 'r'], "user_service"));
        assert!(is_subsequence(&['a', 'b', 'c'], "axbxc"));
        assert!(!is_subsequence(&['z', 'y'], "abc"));
    }

    #[test]
    fn test_word_boundary() {
        assert!(word_boundary_match("user_service", "service"));
        assert!(word_boundary_match("py:models.User", "User"));
        assert!(!word_boundary_match("fooservice", "service"));
    }

    #[test]
    fn test_subsequence_score() {
        // Tight match: consecutive letters
        let s1 = subsequence_score(&['a', 'b', 'c'], "abcdef");
        // Loose match: spread out
        let s2 = subsequence_score(&['a', 'b', 'c'], "axbxxc");
        assert!(s1 > s2, "consecutive match should score higher");
    }
}
