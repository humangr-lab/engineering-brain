/* ═══════════════ REACTIVE STATE STORE ═══════════════
   Proxy-based reactive state. Modules subscribe to slices.
   ~50 lines, no library needed, sufficient for view-only app. */

const _listeners = new Map();

function _createReactiveStore(initial) {
  return new Proxy(initial, {
    set(target, key, value) {
      const old = target[key];
      target[key] = value;
      if (old !== value) {
        const cbs = _listeners.get(key);
        if (cbs) cbs.forEach(cb => cb(value, old, key));
        // Wildcard listeners
        const wcbs = _listeners.get('*');
        if (wcbs) wcbs.forEach(cb => cb(value, old, key));
      }
      return true;
    },
  });
}

export const state = _createReactiveStore({
  // Graph data (from API or static)
  nodes: [],
  edges: [],
  stats: {},
  version: 0,

  // Architecture map data (static — the 25 system nodes)
  sysNodes: [],
  sysEdges: [],
  sysDetails: {},
  submaps: {},
  nodeDetails: {},
  docTree: [],
  klibData: {},

  // Schema-driven loader state
  graphData: null,
  cockpitSchema: null,
  inferredConfig: null,
  drillLevel: 0,
  drillStack: [],
  breadcrumb: [],

  // UI state
  theme: 'light',
  selectedNode: null,
  hoveredNode: null,
  klibOpen: false,
  klibSelectedNode: null,
  klibGroupBy: 'layer',
  klibViewMode: 'list',
  klibFilters: { layers: [], severities: [], tags: [], confidence: 0, search: '' },
  layout: 'default',
  searchOpen: false,

  // ═══ WP-3: Search State ═══
  searchOverlayOpen: false,
  searchFilters: { type: 'all' },
  searchResults: [],

  inSubmap: false,
  currentSubmap: null,
  tourActive: false,
  tourStep: 0,
  docOverlayOpen: false,
  viewMode: '3d',

  // ═══ WP-4: Drill State ═══
  drillFocus: null,              // Currently focused node ID for DOI computation
  visibleNodes: [],              // Node IDs visible after LOD filtering
  lodBudget: 500,                // Max visible nodes (performance budget)

  // ═══ WP-6: Agent State ═══
  agentOpen: false,              // Chat panel open/closed
  agentMessages: [],             // Message history for display
  agentProvider: null,           // Current LLM provider ('anthropic' | 'openai')
  agentHighlightedNodes: [],     // Currently highlighted node IDs by agent
});

/**
 * Subscribe to state changes.
 * @param {string} key - State key to watch, or '*' for all changes
 * @param {Function} callback - (newValue, oldValue, key) => void
 * @returns {Function} unsubscribe function
 */
export function subscribe(key, callback) {
  if (!_listeners.has(key)) _listeners.set(key, new Set());
  _listeners.get(key).add(callback);
  return () => _listeners.get(key).delete(callback);
}

/**
 * Batch-update multiple state keys without triggering intermediate renders.
 */
export function batch(updates) {
  Object.assign(state, updates);
}
