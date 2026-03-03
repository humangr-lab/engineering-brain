//! Force-directed graph layout (Fruchterman-Reingold algorithm).
//!
//! Computes 2D positions for all nodes using:
//! - Repulsive forces between all node pairs (Coulomb-like)
//! - Attractive forces along edges (spring)
//! - Temperature cooling for convergence

use std::collections::HashMap;

use crate::graph::AppGraph;

/// 2D position of a node after layout.
#[derive(Debug, Clone, Copy)]
pub struct Position {
    pub x: f64,
    pub y: f64,
}

/// Force-directed layout engine.
pub struct LayoutEngine {
    positions: Vec<Position>,
    node_index: HashMap<String, usize>,
    edges: Vec<(usize, usize)>,
    width: f64,
    height: f64,
}

impl LayoutEngine {
    /// Create a new layout from the graph. Runs the simulation immediately.
    pub fn new(graph: &AppGraph, width: f64, height: f64) -> Self {
        let n = graph.nodes.len();
        let mut node_index = HashMap::with_capacity(n);
        for (i, node) in graph.nodes.iter().enumerate() {
            node_index.insert(node.id.clone(), i);
        }

        // Map edges to index pairs
        let edges: Vec<(usize, usize)> = graph
            .edges
            .iter()
            .filter_map(|e| {
                let from = node_index.get(&e.from)?;
                let to = node_index.get(&e.to)?;
                Some((*from, *to))
            })
            .collect();

        // Initialize positions in a circle (deterministic, avoids overlap)
        let mut positions = Vec::with_capacity(n);
        if n == 0 {
            return Self {
                positions,
                node_index,
                edges,
                width,
                height,
            };
        }

        let cx = width / 2.0;
        let cy = height / 2.0;
        let radius = width.min(height) * 0.35;

        for i in 0..n {
            let angle = 2.0 * std::f64::consts::PI * (i as f64) / (n as f64);
            positions.push(Position {
                x: cx + radius * angle.cos(),
                y: cy + radius * angle.sin(),
            });
        }

        let mut engine = Self {
            positions,
            node_index,
            edges,
            width,
            height,
        };

        // Run simulation
        let iterations = if n < 50 {
            300
        } else if n < 200 {
            200
        } else {
            120
        };
        engine.simulate(iterations);
        engine
    }

    /// Run the Fruchterman-Reingold simulation for N iterations.
    fn simulate(&mut self, iterations: usize) {
        let n = self.positions.len();
        if n <= 1 {
            return;
        }

        let area = self.width * self.height;
        let k = (area / n as f64).sqrt(); // Optimal distance
        let mut temperature = self.width.min(self.height) * 0.1;
        let cooling = temperature / (iterations as f64 + 1.0);

        let mut displacements = vec![(0.0f64, 0.0f64); n];

        for _ in 0..iterations {
            // Reset displacements
            displacements.fill((0.0, 0.0));

            // Repulsive forces (all pairs)
            for i in 0..n {
                for j in (i + 1)..n {
                    let dx = self.positions[i].x - self.positions[j].x;
                    let dy = self.positions[i].y - self.positions[j].y;
                    let dist = (dx * dx + dy * dy).sqrt().max(0.01);
                    let force = (k * k) / dist;
                    let fx = (dx / dist) * force;
                    let fy = (dy / dist) * force;

                    displacements[i].0 += fx;
                    displacements[i].1 += fy;
                    displacements[j].0 -= fx;
                    displacements[j].1 -= fy;
                }
            }

            // Attractive forces (edges)
            for &(u, v) in &self.edges {
                let dx = self.positions[u].x - self.positions[v].x;
                let dy = self.positions[u].y - self.positions[v].y;
                let dist = (dx * dx + dy * dy).sqrt().max(0.01);
                let force = (dist * dist) / k;
                let fx = (dx / dist) * force;
                let fy = (dy / dist) * force;

                displacements[u].0 -= fx;
                displacements[u].1 -= fy;
                displacements[v].0 += fx;
                displacements[v].1 += fy;
            }

            // Apply displacements with temperature clamping
            for (i, &(dx, dy)) in displacements.iter().enumerate() {
                let dist = (dx * dx + dy * dy).sqrt().max(0.01);
                let capped = dist.min(temperature);
                self.positions[i].x += (dx / dist) * capped;
                self.positions[i].y += (dy / dist) * capped;

                // Keep within bounds (with padding)
                let pad = 5.0;
                self.positions[i].x = self.positions[i].x.clamp(pad, self.width - pad);
                self.positions[i].y = self.positions[i].y.clamp(pad, self.height - pad);
            }

            temperature -= cooling;
            if temperature < 0.1 {
                temperature = 0.1;
            }
        }
    }

    /// Get the position of a node by ID.
    pub fn get_position(&self, id: &str) -> Option<Position> {
        self.node_index.get(id).map(|&i| self.positions[i])
    }

    /// Get all positions as a slice.
    #[allow(dead_code)]
    pub fn positions(&self) -> &[Position] {
        &self.positions
    }

    /// Bounding box: (min_x, min_y, max_x, max_y).
    pub fn bounds(&self) -> (f64, f64, f64, f64) {
        if self.positions.is_empty() {
            return (0.0, 0.0, self.width, self.height);
        }
        let min_x = self
            .positions
            .iter()
            .map(|p| p.x)
            .fold(f64::INFINITY, f64::min);
        let min_y = self
            .positions
            .iter()
            .map(|p| p.y)
            .fold(f64::INFINITY, f64::min);
        let max_x = self
            .positions
            .iter()
            .map(|p| p.x)
            .fold(f64::NEG_INFINITY, f64::max);
        let max_y = self
            .positions
            .iter()
            .map(|p| p.y)
            .fold(f64::NEG_INFINITY, f64::max);
        (min_x, min_y, max_x, max_y)
    }
}
