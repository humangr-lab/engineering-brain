//! Git integration — commit history, blame, and churn metrics.
//!
//! Provides time-travel data (commit timeline), per-file churn metrics,
//! and blame summaries for the architecture visualization.

use std::collections::HashMap;
use std::path::Path;

use git2::{BlameOptions, Repository, Sort};

/// A single git commit with metadata.
#[derive(Debug, Clone)]
pub struct GitCommit {
    #[allow(dead_code)]
    pub hash: String,
    pub short_hash: String,
    pub message: String,
    pub author: String,
    pub timestamp: i64,
    pub files_changed: Vec<String>,
}

/// Churn metrics for a single file.
#[derive(Debug, Clone)]
pub struct ChurnMetrics {
    pub commits: usize,
    pub last_modified: i64,
}

/// Blame summary — author line counts for a file.
#[derive(Debug, Clone)]
pub struct BlameSummary {
    pub authors: Vec<(String, usize)>,
    pub total_lines: usize,
}

/// All git information for a project.
pub struct GitInfo {
    pub commits: Vec<GitCommit>,
    pub file_churns: HashMap<String, ChurnMetrics>,
}

/// Analyze git history for a project path.
///
/// Returns None if path is not inside a git repository.
pub fn analyze_git(path: &Path, max_commits: usize) -> Option<GitInfo> {
    let repo = Repository::discover(path).ok()?;
    let repo_root = repo.workdir()?.to_path_buf();

    // Compute prefix: if project path is a subdirectory of repo root,
    // git paths need this prefix stripped to match adapter-relative paths.
    let path_prefix = path
        .strip_prefix(&repo_root)
        .ok()
        .map(|p| {
            let s = p.to_string_lossy().to_string();
            if s.is_empty() {
                s
            } else if s.ends_with('/') {
                s
            } else {
                format!("{s}/")
            }
        })
        .unwrap_or_default();

    let commits = get_commit_history(&repo, max_commits, &path_prefix);
    let file_churns = compute_file_churns(&commits);

    Some(GitInfo {
        commits,
        file_churns,
    })
}

/// Walk commit history from HEAD, collecting commit metadata.
fn get_commit_history(
    repo: &Repository,
    max_commits: usize,
    path_prefix: &str,
) -> Vec<GitCommit> {
    let mut revwalk = match repo.revwalk() {
        Ok(r) => r,
        Err(_) => return Vec::new(),
    };

    if revwalk.push_head().is_err() {
        return Vec::new();
    }
    let _ = revwalk.set_sorting(Sort::TIME);
    let _ = revwalk.simplify_first_parent();

    let mut commits = Vec::new();

    for oid_result in revwalk.take(max_commits) {
        let oid = match oid_result {
            Ok(o) => o,
            Err(_) => continue,
        };

        let commit = match repo.find_commit(oid) {
            Ok(c) => c,
            Err(_) => continue,
        };

        let author_sig = commit.author();
        let message = commit
            .message()
            .unwrap_or("")
            .lines()
            .next()
            .unwrap_or("")
            .to_string();

        let author = author_sig.name().unwrap_or("unknown").to_string();
        let timestamp = author_sig.when().seconds();

        // Get changed files, filtered and made relative to project path
        let files_changed = get_changed_files(repo, &commit, path_prefix);

        commits.push(GitCommit {
            hash: oid.to_string(),
            short_hash: oid.to_string()[..7].to_string(),
            message,
            author,
            timestamp,
            files_changed,
        });
    }

    commits
}

/// Get files changed in a commit (diff against parent), relative to project path.
fn get_changed_files(
    repo: &Repository,
    commit: &git2::Commit,
    path_prefix: &str,
) -> Vec<String> {
    let tree = match commit.tree() {
        Ok(t) => t,
        Err(_) => return Vec::new(),
    };

    let parent_tree = commit.parent(0).ok().and_then(|p| p.tree().ok());

    let diff = match repo.diff_tree_to_tree(parent_tree.as_ref(), Some(&tree), None) {
        Ok(d) => d,
        Err(_) => return Vec::new(),
    };

    diff.deltas()
        .filter_map(|delta| {
            let path = delta.new_file().path()?;
            let path_str = path.to_string_lossy();

            if path_prefix.is_empty() {
                Some(path_str.to_string())
            } else { path_str.strip_prefix(path_prefix).map(String::from) }
        })
        .collect()
}

/// Compute per-file churn metrics from commit history.
fn compute_file_churns(commits: &[GitCommit]) -> HashMap<String, ChurnMetrics> {
    let mut churns: HashMap<String, ChurnMetrics> = HashMap::new();

    for commit in commits {
        for file in &commit.files_changed {
            let entry = churns.entry(file.clone()).or_insert(ChurnMetrics {
                commits: 0,
                last_modified: 0,
            });
            entry.commits += 1;
            if commit.timestamp > entry.last_modified {
                entry.last_modified = commit.timestamp;
            }
        }
    }

    churns
}

/// Get blame summary for a specific file (lazy-loaded on demand).
pub fn get_blame(project_path: &Path, file_rel: &str) -> Option<BlameSummary> {
    let repo = Repository::discover(project_path).ok()?;
    let repo_root = repo.workdir()?;

    // Reconstruct the full relative path from repo root
    let prefix = project_path.strip_prefix(repo_root).unwrap_or(Path::new(""));
    let blame_path = prefix.join(file_rel);

    let mut opts = BlameOptions::new();
    let blame = repo.blame_file(&blame_path, Some(&mut opts)).ok()?;

    let mut author_lines: HashMap<String, usize> = HashMap::new();
    let mut total_lines = 0;

    for i in 0..blame.len() {
        if let Some(hunk) = blame.get_index(i) {
            let author = hunk
                .final_signature()
                .name()
                .unwrap_or("unknown")
                .to_string();
            let lines = hunk.lines_in_hunk();
            *author_lines.entry(author).or_insert(0) += lines;
            total_lines += lines;
        }
    }

    let mut authors: Vec<_> = author_lines.into_iter().collect();
    authors.sort_by(|a, b| b.1.cmp(&a.1));

    Some(BlameSummary {
        authors,
        total_lines,
    })
}

/// Format a unix timestamp as relative time (e.g., "3d ago", "2mo ago").
pub fn relative_time(timestamp: i64) -> String {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;

    let diff = now - timestamp;
    if diff < 0 {
        return "future".to_string();
    }

    if diff < 60 {
        "just now".to_string()
    } else if diff < 3600 {
        format!("{}m ago", diff / 60)
    } else if diff < 86400 {
        format!("{}h ago", diff / 3600)
    } else if diff < 2_592_000 {
        format!("{}d ago", diff / 86400)
    } else if diff < 31_536_000 {
        format!("{}mo ago", diff / 2_592_000)
    } else {
        format!("{}y ago", diff / 31_536_000)
    }
}
