/* ═══════════════ WP-A11Y: KEYBOARD NAV — Full keyboard navigation for 3D canvas ═══════════════
   Tab into canvas, arrow keys select nearest node, Enter drills, Escape goes up.
   Maintains spatial navigation index by projecting 3D positions to 2D screen space.

   Exports: initKeyboardNav(), selectNode(nodeId), getSelectedNode() */

import { state, subscribe } from '../state.js';
import { cam } from '../scene/engine.js';
import { enterSubmap, exitSubmap } from '../scene/submaps.js';
import { openPanel, closePanel } from '../panels/detail-panel.js';
import { announce } from './aria-manager.js';

/** @type {string|null} Currently keyboard-selected node ID */
let _selectedNodeId = null;

/** @type {HTMLElement|null} The #sc container */
let _container = null;

/** @type {Function|null} Callback for modal opening (set from app.js) */
let _openModalFn = null;

/**
 * Initialize keyboard navigation for the 3D canvas.
 * @param {Object} [options]
 * @param {Function} [options.openModal] - Callback to open modal (nodeId, parentId) => void
 */
export function initKeyboardNav(options = {}) {
  _openModalFn = options.openModal || null;
  _container = document.getElementById('sc');
  if (!_container) return;

  // Make canvas container focusable (also set by aria-manager, but ensure it)
  if (!_container.hasAttribute('tabindex')) {
    _container.setAttribute('tabindex', '0');
  }

  // Focus indicator: canvas border glow when focused
  _container.addEventListener('focus', _onCanvasFocus);
  _container.addEventListener('blur', _onCanvasBlur);

  // Keyboard handler on the container
  _container.addEventListener('keydown', _onKeydown);

  // Sync selection state with external changes
  subscribe('selectedNode', (nodeId) => {
    if (nodeId !== _selectedNodeId) {
      _selectedNodeId = nodeId;
    }
  });

  // Clear selection when exiting submap
  subscribe('inSubmap', (inSubmap) => {
    if (!inSubmap) {
      _selectedNodeId = null;
    }
  });
}

/**
 * Programmatically select a node by ID.
 * @param {string} nodeId
 */
export function selectNode(nodeId) {
  _selectedNodeId = nodeId;
  state.selectedNode = nodeId;

  // Announce to screen readers
  const node = _findNodeData(nodeId);
  if (node) {
    announce(`Selected: ${node.label}, type: ${node.g || 'node'}`);
  }
}

/**
 * Get the currently keyboard-selected node ID.
 * @returns {string|null}
 */
export function getSelectedNode() {
  return _selectedNodeId;
}

// ── Internal ──

function _onCanvasFocus() {
  if (_container) {
    _container.classList.add('a11y-focus');
  }
  // If no node is selected, select the first one
  if (!_selectedNodeId) {
    const nodes = _getVisibleNodes();
    if (nodes.length > 0) {
      selectNode(nodes[0].id);
    }
  }
}

function _onCanvasBlur() {
  if (_container) {
    _container.classList.remove('a11y-focus');
  }
}

/**
 * Main keyboard handler for canvas navigation.
 */
function _onKeydown(e) {
  // Don't intercept when an input/textarea is focused inside canvas (shouldn't happen, but guard)
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

  switch (e.key) {
    case 'ArrowRight':
    case 'ArrowLeft':
    case 'ArrowUp':
    case 'ArrowDown':
      e.preventDefault();
      _navigateSpatial(e.key);
      break;

    case 'Enter':
      e.preventDefault();
      _activateSelected();
      break;

    case ' ':
      e.preventDefault();
      _toggleDetailPanel();
      break;

    case 'Escape':
      e.preventDefault();
      _goBack();
      break;

    case 'Home':
      e.preventDefault();
      _goHome();
      break;

    case 'Tab':
      // Let Tab propagate out of canvas to next focusable element
      // (don't preventDefault)
      break;
  }
}

/**
 * Navigate to the nearest node in the given direction.
 * Projects 3D node positions to 2D screen coordinates, then finds the closest
 * node in the pressed arrow direction.
 */
function _navigateSpatial(key) {
  const nodes = _getVisibleNodes();
  if (nodes.length === 0) return;

  // If nothing selected, select first node
  if (!_selectedNodeId) {
    selectNode(nodes[0].id);
    return;
  }

  const currentNode = nodes.find(n => n.id === _selectedNodeId);
  if (!currentNode) {
    selectNode(nodes[0].id);
    return;
  }

  // Project all nodes to 2D
  const projected = nodes.map(n => ({
    id: n.id,
    node: n,
    ...(_project3Dto2D(n.x || 0, n.y || 0, n.z || 0)),
  }));

  const current = projected.find(p => p.id === _selectedNodeId);
  if (!current) return;

  // Filter candidates by direction
  let candidates;
  switch (key) {
    case 'ArrowRight':
      candidates = projected.filter(p => p.x > current.x + 5 && p.id !== current.id);
      break;
    case 'ArrowLeft':
      candidates = projected.filter(p => p.x < current.x - 5 && p.id !== current.id);
      break;
    case 'ArrowUp':
      candidates = projected.filter(p => p.y < current.y - 5 && p.id !== current.id);
      break;
    case 'ArrowDown':
      candidates = projected.filter(p => p.y > current.y + 5 && p.id !== current.id);
      break;
    default:
      return;
  }

  // If no candidate in strict direction, wrap around to all other nodes
  if (candidates.length === 0) {
    candidates = projected.filter(p => p.id !== current.id);
  }

  if (candidates.length === 0) return;

  // Find nearest by 2D distance, with directional bias
  candidates.sort((a, b) => {
    const da = Math.hypot(a.x - current.x, a.y - current.y);
    const db = Math.hypot(b.x - current.x, b.y - current.y);
    return da - db;
  });

  selectNode(candidates[0].id);
}

/**
 * Project a 3D world position to 2D screen coordinates.
 * @returns {{x: number, y: number}}
 */
function _project3Dto2D(x, y, z) {
  if (!cam) return { x: 0, y: 0 };

  const w = window.innerWidth;
  const h = window.innerHeight;

  // Manual projection using camera matrices
  const mvp = _getProjectionMatrix();
  if (!mvp) return { x: 0, y: 0 };

  // Transform point
  const px = mvp[0] * x + mvp[4] * y + mvp[8] * z + mvp[12];
  const py = mvp[1] * x + mvp[5] * y + mvp[9] * z + mvp[13];
  const pw = mvp[3] * x + mvp[7] * y + mvp[11] * z + mvp[15];

  if (Math.abs(pw) < 0.0001) return { x: 0, y: 0 };

  const ndcX = px / pw;
  const ndcY = py / pw;

  return {
    x: (ndcX + 1) * w * 0.5,
    y: (1 - ndcY) * h * 0.5,
  };
}

/** @type {Float32Array|null} Cached MVP matrix */
let _mvpCache = null;
let _mvpFrame = -1;

function _getProjectionMatrix() {
  // Refresh once per frame
  const frame = performance.now() | 0;
  if (_mvpCache && _mvpFrame === frame) return _mvpCache;

  if (!cam || !cam.projectionMatrix || !cam.matrixWorldInverse) return null;

  // viewProjection = projection * viewInverse
  const proj = cam.projectionMatrix.elements;
  const view = cam.matrixWorldInverse.elements;

  if (!_mvpCache) _mvpCache = new Float32Array(16);

  // 4x4 matrix multiply (column-major)
  for (let i = 0; i < 4; i++) {
    for (let j = 0; j < 4; j++) {
      _mvpCache[j * 4 + i] =
        proj[i] * view[j * 4] +
        proj[i + 4] * view[j * 4 + 1] +
        proj[i + 8] * view[j * 4 + 2] +
        proj[i + 12] * view[j * 4 + 3];
    }
  }

  _mvpFrame = frame;
  return _mvpCache;
}

/**
 * Activate (drill into) the currently selected node.
 */
function _activateSelected() {
  if (!_selectedNodeId) return;

  const id = _selectedNodeId;

  if (state.inSubmap) {
    // In submap: open node modal if it has details
    if (_openModalFn && state.nodeDetails?.[id]) {
      _openModalFn(id, state.currentSubmap);
    }
  } else {
    // Main map: drill into submap if available, otherwise open detail panel
    if (state.submaps?.[id]) {
      enterSubmap(id, state.submaps, state.nodeDetails, _openModalFn);
    } else {
      openPanel(id);
    }
  }
}

/**
 * Toggle detail panel for the selected node.
 */
function _toggleDetailPanel() {
  if (!_selectedNodeId) return;

  const dp = document.getElementById('dp');
  if (dp && dp.classList.contains('open')) {
    closePanel();
  } else {
    openPanel(_selectedNodeId);
  }
}

/**
 * Go back one level: close panel/overlay/exit submap.
 */
function _goBack() {
  // Priority: close detail panel > exit submap > deselect
  const dp = document.getElementById('dp');
  if (dp && dp.classList.contains('open')) {
    closePanel();
    announce('Detail panel closed');
    return;
  }

  if (state.inSubmap) {
    exitSubmap();
    return;
  }

  // Deselect current node
  if (_selectedNodeId) {
    _selectedNodeId = null;
    state.selectedNode = null;
    announce('Node deselected');
  }
}

/**
 * Navigate to root level (L0).
 */
function _goHome() {
  if (state.inSubmap) {
    exitSubmap();
  }

  // Select the first node at root level
  setTimeout(() => {
    const nodes = _getVisibleNodes();
    if (nodes.length > 0) {
      selectNode(nodes[0].id);
    }
  }, state.inSubmap ? 1500 : 100);
}

/**
 * Get the currently visible nodes (main map or submap).
 */
function _getVisibleNodes() {
  if (state.inSubmap && state.currentSubmap) {
    const submap = state.submaps?.[state.currentSubmap];
    return submap?.nodes || [];
  }
  return (state.sysNodes || []).filter(n => !n.hidden);
}

/**
 * Find node data by ID across sysNodes and submap nodes.
 */
function _findNodeData(nodeId) {
  const sysNode = state.sysNodes?.find(n => n.id === nodeId);
  if (sysNode) return sysNode;

  if (state.inSubmap && state.currentSubmap) {
    const submap = state.submaps?.[state.currentSubmap];
    return submap?.nodes?.find(n => n.id === nodeId) || null;
  }

  return null;
}
