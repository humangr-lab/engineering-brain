/* ═══════════════ WP-3: ROUTER — URL hash deep links ═══════════════
   Format: #/layout=orbital&theme=dark&node=auth_service&zoom=1.0
   Parses hash on load to restore state. Subscribes to state changes
   to keep the hash in sync. Handles popstate/hashchange for browser
   back/forward navigation.                                           */

import { state, subscribe, batch } from '../state.js';

const SUPPORTED_PARAMS = ['layout', 'theme', 'node', 'zoom', 'drill'];

let _initialized = false;
let _suppressHashUpdate = false;

/**
 * Initialize the URL hash router.
 * Parses current hash on load, subscribes to state changes, listens
 * for hashchange/popstate events.
 */
export function initRouter() {
  if (_initialized) return;
  _initialized = true;

  // Parse initial hash on page load
  const initial = _parseHash();
  if (Object.keys(initial).length > 0) {
    _applyHashToState(initial);
  }

  // Subscribe to state changes that should update the hash
  subscribe('layout', () => _scheduleHashUpdate());
  subscribe('theme', () => _scheduleHashUpdate());
  subscribe('selectedNode', () => _scheduleHashUpdate());
  subscribe('drillStack', () => _scheduleHashUpdate());

  // Listen for browser back/forward
  window.addEventListener('hashchange', _onHashChange);
  window.addEventListener('popstate', _onHashChange);

  // Set initial hash if empty
  if (!window.location.hash || window.location.hash === '#') {
    _updateHash();
  }
}

/**
 * Get a shareable URL encoding the current view state.
 * @returns {string} Full URL with hash parameters
 */
export function getShareUrl() {
  _updateHash();
  return window.location.href;
}

// ── Hash parsing ──

/**
 * Parse the current URL hash into a parameter object.
 * Format: #/layout=orbital&theme=dark&node=auth_service&zoom=1.0
 * @returns {Object} parsed key-value pairs
 */
function _parseHash() {
  const hash = window.location.hash;
  if (!hash || hash.length < 3) return {};

  // Strip leading #/ or #
  const raw = hash.startsWith('#/') ? hash.slice(2) : hash.slice(1);
  const params = {};

  raw.split('&').forEach(pair => {
    const eqIdx = pair.indexOf('=');
    if (eqIdx === -1) return;
    const key = decodeURIComponent(pair.slice(0, eqIdx));
    const value = decodeURIComponent(pair.slice(eqIdx + 1));
    if (SUPPORTED_PARAMS.includes(key) && value) {
      params[key] = value;
    }
  });

  return params;
}

/**
 * Build a hash string from the current state.
 * @returns {string} e.g. "#/layout=orbital&theme=dark&node=auth_service"
 */
function _buildHash() {
  const parts = [];

  // Layout
  const layout = state.layout || 'default';
  if (layout && layout !== 'default') {
    parts.push('layout=' + encodeURIComponent(layout));
  }

  // Theme
  const theme = state.theme || 'light';
  if (theme && theme !== 'light') {
    parts.push('theme=' + encodeURIComponent(theme));
  }

  // Selected node
  if (state.selectedNode) {
    parts.push('node=' + encodeURIComponent(state.selectedNode));
  }

  // Drill stack (serialized as comma-separated IDs)
  if (state.drillStack && state.drillStack.length > 0) {
    const drillIds = state.drillStack.map(d =>
      typeof d === 'string' ? d : (d.id || d)
    );
    parts.push('drill=' + encodeURIComponent(drillIds.join(',')));
  }

  return parts.length > 0 ? '#/' + parts.join('&') : '#/';
}

// ── State application ──

/**
 * Apply parsed hash parameters to the application state.
 * @param {Object} params - parsed hash parameters
 */
function _applyHashToState(params) {
  _suppressHashUpdate = true;

  const updates = {};

  if (params.layout) {
    updates.layout = params.layout;
  }

  if (params.theme) {
    updates.theme = params.theme;
  }

  if (params.node) {
    updates.selectedNode = params.node;
  }

  if (params.drill) {
    const drillIds = params.drill.split(',').filter(Boolean);
    updates.drillStack = drillIds.map(id => ({ id, label: id, level: 0 }));
  }

  if (Object.keys(updates).length > 0) {
    batch(updates);
  }

  // Allow hash updates again after a tick
  requestAnimationFrame(() => {
    _suppressHashUpdate = false;
  });
}

// ── Hash updating (debounced) ──

let _hashUpdateTimer = null;

function _scheduleHashUpdate() {
  if (_suppressHashUpdate) return;
  if (_hashUpdateTimer) clearTimeout(_hashUpdateTimer);
  _hashUpdateTimer = setTimeout(_updateHash, 100);
}

function _updateHash() {
  if (_suppressHashUpdate) return;

  const newHash = _buildHash();
  const currentHash = window.location.hash || '#/';

  if (newHash !== currentHash) {
    // Use replaceState for routine updates to avoid polluting history
    // Use pushState only for significant navigation changes
    const isSignificant = _isSignificantChange(currentHash, newHash);
    if (isSignificant) {
      history.pushState(null, '', newHash);
    } else {
      history.replaceState(null, '', newHash);
    }
  }
}

/**
 * Determine if a hash change is significant enough to create a history entry.
 * Significant: node selection, drill changes. Not significant: theme, layout.
 */
function _isSignificantChange(oldHash, newHash) {
  const oldParams = _parseHashString(oldHash);
  const newParams = _parseHashString(newHash);

  // Node change or drill change is significant
  if (oldParams.node !== newParams.node) return true;
  if (oldParams.drill !== newParams.drill) return true;

  return false;
}

function _parseHashString(hash) {
  const raw = hash.startsWith('#/') ? hash.slice(2) : hash.slice(1);
  const params = {};
  raw.split('&').forEach(pair => {
    const eqIdx = pair.indexOf('=');
    if (eqIdx > -1) params[pair.slice(0, eqIdx)] = pair.slice(eqIdx + 1);
  });
  return params;
}

// ── Event handlers ──

function _onHashChange() {
  const params = _parseHash();
  if (Object.keys(params).length > 0) {
    _applyHashToState(params);
  }
}
