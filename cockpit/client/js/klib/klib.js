/* ═══════════════ KLIB — Knowledge Library controller ═══════════════
   SOTA: Reactive open/close, filter subscription, history, integration.
   Shneiderman's mantra: overview first, zoom & filter, details on demand. */

import { state, subscribe } from '../state.js';
import { buildFilters } from './filters.js';
import { renderList } from './list.js';
import { renderDetail } from './detail.js';

let _history = [];
let _historyIdx = -1;
let _unsubs = [];

/**
 * Initialize Knowledge Library.
 */
export function initKlib() {
  const btn = document.getElementById('klibBtn');
  const closeBtn = document.getElementById('klibX');
  const backBtn = document.getElementById('klibBack');
  const fwdBtn = document.getElementById('klibFwd');

  if (btn) btn.addEventListener('click', openKlib);
  if (closeBtn) closeBtn.addEventListener('click', closeKlib);
  if (backBtn) backBtn.addEventListener('click', navigateBack);
  if (fwdBtn) fwdBtn.addEventListener('click', navigateForward);

  // Group-by buttons
  document.querySelectorAll('#klibGroupBy .klib-sort-btn').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('#klibGroupBy .klib-sort-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      state.klibGroupBy = b.dataset.grp;
    });
  });

  // React to state changes
  _unsubs.push(subscribe('klibOpen', (open) => {
    if (open) _renderKlib();
    else _hideKlib();
  }));

  _unsubs.push(subscribe('klibGroupBy', () => {
    if (state.klibOpen) _renderCenter();
  }));

  _unsubs.push(subscribe('klibSelectedNode', (nodeId) => {
    if (nodeId && state.klibOpen) renderDetail(nodeId);
  }));

  _unsubs.push(subscribe('klibFilters', () => {
    if (state.klibOpen) {
      _renderCenter();
    }
  }));

  _unsubs.push(subscribe('nodes', () => {
    if (state.klibOpen) _renderKlib();
  }));

  // Keyboard shortcut: Escape closes KLIB
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.klibOpen) {
      closeKlib();
    }
  });
}

export function openKlib() {
  state.klibOpen = true;
  const ov = document.getElementById('klibOv');
  if (ov) {
    ov.classList.add('open');
    ov.style.animation = 'klibFade .25s ease-out';
  }
}

export function closeKlib() {
  state.klibOpen = false;
  document.getElementById('klibOv')?.classList.remove('open');
}

function _getKlibNodes() {
  return state.nodes && state.nodes.length > 0
    ? state.nodes
    : (Array.isArray(state.klibData) ? state.klibData : Object.values(state.klibData || {}));
}

function _renderKlib() {
  const nodes = _getKlibNodes();
  _updateStats();
  buildFilters(nodes);
  _renderCenter();

  // If a node was selected before, re-render detail
  if (state.klibSelectedNode) {
    renderDetail(state.klibSelectedNode);
  }
}

function _hideKlib() {
  document.getElementById('klibOv')?.classList.remove('open');
}

function _renderCenter() {
  const nodes = _getKlibNodes();
  const filtered = _applyFilters(nodes);
  renderList(filtered, state.klibGroupBy);

  // Update result count
  const countEl = document.getElementById('klibResultCount');
  if (countEl) {
    const total = nodes.length;
    const shown = filtered.length;
    countEl.textContent = total === 0
      ? 'No data available'
      : shown === total
        ? `${total.toLocaleString()} nodes`
        : `${shown.toLocaleString()} of ${total.toLocaleString()} nodes`;
  }
}

function _applyFilters(nodes) {
  if (!nodes || !nodes.length) return [];
  const f = state.klibFilters;
  let result = nodes;

  // Layer filter
  if (f.layers?.length > 0) {
    result = result.filter(n => f.layers.includes(n.layer));
  }

  // Severity filter
  if (f.severities?.length > 0) {
    result = result.filter(n => f.severities.includes((n.severity || '').toUpperCase()));
  }

  // Confidence filter
  if (f.confidence > 0) {
    result = result.filter(n => (n.confidence || 0) >= f.confidence);
  }

  // Search filter
  if (f.search) {
    const q = f.search.toLowerCase();
    result = result.filter(n => {
      const haystack = `${n.id} ${n.text || ''} ${n.why || ''} ${n.howTo || ''} ${(n.technologies || []).join(' ')} ${(n.domains || []).join(' ')}`.toLowerCase();
      return haystack.includes(q);
    });
  }

  // Tag filter (ANY match)
  if (f.tags?.length > 0) {
    result = result.filter(n => {
      const allTags = [...(n.technologies || []), ...(n.domains || [])];
      return f.tags.some(t => allTags.includes(t));
    });
  }

  return result;
}

function _updateStats() {
  const bar = document.getElementById('klibStatsMini');
  if (!bar) return;
  const stats = state.stats || {};
  const totalNodes = stats.total_nodes || state.nodes.length;
  const totalEdges = stats.total_edges || state.edges.length;
  const edgeTypes = Object.keys(stats.by_edge_type || {}).length || 22;
  const domains = Object.keys(stats.by_domain || {}).length || 0;

  bar.innerHTML = `
    <div class="klib-stat-mini"><span class="n">${totalNodes.toLocaleString()}</span><span class="l">Nodes</span></div>
    <div class="klib-stat-mini"><span class="n">${totalEdges.toLocaleString()}</span><span class="l">Edges</span></div>
    <div class="klib-stat-mini"><span class="n">6</span><span class="l">Layers</span></div>
    <div class="klib-stat-mini"><span class="n">${edgeTypes}</span><span class="l">Edge Types</span></div>
    ${domains ? `<div class="klib-stat-mini"><span class="n">${domains}</span><span class="l">Domains</span></div>` : ''}
  `;
}

/* ── Navigation History ────────────────────────────────── */

function _pushHistory(item) {
  // Don't push duplicates
  if (_history[_historyIdx] === item) return;
  _history = _history.slice(0, _historyIdx + 1);
  _history.push(item);
  _historyIdx = _history.length - 1;
  _updateNavButtons();
}

function navigateBack() {
  if (_historyIdx > 0) {
    _historyIdx--;
    const item = _history[_historyIdx];
    if (item) state.klibSelectedNode = item;
    _updateNavButtons();
  }
}

function navigateForward() {
  if (_historyIdx < _history.length - 1) {
    _historyIdx++;
    const item = _history[_historyIdx];
    if (item) state.klibSelectedNode = item;
    _updateNavButtons();
  }
}

function _updateNavButtons() {
  const back = document.getElementById('klibBack');
  const fwd = document.getElementById('klibFwd');
  if (back) back.disabled = _historyIdx <= 0;
  if (fwd) fwd.disabled = _historyIdx >= _history.length - 1;
}

/**
 * Navigate to a node in the KLIB.
 */
export function navigateToNode(nodeId) {
  _pushHistory(nodeId);
  state.klibSelectedNode = nodeId;
}
