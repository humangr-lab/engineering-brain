//! TUI rendering — Ratatui widgets, App state, and draw loop.
//!
//! Layout:
//! ┌──────────────────────────────────┬──────────────────┐
//! │                                  │    Statistics     │
//! │        Graph Canvas              │    (by type)      │
//! │     (Braille characters)         │                   │
//! │                                  ├──────────────────┤
//! │                                  │  Node Detail      │
//! │                                  │  (selected node)  │
//! ├──────────────────────────────────┴──────────────────┤
//! │  [keybinds]  [search]                  nodes/edges   │
//! └─────────────────────────────────────────────────────┘

use std::collections::HashMap;
use std::path::PathBuf;
use std::time::Instant;

use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::symbols::Marker;
use ratatui::text::{Line, Span};
use ratatui::widgets::canvas::{Canvas, Context, Points};
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};
use ratatui::Frame;

use crate::git::{self, BlameSummary, GitInfo};
use crate::graph::AppGraph;
use crate::layout::LayoutEngine;
use crate::search::{self, SearchResult};

/// Color palette for node types (ANSI 256 approximations of OKLCH tokens).
fn type_color(node_type: &str) -> Color {
    match node_type {
        "module" | "namespace" => Color::Rgb(100, 180, 255),  // Blue
        "class" => Color::Rgb(180, 130, 255),                  // Purple
        "function" => Color::Rgb(120, 220, 140),               // Green
        "method" => Color::Rgb(90, 200, 120),                  // Green (darker)
        "export" => Color::Rgb(100, 200, 200),                 // Cyan
        "component" => Color::Rgb(255, 180, 100),              // Orange
        "hook" => Color::Rgb(255, 140, 200),                   // Pink
        "struct" => Color::Rgb(220, 160, 255),                 // Light purple
        "enum" => Color::Rgb(200, 140, 220),                   // Magenta
        "trait" | "interface" => Color::Rgb(140, 200, 255),    // Light blue
        "type" => Color::Rgb(160, 180, 220),                   // Steel blue
        "constructor" => Color::Rgb(150, 230, 150),            // Light green
        "service" => Color::Rgb(255, 140, 100),                // Red-orange
        "network" => Color::Rgb(200, 200, 100),                // Yellow
        "volume" => Color::Rgb(180, 180, 180),                 // Gray
        _ => Color::Rgb(160, 160, 160),                        // Default gray
    }
}

/// Churn heatmap color: blue (cold) → yellow → red (hot).
fn churn_color(normalized: f64) -> Color {
    let n = normalized.clamp(0.0, 1.0);
    if n < 0.5 {
        let t = n * 2.0;
        Color::Rgb(
            (60.0 + 195.0 * t) as u8,
            (100.0 + 155.0 * t) as u8,
            (255.0 - 155.0 * t) as u8,
        )
    } else {
        let t = (n - 0.5) * 2.0;
        Color::Rgb(
            255,
            (255.0 - 155.0 * t) as u8,
            (100.0 - 100.0 * t) as u8,
        )
    }
}

/// Blend a base color toward white based on pulse progress (0.0 = white, 1.0 = base).
fn pulse_blend(base: Color, elapsed_secs: f64, duration: f64) -> Color {
    let fade = (elapsed_secs / duration).clamp(0.0, 1.0); // 0→1 as time passes
    if let Color::Rgb(r, g, b) = base {
        Color::Rgb(
            (r as f64 + (255.0 - r as f64) * (1.0 - fade)) as u8,
            (g as f64 + (255.0 - g as f64) * (1.0 - fade)) as u8,
            (b as f64 + (255.0 - b as f64) * (1.0 - fade)) as u8,
        )
    } else {
        base
    }
}

/// Author colors for blame overlay (up to 8 distinct authors).
const BLAME_COLORS: [Color; 8] = [
    Color::Rgb(100, 200, 180),
    Color::Rgb(180, 130, 255),
    Color::Rgb(255, 180, 100),
    Color::Rgb(120, 220, 140),
    Color::Rgb(255, 140, 200),
    Color::Rgb(140, 200, 255),
    Color::Rgb(200, 200, 100),
    Color::Rgb(255, 140, 100),
];

/// Sort modes for the stats panel.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SortMode {
    ByCount,
    ByName,
    ByType,
}

impl SortMode {
    fn next(self) -> Self {
        match self {
            SortMode::ByCount => SortMode::ByName,
            SortMode::ByName => SortMode::ByType,
            SortMode::ByType => SortMode::ByCount,
        }
    }

    fn label(self) -> &'static str {
        match self {
            SortMode::ByCount => "count",
            SortMode::ByName => "name",
            SortMode::ByType => "type",
        }
    }
}

/// TUI application state.
pub struct App {
    pub graph: AppGraph,
    pub layout: LayoutEngine,
    pub project_path: PathBuf,

    // Viewport
    pub offset_x: f64,
    pub offset_y: f64,
    pub zoom_level: f64,

    // Selection
    pub selected_index: Option<usize>,
    pub show_detail: bool,

    // Display toggles
    pub show_edges: bool,
    pub show_labels: bool,
    pub sort_mode: SortMode,

    // Search
    pub search_active: bool,
    pub search_query: String,
    pub search_results: Vec<usize>,
    pub ranked_results: Vec<SearchResult>,
    node_importance: HashMap<usize, f64>,

    // Git integration
    pub git_info: Option<GitInfo>,

    // Time-travel
    pub time_travel_active: bool,
    pub time_travel_index: usize,
    pub highlighted_nodes: Vec<usize>,

    // Churn heatmap
    pub churn_active: bool,
    node_churn: HashMap<usize, f64>,

    // Blame overlay
    pub blame_active: bool,
    blame_cache: HashMap<String, BlameSummary>,

    // Live pulse animation
    pulse_nodes: HashMap<usize, Instant>,
    file_to_nodes: HashMap<String, Vec<usize>>,

    // Precomputed
    type_counts: Vec<(String, usize)>,
}

impl App {
    pub fn new(graph: AppGraph, git_info: Option<GitInfo>, project_path: PathBuf) -> Self {
        let layout = LayoutEngine::new(&graph, 200.0, 100.0);

        // Count by type
        let mut counts: HashMap<String, usize> = HashMap::new();
        for node in &graph.nodes {
            *counts.entry(node.node_type.clone()).or_insert(0) += 1;
        }
        let mut type_counts: Vec<_> = counts.into_iter().collect();
        type_counts.sort_by(|a, b| b.1.cmp(&a.1));

        // Build file-to-nodes mapping (for pulse + churn)
        let file_to_nodes = compute_file_to_nodes(&graph);

        // Precompute churn data
        let node_churn = if let Some(ref gi) = git_info {
            compute_node_churn(&graph, &file_to_nodes, &gi.file_churns)
        } else {
            HashMap::new()
        };

        // Precompute node importance (connection-based ranking)
        let node_importance = search::compute_importance(&graph);

        App {
            graph,
            layout,
            project_path,
            offset_x: 0.0,
            offset_y: 0.0,
            zoom_level: 1.0,
            selected_index: None,
            show_detail: false,
            show_edges: true,
            show_labels: true,
            sort_mode: SortMode::ByCount,
            search_active: false,
            search_query: String::new(),
            search_results: Vec::new(),
            ranked_results: Vec::new(),
            node_importance,
            git_info,
            time_travel_active: false,
            time_travel_index: 0,
            highlighted_nodes: Vec::new(),
            churn_active: false,
            node_churn,
            blame_active: false,
            blame_cache: HashMap::new(),
            pulse_nodes: HashMap::new(),
            file_to_nodes,
            type_counts,
        }
    }

    pub fn pan(&mut self, dx: f64, dy: f64) {
        self.offset_x += dx / self.zoom_level;
        self.offset_y += dy / self.zoom_level;
    }

    pub fn zoom(&mut self, factor: f64) {
        self.zoom_level = (self.zoom_level * factor).clamp(0.1, 10.0);
    }

    pub fn reset_view(&mut self) {
        self.offset_x = 0.0;
        self.offset_y = 0.0;
        self.zoom_level = 1.0;
    }

    pub fn select_next(&mut self) {
        let n = self.graph.nodes.len();
        if n == 0 {
            return;
        }
        if self.search_results.is_empty() {
            self.selected_index = Some(match self.selected_index {
                Some(i) => (i + 1) % n,
                None => 0,
            });
        } else {
            let current_pos = self.selected_index.and_then(|idx| {
                self.search_results.iter().position(|&r| r == idx)
            });
            let next = match current_pos {
                Some(pos) => (pos + 1) % self.search_results.len(),
                None => 0,
            };
            self.selected_index = Some(self.search_results[next]);
        }
        if self.search_active {
            self.center_on_selected();
        }
    }

    pub fn select_prev(&mut self) {
        let n = self.graph.nodes.len();
        if n == 0 {
            return;
        }
        if self.search_results.is_empty() {
            self.selected_index = Some(match self.selected_index {
                Some(0) => n - 1,
                Some(i) => i - 1,
                None => n - 1,
            });
        } else {
            let current_pos = self.selected_index.and_then(|idx| {
                self.search_results.iter().position(|&r| r == idx)
            });
            let prev = match current_pos {
                Some(0) => self.search_results.len() - 1,
                Some(pos) => pos - 1,
                None => 0,
            };
            self.selected_index = Some(self.search_results[prev]);
        }
        if self.search_active {
            self.center_on_selected();
        }
    }

    pub fn toggle_detail(&mut self) {
        if self.selected_index.is_some() {
            self.show_detail = !self.show_detail;
        }
    }

    pub fn deselect(&mut self) {
        if self.search_active {
            self.search_active = false;
            self.search_query.clear();
            self.search_results.clear();
        } else {
            self.selected_index = None;
            self.show_detail = false;
        }
    }

    pub fn toggle_edges(&mut self) {
        self.show_edges = !self.show_edges;
    }

    pub fn toggle_labels(&mut self) {
        self.show_labels = !self.show_labels;
    }

    pub fn cycle_sort(&mut self) {
        self.sort_mode = self.sort_mode.next();
    }

    pub fn toggle_search(&mut self) {
        self.search_active = !self.search_active;
        if !self.search_active {
            self.search_query.clear();
            self.search_results.clear();
            self.ranked_results.clear();
        }
    }

    pub fn search_input(&mut self, c: char) {
        self.search_query.push(c);
        self.update_search();
    }

    pub fn search_backspace(&mut self) {
        self.search_query.pop();
        self.update_search();
    }

    fn update_search(&mut self) {
        if self.search_query.is_empty() {
            self.search_results.clear();
            self.ranked_results.clear();
            return;
        }

        self.ranked_results = search::ranked_search(
            &self.search_query,
            &self.graph,
            &self.node_importance,
            &self.node_churn,
        );

        self.search_results = self
            .ranked_results
            .iter()
            .map(|r| r.node_index)
            .collect();

        if !self.search_results.is_empty() {
            self.selected_index = Some(self.search_results[0]);
            self.center_on_selected();
        }
    }

    /// Auto-pan to center the selected node in the viewport.
    pub fn center_on_selected(&mut self) {
        if let Some(idx) = self.selected_index {
            if let Some(pos) = self.layout.get_position(&self.graph.nodes[idx].id) {
                let (min_x, min_y, max_x, max_y) = self.layout.bounds();
                let cx = (min_x + max_x) / 2.0;
                let cy = (min_y + max_y) / 2.0;
                self.offset_x = pos.x - cx;
                self.offset_y = pos.y - cy;
            }
        }
    }

    // ─── Git: Time-Travel ─────────────────────────────────────────────

    pub fn toggle_time_travel(&mut self) {
        if self.git_info.is_none() {
            return;
        }
        self.time_travel_active = !self.time_travel_active;
        if self.time_travel_active {
            self.time_travel_index = 0;
            self.update_time_travel_highlight();
        } else {
            self.highlighted_nodes.clear();
        }
    }

    pub fn time_travel_next(&mut self) {
        if let Some(ref gi) = self.git_info {
            if gi.commits.is_empty() {
                return;
            }
            if self.time_travel_index + 1 < gi.commits.len() {
                self.time_travel_index += 1;
                self.update_time_travel_highlight();
            }
        }
    }

    pub fn time_travel_prev(&mut self) {
        if self.time_travel_index > 0 {
            self.time_travel_index -= 1;
            self.update_time_travel_highlight();
        }
    }

    fn update_time_travel_highlight(&mut self) {
        self.highlighted_nodes.clear();
        if let Some(ref gi) = self.git_info {
            if let Some(commit) = gi.commits.get(self.time_travel_index) {
                for file in &commit.files_changed {
                    if let Some(node_indices) = self.file_to_nodes.get(file) {
                        self.highlighted_nodes.extend(node_indices);
                    }
                }
            }
        }
    }

    // ─── Git: Churn Heatmap ───────────────────────────────────────────

    pub fn toggle_churn(&mut self) {
        if self.git_info.is_none() {
            return;
        }
        self.churn_active = !self.churn_active;
    }

    // ─── Git: Blame ───────────────────────────────────────────────────

    pub fn toggle_blame(&mut self) {
        if self.git_info.is_none() {
            return;
        }
        self.blame_active = !self.blame_active;
    }

    /// Get blame summary for the selected node's file (lazy-loaded + cached).
    fn get_selected_blame(&mut self) -> Option<BlameSummary> {
        let node = self.selected_index.map(|i| &self.graph.nodes[i])?;
        let file_path = node.file_path.as_ref()?;

        if let Some(cached) = self.blame_cache.get(file_path) {
            return Some(cached.clone());
        }

        if let Some(blame) = git::get_blame(&self.project_path, file_path) {
            self.blame_cache.insert(file_path.clone(), blame.clone());
            Some(blame)
        } else {
            None
        }
    }

    // ─── Live Pulse ───────────────────────────────────────────────────

    /// Called when a file changes (from the watcher).
    pub fn on_file_changed(&mut self, rel_path: &str) {
        let now = Instant::now();
        if let Some(node_indices) = self.file_to_nodes.get(rel_path) {
            for &idx in node_indices {
                self.pulse_nodes.insert(idx, now);
            }
        }
    }

    pub fn tick(&mut self) {
        // Remove expired pulses (older than 3 seconds)
        let now = Instant::now();
        self.pulse_nodes
            .retain(|_, start| now.duration_since(*start).as_secs_f64() < 3.0);
    }
}

/// Build file_path → node_indices mapping via DFS through "contains" edges.
fn compute_file_to_nodes(graph: &AppGraph) -> HashMap<String, Vec<usize>> {
    let id_to_idx: HashMap<&str, usize> = graph
        .nodes
        .iter()
        .enumerate()
        .map(|(i, n)| (n.id.as_str(), i))
        .collect();

    // Parent → children via "contains" edges
    let mut children: HashMap<usize, Vec<usize>> = HashMap::new();
    for edge in &graph.edges {
        if edge.edge_type == "contains" {
            if let (Some(&from_idx), Some(&to_idx)) = (
                id_to_idx.get(edge.from.as_str()),
                id_to_idx.get(edge.to.as_str()),
            ) {
                children.entry(from_idx).or_default().push(to_idx);
            }
        }
    }

    // DFS from each root node with file_path
    let mut file_to_nodes: HashMap<String, Vec<usize>> = HashMap::new();
    for (i, node) in graph.nodes.iter().enumerate() {
        if let Some(ref path) = node.file_path {
            let mut stack = vec![i];
            while let Some(idx) = stack.pop() {
                file_to_nodes.entry(path.clone()).or_default().push(idx);
                if let Some(kids) = children.get(&idx) {
                    stack.extend(kids);
                }
            }
        }
    }

    file_to_nodes
}

/// Compute normalized churn score (0.0-1.0) per node index.
fn compute_node_churn(
    graph: &AppGraph,
    file_to_nodes: &HashMap<String, Vec<usize>>,
    file_churns: &HashMap<String, git::ChurnMetrics>,
) -> HashMap<usize, f64> {
    let max_commits = file_churns
        .values()
        .map(|c| c.commits)
        .max()
        .unwrap_or(1)
        .max(1) as f64;

    let mut node_churn = HashMap::new();

    for (file, churn) in file_churns {
        let normalized = (churn.commits as f64) / max_commits;
        if let Some(node_indices) = file_to_nodes.get(file) {
            for &idx in node_indices {
                if idx < graph.nodes.len() {
                    node_churn.insert(idx, normalized);
                }
            }
        }
    }

    node_churn
}

/// Main draw function — called every frame.
pub fn draw(frame: &mut Frame, app: &mut App) {
    let area = frame.area();

    // Top-level split: main area + status bar
    let outer = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(5), Constraint::Length(3)])
        .split(area);

    let main_area = outer[0];
    let status_area = outer[1];

    // Main area: canvas + side panel
    let main_split = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(70), Constraint::Percentage(30)])
        .split(main_area);

    let canvas_area = main_split[0];
    let side_area = main_split[1];

    // Side panel: stats + optional detail
    let side_constraints = if app.show_detail && app.selected_index.is_some() {
        vec![Constraint::Percentage(50), Constraint::Percentage(50)]
    } else {
        vec![Constraint::Percentage(100)]
    };
    let side_split = Layout::default()
        .direction(Direction::Vertical)
        .constraints(side_constraints)
        .split(side_area);

    // ─── Draw Graph Canvas ───────────────────────────────────────────────
    draw_canvas(frame, app, canvas_area);

    // ─── Draw Stats Panel ────────────────────────────────────────────────
    if app.time_travel_active {
        draw_git_panel(frame, app, side_split[0]);
    } else {
        draw_stats(frame, app, side_split[0]);
    }

    // ─── Draw Detail Panel ───────────────────────────────────────────────
    if app.show_detail && app.selected_index.is_some() && side_split.len() > 1 {
        draw_detail(frame, app, side_split[1]);
    }

    // ─── Draw Status Bar ─────────────────────────────────────────────────
    draw_status_bar(frame, app, status_area);

    // ─── Draw Time-Travel Slider ─────────────────────────────────────────
    if app.time_travel_active {
        draw_time_travel_slider(frame, app, canvas_area);
    }

    // ─── Draw Search Overlay ─────────────────────────────────────────────
    if app.search_active {
        draw_search(frame, app, area);
    }
}

fn draw_canvas(frame: &mut Frame, app: &App, area: Rect) {
    let (min_x, min_y, max_x, max_y) = app.layout.bounds();
    let pad = 5.0;

    let view_w = (max_x - min_x + pad * 2.0) / app.zoom_level;
    let view_h = (max_y - min_y + pad * 2.0) / app.zoom_level;
    let cx = (min_x + max_x) / 2.0 + app.offset_x;
    let cy = (min_y + max_y) / 2.0 + app.offset_y;

    let x_min = cx - view_w / 2.0;
    let x_max = cx + view_w / 2.0;
    let y_min = cy - view_h / 2.0;
    let y_max = cy + view_h / 2.0;

    let title = if app.churn_active {
        format!(
            " Ontology Map \u{2014} Churn Heatmap \u{2014} {} nodes ",
            app.graph.nodes.len()
        )
    } else if app.time_travel_active {
        " Ontology Map \u{2014} Time Travel ".to_string()
    } else {
        format!(
            " Ontology Map \u{2014} {} nodes, {} edges ",
            app.graph.nodes.len(),
            app.graph.edges.len()
        )
    };

    let canvas = Canvas::default()
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(title)
                .border_style(Style::default().fg(Color::Rgb(60, 80, 100)))
                .title_style(Style::default().fg(Color::Rgb(100, 200, 180))),
        )
        .marker(Marker::Braille)
        .x_bounds([x_min, x_max])
        .y_bounds([y_min, y_max])
        .paint(|ctx| {
            paint_graph(ctx, app);
        });

    frame.render_widget(canvas, area);
}

/// Paint graph into the canvas context.
fn paint_graph(ctx: &mut Context<'_>, app: &App) {
    let now = Instant::now();

    // Draw edges first (behind nodes)
    if app.show_edges {
        for edge in &app.graph.edges {
            let from_pos = app.layout.get_position(&edge.from);
            let to_pos = app.layout.get_position(&edge.to);
            if let (Some(from), Some(to)) = (from_pos, to_pos) {
                let color = match edge.edge_type.as_str() {
                    "imports" => Color::Rgb(60, 70, 90),
                    "contains" => Color::Rgb(50, 60, 70),
                    "depends_on" => Color::Rgb(80, 60, 50),
                    "exports" => Color::Rgb(50, 70, 60),
                    "implements" => Color::Rgb(70, 50, 80),
                    "calls" => Color::Rgb(70, 80, 50),
                    _ => Color::Rgb(50, 50, 60),
                };
                ctx.draw(&ratatui::widgets::canvas::Line {
                    x1: from.x,
                    y1: from.y,
                    x2: to.x,
                    y2: to.y,
                    color,
                });
            }
        }
    }

    // Draw nodes
    for (i, node) in app.graph.nodes.iter().enumerate() {
        if let Some(pos) = app.layout.get_position(&node.id) {
            let is_selected = app.selected_index == Some(i);
            let is_search_hit = app.search_results.contains(&i);
            let is_highlighted = app.time_travel_active && app.highlighted_nodes.contains(&i);
            let is_pulsing = app.pulse_nodes.contains_key(&i);

            // Determine base color
            let base_color = if app.churn_active {
                if let Some(&churn_val) = app.node_churn.get(&i) {
                    churn_color(churn_val)
                } else {
                    Color::Rgb(40, 40, 50) // No churn data = dim
                }
            } else {
                type_color(&node.node_type)
            };

            // Apply overlays
            let color = if is_selected {
                Color::Rgb(255, 255, 255)
            } else if is_highlighted {
                Color::Rgb(255, 220, 80) // Time-travel highlight: gold
            } else if is_search_hit {
                Color::Rgb(255, 220, 100)
            } else if is_pulsing {
                let elapsed = now
                    .duration_since(app.pulse_nodes[&i])
                    .as_secs_f64();
                pulse_blend(base_color, elapsed, 3.0)
            } else {
                base_color
            };

            // Draw node as a cluster of points
            let offsets: &[(f64, f64)] = if is_selected || is_highlighted {
                &[
                    (0.0, 0.0),
                    (0.3, 0.0),
                    (-0.3, 0.0),
                    (0.0, 0.3),
                    (0.0, -0.3),
                    (0.3, 0.3),
                    (-0.3, 0.3),
                    (0.3, -0.3),
                    (-0.3, -0.3),
                ]
            } else if is_pulsing {
                &[
                    (0.0, 0.0),
                    (0.3, 0.0),
                    (-0.3, 0.0),
                    (0.0, 0.3),
                    (0.0, -0.3),
                    (0.2, 0.2),
                    (-0.2, 0.2),
                ]
            } else {
                &[
                    (0.0, 0.0),
                    (0.2, 0.0),
                    (-0.2, 0.0),
                    (0.0, 0.2),
                    (0.0, -0.2),
                ]
            };

            for &(dx, dy) in offsets {
                ctx.draw(&Points {
                    coords: &[(pos.x + dx, pos.y + dy)],
                    color,
                });
            }

            // Draw label
            if app.show_labels && app.zoom_level >= 0.5 {
                let label_color = if is_selected {
                    Color::White
                } else if is_highlighted {
                    Color::Rgb(255, 220, 80)
                } else {
                    Color::Rgb(140, 140, 150)
                };
                let label = if node.label.chars().count() > 16 {
                    let truncated: String = node.label.chars().take(13).collect();
                    format!("{truncated}...")
                } else {
                    node.label.clone()
                };
                ctx.print(
                    pos.x + 0.8,
                    pos.y,
                    Span::styled(label, Style::default().fg(label_color)),
                );
            }
        }
    }
}

fn draw_stats(frame: &mut Frame, app: &App, area: Rect) {
    let mut lines = Vec::new();

    lines.push(Line::from(vec![
        Span::styled(" Nodes  ", Style::default().fg(Color::Rgb(100, 200, 180))),
        Span::styled(
            format!("{}", app.graph.nodes.len()),
            Style::default()
                .fg(Color::White)
                .add_modifier(Modifier::BOLD),
        ),
    ]));
    lines.push(Line::from(vec![
        Span::styled(" Edges  ", Style::default().fg(Color::Rgb(100, 200, 180))),
        Span::styled(
            format!("{}", app.graph.edges.len()),
            Style::default()
                .fg(Color::White)
                .add_modifier(Modifier::BOLD),
        ),
    ]));

    // Git summary
    if let Some(ref gi) = app.git_info {
        lines.push(Line::from(vec![
            Span::styled(
                " Commits ",
                Style::default().fg(Color::Rgb(100, 200, 180)),
            ),
            Span::styled(
                format!("{}", gi.commits.len()),
                Style::default()
                    .fg(Color::White)
                    .add_modifier(Modifier::BOLD),
            ),
        ]));
    }

    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        format!(" By Type (sort: {})", app.sort_mode.label()),
        Style::default()
            .fg(Color::Rgb(100, 200, 180))
            .add_modifier(Modifier::BOLD),
    )));
    lines.push(Line::from(Span::styled(
        " \u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}",
        Style::default().fg(Color::Rgb(60, 80, 100)),
    )));

    let mut sorted_types = app.type_counts.clone();
    match app.sort_mode {
        SortMode::ByCount => sorted_types.sort_by(|a, b| b.1.cmp(&a.1)),
        SortMode::ByName => sorted_types.sort_by(|a, b| a.0.cmp(&b.0)),
        SortMode::ByType => {} // keep original order
    }

    for (node_type, count) in &sorted_types {
        let color = type_color(node_type);
        lines.push(Line::from(vec![
            Span::styled(" \u{25cf} ", Style::default().fg(color)),
            Span::styled(
                format!("{node_type:<12}"),
                Style::default().fg(Color::Rgb(180, 180, 190)),
            ),
            Span::styled(
                format!("{count:>4}"),
                Style::default()
                    .fg(Color::White)
                    .add_modifier(Modifier::BOLD),
            ),
        ]));
    }

    // Adapters
    if !app.graph.adapters_used.is_empty() {
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled(
            " Adapters",
            Style::default()
                .fg(Color::Rgb(100, 200, 180))
                .add_modifier(Modifier::BOLD),
        )));
        for adapter in &app.graph.adapters_used {
            lines.push(Line::from(Span::styled(
                format!("   {adapter}"),
                Style::default().fg(Color::Rgb(160, 160, 170)),
            )));
        }
    }

    let stats = Paragraph::new(lines).block(
        Block::default()
            .borders(Borders::ALL)
            .title(" Statistics ")
            .border_style(Style::default().fg(Color::Rgb(60, 80, 100)))
            .title_style(Style::default().fg(Color::Rgb(100, 200, 180))),
    );

    frame.render_widget(stats, area);
}

/// Git panel shown during time-travel mode (replaces stats).
fn draw_git_panel(frame: &mut Frame, app: &App, area: Rect) {
    let mut lines = Vec::new();

    let gi = match app.git_info {
        Some(ref gi) => gi,
        None => return,
    };

    lines.push(Line::from(Span::styled(
        format!(
            " Commit {}/{} ",
            app.time_travel_index + 1,
            gi.commits.len()
        ),
        Style::default()
            .fg(Color::Rgb(255, 220, 80))
            .add_modifier(Modifier::BOLD),
    )));
    lines.push(Line::from(""));

    // Show commits around the current index
    let start = app.time_travel_index.saturating_sub(2);
    let end = (start + 8).min(gi.commits.len());

    for i in start..end {
        let commit = &gi.commits[i];
        let is_current = i == app.time_travel_index;

        let prefix = if is_current { "\u{25b6} " } else { "  " };
        let hash_color = if is_current {
            Color::Rgb(255, 220, 80)
        } else {
            Color::Rgb(100, 200, 180)
        };
        let msg_color = if is_current {
            Color::White
        } else {
            Color::Rgb(160, 160, 170)
        };

        lines.push(Line::from(vec![
            Span::styled(prefix, Style::default().fg(hash_color)),
            Span::styled(
                &commit.short_hash,
                Style::default()
                    .fg(hash_color)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw(" "),
            Span::styled(
                truncate_str(&commit.message, 20),
                Style::default().fg(msg_color),
            ),
        ]));
        lines.push(Line::from(vec![
            Span::raw("    "),
            Span::styled(
                &commit.author,
                Style::default().fg(Color::Rgb(130, 130, 140)),
            ),
            Span::raw(" "),
            Span::styled(
                git::relative_time(commit.timestamp),
                Style::default().fg(Color::Rgb(100, 100, 110)),
            ),
        ]));
    }

    // Files changed in current commit
    if let Some(commit) = gi.commits.get(app.time_travel_index) {
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled(
            format!(" {} files changed", commit.files_changed.len()),
            Style::default()
                .fg(Color::Rgb(100, 200, 180))
                .add_modifier(Modifier::BOLD),
        )));
        for file in commit.files_changed.iter().take(8) {
            let display = truncate_str(file, 24);
            lines.push(Line::from(Span::styled(
                format!("   {display}"),
                Style::default().fg(Color::Rgb(160, 160, 170)),
            )));
        }
        if commit.files_changed.len() > 8 {
            lines.push(Line::from(Span::styled(
                format!("   ... +{} more", commit.files_changed.len() - 8),
                Style::default().fg(Color::Rgb(100, 100, 110)),
            )));
        }
    }

    let panel = Paragraph::new(lines).block(
        Block::default()
            .borders(Borders::ALL)
            .title(" Git History ")
            .border_style(Style::default().fg(Color::Rgb(80, 70, 40)))
            .title_style(Style::default().fg(Color::Rgb(255, 220, 80))),
    );

    frame.render_widget(panel, area);
}

fn draw_detail(frame: &mut Frame, app: &mut App, area: Rect) {
    let idx = match app.selected_index {
        Some(i) => i,
        None => return,
    };

    // Clone all needed node data upfront to avoid borrow conflicts
    let node_label = app.graph.nodes[idx].label.clone();
    let node_type = app.graph.nodes[idx].node_type.clone();
    let node_file_path = app.graph.nodes[idx].file_path.clone();
    let node_line_count = app.graph.nodes[idx].line_count;
    let node_layer = app.graph.nodes[idx].layer.clone();
    let node_id = app.graph.nodes[idx].id.clone();

    // Fetch blame data (mutable borrow) before building lines
    let blame_data = if app.blame_active && node_file_path.is_some() {
        app.get_selected_blame()
    } else {
        None
    };

    let mut lines = Vec::new();

    lines.push(Line::from(vec![Span::styled(
        &node_label,
        Style::default()
            .fg(Color::White)
            .add_modifier(Modifier::BOLD),
    )]));
    lines.push(Line::from(""));

    lines.push(Line::from(vec![
        Span::styled(" Type    ", Style::default().fg(Color::Rgb(100, 200, 180))),
        Span::styled(
            &node_type,
            Style::default().fg(type_color(&node_type)),
        ),
    ]));

    if let Some(ref path) = node_file_path {
        lines.push(Line::from(vec![
            Span::styled(" File    ", Style::default().fg(Color::Rgb(100, 200, 180))),
            Span::styled(path.as_str(), Style::default().fg(Color::Rgb(180, 180, 190))),
        ]));
    }

    if let Some(loc) = node_line_count {
        lines.push(Line::from(vec![
            Span::styled(" LOC     ", Style::default().fg(Color::Rgb(100, 200, 180))),
            Span::styled(
                format!("{loc}"),
                Style::default().fg(Color::Rgb(180, 180, 190)),
            ),
        ]));
    }

    if let Some(ref layer) = node_layer {
        lines.push(Line::from(vec![
            Span::styled(" Layer   ", Style::default().fg(Color::Rgb(100, 200, 180))),
            Span::styled(layer.as_str(), Style::default().fg(Color::Rgb(180, 180, 190))),
        ]));
    }

    // Churn info
    if let Some(ref gi) = app.git_info {
        if let Some(ref path) = node_file_path {
            if let Some(churn) = gi.file_churns.get(path) {
                lines.push(Line::from(""));
                lines.push(Line::from(vec![
                    Span::styled(
                        " Churn   ",
                        Style::default().fg(Color::Rgb(100, 200, 180)),
                    ),
                    Span::styled(
                        format!("{} commits", churn.commits),
                        Style::default().fg(Color::Rgb(255, 180, 100)),
                    ),
                ]));
                lines.push(Line::from(vec![
                    Span::styled(
                        " Last    ",
                        Style::default().fg(Color::Rgb(100, 200, 180)),
                    ),
                    Span::styled(
                        git::relative_time(churn.last_modified),
                        Style::default().fg(Color::Rgb(180, 180, 190)),
                    ),
                ]));
            }
        }
    }

    // Blame overlay
    if let Some(ref bd) = blame_data {
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled(
            format!(" Blame ({} lines)", bd.total_lines),
            Style::default()
                .fg(Color::Rgb(100, 200, 180))
                .add_modifier(Modifier::BOLD),
        )));
        for (j, (author, line_count)) in bd.authors.iter().take(6).enumerate() {
            let pct = if bd.total_lines > 0 {
                (*line_count as f64 / bd.total_lines as f64 * 100.0) as u32
            } else {
                0
            };
            let color = BLAME_COLORS[j % BLAME_COLORS.len()];
            lines.push(Line::from(vec![
                Span::styled(" \u{25cf} ", Style::default().fg(color)),
                Span::styled(
                    truncate_str(author, 14),
                    Style::default().fg(Color::Rgb(180, 180, 190)),
                ),
                Span::styled(
                    format!(" {pct}% ({line_count})"),
                    Style::default().fg(Color::Rgb(130, 130, 140)),
                ),
            ]));
        }
        if bd.authors.len() > 6 {
            lines.push(Line::from(Span::styled(
                format!("   +{} more", bd.authors.len() - 6),
                Style::default().fg(Color::Rgb(100, 100, 110)),
            )));
        }
    }

    // Connections
    let incoming: Vec<_> = app
        .graph
        .edges
        .iter()
        .filter(|e| e.to == node_id)
        .collect();
    let outgoing: Vec<_> = app
        .graph
        .edges
        .iter()
        .filter(|e| e.from == node_id)
        .collect();

    lines.push(Line::from(""));
    lines.push(Line::from(vec![Span::styled(
        format!(" \u{2190} {} incoming", incoming.len()),
        Style::default().fg(Color::Rgb(130, 180, 255)),
    )]));
    for edge in incoming.iter().take(5) {
        lines.push(Line::from(Span::styled(
            format!("   {} ({})", edge.from, edge.edge_type),
            Style::default().fg(Color::Rgb(120, 120, 130)),
        )));
    }
    if incoming.len() > 5 {
        lines.push(Line::from(Span::styled(
            format!("   ... +{} more", incoming.len() - 5),
            Style::default().fg(Color::Rgb(90, 90, 100)),
        )));
    }

    lines.push(Line::from(vec![Span::styled(
        format!(" \u{2192} {} outgoing", outgoing.len()),
        Style::default().fg(Color::Rgb(255, 180, 130)),
    )]));
    for edge in outgoing.iter().take(5) {
        lines.push(Line::from(Span::styled(
            format!("   {} ({})", edge.to, edge.edge_type),
            Style::default().fg(Color::Rgb(120, 120, 130)),
        )));
    }
    if outgoing.len() > 5 {
        lines.push(Line::from(Span::styled(
            format!("   ... +{} more", outgoing.len() - 5),
            Style::default().fg(Color::Rgb(90, 90, 100)),
        )));
    }

    let detail = Paragraph::new(lines)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(" Detail ")
                .border_style(Style::default().fg(Color::Rgb(60, 80, 100)))
                .title_style(Style::default().fg(Color::Rgb(100, 200, 180))),
        )
        .wrap(Wrap { trim: true });

    frame.render_widget(detail, area);
}

/// Draw the time-travel slider at the bottom of the canvas area.
fn draw_time_travel_slider(frame: &mut Frame, app: &App, canvas_area: Rect) {
    let gi = match app.git_info {
        Some(ref gi) if !gi.commits.is_empty() => gi,
        _ => return,
    };

    // Slider at the bottom of the canvas, overlaid
    let slider_height = 3u16;
    let y = canvas_area.y + canvas_area.height.saturating_sub(slider_height + 1);
    let slider_area = Rect::new(
        canvas_area.x + 1,
        y,
        canvas_area.width.saturating_sub(2),
        slider_height,
    );

    let total = gi.commits.len();
    let progress = if total > 1 {
        app.time_travel_index as f64 / (total - 1) as f64
    } else {
        0.0
    };

    // Build slider bar
    let bar_width = slider_area.width.saturating_sub(4) as usize;
    let pos = (progress * bar_width as f64) as usize;

    let mut bar = String::new();
    bar.push('\u{25c4}'); // ◄
    for i in 0..bar_width {
        if i == pos {
            bar.push('\u{25cf}'); // ●
        } else {
            bar.push('\u{2550}'); // ═
        }
    }
    bar.push('\u{25ba}'); // ►

    // Commit info
    let commit_info = if let Some(commit) = gi.commits.get(app.time_travel_index) {
        format!(
            "  {} {} \u{2014} {}",
            commit.short_hash,
            truncate_str(&commit.message, 30),
            git::relative_time(commit.timestamp)
        )
    } else {
        String::new()
    };

    let line = Line::from(vec![
        Span::styled(
            bar,
            Style::default()
                .fg(Color::Rgb(255, 220, 80))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(commit_info, Style::default().fg(Color::Rgb(180, 180, 190))),
    ]);

    let slider = Paragraph::new(line).block(
        Block::default()
            .borders(Borders::ALL)
            .title(" \u{23f1} Time Travel (h/l to navigate, T to exit) ")
            .border_style(Style::default().fg(Color::Rgb(80, 70, 40)))
            .title_style(
                Style::default()
                    .fg(Color::Rgb(255, 220, 80))
                    .add_modifier(Modifier::BOLD),
            )
            .style(Style::default().bg(Color::Rgb(20, 20, 30))),
    );

    frame.render_widget(slider, slider_area);
}

fn draw_status_bar(frame: &mut Frame, app: &App, area: Rect) {
    let edges_icon = if app.show_edges { "on" } else { "off" };
    let labels_icon = if app.show_labels { "on" } else { "off" };

    let selected_info = match app.selected_index {
        Some(i) => format!(" \u{25c6} {}", app.graph.nodes[i].label),
        None => String::new(),
    };

    let zoom_pct = (app.zoom_level * 100.0) as u32;

    let mut spans = vec![
        Span::styled(
            " q",
            Style::default()
                .fg(Color::Rgb(100, 200, 180))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(":quit ", Style::default().fg(Color::Rgb(120, 120, 130))),
        Span::styled(
            "hjkl",
            Style::default()
                .fg(Color::Rgb(100, 200, 180))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(":pan ", Style::default().fg(Color::Rgb(120, 120, 130))),
        Span::styled(
            "+/-",
            Style::default()
                .fg(Color::Rgb(100, 200, 180))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            format!(":zoom({zoom_pct}%) "),
            Style::default().fg(Color::Rgb(120, 120, 130)),
        ),
        Span::styled(
            "/",
            Style::default()
                .fg(Color::Rgb(100, 200, 180))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(":search ", Style::default().fg(Color::Rgb(120, 120, 130))),
        Span::styled(
            "e",
            Style::default()
                .fg(Color::Rgb(100, 200, 180))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            format!(":edges({edges_icon}) "),
            Style::default().fg(Color::Rgb(120, 120, 130)),
        ),
        Span::styled(
            "n",
            Style::default()
                .fg(Color::Rgb(100, 200, 180))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            format!(":labels({labels_icon}) "),
            Style::default().fg(Color::Rgb(120, 120, 130)),
        ),
    ];

    // Git keybinds (only shown if git is available)
    if app.git_info.is_some() {
        spans.push(Span::styled(
            "t",
            Style::default()
                .fg(Color::Rgb(255, 220, 80))
                .add_modifier(Modifier::BOLD),
        ));
        spans.push(Span::styled(
            ":time ",
            Style::default().fg(Color::Rgb(120, 120, 130)),
        ));
        spans.push(Span::styled(
            "c",
            Style::default()
                .fg(Color::Rgb(255, 220, 80))
                .add_modifier(Modifier::BOLD),
        ));
        let churn_icon = if app.churn_active { "on" } else { "off" };
        spans.push(Span::styled(
            format!(":churn({churn_icon}) "),
            Style::default().fg(Color::Rgb(120, 120, 130)),
        ));
        spans.push(Span::styled(
            "b",
            Style::default()
                .fg(Color::Rgb(255, 220, 80))
                .add_modifier(Modifier::BOLD),
        ));
        let blame_icon = if app.blame_active { "on" } else { "off" };
        spans.push(Span::styled(
            format!(":blame({blame_icon}) "),
            Style::default().fg(Color::Rgb(120, 120, 130)),
        ));
    }

    // Pulse indicator
    if !app.pulse_nodes.is_empty() {
        spans.push(Span::styled(
            format!(" \u{26a1}{}", app.pulse_nodes.len()),
            Style::default()
                .fg(Color::Rgb(255, 255, 100))
                .add_modifier(Modifier::BOLD),
        ));
    }

    spans.push(Span::styled(
        selected_info,
        Style::default()
            .fg(Color::Rgb(255, 220, 100))
            .add_modifier(Modifier::BOLD),
    ));

    let line = Line::from(spans);

    let bar = Paragraph::new(line).block(
        Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Rgb(40, 50, 60))),
    );

    frame.render_widget(bar, area);
}

fn draw_search(frame: &mut Frame, app: &App, area: Rect) {
    let width = 50u16.min(area.width.saturating_sub(4));
    let x = (area.width.saturating_sub(width)) / 2;

    let result_count = app.ranked_results.len();
    let has_results = !app.ranked_results.is_empty();
    let list_height = if has_results {
        (result_count as u16).min(8) + 1
    } else {
        0
    };
    let total_height = 3 + list_height;
    let search_area = Rect::new(x, 1, width, total_height);

    let results_info = if app.search_query.is_empty() {
        String::new()
    } else {
        format!(" ({result_count} matches)")
    };

    let mut lines = vec![Line::from(vec![
        Span::styled(
            " / ",
            Style::default()
                .fg(Color::Rgb(100, 200, 180))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(&app.search_query, Style::default().fg(Color::White)),
        Span::styled(
            "\u{2588}",
            Style::default().fg(Color::Rgb(100, 200, 180)),
        ),
        Span::styled(
            results_info,
            Style::default().fg(Color::Rgb(120, 120, 130)),
        ),
    ])];

    // Show ranked results below the search input
    for (rank, result) in app.ranked_results.iter().take(8).enumerate() {
        let node = &app.graph.nodes[result.node_index];
        let is_selected = app.selected_index == Some(result.node_index);
        let prefix = if is_selected { "\u{25b6} " } else { "  " };
        let label_color = if is_selected {
            Color::White
        } else {
            Color::Rgb(180, 180, 190)
        };

        lines.push(Line::from(vec![
            Span::styled(prefix, Style::default().fg(Color::Rgb(100, 200, 180))),
            Span::styled(
                format!("{:>2}. ", rank + 1),
                Style::default().fg(Color::Rgb(80, 80, 90)),
            ),
            Span::styled(
                truncate_str(&node.label, 20),
                Style::default().fg(label_color).add_modifier(
                    if is_selected {
                        Modifier::BOLD
                    } else {
                        Modifier::empty()
                    },
                ),
            ),
            Span::styled(
                format!(" {}", node.node_type),
                Style::default().fg(type_color(&node.node_type)),
            ),
            Span::styled(
                format!(" [{}]", result.match_kind.label()),
                Style::default().fg(Color::Rgb(80, 80, 90)),
            ),
        ]));
    }

    let search = Paragraph::new(lines).block(
        Block::default()
            .borders(Borders::ALL)
            .title(" Search (Tab: next, Esc: close) ")
            .border_style(Style::default().fg(Color::Rgb(100, 200, 180)))
            .title_style(
                Style::default()
                    .fg(Color::Rgb(100, 200, 180))
                    .add_modifier(Modifier::BOLD),
            )
            .style(Style::default().bg(Color::Rgb(20, 25, 35))),
    );

    frame.render_widget(search, search_area);
}

/// Truncate a string with "..." if too long (unicode-safe).
fn truncate_str(s: &str, max_len: usize) -> String {
    let char_count = s.chars().count();
    if char_count <= max_len {
        s.to_string()
    } else if max_len > 3 {
        let truncated: String = s.chars().take(max_len - 3).collect();
        format!("{truncated}...")
    } else {
        s.chars().take(max_len).collect()
    }
}
