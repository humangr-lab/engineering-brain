/**
 * Multi-Map Federation — connect multiple projects into a meta-map.
 * Pure engine module (no React dependency).
 *
 * Each project is a "map" with its own graph. The federation layer
 * merges them and creates cross-project edges based on shared symbols.
 */

import type { Node, Edge, GraphSnapshot } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface FederatedProject {
  /** Unique project ID */
  id: string;
  /** Project display name */
  name: string;
  /** Project root path */
  path: string;
  /** Color used to distinguish this project in the meta-map */
  color: string;
  /** Graph snapshot */
  snapshot: GraphSnapshot;
}

export interface FederatedGraph {
  /** All nodes across all projects (IDs prefixed with project ID) */
  nodes: Node[];
  /** All edges including cross-project links */
  edges: Edge[];
  /** Cross-project edges discovered */
  crossEdges: CrossProjectEdge[];
  /** Project metadata */
  projects: FederatedProject[];
}

export interface CrossProjectEdge {
  fromProject: string;
  toProject: string;
  fromNodeId: string;
  toNodeId: string;
  type: string;
  /** How the connection was discovered */
  reason: string;
}

// ─── Federation Colors ───────────────────────────────────────────────────────

const PROJECT_COLORS = [
  "#10b981", // emerald
  "#6366f1", // indigo
  "#f59e0b", // amber
  "#ef4444", // red
  "#06b6d4", // cyan
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#14b8a6", // teal
];

// ─── Core Functions ──────────────────────────────────────────────────────────

/** Create a federated graph from multiple project snapshots */
export function createFederatedGraph(
  projects: Omit<FederatedProject, "color">[],
): FederatedGraph {
  const federatedProjects: FederatedProject[] = projects.map((p, i) => ({
    ...p,
    color: PROJECT_COLORS[i % PROJECT_COLORS.length],
  }));

  // Prefix all node/edge IDs with project ID
  const allNodes: Node[] = [];
  const allEdges: Edge[] = [];

  for (const project of federatedProjects) {
    for (const node of project.snapshot.nodes) {
      allNodes.push({
        ...node,
        id: `${project.id}::${node.id}`,
        metadata: {
          ...node.metadata,
          _federation_project: project.id,
          _federation_color: project.color,
          _federation_name: project.name,
        },
      });
    }
    for (const edge of project.snapshot.edges) {
      allEdges.push({
        ...edge,
        from: `${project.id}::${edge.from}`,
        to: `${project.id}::${edge.to}`,
      });
    }
  }

  // Discover cross-project edges
  const crossEdges = discoverCrossProjectEdges(federatedProjects);

  // Add cross-project edges to the graph
  for (const cross of crossEdges) {
    allEdges.push({
      from: `${cross.fromProject}::${cross.fromNodeId}`,
      to: `${cross.toProject}::${cross.toNodeId}`,
      type: cross.type,
      weight: 0.5, // lower weight for cross-project links
    });
  }

  return {
    nodes: allNodes,
    edges: allEdges,
    crossEdges,
    projects: federatedProjects,
  };
}

// Common symbol names that generate noisy cross-project edges
const COMMON_SYMBOLS = new Set([
  "index", "main", "app", "config", "utils", "helpers", "types",
  "constants", "errors", "test", "spec", "setup", "init", "mod",
  "lib", "src", "api", "client", "server", "handler", "router",
  "middleware", "model", "schema", "service", "controller",
  "default", "base", "common", "core", "shared",
]);

/** Max cross-project edges per symbol to prevent O(n²) blowup */
const MAX_EDGES_PER_SYMBOL = 5;

/** Discover cross-project edges based on shared symbols */
function discoverCrossProjectEdges(
  projects: FederatedProject[],
): CrossProjectEdge[] {
  const crossEdges: CrossProjectEdge[] = [];

  // Build index: symbol name → [(projectId, nodeId)]
  const symbolIndex = new Map<string, { project: string; nodeId: string }[]>();

  for (const project of projects) {
    for (const node of project.snapshot.nodes) {
      // Extract symbol name (last part of dotted path)
      const parts = node.id.split(/[.:]/);
      const symbol = parts[parts.length - 1]?.toLowerCase();
      // Skip short, empty, or overly common symbols
      if (!symbol || symbol.length < 4 || COMMON_SYMBOLS.has(symbol)) continue;

      const entry = { project: project.id, nodeId: node.id };
      const existing = symbolIndex.get(symbol);
      if (existing) {
        existing.push(entry);
      } else {
        symbolIndex.set(symbol, [entry]);
      }
    }
  }

  // Find shared symbols across projects
  for (const [symbol, entries] of symbolIndex) {
    // Only consider symbols that appear in multiple projects
    const projectIds = new Set(entries.map((e) => e.project));
    if (projectIds.size < 2) continue;

    // Create edges between the first occurrence in each project pair
    const byProject = new Map<string, string>();
    for (const entry of entries) {
      if (!byProject.has(entry.project)) {
        byProject.set(entry.project, entry.nodeId);
      }
    }

    const projectList = Array.from(byProject.entries());
    let edgeCount = 0;
    for (let i = 0; i < projectList.length - 1 && edgeCount < MAX_EDGES_PER_SYMBOL; i++) {
      for (let j = i + 1; j < projectList.length && edgeCount < MAX_EDGES_PER_SYMBOL; j++) {
        crossEdges.push({
          fromProject: projectList[i][0],
          toProject: projectList[j][0],
          fromNodeId: projectList[i][1],
          toNodeId: projectList[j][1],
          type: "SHARED_SYMBOL",
          reason: `Shared symbol: "${symbol}"`,
        });
        edgeCount++;
      }
    }
  }

  return crossEdges;
}

/** Get federation stats */
export function getFederationStats(
  graph: FederatedGraph,
): {
  totalNodes: number;
  totalEdges: number;
  crossEdges: number;
  projects: { id: string; name: string; color: string; nodes: number; edges: number }[];
} {
  const projectStats = new Map<string, { nodes: number; edges: number }>();

  for (const p of graph.projects) {
    projectStats.set(p.id, {
      nodes: p.snapshot.nodes.length,
      edges: p.snapshot.edges.length,
    });
  }

  return {
    totalNodes: graph.nodes.length,
    totalEdges: graph.edges.length,
    crossEdges: graph.crossEdges.length,
    projects: graph.projects.map((p) => ({
      id: p.id,
      name: p.name,
      color: p.color,
      nodes: projectStats.get(p.id)?.nodes ?? 0,
      edges: projectStats.get(p.id)?.edges ?? 0,
    })),
  };
}
