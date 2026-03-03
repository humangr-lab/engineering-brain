/* ═══════════════ WP-4: LOD MANAGER — DOI-based visibility + LOD tiers ═══════════════
   ExplorViz distance-based LOD + Furnas DOI formula.

   DOI formula: DOI(x) = API(x) - D(x, focus)
   Where:
     API = a priori importance (LOC-based, complexity, degree centrality)
     D   = weighted tree distance (weights 1, 2, 4, 8 per level crossing)

   LOD tiers:
     DOI > 8.0:  Full detail (3D shape + label + glow)
     DOI 5.0-8.0: Simplified (shape + label, no glow)
     DOI 2.0-5.0: Dot (color dot, no label)
     DOI 0.0-2.0: Sub-pixel dot or hidden
     DOI < 0.0:  Hidden

   Node visibility budget: max N visible nodes based on performance.

   References:
     - docs/research/F-06_fractal_drill_down.md Sections 2, 3, 8.2
     - Furnas, G. W. (1986). "Generalized Fisheye Views"                          */

import { scene } from '../scene/engine.js';
import { state, subscribe } from '../state.js';

/* ── Constants ── */

/** DOI tier boundaries */
const DOI_TIERS = Object.freeze({
  FULL:       8.0,
  SIMPLIFIED: 5.0,
  DOT:        2.0,
  HIDDEN:     0.0,
});

/** Weighted edge distances for tree distance computation */
const LEVEL_WEIGHTS = [1, 2, 4, 8]; // L0->L1=1, L1->L2=2, L2->L3=4, L3->L4=8

/** Maximum visible nodes (performance budget) */
const DEFAULT_LOD_BUDGET = 500;

/* ── Module state ── */

let _focusNodeId = null;
let _focusLevel = 0;
let _nodeDoiMap = new Map();      // nodeId -> {doi, tier, api, distance}
let _nodeMeshMap = new Map();     // nodeId -> Three.js mesh reference
let _parentMap = new Map();       // nodeId -> parentId (containment tree)
let _childrenMap = new Map();     // nodeId -> [childId, ...]
let _depthMap = new Map();        // nodeId -> depth level
let _initialized = false;
let _budget = DEFAULT_LOD_BUDGET;

/* ── Public API ── */

/**
 * Initialize the LOD manager. Builds the containment tree from graph data.
 * Call once during boot after state.sysNodes and state.sysEdges are populated.
 */
export function initLODManager() {
  _buildContainmentTree();
  _computeAPI();
  _initialized = true;

  // Read budget from state if set
  _budget = state.lodBudget || DEFAULT_LOD_BUDGET;

  // Subscribe to budget changes
  subscribe('lodBudget', (val) => {
    _budget = val || DEFAULT_LOD_BUDGET;
    if (_focusNodeId != null) _applyLOD();
  });

  console.log('[WP-4] LODManager initialized, nodes:', _nodeDoiMap.size);
}

/**
 * Update the focus point. Recalculates DOI for all nodes and applies LOD.
 * Called when the user drills into/out of a node.
 * @param {string|null} nodeId - The focused node ID (null = system overview)
 */
export function updateFocus(nodeId) {
  _focusNodeId = nodeId;
  _focusLevel = _depthMap.get(nodeId) || 0;

  // Recalculate DOI for all tracked nodes
  for (const [nid, entry] of _nodeDoiMap) {
    const distance = _computeDistance(nid, nodeId);
    const doi = entry.api - distance;
    entry.distance = distance;
    entry.doi = doi;
    entry.tier = _doiToTier(doi);
  }

  // Apply LOD (visibility/opacity/scale) to scene objects
  _applyLOD();

  // Store visible nodes in state
  const visibleNodes = [];
  for (const [nid, entry] of _nodeDoiMap) {
    if (entry.tier !== 'hidden') visibleNodes.push(nid);
  }
  state.visibleNodes = visibleNodes;
}

/**
 * Get the LOD info for a specific node.
 * @param {string} nodeId
 * @returns {{ doi: number, tier: string, api: number, distance: number } | null}
 */
export function getNodeLOD(nodeId) {
  return _nodeDoiMap.get(nodeId) || null;
}

/**
 * Register a Three.js mesh for LOD management.
 * @param {string} nodeId
 * @param {THREE.Object3D} mesh
 */
export function registerNodeMesh(nodeId, mesh) {
  _nodeMeshMap.set(nodeId, mesh);
}

/**
 * Unregister a mesh from LOD management.
 * @param {string} nodeId
 */
export function unregisterNodeMesh(nodeId) {
  _nodeMeshMap.delete(nodeId);
}

/**
 * Get all nodes sorted by DOI (highest first), limited to budget.
 * @returns {Array<{id, doi, tier}>}
 */
export function getVisibleNodesByDOI() {
  const entries = [];
  for (const [id, entry] of _nodeDoiMap) {
    entries.push({ id, doi: entry.doi, tier: entry.tier });
  }
  entries.sort((a, b) => b.doi - a.doi);
  return entries.slice(0, _budget);
}

/* ── Internal: Build containment tree ── */

function _buildContainmentTree() {
  const nodes = state.sysNodes || [];
  const edges = state.sysEdges || [];
  const submaps = state.submaps || {};

  _parentMap.clear();
  _childrenMap.clear();
  _depthMap.clear();
  _nodeDoiMap.clear();

  // Initialize all nodes at depth 0
  for (const node of nodes) {
    _childrenMap.set(node.id, []);
    _depthMap.set(node.id, 0);
    _nodeDoiMap.set(node.id, { doi: 0, tier: 'full', api: 0, distance: 0 });
  }

  // Build parent-child from CONTAINS edges
  for (const edge of edges) {
    const from = edge.f || edge.from;
    const to = edge.t || edge.to;
    if (edge.type === 'CONTAINS' || edge.c === 'white') {
      _parentMap.set(to, from);
      if (!_childrenMap.has(from)) _childrenMap.set(from, []);
      _childrenMap.get(from).push(to);
    }
  }

  // Build from submap data
  for (const [parentId, smData] of Object.entries(submaps)) {
    const children = smData.nodes || [];
    for (const child of children) {
      const childId = child.id || child;
      _parentMap.set(childId, parentId);
      if (!_childrenMap.has(parentId)) _childrenMap.set(parentId, []);
      _childrenMap.get(parentId).push(childId);

      // Add submap children to tracking
      if (!_nodeDoiMap.has(childId)) {
        _nodeDoiMap.set(childId, { doi: 0, tier: 'full', api: 0, distance: 0 });
      }
      _depthMap.set(childId, (_depthMap.get(parentId) || 0) + 1);
    }
  }

  // Compute depths via BFS from roots
  const roots = [];
  for (const node of nodes) {
    if (!_parentMap.has(node.id)) roots.push(node.id);
  }

  const queue = roots.map(id => [id, 0]);
  while (queue.length > 0) {
    const [nodeId, depth] = queue.shift();
    _depthMap.set(nodeId, depth);
    const children = _childrenMap.get(nodeId) || [];
    for (const childId of children) {
      queue.push([childId, depth + 1]);
    }
  }
}

/* ── Internal: Compute API (a priori importance) ── */

function _computeAPI() {
  const nodes = state.sysNodes || [];
  const edges = state.sysEdges || [];
  const submaps = state.submaps || {};
  const nodeDetails = state.nodeDetails || {};

  // Degree centrality map
  const degreeMap = new Map();
  for (const edge of edges) {
    const from = edge.f || edge.from;
    const to = edge.t || edge.to;
    degreeMap.set(from, (degreeMap.get(from) || 0) + 1);
    degreeMap.set(to, (degreeMap.get(to) || 0) + 1);
  }

  for (const [nodeId, entry] of _nodeDoiMap) {
    const depth = _depthMap.get(nodeId) || 0;
    const degree = degreeMap.get(nodeId) || 0;
    const childCount = (_childrenMap.get(nodeId) || []).length;

    // API heuristic (from research doc Section 3):
    // L0: log(total_LOC) + edge_count * 0.1
    // General: log(childCount + 1) + degree * 0.1 + (is_hero ? 3 : 0)
    const node = nodes.find(n => n.id === nodeId);
    const isHero = node?.hero || false;
    const loc = node?._inferredSize || 1;

    let api = Math.log2(Math.max(loc, 1)) + degree * 0.1 + childCount * 0.3;
    if (isHero) api += 3;
    if (submaps[nodeId]) api += 2; // Has submap = important

    // Clamp to [0, 10]
    entry.api = Math.min(10, Math.max(0, api));
  }
}

/* ── Internal: Compute distance ── */

/**
 * Compute weighted tree distance between two nodes.
 * Uses shortest path in the containment tree.
 */
function _computeDistance(nodeId, focusId) {
  if (!focusId || nodeId === focusId) return 0;

  // Find path from nodeId to root
  const pathA = _pathToRoot(nodeId);
  const pathB = _pathToRoot(focusId);

  // Find LCA (lowest common ancestor)
  const setA = new Set(pathA);
  let lca = null;
  for (const id of pathB) {
    if (setA.has(id)) { lca = id; break; }
  }

  if (!lca) {
    // Disconnected: return max distance
    return 20;
  }

  // Compute weighted distance: sum of level weights along path
  const depthLCA = _depthMap.get(lca) || 0;
  const depthA = _depthMap.get(nodeId) || 0;
  const depthB = _depthMap.get(focusId) || 0;

  let distance = 0;

  // Distance from nodeId up to LCA
  for (let d = depthA; d > depthLCA; d--) {
    const weight = LEVEL_WEIGHTS[Math.min(d - 1, LEVEL_WEIGHTS.length - 1)];
    distance += weight;
  }

  // Distance from focusId up to LCA
  for (let d = depthB; d > depthLCA; d--) {
    const weight = LEVEL_WEIGHTS[Math.min(d - 1, LEVEL_WEIGHTS.length - 1)];
    distance += weight;
  }

  return distance;
}

function _pathToRoot(nodeId) {
  const path = [nodeId];
  let current = nodeId;
  const visited = new Set();

  while (_parentMap.has(current) && !visited.has(current)) {
    visited.add(current);
    current = _parentMap.get(current);
    path.push(current);
  }

  return path;
}

/* ── Internal: DOI to tier mapping ── */

function _doiToTier(doi) {
  if (doi >= DOI_TIERS.FULL) return 'full';
  if (doi >= DOI_TIERS.SIMPLIFIED) return 'simplified';
  if (doi >= DOI_TIERS.DOT) return 'dot';
  if (doi >= DOI_TIERS.HIDDEN) return 'subpixel';
  return 'hidden';
}

/* ── Internal: Apply LOD to scene objects ── */

function _applyLOD() {
  // Sort by DOI, enforce budget
  const sorted = [];
  for (const [nodeId, entry] of _nodeDoiMap) {
    sorted.push({ id: nodeId, ...entry });
  }
  sorted.sort((a, b) => b.doi - a.doi);

  let visibleCount = 0;

  for (const entry of sorted) {
    const mesh = _nodeMeshMap.get(entry.id);
    if (!mesh) continue;

    const overBudget = visibleCount >= _budget;

    if (overBudget || entry.tier === 'hidden') {
      // Hide node
      mesh.visible = false;
    } else if (entry.tier === 'subpixel') {
      // Sub-pixel: barely visible
      mesh.visible = true;
      mesh.scale.setScalar(0.1);
      _setMeshOpacity(mesh, 0.1);
      visibleCount++;
    } else if (entry.tier === 'dot') {
      // Dot: small, no label
      mesh.visible = true;
      mesh.scale.setScalar(0.3);
      _setMeshOpacity(mesh, 0.4);
      _hideLabels(mesh);
      visibleCount++;
    } else if (entry.tier === 'simplified') {
      // Simplified: shape + label, no glow
      mesh.visible = true;
      mesh.scale.setScalar(0.7);
      _setMeshOpacity(mesh, 0.8);
      _showLabels(mesh);
      visibleCount++;
    } else {
      // Full detail
      mesh.visible = true;
      mesh.scale.setScalar(1.0);
      _setMeshOpacity(mesh, 1.0);
      _showLabels(mesh);
      visibleCount++;
    }
  }
}

function _setMeshOpacity(mesh, opacity) {
  mesh.traverse(child => {
    if (child.material) {
      const materials = Array.isArray(child.material) ? child.material : [child.material];
      for (const mat of materials) {
        if (mat.transparent !== undefined) {
          mat.transparent = opacity < 1;
          mat.opacity = opacity;
        }
      }
    }
  });
}

function _hideLabels(mesh) {
  mesh.traverse(child => {
    if (child.element instanceof HTMLElement) {
      child.visible = false;
    }
  });
}

function _showLabels(mesh) {
  mesh.traverse(child => {
    if (child.element instanceof HTMLElement) {
      child.visible = true;
    }
  });
}
