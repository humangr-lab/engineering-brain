/* ═══════════════ CONFIG ═══════════════
   API URL, theme defaults, feature flags.
   Everything configurable in one place. */

// Auto-detect: if data/graph.json exists, use static mode
const _isStatic = document.querySelector('meta[name="cockpit-static"]')?.content === 'true';

export const CONFIG = {
  API_BASE: _isStatic ? '' : (window.COCKPIT_API || 'http://localhost:8420'),
  STATIC_GRAPH_URL: './data/graph.json',
  IS_STATIC: _isStatic,

  // Schema-driven loader
  SCHEMA_URL: _getParam('schema') || '',
  COCKPIT_SCHEMA_URL: _getParam('cockpit_schema') || '',
  GRAPH_DATA_URL: _getParam('graph') || '',
  ENABLE_INFERENCE_LOG: _getParam('inference_log') === 'true',

  // SSE
  SSE_ENABLED: true,
  SSE_POLL_FALLBACK_MS: 5000,

  // Defaults
  DEFAULT_THEME: 'light',
  DEFAULT_LAYOUT: 'default',
  DEFAULT_PAGE_SIZE: 500,

  // Three.js
  BLOOM_STRENGTH: 0.25,
  BLOOM_RADIUS: 0.3,
  BLOOM_THRESHOLD: 0.92,
  ORTHO_FRUSTUM: 14,

  // ═══ WP-PERF: Performance thresholds ═══
  INSTANCED_THRESHOLD: 100,  // Node count above which InstancedMesh is used
};

function _getParam(name) {
  try {
    return new URLSearchParams(window.location.search).get(name) || '';
  } catch { return ''; }
}

export const FEATURES = {
  FORCE_GRAPH: true,
  SSE_REALTIME: true,
  TOUR: true,
  DUAL_LAYOUT: true,
  SEARCH: true,
  DOC_MAP: true,
  KLIB: true,
};
