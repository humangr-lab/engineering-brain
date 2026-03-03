/* ═══════════════ WP-3: SEARCH OVERLAY — Cmd+K search with fuzzy matching ═══════════════
   600px centered overlay with backdrop. Debounced (150ms) fuzzy matching.
   Filter chips: All, Package, File, Class, Function.
   Full keyboard navigation: Down/Up, Enter, Escape, Tab to cycle filters.
   Max 20 results, grouped by level (L0/L1/L2).                                         */

import { state, subscribe, batch } from '../state.js';
import { buildSearchIndex, searchNodes } from '../search.js';

let _overlay = null;
let _input = null;
let _resultsEl = null;
let _filtersEl = null;
let _footerCount = null;
let _debounceTimer = null;
let _activeIdx = -1;
let _currentResults = [];
let _onNavigate = null;

const FILTER_CHIPS = [
  { key: 'all', label: 'All' },
  { key: 'package', label: 'Package' },
  { key: 'file', label: 'File' },
  { key: 'class', label: 'Class' },
  { key: 'function', label: 'Function' },
];

const DEBOUNCE_MS = 150;
const MAX_RESULTS = 20;

/**
 * Initialize the search overlay system.
 * @param {Function} navigateFn - (item) => void, called when user selects a result
 */
export function initSearchOverlay(navigateFn) {
  _onNavigate = navigateFn;

  _overlay = document.getElementById('wp3SearchOv');
  _input = document.getElementById('wp3SearchInput');
  _resultsEl = document.getElementById('wp3SearchResults');
  _filtersEl = document.getElementById('wp3SearchFilters');
  _footerCount = document.getElementById('wp3SearchCount');

  if (!_overlay || !_input || !_resultsEl) return;

  // Build filter chips
  _buildFilterChips();

  // Input handler with debounce
  _input.addEventListener('input', () => {
    if (_debounceTimer) clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(() => _runSearch(_input.value), DEBOUNCE_MS);
  });

  // Click on backdrop to close
  _overlay.addEventListener('click', (e) => {
    if (e.target === _overlay) closeSearchOverlay();
  });

  // Keyboard handler (delegated to overlay so it only fires when open)
  _overlay.addEventListener('keydown', _onOverlayKeydown);

  // Subscribe to state.searchOverlayOpen
  subscribe('searchOverlayOpen', (isOpen) => {
    if (isOpen) _show();
    else _hide();
  });

  // Rebuild search index when nodes change
  subscribe('sysNodes', () => buildSearchIndex(_collectNodes()));
  subscribe('nodes', () => buildSearchIndex(_collectNodes()));

  // Initial index build
  buildSearchIndex(_collectNodes());
}

/**
 * Open the search overlay.
 */
export function openSearchOverlay() {
  state.searchOverlayOpen = true;
}

/**
 * Close the search overlay.
 */
export function closeSearchOverlay() {
  state.searchOverlayOpen = false;
}

// ── Internal methods ──

function _show() {
  if (!_overlay) return;
  _overlay.classList.add('open');
  _input.value = '';
  _activeIdx = -1;
  _currentResults = [];
  _setFilter('all');
  _runSearch('');

  // Focus input after transition
  requestAnimationFrame(() => _input.focus());
}

function _hide() {
  if (!_overlay) return;
  _overlay.classList.remove('open');
  _input.blur();
}

/**
 * Collect all searchable nodes from state.
 * @returns {Array} node list for indexing
 */
function _collectNodes() {
  const nodes = [];

  // Architecture nodes (sysmap)
  if (state.sysNodes) {
    state.sysNodes.forEach(n => {
      nodes.push({
        id: n.id,
        label: n.label,
        sub: n.sub || '',
        group: n.g || 'module',
        type: 'main',
        nodeType: _inferNodeType(n),
        parentId: null,
        detail: state.sysDetails?.[n.id]?.d || '',
      });
    });
  }

  // Sub-map nodes
  if (state.submaps) {
    Object.entries(state.submaps).forEach(([pid, sm]) => {
      if (sm.nodes) {
        sm.nodes.forEach(n => {
          nodes.push({
            id: n.id,
            label: n.label,
            sub: n.sub || '',
            group: sm.color || 'module',
            type: 'sub',
            nodeType: _inferNodeType(n),
            parentId: pid,
            detail: state.nodeDetails?.[n.id]?.d || '',
          });
        });
      }
    });
  }

  // Live knowledge nodes
  if (state.nodes) {
    state.nodes.forEach(n => {
      nodes.push({
        id: n.id,
        label: n.text || n.label || n.id,
        sub: n.layerName || '',
        group: 'klib',
        type: 'klib',
        nodeType: 'knowledge',
        parentId: null,
        detail: (n.why || '') + ' ' + (n.technologies || []).join(' '),
      });
    });
  }

  return nodes;
}

/**
 * Infer node type from node data for filter matching.
 */
function _inferNodeType(n) {
  const id = (n.id || '').toLowerCase();
  const sub = (n.sub || '').toLowerCase();
  const label = (n.label || '').toLowerCase();

  if (sub.includes('package') || sub.includes('module') || n.g === 'source') return 'package';
  if (sub.includes('file') || id.endsWith('.py') || id.endsWith('.js') || id.endsWith('.ts')) return 'file';
  if (sub.includes('class') || /^[A-Z]/.test(n.label || '')) return 'class';
  if (sub.includes('function') || sub.includes('method') || label.includes('()')) return 'function';
  return 'package'; // default
}

/**
 * Build the filter chip buttons.
 */
function _buildFilterChips() {
  if (!_filtersEl) return;

  _filtersEl.innerHTML = FILTER_CHIPS.map(chip =>
    `<button class="wp3-search-chip${chip.key === 'all' ? ' active' : ''}" data-filter="${chip.key}" tabindex="-1">${chip.label}</button>`
  ).join('');

  _filtersEl.addEventListener('click', (e) => {
    const btn = e.target.closest('.wp3-search-chip');
    if (!btn) return;
    _setFilter(btn.dataset.filter);
    _runSearch(_input.value);
    _input.focus();
  });
}

/**
 * Set the active filter chip.
 */
function _setFilter(filterKey) {
  batch({ searchFilters: { type: filterKey } });

  if (_filtersEl) {
    _filtersEl.querySelectorAll('.wp3-search-chip').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.filter === filterKey);
    });
  }
}

/**
 * Run search with current query and filters.
 */
function _runSearch(query) {
  const filter = state.searchFilters?.type || 'all';
  const results = searchNodes(query, filter);
  _currentResults = results.slice(0, MAX_RESULTS);
  _activeIdx = _currentResults.length > 0 ? 0 : -1;
  _renderResults(query);
}

/**
 * Render search results into the results container.
 */
function _renderResults(query) {
  if (!_resultsEl) return;

  if (_currentResults.length === 0 && query.trim()) {
    _resultsEl.innerHTML = '<div class="wp3-search-empty">No results found</div>';
    if (_footerCount) _footerCount.textContent = '0 results';
    return;
  }

  if (_currentResults.length === 0) {
    // Show recent / default items
    _resultsEl.innerHTML = '<div class="wp3-search-empty">Type to search nodes, modules, files...</div>';
    if (_footerCount) _footerCount.textContent = '';
    return;
  }

  // Group results by level/type
  const grouped = _groupResults(_currentResults);
  let html = '';
  let globalIdx = 0;

  for (const group of grouped) {
    html += `<div class="wp3-search-group-header">${group.label}</div>`;

    for (const item of group.items) {
      const isActive = globalIdx === _activeIdx;
      html += `<div class="wp3-search-result${isActive ? ' active' : ''}" data-idx="${globalIdx}">`;
      html += `<div class="wp3-search-result-main">`;
      html += `<span class="wp3-search-result-title">${_highlight(item.label, query)}</span>`;
      html += `<span class="wp3-search-result-badge">${_badgeLabel(item)}</span>`;
      html += `</div>`;
      if (item.sub) {
        html += `<div class="wp3-search-result-sub">${_highlight(item.sub, query)}</div>`;
      }
      html += `</div>`;
      globalIdx++;
    }
  }

  _resultsEl.innerHTML = html;

  if (_footerCount) {
    _footerCount.textContent = `${_currentResults.length} result${_currentResults.length !== 1 ? 's' : ''}`;
  }

  // Wire click handlers
  _resultsEl.querySelectorAll('.wp3-search-result').forEach(el => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.dataset.idx, 10);
      if (idx >= 0 && idx < _currentResults.length) {
        _selectResult(idx);
      }
    });
  });

  // Scroll active into view
  _scrollActiveIntoView();
}

/**
 * Group results by their type/level for section headers.
 */
function _groupResults(results) {
  const groups = new Map();

  for (const item of results) {
    let label;
    if (item.type === 'klib') label = 'Knowledge';
    else if (item.type === 'sub') label = 'L1: Module';
    else label = 'L0: System';

    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(item);
  }

  return Array.from(groups.entries()).map(([label, items]) => ({ label, items }));
}

/**
 * Get badge label for a result item.
 */
function _badgeLabel(item) {
  if (item.type === 'klib') return 'Knowledge';
  if (item.nodeType === 'file') return 'File';
  if (item.nodeType === 'class') return 'Class';
  if (item.nodeType === 'function') return 'Function';
  return item.group || 'Package';
}

/**
 * Highlight matching text in a string.
 */
function _highlight(text, query) {
  if (!query || !text) return text || '';
  const q = query.trim().toLowerCase();
  if (!q) return text;

  const idx = text.toLowerCase().indexOf(q);
  if (idx === -1) return text;
  return (
    _escapeHtml(text.slice(0, idx)) +
    '<mark>' + _escapeHtml(text.slice(idx, idx + q.length)) + '</mark>' +
    _escapeHtml(text.slice(idx + q.length))
  );
}

function _escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Keyboard handler for overlay.
 */
function _onOverlayKeydown(e) {
  switch (e.key) {
    case 'Escape':
      e.preventDefault();
      closeSearchOverlay();
      break;

    case 'ArrowDown':
      e.preventDefault();
      _moveSelection(1);
      break;

    case 'ArrowUp':
      e.preventDefault();
      _moveSelection(-1);
      break;

    case 'Enter':
      e.preventDefault();
      if (_activeIdx >= 0 && _activeIdx < _currentResults.length) {
        _selectResult(_activeIdx);
      }
      break;

    case 'Tab': {
      e.preventDefault();
      // Cycle through filter chips
      const chips = FILTER_CHIPS.map(c => c.key);
      const currentFilter = state.searchFilters?.type || 'all';
      const currentIdx = chips.indexOf(currentFilter);
      const direction = e.shiftKey ? -1 : 1;
      const nextIdx = (currentIdx + direction + chips.length) % chips.length;
      _setFilter(chips[nextIdx]);
      _runSearch(_input.value);
      break;
    }
  }
}

/**
 * Move the active selection up or down.
 */
function _moveSelection(direction) {
  if (_currentResults.length === 0) return;

  _activeIdx = Math.max(0, Math.min(_currentResults.length - 1, _activeIdx + direction));

  // Update DOM active state
  const items = _resultsEl.querySelectorAll('.wp3-search-result');
  items.forEach((el, i) => el.classList.toggle('active', i === _activeIdx));
  _scrollActiveIntoView();
}

/**
 * Scroll the active result into view.
 */
function _scrollActiveIntoView() {
  const active = _resultsEl?.querySelector('.wp3-search-result.active');
  if (active) {
    active.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
}

/**
 * Select a result by index and navigate to it.
 */
function _selectResult(idx) {
  const item = _currentResults[idx];
  if (!item) return;

  closeSearchOverlay();

  if (_onNavigate) {
    _onNavigate(item);
  }
}
