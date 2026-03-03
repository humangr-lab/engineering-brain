/**
 * Heatmap Engine — node recoloring by metric.
 * Pure engine module (no React dependency).
 *
 * Toggle with H key. Metrics: degree centrality, complexity (metadata),
 * LOC (metadata), or layer.
 */

import type { Node, Edge } from "@/lib/api";

export type HeatmapMetric = "degree" | "complexity" | "loc" | "layer" | "confidence";

/** OKLCH-inspired gradient: low (dark blue) → high (bright red) */
const GRADIENT = [
  "#1e3a5f", // 0.0 — deep blue (cold)
  "#1e6091", // 0.2
  "#3b9c6b", // 0.4 — green
  "#d4a017", // 0.6 — yellow
  "#e06c2e", // 0.8 — orange
  "#d93025", // 1.0 — red (hot)
] as const;

export interface HeatmapResult {
  /** Node ID → normalized value [0, 1] */
  values: Map<string, number>;
  /** Node ID → hex color */
  colors: Map<string, string>;
  /** Metric used */
  metric: HeatmapMetric;
  /** Min/max raw values */
  range: { min: number; max: number };
}

/** Compute heatmap values for all nodes */
export function computeHeatmap(
  nodes: Node[],
  edges: Edge[],
  metric: HeatmapMetric,
): HeatmapResult {
  const rawValues = new Map<string, number>();

  switch (metric) {
    case "degree": {
      // Degree centrality: count of connected edges
      const counts = new Map<string, number>();
      for (const e of edges) {
        counts.set(e.from, (counts.get(e.from) ?? 0) + 1);
        counts.set(e.to, (counts.get(e.to) ?? 0) + 1);
      }
      for (const n of nodes) {
        rawValues.set(n.id, counts.get(n.id) ?? 0);
      }
      break;
    }

    case "complexity": {
      // From metadata if available, otherwise estimate from edge count
      for (const n of nodes) {
        const meta = n.metadata?.complexity;
        rawValues.set(
          n.id,
          typeof meta === "number" ? meta : (n.outEdges?.length ?? 0),
        );
      }
      break;
    }

    case "loc": {
      // Lines of code from metadata
      for (const n of nodes) {
        const meta = n.metadata?.loc ?? n.metadata?.lines;
        rawValues.set(n.id, typeof meta === "number" ? meta : 0);
      }
      break;
    }

    case "layer": {
      // Layer number as heat value (higher layer = hotter)
      for (const n of nodes) {
        rawValues.set(n.id, n.layer);
      }
      break;
    }

    case "confidence": {
      for (const n of nodes) {
        rawValues.set(n.id, n.confidence);
      }
      break;
    }
  }

  // Normalize to [0, 1]
  let min = Infinity;
  let max = -Infinity;
  for (const v of rawValues.values()) {
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (min === max) max = min + 1; // avoid division by zero

  const values = new Map<string, number>();
  const colors = new Map<string, string>();
  for (const [id, raw] of rawValues) {
    const norm = (raw - min) / (max - min);
    values.set(id, norm);
    colors.set(id, interpolateGradient(norm));
  }

  return { values, colors, metric, range: { min, max } };
}

/** Interpolate through gradient based on value [0, 1] */
function interpolateGradient(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const segments = GRADIENT.length - 1;
  const idx = clamped * segments;
  const lo = Math.floor(idx);
  const hi = Math.min(lo + 1, segments);
  const frac = idx - lo;

  return lerpColor(GRADIENT[lo], GRADIENT[hi], frac);
}

/** Linearly interpolate between two hex colors */
function lerpColor(a: string, b: string, t: number): string {
  const ar = parseInt(a.slice(1, 3), 16);
  const ag = parseInt(a.slice(3, 5), 16);
  const ab = parseInt(a.slice(5, 7), 16);
  const br = parseInt(b.slice(1, 3), 16);
  const bg = parseInt(b.slice(3, 5), 16);
  const bb = parseInt(b.slice(5, 7), 16);

  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const bv = Math.round(ab + (bb - ab) * t);

  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${bv.toString(16).padStart(2, "0")}`;
}

/** Get available metrics for the current graph */
export function getAvailableMetrics(nodes: Node[]): HeatmapMetric[] {
  const metrics: HeatmapMetric[] = ["degree", "layer", "confidence"];

  // Check if nodes have complexity or LOC metadata
  const hasComplexity = nodes.some(
    (n) => typeof n.metadata?.complexity === "number",
  );
  const hasLoc = nodes.some(
    (n) =>
      typeof n.metadata?.loc === "number" ||
      typeof n.metadata?.lines === "number",
  );

  if (hasComplexity) metrics.push("complexity");
  if (hasLoc) metrics.push("loc");

  return metrics;
}
