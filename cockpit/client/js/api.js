/* ═══════════════ API CLIENT ═══════════════
   fetch wrapper, SSE client, retry logic.
   Connects to FastAPI server or loads static graph.json. */

import { CONFIG, FEATURES } from './config.js';
import { state, batch } from './state.js';

let _eventSource = null;
let _pollTimer = null;

/**
 * Fetch full graph from API or static file.
 * @returns {Promise<Object>} {version, stats, nodes, edges}
 */
export async function fetchGraph() {
  if (CONFIG.IS_STATIC) {
    const res = await fetch(CONFIG.STATIC_GRAPH_URL);
    if (!res.ok) throw new Error(`Static graph load failed: ${res.status}`);
    return res.json();
  }
  const res = await fetch(`${CONFIG.API_BASE}/api/graph`);
  if (!res.ok) throw new Error(`API graph load failed: ${res.status}`);
  return res.json();
}

/**
 * Fetch single node by ID.
 */
export async function fetchNode(id) {
  if (CONFIG.IS_STATIC) return state.nodes.find(n => n.id === id) || null;
  const res = await fetch(`${CONFIG.API_BASE}/api/nodes/${encodeURIComponent(id)}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API node fetch failed: ${res.status}`);
  return res.json();
}

/**
 * Fetch filtered nodes list.
 */
export async function fetchNodes(params = {}) {
  if (CONFIG.IS_STATIC) {
    // Client-side filtering from state
    let nodes = [...state.nodes];
    if (params.layer !== undefined) nodes = nodes.filter(n => n.layer === params.layer);
    if (params.severity) nodes = nodes.filter(n => n.severity?.toLowerCase() === params.severity.toLowerCase());
    if (params.q) {
      const q = params.q.toLowerCase();
      nodes = nodes.filter(n => `${n.id} ${n.text}`.toLowerCase().includes(q));
    }
    const offset = params.offset || 0;
    const limit = params.limit || 500;
    return nodes.slice(offset, offset + limit);
  }
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v != null) qs.set(k, v); });
  const res = await fetch(`${CONFIG.API_BASE}/api/nodes?${qs}`);
  if (!res.ok) throw new Error(`API nodes fetch failed: ${res.status}`);
  return res.json();
}

/**
 * Fetch stats.
 */
export async function fetchStats() {
  if (CONFIG.IS_STATIC) return state.stats;
  const res = await fetch(`${CONFIG.API_BASE}/api/stats`);
  if (!res.ok) throw new Error(`API stats fetch failed: ${res.status}`);
  return res.json();
}

/**
 * Connect SSE stream for real-time version updates.
 */
export function connectSSE(onUpdate) {
  if (CONFIG.IS_STATIC || !FEATURES.SSE_REALTIME) return;

  try {
    _eventSource = new EventSource(`${CONFIG.API_BASE}/api/stream`);
    _eventSource.addEventListener('version', (e) => {
      const data = JSON.parse(e.data);
      if (data.version !== state.version) {
        onUpdate(data);
      }
    });
    _eventSource.onerror = () => {
      // Fallback to polling
      _eventSource.close();
      _eventSource = null;
      _startPolling(onUpdate);
    };
  } catch {
    _startPolling(onUpdate);
  }
}

function _startPolling(onUpdate) {
  if (_pollTimer) return;
  _pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`${CONFIG.API_BASE}/api/graph/version`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.version !== state.version) {
        onUpdate(data);
      }
    } catch { /* ignore polling errors */ }
  }, CONFIG.SSE_POLL_FALLBACK_MS);
}

/**
 * Full connect flow: fetch initial graph + establish SSE.
 * @returns {Promise<Object>} initial graph data
 */
export async function connectAPI() {
  // Try API first, fall back to static
  let graph;
  try {
    graph = await fetchGraph();
  } catch {
    // Try static file as fallback
    try {
      const res = await fetch('./data/graph.json');
      if (res.ok) graph = await res.json();
    } catch { /* no fallback available */ }
  }

  if (graph) {
    batch({
      nodes: graph.nodes || [],
      edges: graph.edges || [],
      stats: graph.stats || {},
      version: graph.version || 0,
    });
  }

  // Connect SSE for live updates
  connectSSE(async (versionData) => {
    const newGraph = await fetchGraph();
    batch({
      nodes: newGraph.nodes || [],
      edges: newGraph.edges || [],
      stats: newGraph.stats || {},
      version: newGraph.version || 0,
    });
  });

  return graph;
}

/**
 * Disconnect SSE and stop polling.
 */
export function disconnect() {
  if (_eventSource) { _eventSource.close(); _eventSource = null; }
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}
