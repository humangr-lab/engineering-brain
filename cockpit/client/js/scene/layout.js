/* ═══════════════ LAYOUT — Node positioning algorithms ═══════════════
   Original: default (orbital), pipeline, funnel.
   Added: tree, grid, force, grouped, layered.
   All layout functions return Map<nodeId, {x, y, z}>.                */

import * as T from 'three';
import { cam, ctrl } from './engine.js';

// ── ORIGINAL LAYOUTS (preserved) ──

/**
 * Default (orbital) layout -- nodes positioned as in sysmap data.
 * Uses explicit x,z positions from node data. Y from inferred size or
 * hardcoded yBase table (backward compat with sysmap.js).
 */
export function defaultLayout(nodes) {
  const positions = new Map();

  // Legacy yBase for backward compat with sysmap.js nodes
  const yBase = {
    erg: 0.25, scorer: 0.16, taxon: 0.16, router: 0.16, embed: 0.16, packv2: 0.16,
    l0: 0.12, l1: 0.12, l2: 0.12, l3: 0.12, l4: 0.12, l5: 0.12,
    cryst: 0.18, promot: 0.18, xlay: 0.18, linkp: 0.18, adapt: 0.18, trust: 0.18,
    eladder: 0.18, bedge: 0.18, pdecay: 0.18, ctensor: 0.18, dstcomb: 0.18,
    seeds: 0.14, mining: 0.14, ontol: 0.14, obslog: 0.14,
    llm: 0.14, mcp: 0.14, cicd: 0.14, ide: 0.14, klib: 0.18,
  };

  nodes.forEach(n => {
    // Use inferred size for Y if available, fallback to yBase or default
    const inferredSize = n._inferredSize || null;
    const baseYFactor = yBase[n.id] || 0.15;
    const y = inferredSize != null
      ? inferredSize * 0.5 + 0.5
      : baseYFactor * 7;
    positions.set(n.id, { x: n.x, y, z: n.z });
  });
  return positions;
}

/**
 * Horizontal pipeline layout.
 */
export function pipelineLayout(nodes) {
  const positions = new Map();
  const groups = {};
  const groupOrder = [];

  nodes.forEach(n => {
    const g = n.g || 'module';
    if (!groups[g]) {
      groups[g] = [];
      groupOrder.push(g);
    }
    groups[g].push(n);
  });

  // Use original order if it matches the legacy groups, else use discovery order
  const order = ['source', 'layer', 'module', 'consumer'];
  const hasLegacy = order.every(g => groups[g]);
  const useOrder = hasLegacy ? order : groupOrder;

  let xOffset = -(useOrder.length - 1) * 6;
  useOrder.forEach(g => {
    const arr = groups[g] || [];
    arr.forEach((n, i) => {
      const spread = arr.length > 1 ? (i - (arr.length - 1) / 2) * 2.5 : 0;
      positions.set(n.id, { x: xOffset, y: 1.2, z: spread });
    });
    xOffset += 12;
  });
  return positions;
}

/**
 * Vertical funnel layout.
 */
export function funnelLayout(nodes) {
  const positions = new Map();
  const groups = {};
  const groupOrder = [];

  nodes.forEach(n => {
    const g = n.g || 'module';
    if (!groups[g]) {
      groups[g] = [];
      groupOrder.push(g);
    }
    groups[g].push(n);
  });

  const order = ['source', 'module', 'layer', 'consumer'];
  const hasLegacy = order.every(g => groups[g]);
  const useOrder = hasLegacy ? order : groupOrder;

  let zOffset = -(useOrder.length - 1) * 5;
  useOrder.forEach(g => {
    const arr = groups[g] || [];
    arr.forEach((n, i) => {
      const spread = arr.length > 1 ? (i - (arr.length - 1) / 2) * 2.5 : 0;
      positions.set(n.id, { x: spread, y: 1.2, z: zOffset });
    });
    zOffset += 10;
  });
  return positions;
}

// ── NEW LAYOUTS (added for WP-0) ──

/**
 * Grid layout -- simple rows and columns. Best for < 10 nodes.
 */
export function gridLayout(nodes) {
  const positions = new Map();
  const n = nodes.length;
  const cols = Math.ceil(Math.sqrt(n));
  const spacing = 4;

  nodes.forEach((node, i) => {
    const row = Math.floor(i / cols);
    const col = i % cols;
    const x = (col - (cols - 1) / 2) * spacing;
    const z = (row - (Math.ceil(n / cols) - 1) / 2) * spacing;
    positions.set(node.id, { x, y: 1.0, z });
  });

  return positions;
}

/**
 * Tree layout -- top-down hierarchical.
 * Uses parent field or CONTAINS edges to build the tree.
 * Nodes without parents are placed at the root level.
 */
export function treeLayout(nodes, edges = []) {
  const positions = new Map();

  // Build parent-child map
  const children = {};
  const hasParent = new Set();

  for (const n of nodes) {
    children[n.id] = [];
  }

  // From parent field
  for (const n of nodes) {
    if (n.parent && children[n.parent]) {
      children[n.parent].push(n.id);
      hasParent.add(n.id);
    }
  }

  // From CONTAINS edges
  for (const e of edges) {
    const from = e.f || e.from;
    const to = e.t || e.to;
    if ((e.type === 'CONTAINS' || e.c === 'white') && children[from] && !hasParent.has(to)) {
      children[from].push(to);
      hasParent.add(to);
    }
  }

  // Find roots (no parent)
  const roots = nodes.filter(n => !hasParent.has(n.id)).map(n => n.id);
  if (!roots.length && nodes.length) {
    roots.push(nodes[0].id);
  }

  const levelSpacing = 5;
  const siblingSpacing = 3.5;

  // BFS to assign levels and positions
  let xCounter = 0;
  function _layoutSubtree(nodeId, depth) {
    const kids = children[nodeId] || [];
    if (!kids.length) {
      // Leaf node
      const x = xCounter * siblingSpacing;
      xCounter++;
      positions.set(nodeId, { x, y: 1.0, z: -depth * levelSpacing });
      return x;
    }

    // Layout children first
    const childXPositions = kids.map(kid => _layoutSubtree(kid, depth + 1));
    const minX = Math.min(...childXPositions);
    const maxX = Math.max(...childXPositions);
    const centerX = (minX + maxX) / 2;

    positions.set(nodeId, { x: centerX, y: 1.0, z: -depth * levelSpacing });
    return centerX;
  }

  for (const root of roots) {
    _layoutSubtree(root, 0);
    xCounter += 1; // Gap between trees
  }

  // Center the layout
  if (positions.size) {
    const allX = [...positions.values()].map(p => p.x);
    const allZ = [...positions.values()].map(p => p.z);
    const cx = (Math.min(...allX) + Math.max(...allX)) / 2;
    const cz = (Math.min(...allZ) + Math.max(...allZ)) / 2;
    for (const [id, pos] of positions) {
      positions.set(id, { x: pos.x - cx, y: pos.y, z: pos.z - cz });
    }
  }

  return positions;
}

/**
 * Force-directed layout -- simple spring-embedder simulation.
 * Deterministic (seeded from node index, no randomness).
 * Runs synchronously for ~100 iterations.
 */
export function forceLayout(nodes, edges = []) {
  const positions = new Map();
  const n = nodes.length;
  if (!n) return positions;

  // Deterministic initial positions: golden angle spiral
  const PHI = (1 + Math.sqrt(5)) / 2;
  const pos = {};
  for (let i = 0; i < n; i++) {
    const theta = 2 * Math.PI * i / PHI;
    const r = Math.sqrt(i + 0.5) * 2;
    pos[nodes[i].id] = { x: r * Math.cos(theta), z: r * Math.sin(theta) };
  }

  // Build adjacency
  const adj = new Set();
  for (const e of edges) {
    const from = e.f || e.from;
    const to = e.t || e.to;
    if (from && to) adj.add(`${from}|${to}`);
  }

  // Spring-embedder: 80 iterations
  const ITERATIONS = 80;
  const REPULSION = 30;
  const ATTRACTION = 0.05;
  const DAMPING = 0.9;
  const velocity = {};
  for (const nd of nodes) velocity[nd.id] = { x: 0, z: 0 };

  for (let iter = 0; iter < ITERATIONS; iter++) {
    const temp = 1.0 - iter / ITERATIONS; // Cooling

    // Repulsion (all pairs)
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = nodes[i].id, b = nodes[j].id;
        const dx = pos[a].x - pos[b].x;
        const dz = pos[a].z - pos[b].z;
        const dist = Math.sqrt(dx * dx + dz * dz) || 0.01;
        const force = REPULSION / (dist * dist);
        const fx = (dx / dist) * force * temp;
        const fz = (dz / dist) * force * temp;
        velocity[a].x += fx;
        velocity[a].z += fz;
        velocity[b].x -= fx;
        velocity[b].z -= fz;
      }
    }

    // Attraction (connected pairs)
    for (const e of edges) {
      const from = e.f || e.from;
      const to = e.t || e.to;
      if (!pos[from] || !pos[to]) continue;
      const dx = pos[from].x - pos[to].x;
      const dz = pos[from].z - pos[to].z;
      const dist = Math.sqrt(dx * dx + dz * dz) || 0.01;
      const force = ATTRACTION * dist * temp;
      const fx = (dx / dist) * force;
      const fz = (dz / dist) * force;
      velocity[from].x -= fx;
      velocity[from].z -= fz;
      velocity[to].x += fx;
      velocity[to].z += fz;
    }

    // Apply velocities with damping
    for (const nd of nodes) {
      velocity[nd.id].x *= DAMPING;
      velocity[nd.id].z *= DAMPING;
      pos[nd.id].x += velocity[nd.id].x;
      pos[nd.id].z += velocity[nd.id].z;
    }
  }

  // Center and scale to reasonable bounds
  const allX = Object.values(pos).map(p => p.x);
  const allZ = Object.values(pos).map(p => p.z);
  const cx = (Math.min(...allX) + Math.max(...allX)) / 2;
  const cz = (Math.min(...allZ) + Math.max(...allZ)) / 2;
  const range = Math.max(
    Math.max(...allX) - Math.min(...allX),
    Math.max(...allZ) - Math.min(...allZ),
    1
  );
  const scale = Math.min(30 / range, 1.5); // Cap at 30 units wide

  for (const nd of nodes) {
    positions.set(nd.id, {
      x: (pos[nd.id].x - cx) * scale,
      y: 1.0,
      z: (pos[nd.id].z - cz) * scale,
    });
  }

  return positions;
}

/**
 * Grouped layout -- clusters nodes by group, arranged in a circle of clusters.
 * Within each cluster, nodes are arranged in a small grid.
 */
export function groupedLayout(nodes) {
  const positions = new Map();
  const groups = {};
  const groupOrder = [];

  for (const n of nodes) {
    const g = n.g || n.group || 'default';
    if (!groups[g]) {
      groups[g] = [];
      groupOrder.push(g);
    }
    groups[g].push(n);
  }

  const nGroups = groupOrder.length;
  const clusterRadius = Math.max(nGroups * 3, 8);

  groupOrder.forEach((g, gi) => {
    const angle = (gi / nGroups) * Math.PI * 2;
    const cx = clusterRadius * Math.cos(angle);
    const cz = clusterRadius * Math.sin(angle);
    const arr = groups[g];
    const cols = Math.ceil(Math.sqrt(arr.length));
    const spacing = 2.5;

    arr.forEach((n, i) => {
      const row = Math.floor(i / cols);
      const col = i % cols;
      const ox = (col - (cols - 1) / 2) * spacing;
      const oz = (row - (Math.ceil(arr.length / cols) - 1) / 2) * spacing;
      positions.set(n.id, { x: cx + ox, y: 1.0, z: cz + oz });
    });
  });

  return positions;
}

/**
 * Layered layout -- horizontal bands separated by group.
 * Groups are stacked vertically (in z axis), with nodes spread horizontally.
 */
export function layeredLayout(nodes) {
  const positions = new Map();
  const groups = {};
  const groupOrder = [];

  for (const n of nodes) {
    const g = n.g || n.group || 'default';
    if (!groups[g]) {
      groups[g] = [];
      groupOrder.push(g);
    }
    groups[g].push(n);
  }

  const layerSpacing = 6;
  const nodeSpacing = 3;

  groupOrder.forEach((g, gi) => {
    const arr = groups[g];
    const z = (gi - (groupOrder.length - 1) / 2) * layerSpacing;

    arr.forEach((n, i) => {
      const x = (i - (arr.length - 1) / 2) * nodeSpacing;
      positions.set(n.id, { x, y: 1.0, z });
    });
  });

  return positions;
}

// ── LAYOUT DISPATCHER ──

/**
 * Compute positions for any named layout.
 * @param {string} layoutName
 * @param {Array} nodes
 * @param {Array} [edges=[]]
 * @returns {Map<string, {x,y,z}>}
 */
export function computeLayout(layoutName, nodes, edges = []) {
  switch (layoutName) {
    case 'default':
    case 'orbital':
      return defaultLayout(nodes);
    case 'horizontal':
    case 'pipeline':
      return pipelineLayout(nodes);
    case 'vertical':
      return funnelLayout(nodes);
    case 'tree':
      return treeLayout(nodes, edges);
    case 'grid':
      return gridLayout(nodes);
    case 'force':
      return forceLayout(nodes, edges);
    case 'grouped':
      return groupedLayout(nodes);
    case 'layered':
      return layeredLayout(nodes);
    default:
      return defaultLayout(nodes);
  }
}

// ── TRANSITIONS (preserved) ──

/**
 * Smoothly transition icon positions.
 */
export function transitionLayout(icons, positions, duration = 1200) {
  const startPositions = new Map();
  const startTime = performance.now();

  icons.forEach(icon => {
    startPositions.set(icon.id, {
      x: icon.mesh.position.x,
      y: icon.mesh.position.y,
      z: icon.mesh.position.z,
    });
  });

  return new Promise(resolve => {
    function step() {
      const elapsed = performance.now() - startTime;
      const t = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3); // easeOutCubic

      icons.forEach(icon => {
        const start = startPositions.get(icon.id);
        const end = positions.get(icon.id);
        if (!start || !end) return;
        icon.mesh.position.x = start.x + (end.x - start.x) * ease;
        icon.mesh.position.y = start.y + (end.y - start.y) * ease;
        icon.mesh.position.z = start.z + (end.z - start.z) * ease;
      });

      if (t < 1) requestAnimationFrame(step);
      else resolve();
    }
    step();
  });
}

/**
 * Animate camera to a target position.
 */
export function animateCamera(targetPos, targetLookAt, duration = 1500) {
  const startPos = cam.position.clone();
  const startTarget = ctrl.target.clone();
  const startTime = performance.now();
  const endPos = new T.Vector3(targetPos.x, targetPos.y, targetPos.z);
  const endTarget = new T.Vector3(targetLookAt.x, targetLookAt.y, targetLookAt.z);

  return new Promise(resolve => {
    function step() {
      const elapsed = performance.now() - startTime;
      const t = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);

      cam.position.lerpVectors(startPos, endPos, ease);
      ctrl.target.lerpVectors(startTarget, endTarget, ease);
      cam.updateProjectionMatrix();

      if (t < 1) requestAnimationFrame(step);
      else resolve();
    }
    step();
  });
}

// Camera presets per layout
export const CAMERA_PRESETS = {
  default:    { pos: { x: 12, y: 18, z: 12 },  lookAt: { x: 0, y: 0, z: 0 } },
  orbital:    { pos: { x: 12, y: 18, z: 12 },  lookAt: { x: 0, y: 0, z: 0 } },
  horizontal: { pos: { x: 0, y: 20, z: 25 },   lookAt: { x: 0, y: 0, z: 0 } },
  pipeline:   { pos: { x: 0, y: 20, z: 25 },   lookAt: { x: 0, y: 0, z: 0 } },
  vertical:   { pos: { x: 20, y: 15, z: 0 },    lookAt: { x: 0, y: 0, z: 0 } },
  tree:       { pos: { x: 0, y: 25, z: 18 },    lookAt: { x: 0, y: 0, z: 0 } },
  grid:       { pos: { x: 0, y: 20, z: 12 },    lookAt: { x: 0, y: 0, z: 0 } },
  force:      { pos: { x: 12, y: 20, z: 12 },   lookAt: { x: 0, y: 0, z: 0 } },
  grouped:    { pos: { x: 15, y: 22, z: 15 },   lookAt: { x: 0, y: 0, z: 0 } },
  layered:    { pos: { x: 0, y: 20, z: 18 },    lookAt: { x: 0, y: 0, z: 0 } },
};
