//! Git integration — log, blame, changed files.
//! Used for time-travel slider and live code pulse.

use std::path::Path;
use std::process::Command;

use serde::Serialize;

/// A simplified git commit for the time-travel slider.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GitCommit {
    pub hash: String,
    pub short_hash: String,
    pub author: String,
    pub date: String,
    pub message: String,
    pub changed_files: Vec<String>,
}

/// Get git log for a project directory (last N commits).
/// Uses a single `git log --name-only` call (no N+1 subprocess problem).
pub fn get_git_log(project_path: &Path, max_commits: usize) -> Result<Vec<GitCommit>, String> {
    if !project_path.join(".git").exists() {
        return Err("Not a git repository".to_string());
    }

    // Single git call: metadata + changed files separated by record markers
    let output = Command::new("git")
        .current_dir(project_path)
        .args([
            "log",
            &format!("-{}", max_commits),
            "--pretty=format:---COMMIT---%H|%h|%an|%aI|%s",
            "--name-only",
        ])
        .output()
        .map_err(|e| format!("git log failed: {}", e))?;

    if !output.status.success() {
        return Err(format!(
            "git log error: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    let log_text = String::from_utf8_lossy(&output.stdout);
    let mut commits = Vec::new();

    // Split by our commit marker
    for chunk in log_text.split("---COMMIT---") {
        let chunk = chunk.trim();
        if chunk.is_empty() {
            continue;
        }

        let mut lines = chunk.lines();
        let header = match lines.next() {
            Some(h) => h,
            None => continue,
        };

        let parts: Vec<&str> = header.splitn(5, '|').collect();
        if parts.len() < 5 {
            continue;
        }

        // Remaining lines (skipping blanks) are changed file paths
        let changed_files: Vec<String> = lines
            .filter(|l| !l.is_empty())
            .map(|l| l.to_string())
            .collect();

        commits.push(GitCommit {
            hash: parts[0].to_string(),
            short_hash: parts[1].to_string(),
            author: parts[2].to_string(),
            date: parts[3].to_string(),
            message: parts[4].to_string(),
            changed_files,
        });
    }

    Ok(commits)
}

/// Get files changed since a given commit hash.
pub fn get_changed_files_since(
    project_path: &Path,
    since_hash: &str,
) -> Result<Vec<String>, String> {
    let output = Command::new("git")
        .current_dir(project_path)
        .args(["diff", "--name-only", since_hash, "HEAD"])
        .output()
        .map_err(|e| format!("git diff failed: {}", e))?;

    Ok(String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(|s| s.to_string())
        .collect())
}

/// Get recently modified files (for live pulse detection).
pub fn get_recently_modified(project_path: &Path, seconds: u64) -> Result<Vec<String>, String> {
    let output = Command::new("git")
        .current_dir(project_path)
        .args([
            "diff",
            "--name-only",
            &format!("HEAD@{{{}.seconds.ago}}", seconds),
        ])
        .output()
        .map_err(|e| format!("git diff failed: {}", e))?;

    if !output.status.success() {
        // Fallback: list uncommitted changes
        let output2 = Command::new("git")
            .current_dir(project_path)
            .args(["diff", "--name-only"])
            .output()
            .map_err(|e| format!("git diff failed: {}", e))?;

        return Ok(String::from_utf8_lossy(&output2.stdout)
            .lines()
            .map(|s| s.to_string())
            .collect());
    }

    Ok(String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(|s| s.to_string())
        .collect())
}
