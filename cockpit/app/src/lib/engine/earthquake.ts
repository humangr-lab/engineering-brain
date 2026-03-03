/**
 * Dependency Earthquake — BFS cascade visualization.
 * Pure engine module (no React dependency).
 *
 * Usage: Select a node, press D → BFS propagation shows all affected nodes
 * with depth-colored rings and physics shake.
 */

import type { Node, Edge } from "@/lib/api";

export interface EarthquakeResult {
  /** Node IDs at each BFS depth. depth[0] = selected node */
  layers: string[][];
  /** Total affected nodes (excluding the epicenter) */
  affectedCount: number;
  /** Percentage of codebase affected */
  affectedPercent: number;
}

/** Color by BFS depth: red → orange → yellow → gray */
export const DEPTH_COLORS = [
  "#ef4444", // depth 0 — epicenter (red)
  "#f97316", // depth 1 (orange)
  "#eab308", // depth 2 (yellow)
  "#a3a3a3", // depth 3+ (gray)
] as const;

/**
 * Run BFS from a node, returning all reachable nodes grouped by depth.
 * Traverses both outgoing and incoming edges (full dependency blast radius).
 */
export function computeEarthquake(
  epicenterId: string,
  nodes: Node[],
  edges: Edge[],
  maxDepth = 10,
): EarthquakeResult {
  const nodeSet = new Set(nodes.map((n) => n.id));

  // Build adjacency list (both directions)
  const adj = new Map<string, Set<string>>();
  for (const e of edges) {
    if (!adj.has(e.from)) adj.set(e.from, new Set());
    if (!adj.has(e.to)) adj.set(e.to, new Set());
    adj.get(e.from)!.add(e.to);
    adj.get(e.to)!.add(e.from);
  }

  // BFS
  const visited = new Set<string>();
  const layers: string[][] = [];
  let frontier = [epicenterId];
  visited.add(epicenterId);

  for (let depth = 0; depth <= maxDepth && frontier.length > 0; depth++) {
    layers.push([...frontier]);
    const next: string[] = [];
    for (const id of frontier) {
      const neighbors = adj.get(id);
      if (!neighbors) continue;
      for (const nb of neighbors) {
        if (!visited.has(nb) && nodeSet.has(nb)) {
          visited.add(nb);
          next.push(nb);
        }
      }
    }
    frontier = next;
  }

  const affectedCount = visited.size - 1; // exclude epicenter
  const affectedPercent =
    nodes.length > 0 ? (affectedCount / nodes.length) * 100 : 0;

  return { layers, affectedCount, affectedPercent };
}

/**
 * Get the color for a node based on its earthquake depth.
 * Returns null if node is not in the earthquake result.
 */
export function getEarthquakeColor(
  nodeId: string,
  result: EarthquakeResult,
): string | null {
  for (let i = 0; i < result.layers.length; i++) {
    if (result.layers[i].includes(nodeId)) {
      return DEPTH_COLORS[Math.min(i, DEPTH_COLORS.length - 1)];
    }
  }
  return null;
}

/**
 * Compute shake displacement for a node based on earthquake depth.
 * Returns { x, y, z } displacement in world units.
 */
export function computeShake(
  depth: number,
  time: number,
  intensity = 1.0,
): { x: number; y: number; z: number } {
  // Shake intensity decreases with depth, uses spring-like decay
  const depthFactor = Math.max(0, 1 - depth * 0.25);
  const decay = Math.exp(-time * 3); // fast decay over ~1s
  const freq = 15 + depth * 5; // higher depth = higher frequency (smaller shake)
  const amplitude = 0.3 * intensity * depthFactor * decay;

  return {
    x: amplitude * Math.sin(time * freq),
    y: amplitude * Math.sin(time * freq * 1.3 + 1.0),
    z: amplitude * Math.sin(time * freq * 0.7 + 2.0),
  };
}
