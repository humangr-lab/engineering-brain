/**
 * Ghost Mode — detect "ghost nodes" that should exist but don't.
 * Pure engine module (no React dependency).
 *
 * Ghost types:
 * - Missing test files (module exists, test_module does not)
 * - TODO/FIXME comments (from metadata)
 * - Missing docs (public module without docstring)
 */

import type { Node, Edge } from "@/lib/api";

export interface GhostNode {
  id: string;
  label: string;
  ghostType: "missing_test" | "todo" | "missing_doc";
  reason: string;
  /** ID of the real node this ghost relates to */
  relatedNodeId: string;
  /** Opacity for rendering (0-1) */
  opacity: number;
}

/**
 * Detect ghost nodes based on the current graph.
 */
export function detectGhosts(nodes: Node[], _edges: Edge[]): GhostNode[] {
  const ghosts: GhostNode[] = [];
  const nodeIds = new Set(nodes.map((n) => n.id));

  for (const node of nodes) {
    // 1. Missing test files
    if (
      node.type === "module" &&
      !node.id.includes("test") &&
      !node.id.includes("__")
    ) {
      // Check if a corresponding test module exists
      const testId = node.id.replace(/^(python:|js:)/, "$1test_");
      const testId2 = node.id.replace(/^(python:|js:)(.+)/, "$1$2.test");
      const testId3 = node.id.replace(
        /^(python:|js:)(.+)/,
        "$1__tests__/$2",
      );

      const hasTest =
        nodeIds.has(testId) || nodeIds.has(testId2) || nodeIds.has(testId3);

      if (!hasTest) {
        ghosts.push({
          id: `ghost:test:${node.id}`,
          label: `test_${node.text}`,
          ghostType: "missing_test",
          reason: `Missing test file for ${node.text}`,
          relatedNodeId: node.id,
          opacity: 0.3,
        });
      }
    }

    // 2. TODO/FIXME from metadata
    const todoCount = node.metadata?.todos;
    if (typeof todoCount === "number" && todoCount > 0) {
      ghosts.push({
        id: `ghost:todo:${node.id}`,
        label: `${todoCount} TODO${todoCount > 1 ? "s" : ""}`,
        ghostType: "todo",
        reason: `${todoCount} unresolved TODO/FIXME in ${node.text}`,
        relatedNodeId: node.id,
        opacity: 0.25,
      });
    }

    // 3. Missing docs for public modules
    if (
      node.type === "module" &&
      !node.metadata?.has_docstring &&
      !node.id.includes("test") &&
      !node.id.includes("__init__")
    ) {
      // Only flag if module has exported functions/classes
      const hasExports = nodes.some(
        (n) =>
          n.id.startsWith(node.id + ":") &&
          (n.type === "function" || n.type === "class"),
      );
      if (hasExports) {
        ghosts.push({
          id: `ghost:doc:${node.id}`,
          label: `docs: ${node.text}`,
          ghostType: "missing_doc",
          reason: `Public module ${node.text} has no documentation`,
          relatedNodeId: node.id,
          opacity: 0.2,
        });
      }
    }
  }

  return ghosts;
}

/** Get ghost summary for display */
export function getGhostSummary(ghosts: GhostNode[]): {
  total: number;
  missingTests: number;
  todos: number;
  missingDocs: number;
} {
  return {
    total: ghosts.length,
    missingTests: ghosts.filter((g) => g.ghostType === "missing_test").length,
    todos: ghosts.filter((g) => g.ghostType === "todo").length,
    missingDocs: ghosts.filter((g) => g.ghostType === "missing_doc").length,
  };
}
