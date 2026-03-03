//! Ontology Map TUI — Terminal-based code architecture visualization.
//!
//! Features:
//! - Force-directed graph layout rendered with Braille characters (2x4 sub-pixel)
//! - Interactive navigation: arrow keys pan, +/- zoom, Tab cycle nodes, Enter select
//! - Color-coded nodes by layer (ANSI 256-color)
//! - Stats panel with node/edge counts, layer breakdown
//! - Detail panel for selected node
//! - Tree-sitter AST parsing for Python, JS/TS, Go, Rust, Java, C#, Docker Compose
//! - Git time-travel: commit timeline, churn heatmap, blame overlay
//! - Live reload: file watcher with pulse animation on save

mod adapters;
mod cli;
mod git;
mod graph;
mod layout;
mod search;
mod ui;
mod watcher;

use std::io;
use std::path::PathBuf;
use std::time::{Duration, Instant};

use anyhow::Result;
use clap::Parser;
use crossterm::event::{self, Event, KeyCode, KeyModifiers};
use crossterm::execute;
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;

use crate::cli::Cli;
use crate::graph::AppGraph;
use crate::ui::App;

fn main() -> Result<()> {
    env_logger::init();
    let cli = Cli::parse();

    let path = cli.path.canonicalize().unwrap_or(cli.path.clone());

    // Run adapters
    eprintln!(
        "🔍 Analyzing {}...",
        path.file_name().map_or_else(|| path.display().to_string(), |n| n.to_string_lossy().to_string())
    );

    let graph = adapters::analyze_project(&path, cli.max_files)?;

    if graph.adapters_used.is_empty() {
        eprintln!(
            "✅ Found {} nodes, {} edges",
            graph.nodes.len(),
            graph.edges.len(),
        );
    } else {
        eprintln!(
            "✅ Found {} nodes, {} edges ({} adapters)",
            graph.nodes.len(),
            graph.edges.len(),
            graph.adapters_used.join(", ")
        );
    }

    // Git analysis
    let git_info = if cli.no_git {
        None
    } else {
        eprintln!("🔀 Analyzing git history...");
        let info = git::analyze_git(&path, cli.max_commits);
        if let Some(ref gi) = info {
            eprintln!(
                "   {} commits, {} files tracked",
                gi.commits.len(),
                gi.file_churns.len()
            );
        } else {
            eprintln!("   (not a git repository)");
        }
        info
    };

    // JSON mode
    if cli.json {
        let json = serde_json::to_string_pretty(&graph)?;
        println!("{json}");
        return Ok(());
    }

    // Stats mode
    if cli.stats {
        print_stats(&graph, &git_info);
        return Ok(());
    }

    // No nodes? Exit gracefully
    if graph.nodes.is_empty() {
        eprintln!(
            "⚠️  No source files found. Supported: Python, JS/TS, Go, Rust, Java, C#, Docker Compose"
        );
        return Ok(());
    }

    // File watcher
    let file_watcher = if cli.no_watch {
        None
    } else {
        match watcher::FileWatcher::new(&path) {
            Ok(w) => Some(w),
            Err(e) => {
                log::warn!("File watcher failed to start: {e}");
                None
            }
        }
    };

    // Run TUI
    run_tui(graph, git_info, file_watcher, path)
}

fn print_stats(graph: &AppGraph, git_info: &Option<git::GitInfo>) {
    println!("┌─────────────────────────────────────┐");
    println!("│       Ontology Map — Statistics      │");
    println!("├─────────────────────────────────────┤");
    println!("│ Nodes:    {:>6}                     │", graph.nodes.len());
    println!("│ Edges:    {:>6}                     │", graph.edges.len());
    println!(
        "│ Adapters: {:>6}                     │",
        graph.adapters_used.len()
    );

    if let Some(ref gi) = git_info {
        println!("│ Commits:  {:>6}                     │", gi.commits.len());
        println!(
            "│ Tracked:  {:>6} files               │",
            gi.file_churns.len()
        );

        // Top 5 most churned files
        let mut churns: Vec<_> = gi.file_churns.iter().collect();
        churns.sort_by(|a, b| b.1.commits.cmp(&a.1.commits));
        if !churns.is_empty() {
            println!("├─────────────────────────────────────┤");
            println!("│ Hottest files (most commits):       │");
            for (path, churn) in churns.iter().take(5) {
                let display = if path.len() > 28 {
                    format!("...{}", &path[path.len() - 25..])
                } else {
                    (*path).to_string()
                };
                println!("│   {:>3}x  {:<28} │", churn.commits, display);
            }
        }
    }

    println!("├─────────────────────────────────────┤");

    // Count by type
    let mut type_counts: std::collections::HashMap<&str, usize> =
        std::collections::HashMap::new();
    for node in &graph.nodes {
        *type_counts.entry(&node.node_type).or_insert(0) += 1;
    }
    let mut types: Vec<_> = type_counts.into_iter().collect();
    types.sort_by(|a, b| b.1.cmp(&a.1));
    for (t, count) in &types {
        println!("│ {t:.<20} {count:>6}        │");
    }
    println!("└─────────────────────────────────────┘");
}

fn run_tui(
    graph: AppGraph,
    git_info: Option<git::GitInfo>,
    mut file_watcher: Option<watcher::FileWatcher>,
    project_path: PathBuf,
) -> Result<()> {
    // Terminal setup
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // App state
    let mut app = App::new(graph, git_info, project_path);

    // Main loop
    let tick_rate = Duration::from_millis(50); // 20fps
    let mut last_tick = Instant::now();

    loop {
        terminal.draw(|frame| ui::draw(frame, &mut app))?;

        let timeout = tick_rate.saturating_sub(last_tick.elapsed());
        if event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                // Time-travel mode captures left/right arrows
                if app.time_travel_active {
                    match key.code {
                        KeyCode::Left | KeyCode::Char('h') => {
                            app.time_travel_prev();
                            continue;
                        }
                        KeyCode::Right | KeyCode::Char('l') => {
                            app.time_travel_next();
                            continue;
                        }
                        KeyCode::Char('t') | KeyCode::Esc => {
                            app.toggle_time_travel();
                            continue;
                        }
                        KeyCode::Char('q') => break,
                        KeyCode::Char('c') if key.modifiers == KeyModifiers::CONTROL => break,
                        _ => {}
                    }
                }

                // Search mode captures all character input first
                if app.search_active {
                    match key.code {
                        KeyCode::Esc => app.deselect(),
                        KeyCode::Enter => {
                            app.search_active = false;
                        }
                        KeyCode::Backspace => app.search_backspace(),
                        KeyCode::Tab => app.select_next(),
                        KeyCode::BackTab => app.select_prev(),
                        KeyCode::Char('c') if key.modifiers == KeyModifiers::CONTROL => break,
                        KeyCode::Char(c) => app.search_input(c),
                        _ => {}
                    }
                } else {
                    match (key.code, key.modifiers) {
                        // Quit
                        (KeyCode::Char('q'), _)
                        | (KeyCode::Char('c'), KeyModifiers::CONTROL) => {
                            break;
                        }

                        // Pan
                        (KeyCode::Left | KeyCode::Char('h'), _) => app.pan(-5.0, 0.0),
                        (KeyCode::Right | KeyCode::Char('l'), _) => app.pan(5.0, 0.0),
                        (KeyCode::Up | KeyCode::Char('k'), _) => app.pan(0.0, -5.0),
                        (KeyCode::Down | KeyCode::Char('j'), _) => app.pan(0.0, 5.0),

                        // Zoom
                        (KeyCode::Char('+') | KeyCode::Char('='), _) => app.zoom(1.1),
                        (KeyCode::Char('-'), _) => app.zoom(0.9),
                        (KeyCode::Char('0'), _) => app.reset_view(),

                        // Node navigation
                        (KeyCode::Tab, _) => app.select_next(),
                        (KeyCode::BackTab, _) => app.select_prev(),
                        (KeyCode::Enter, _) => app.toggle_detail(),
                        (KeyCode::Esc, _) => app.deselect(),

                        // Toggles
                        (KeyCode::Char('e'), _) => app.toggle_edges(),
                        (KeyCode::Char('n'), _) => app.toggle_labels(),
                        (KeyCode::Char('s'), _) => app.cycle_sort(),
                        (KeyCode::Char('/'), _) => app.toggle_search(),

                        // Git features
                        (KeyCode::Char('t'), _) => app.toggle_time_travel(),
                        (KeyCode::Char('b'), _) => app.toggle_blame(),
                        (KeyCode::Char('c'), _) => app.toggle_churn(),

                        _ => {}
                    }
                }
            }
        }

        if last_tick.elapsed() >= tick_rate {
            // Poll file watcher for changes
            if let Some(ref mut fw) = file_watcher {
                let events = fw.poll();
                for event in events {
                    app.on_file_changed(&event.rel_path);
                }
            }

            app.tick();
            last_tick = Instant::now();
        }
    }

    // Teardown
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    Ok(())
}
