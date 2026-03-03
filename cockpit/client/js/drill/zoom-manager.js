/* ═══════════════ WP-4: ZOOM MANAGER — 5-level FSM for fractal drill-down ═══════════════
   FSM States: SYSTEM(L0) -> MODULE(L1) -> FILE(L2) -> FUNCTION(L3) -> CODE(L4)

   Transitions:
     - drillInto(nodeId): L0->L1->L2->L3 (distance-based or double-click)
     - drillOut(): reverse, one level up
     - jumpTo(level, nodeId): direct jump (breadcrumb click)
     - edit(): L3->L4 (explicit "Edit" button only)
     - closeEditor(): L4->L3

   Distance thresholds with hysteresis (ExplorViz pattern):
     L0->L1: < 40 units (hysteresis 8)
     L1->L2: < 15 units (hysteresis 3)
     L2->L3: < 5 units  (hysteresis 1)
     L3->L4: explicit only (no distance trigger)

   References:
     - docs/research/F-06_fractal_drill_down.md Sections 2, 8.1
     - docs/design/wireframes.md Screen 2                                           */

import { state, subscribe, batch } from '../state.js';
import { cam, ctrl } from '../scene/engine.js';
import { transitionCamera, flyToNode } from './camera-transitions.js';
import { renderLevel, exitLevel } from './level-renderers.js';
import { updateFocus } from './lod-manager.js';
import { getCache } from './data-cache.js';

/* ── Constants ── */

export const LEVELS = Object.freeze({
  SYSTEM:   0,
  MODULE:   1,
  FILE:     2,
  FUNCTION: 3,
  CODE:     4,
});

const LEVEL_NAMES = ['System', 'Module', 'File', 'Function', 'Code'];

/**
 * Distance thresholds for automatic drill transitions (ExplorViz pattern).
 * Each entry: [threshold, hysteresis].
 * When camera distance < threshold, drill in.
 * When camera distance > threshold + hysteresis, drill out.
 */
const DISTANCE_THRESHOLDS = [
  [40, 8],  // L0->L1
  [15, 3],  // L1->L2
  [5,  1],  // L2->L3
  // L3->L4 is explicit only
];

/* ── FSM State ── */

let _currentLevel = LEVELS.SYSTEM;
let _drillStack = [];           // [{id, label, level, nodeData}]
let _transitioning = false;     // Lock during camera animation
let _distanceCheckEnabled = false;
let _lastDistanceCheck = 0;
const _DISTANCE_CHECK_INTERVAL = 200; // ms between distance checks

/* ── Subscribers ── */

const _subscribers = new Set();

function _notify(event, data) {
  for (const cb of _subscribers) {
    try { cb(event, data); } catch (e) { console.warn('[ZoomManager] Subscriber error:', e); }
  }
}

/**
 * Subscribe to zoom manager events.
 * Events: 'levelChange', 'drillIn', 'drillOut', 'transitionStart', 'transitionEnd'
 * @param {Function} callback - (event, data) => void
 * @returns {Function} unsubscribe
 */
export function onZoomEvent(callback) {
  _subscribers.add(callback);
  return () => _subscribers.delete(callback);
}

/* ── Public API ── */

/**
 * Initialize the zoom manager. Wire into render loop for distance-based transitions.
 * Call once during boot after the Three.js engine is ready.
 */
export function initZoomManager() {
  _currentLevel = LEVELS.SYSTEM;
  _drillStack = [];
  _transitioning = false;

  // Sync state
  _syncState();

  // Enable distance-based checking after first render settles
  setTimeout(() => { _distanceCheckEnabled = true; }, 1000);

  console.log('[WP-4] ZoomManager initialized');
}

/**
 * Called every animation frame to check camera distance for auto-transitions.
 * Throttled internally to avoid per-frame computation.
 */
export function tickZoomManager() {
  if (!_distanceCheckEnabled || _transitioning) return;

  const now = performance.now();
  if (now - _lastDistanceCheck < _DISTANCE_CHECK_INTERVAL) return;
  _lastDistanceCheck = now;

  _checkDistanceThresholds();
}

/**
 * Drill into a child node. Transitions from current level to current+1.
 * @param {string} nodeId - ID of the node to drill into
 * @param {object} [nodeData] - Optional node data (label, children, source_location, etc.)
 * @returns {Promise<boolean>} true if transition succeeded
 */
export async function drillInto(nodeId, nodeData) {
  if (_transitioning) return false;
  if (_currentLevel >= LEVELS.FUNCTION) return false; // L3->L4 uses edit()

  const nextLevel = _currentLevel + 1;
  const data = nodeData || _resolveNodeData(nodeId);
  if (!data) {
    console.warn(`[WP-4] drillInto: no data for node "${nodeId}"`);
    return false;
  }

  // Check if node has children at next level (for L0-L2)
  if (nextLevel <= LEVELS.FILE && !_hasChildren(nodeId, data)) {
    console.warn(`[WP-4] drillInto: node "${nodeId}" has no children for L${nextLevel}`);
    return false;
  }

  _transitioning = true;
  _notify('transitionStart', { from: _currentLevel, to: nextLevel, nodeId });

  // Push onto drill stack
  const stackEntry = {
    id: nodeId,
    label: data.label || data.title || nodeId,
    level: nextLevel,
    nodeData: data,
  };
  _drillStack.push(stackEntry);

  // Exit current level rendering
  exitLevel(_currentLevel);

  // Camera transition
  await flyToNode(nodeId, nextLevel, data);

  // Enter new level rendering
  _currentLevel = nextLevel;
  renderLevel(_currentLevel, data);

  // Update LOD focus
  updateFocus(nodeId);

  // Sync state store
  _syncState();

  _transitioning = false;
  _notify('drillIn', { level: _currentLevel, nodeId, data });
  _notify('transitionEnd', { level: _currentLevel });
  _notify('levelChange', { level: _currentLevel, stack: [..._drillStack] });

  return true;
}

/**
 * Drill out one level. Transitions from current level to current-1.
 * @returns {Promise<boolean>} true if transition succeeded
 */
export async function drillOut() {
  if (_transitioning) return false;
  if (_currentLevel <= LEVELS.SYSTEM) return false;

  // If in CODE mode (L4), use closeEditor path
  if (_currentLevel === LEVELS.CODE) {
    return closeEditor();
  }

  const prevLevel = _currentLevel - 1;
  _transitioning = true;
  _notify('transitionStart', { from: _currentLevel, to: prevLevel });

  // Exit current level rendering
  exitLevel(_currentLevel);

  // Pop from drill stack
  const popped = _drillStack.pop();

  // Determine parent node for camera target
  const parentEntry = _drillStack[_drillStack.length - 1] || null;
  const parentId = parentEntry?.id || null;

  // Camera transition back
  await flyToNode(parentId, prevLevel, parentEntry?.nodeData || null);

  // Enter previous level rendering
  _currentLevel = prevLevel;
  if (parentEntry) {
    renderLevel(_currentLevel, parentEntry.nodeData);
  }

  // Update LOD focus
  updateFocus(parentId);

  // Sync state store
  _syncState();

  _transitioning = false;
  _notify('drillOut', { level: _currentLevel, poppedId: popped?.id });
  _notify('transitionEnd', { level: _currentLevel });
  _notify('levelChange', { level: _currentLevel, stack: [..._drillStack] });

  return true;
}

/**
 * Jump directly to a specific level (e.g., breadcrumb click).
 * Drills out repeatedly until the target level is reached.
 * @param {number} level - Target level (0-4)
 * @param {string} [nodeId] - Optional node ID at target level
 * @returns {Promise<boolean>}
 */
export async function jumpTo(level, nodeId) {
  if (_transitioning) return false;
  if (level < LEVELS.SYSTEM || level > LEVELS.CODE) return false;
  if (level === _currentLevel) return true;

  // Drilling out to a lower level
  if (level < _currentLevel) {
    _transitioning = true;
    _notify('transitionStart', { from: _currentLevel, to: level });

    // Exit current level
    exitLevel(_currentLevel);

    // Trim drill stack to target level
    while (_drillStack.length > level) {
      _drillStack.pop();
    }

    // Determine target node
    const targetEntry = _drillStack[_drillStack.length - 1] || null;
    const targetId = targetEntry?.id || nodeId || null;

    // Camera transition
    await flyToNode(targetId, level, targetEntry?.nodeData || null);

    // Enter target level rendering
    _currentLevel = level;
    if (targetEntry) {
      renderLevel(_currentLevel, targetEntry.nodeData);
    }

    // Update LOD focus
    updateFocus(targetId);

    // Sync state store
    _syncState();

    _transitioning = false;
    _notify('transitionEnd', { level: _currentLevel });
    _notify('levelChange', { level: _currentLevel, stack: [..._drillStack] });
    return true;
  }

  // Drilling in requires intermediate steps (not supported as direct jump)
  console.warn(`[WP-4] jumpTo: cannot jump forward from L${_currentLevel} to L${level}`);
  return false;
}

/**
 * Enter edit mode (L3 -> L4). Triggered by explicit "Edit" button only.
 * Loads CodeMirror 6 lazily.
 * @returns {Promise<boolean>}
 */
export async function edit() {
  if (_transitioning) return false;
  if (_currentLevel !== LEVELS.FUNCTION) {
    console.warn('[WP-4] edit(): can only enter edit mode from L3 (FUNCTION)');
    return false;
  }

  _transitioning = true;
  const prevLevel = _currentLevel;
  _notify('transitionStart', { from: prevLevel, to: LEVELS.CODE });

  // The current function's data
  const currentEntry = _drillStack[_drillStack.length - 1];

  // Push a CODE-level entry onto the stack
  _drillStack.push({
    id: currentEntry?.id || 'code',
    label: currentEntry?.label || 'Code',
    level: LEVELS.CODE,
    nodeData: currentEntry?.nodeData || null,
  });

  // Exit L3 rendering, enter L4 rendering
  exitLevel(LEVELS.FUNCTION);
  _currentLevel = LEVELS.CODE;
  renderLevel(LEVELS.CODE, currentEntry?.nodeData || null);

  // Sync state store
  _syncState();

  _transitioning = false;
  _notify('drillIn', { level: _currentLevel, nodeId: currentEntry?.id });
  _notify('transitionEnd', { level: _currentLevel });
  _notify('levelChange', { level: _currentLevel, stack: [..._drillStack] });

  return true;
}

/**
 * Close editor (L4 -> L3). Triggered by Escape or breadcrumb.
 * @returns {Promise<boolean>}
 */
export async function closeEditor() {
  if (_transitioning) return false;
  if (_currentLevel !== LEVELS.CODE) return false;

  _transitioning = true;
  _notify('transitionStart', { from: LEVELS.CODE, to: LEVELS.FUNCTION });

  // Exit L4 rendering
  exitLevel(LEVELS.CODE);

  // Pop CODE entry from stack
  _drillStack.pop();

  // Re-enter L3 rendering
  _currentLevel = LEVELS.FUNCTION;
  const currentEntry = _drillStack[_drillStack.length - 1];
  if (currentEntry) {
    renderLevel(LEVELS.FUNCTION, currentEntry.nodeData);
  }

  // Sync state
  _syncState();

  _transitioning = false;
  _notify('drillOut', { level: _currentLevel });
  _notify('transitionEnd', { level: _currentLevel });
  _notify('levelChange', { level: _currentLevel, stack: [..._drillStack] });

  return true;
}

/**
 * Get the current drill level.
 * @returns {number} 0-4
 */
export function getCurrentLevel() {
  return _currentLevel;
}

/**
 * Get the current drill stack (copy).
 * @returns {Array<{id, label, level}>}
 */
export function getDrillStack() {
  return _drillStack.map(e => ({ id: e.id, label: e.label, level: e.level }));
}

/**
 * Check if the zoom manager is currently transitioning.
 * @returns {boolean}
 */
export function isTransitioning() {
  return _transitioning;
}

/**
 * Get the human-readable name for a level number.
 * @param {number} level
 * @returns {string}
 */
export function getLevelName(level) {
  return LEVEL_NAMES[level] || 'Unknown';
}

/* ── Distance-based auto-transitions ── */

function _checkDistanceThresholds() {
  if (_currentLevel >= LEVELS.FUNCTION) return; // L3+ has no distance triggers

  const focusEntry = _drillStack[_drillStack.length - 1];
  if (!focusEntry && _currentLevel > LEVELS.SYSTEM) return;

  // Get the focus point (current drill target or origin)
  const focusPos = _getFocusPosition(focusEntry);
  if (!focusPos) return;

  const camPos = cam.position;
  const distance = Math.sqrt(
    (camPos.x - focusPos.x) ** 2 +
    (camPos.y - focusPos.y) ** 2 +
    (camPos.z - focusPos.z) ** 2
  );

  // Check drill-in threshold for current level
  if (_currentLevel < LEVELS.FUNCTION) {
    const [threshold] = DISTANCE_THRESHOLDS[_currentLevel] || [];
    if (threshold && distance < threshold) {
      // Find the nearest node at the next level to drill into
      const nearestChild = _findNearestChild(_currentLevel);
      if (nearestChild) {
        drillInto(nearestChild.id, nearestChild);
      }
    }
  }

  // Check drill-out threshold (only if we've drilled in)
  if (_currentLevel > LEVELS.SYSTEM) {
    const [threshold, hysteresis] = DISTANCE_THRESHOLDS[_currentLevel - 1] || [];
    if (threshold && hysteresis && distance > threshold + hysteresis) {
      drillOut();
    }
  }
}

/* ── Internal helpers ── */

function _resolveNodeData(nodeId) {
  // Try submap data first
  if (state.submaps && state.submaps[nodeId]) {
    const sm = state.submaps[nodeId];
    return {
      id: nodeId,
      label: sm.title || nodeId,
      children: sm.nodes || [],
      edges: sm.edges || [],
      color: sm.color,
      ...sm,
    };
  }

  // Try graph data nodes
  const graphNode = (state.sysNodes || []).find(n => n.id === nodeId);
  if (graphNode) {
    return {
      id: nodeId,
      label: graphNode.label || nodeId,
      ...graphNode,
    };
  }

  // Try node details
  if (state.nodeDetails && state.nodeDetails[nodeId]) {
    return {
      id: nodeId,
      label: state.nodeDetails[nodeId].t || nodeId,
      ...state.nodeDetails[nodeId],
    };
  }

  return null;
}

function _hasChildren(nodeId, data) {
  // Submap has explicit children
  if (data.children && data.children.length > 0) return true;
  if (data.nodes && data.nodes.length > 0) return true;

  // Check if there are CONTAINS edges to this node
  const edges = state.sysEdges || [];
  const hasContains = edges.some(e => {
    const from = e.f || e.from;
    return from === nodeId && (e.type === 'CONTAINS' || e.c === 'white');
  });
  return hasContains;
}

function _getFocusPosition(entry) {
  if (!entry) {
    return { x: 0, y: 0, z: 0 }; // Origin for L0
  }

  // Try to find position from sys nodes
  const node = (state.sysNodes || []).find(n => n.id === entry.id);
  if (node && node.x != null && node.z != null) {
    return { x: node.x, y: node.y || 1, z: node.z };
  }

  // Use ctrl.target as fallback
  return { x: ctrl.target.x, y: ctrl.target.y, z: ctrl.target.z };
}

function _findNearestChild(currentLevel) {
  // For auto-drill, find the node nearest to the camera gaze direction
  // This is a simplified implementation -- returns first available child
  const focusEntry = _drillStack[_drillStack.length - 1];

  if (currentLevel === LEVELS.SYSTEM) {
    // At L0: find system nodes with submaps
    const nodesWithSubmaps = (state.sysNodes || []).filter(n => state.submaps && state.submaps[n.id]);
    if (!nodesWithSubmaps.length) return null;

    // Find nearest to camera gaze
    return _nearestToCamera(nodesWithSubmaps);
  }

  // For deeper levels, return null (distance auto-drill only supports L0->L1 for now)
  return null;
}

function _nearestToCamera(nodes) {
  const target = ctrl.target;
  let nearest = null;
  let minDist = Infinity;

  for (const n of nodes) {
    if (n.x == null || n.z == null) continue;
    const dx = (n.x || 0) - target.x;
    const dz = (n.z || 0) - target.z;
    const dist = dx * dx + dz * dz;
    if (dist < minDist) {
      minDist = dist;
      nearest = n;
    }
  }

  return nearest;
}

function _syncState() {
  batch({
    drillLevel: _currentLevel,
    drillStack: _drillStack.map(e => ({ id: e.id, label: e.label, level: e.level })),
    breadcrumb: _drillStack.map(e => ({ id: e.id, label: e.label, level: e.level })),
  });
}
