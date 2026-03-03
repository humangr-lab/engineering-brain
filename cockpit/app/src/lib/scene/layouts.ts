/* ====== LAYOUTS -- Position algorithms for 3D system maps ======
   Orbital, force (d3-force-3d), tree, grid, pipeline.
   Each layout takes SysmapNodes and returns positioned nodes.    */

import type { SysmapNode } from "@/lib/inference/build-sysmap";
import type { LayoutName } from "@/lib/inference/layout-selector";

export interface PositionedNode extends SysmapNode {
  px: number;
  py: number;
  pz: number;
}

// ── Public API ──

export function applyLayout(
  layout: LayoutName,
  nodes: SysmapNode[],
  edges: { f: string; t: string }[],
): PositionedNode[] {
  switch (layout) {
    case "orbital":
      return orbitalLayout(nodes);
    case "tree":
      return treeLayout(nodes, edges);
    case "pipeline":
      return pipelineLayout(nodes, edges);
    case "grid":
      return gridLayout(nodes);
    case "layered":
      return layeredLayout(nodes);
    case "force":
    default:
      return forceLayout(nodes, edges);
  }
}

// ── Orbital layout ──
// Nodes grouped by `g` field, each group on a concentric ring.

function orbitalLayout(nodes: SysmapNode[]): PositionedNode[] {
  const groups = new Map<string, SysmapNode[]>();
  for (const n of nodes) {
    const list = groups.get(n.g) || [];
    list.push(n);
    groups.set(n.g, list);
  }

  const result: PositionedNode[] = [];
  const groupKeys = [...groups.keys()].sort();
  const ringSpacing = 6;

  for (let gi = 0; gi < groupKeys.length; gi++) {
    const group = groups.get(groupKeys[gi])!;
    const ringRadius = (gi + 1) * ringSpacing;

    for (let ni = 0; ni < group.length; ni++) {
      const angle = (ni / group.length) * Math.PI * 2;
      const n = group[ni];
      result.push({
        ...n,
        px: ringRadius * Math.cos(angle),
        py: (gi - groupKeys.length / 2) * 1.5,
        pz: ringRadius * Math.sin(angle),
      });
    }
  }

  return result;
}

// ── Force layout (static approximation) ──
// Uses golden ratio spiral as a fast deterministic placement.
// For true force simulation, d3-force-3d can be layered on top.

function forceLayout(
  nodes: SysmapNode[],
  _edges: { f: string; t: string }[],
): PositionedNode[] {
  const count = nodes.length;
  const radius = Math.max(8, Math.sqrt(count) * 2);

  return nodes.map((n, i) => {
    // Golden ratio spiral on sphere
    const phi = Math.acos(1 - (2 * (i + 0.5)) / count);
    const theta = Math.PI * (1 + Math.sqrt(5)) * i;

    return {
      ...n,
      px: radius * Math.sin(phi) * Math.cos(theta),
      py: radius * Math.cos(phi) * 0.5,
      pz: radius * Math.sin(phi) * Math.sin(theta),
    };
  });
}

// ── Tree layout ──
// Hierarchical top-down from CONTAINS edges / parent field.

function treeLayout(
  nodes: SysmapNode[],
  edges: { f: string; t: string }[],
): PositionedNode[] {
  // Build parent -> children map
  const children = new Map<string, string[]>();
  const hasParent = new Set<string>();

  for (const e of edges) {
    const list = children.get(e.f) || [];
    list.push(e.t);
    children.set(e.f, list);
    hasParent.add(e.t);
  }

  // Find roots (no parent)
  const nodeIds = new Set(nodes.map((n) => n.id));
  const roots = nodes.filter((n) => !hasParent.has(n.id));
  if (roots.length === 0 && nodes.length > 0) {
    roots.push(nodes[0]);
  }

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const positioned = new Map<string, PositionedNode>();

  // BFS from roots
  const queue: { id: string; depth: number; index: number; siblingCount: number }[] = [];
  for (let i = 0; i < roots.length; i++) {
    queue.push({ id: roots[i].id, depth: 0, index: i, siblingCount: roots.length });
  }

  const layerSpacing = 5;
  const siblingSpacing = 4;

  while (queue.length) {
    const { id, depth, index, siblingCount } = queue.shift()!;
    if (positioned.has(id)) continue;

    const n = nodeMap.get(id);
    if (!n) continue;

    const xOffset = (index - (siblingCount - 1) / 2) * siblingSpacing;

    positioned.set(id, {
      ...n,
      px: xOffset,
      py: -depth * layerSpacing,
      pz: 0,
    });

    const kids = (children.get(id) || []).filter((cid) => nodeIds.has(cid) && !positioned.has(cid));
    for (let ci = 0; ci < kids.length; ci++) {
      queue.push({ id: kids[ci], depth: depth + 1, index: ci, siblingCount: kids.length });
    }
  }

  // Place any unpositioned nodes in a fallback row
  let fallbackIdx = 0;
  for (const n of nodes) {
    if (!positioned.has(n.id)) {
      positioned.set(n.id, {
        ...n,
        px: fallbackIdx * siblingSpacing,
        py: 5,
        pz: 10,
      });
      fallbackIdx++;
    }
  }

  return [...positioned.values()];
}

// ── Grid layout ──
// Simple grid for small graphs (<10 nodes).

function gridLayout(nodes: SysmapNode[]): PositionedNode[] {
  const cols = Math.ceil(Math.sqrt(nodes.length));
  const spacing = 4;

  return nodes.map((n, i) => {
    const row = Math.floor(i / cols);
    const col = i % cols;
    return {
      ...n,
      px: (col - (cols - 1) / 2) * spacing,
      py: 0,
      pz: (row - Math.floor(nodes.length / cols) / 2) * spacing,
    };
  });
}

// ── Pipeline layout ──
// Linear left-to-right for DAG structures.

function pipelineLayout(
  nodes: SysmapNode[],
  edges: { f: string; t: string }[],
): PositionedNode[] {
  // Topological sort
  const inDeg = new Map<string, number>();
  const adj = new Map<string, string[]>();
  for (const n of nodes) {
    inDeg.set(n.id, 0);
    adj.set(n.id, []);
  }
  for (const e of edges) {
    if (inDeg.has(e.t)) {
      inDeg.set(e.t, (inDeg.get(e.t) || 0) + 1);
    }
    if (adj.has(e.f)) {
      adj.get(e.f)!.push(e.t);
    }
  }

  const queue: string[] = [];
  for (const [id, deg] of inDeg) {
    if (deg === 0) queue.push(id);
  }

  const order: string[] = [];
  const visited = new Set<string>();
  while (queue.length) {
    const id = queue.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);
    order.push(id);
    for (const next of adj.get(id) || []) {
      const d = (inDeg.get(next) || 1) - 1;
      inDeg.set(next, d);
      if (d === 0) queue.push(next);
    }
  }

  // Add any remaining nodes
  for (const n of nodes) {
    if (!visited.has(n.id)) order.push(n.id);
  }

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const spacing = 5;

  return order.map((id, i) => {
    const n = nodeMap.get(id)!;
    return {
      ...n,
      px: i * spacing - ((order.length - 1) * spacing) / 2,
      py: 0,
      pz: 0,
    };
  });
}

// ── Layered layout ──
// Groups stacked vertically by `g` field.

function layeredLayout(nodes: SysmapNode[]): PositionedNode[] {
  const groups = new Map<string, SysmapNode[]>();
  for (const n of nodes) {
    const list = groups.get(n.g) || [];
    list.push(n);
    groups.set(n.g, list);
  }

  const result: PositionedNode[] = [];
  const groupKeys = [...groups.keys()].sort();
  const layerSpacing = 6;
  const nodeSpacing = 4;

  for (let gi = 0; gi < groupKeys.length; gi++) {
    const group = groups.get(groupKeys[gi])!;
    const y = -gi * layerSpacing;

    for (let ni = 0; ni < group.length; ni++) {
      const n = group[ni];
      result.push({
        ...n,
        px: (ni - (group.length - 1) / 2) * nodeSpacing,
        py: y,
        pz: 0,
      });
    }
  }

  return result;
}
