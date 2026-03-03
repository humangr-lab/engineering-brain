/* ═══════════════ SEARCH — Pure search engine (index + fuzzy matching) ═══════════════
   Provides index building, fuzzy search, and scoring. No DOM manipulation.
   Consumed by search-overlay.js (WP-3) for the Cmd+K overlay.

   Exports: buildSearchIndex(nodes), searchNodes(query, filter), initSearch (legacy compat) */

import { state, subscribe } from './state.js';

/** @type {Array} Internal search index */
let _index = [];

/** @type {Function|null} Legacy navigation callback (kept for backward compat) */
let _legacyOnNavigate = null;

/**
 * Build or rebuild the search index from a list of nodes.
 * Each node should have: { id, label, sub, group, type, nodeType, parentId, detail }
 * @param {Array} nodes
 */
export function buildSearchIndex(nodes) {
  if (!Array.isArray(nodes)) return;
  _index = nodes.map(n => ({
    id: n.id,
    label: n.label || '',
    sub: n.sub || '',
    group: n.group || n.g || '',
    type: n.type || 'main',
    nodeType: n.nodeType || 'package',
    parentId: n.parentId || null,
    detail: n.detail || '',
    // Pre-compute lowercase haystack for fast matching
    _haystack: `${n.label || ''} ${n.sub || ''} ${n.detail || ''} ${n.id || ''}`.toLowerCase(),
  }));
}

/**
 * Search the index with a query string and optional type filter.
 * Returns up to 20 results, scored by relevance.
 * @param {string} query - search query
 * @param {string} [filter='all'] - type filter: 'all', 'package', 'file', 'class', 'function'
 * @returns {Array} matching items sorted by relevance
 */
export function searchNodes(query, filter = 'all') {
  const q = (query || '').toLowerCase().trim();

  let candidates = _index;

  // Apply type filter
  if (filter && filter !== 'all') {
    candidates = candidates.filter(item => item.nodeType === filter);
  }

  if (!q) {
    // No query: return first 10 items (most relevant by default order)
    return candidates.slice(0, 10);
  }

  // Score and filter
  const scored = [];
  for (const item of candidates) {
    const score = _score(item, q);
    if (score > 0) {
      scored.push({ ...item, _score: score });
    }
  }

  // Sort by score descending
  scored.sort((a, b) => b._score - a._score);

  return scored.slice(0, 20);
}

/**
 * Compute a relevance score for an item against a query.
 * Higher score = better match.
 * @param {Object} item - index item
 * @param {string} q - lowercase query
 * @returns {number} relevance score (0 = no match)
 */
function _score(item, q) {
  let score = 0;

  // Exact ID match (highest priority)
  if (item.id.toLowerCase() === q) return 100;

  // Label starts with query
  const labelLower = item.label.toLowerCase();
  if (labelLower.startsWith(q)) {
    score += 50;
  } else if (labelLower.includes(q)) {
    score += 30;
  }

  // ID contains query
  if (item.id.toLowerCase().includes(q)) {
    score += 20;
  }

  // Sub text contains query
  if (item.sub.toLowerCase().includes(q)) {
    score += 10;
  }

  // Detail text contains query
  if (item.detail.toLowerCase().includes(q)) {
    score += 5;
  }

  // Fuzzy matching: check if all query chars appear in order in the label
  if (score === 0) {
    if (_fuzzyMatch(labelLower, q)) {
      score += 8;
    } else if (_fuzzyMatch(item._haystack, q)) {
      score += 3;
    }
  }

  return score;
}

/**
 * Simple fuzzy match: check if all chars of needle appear in order in haystack.
 * @param {string} haystack
 * @param {string} needle
 * @returns {boolean}
 */
function _fuzzyMatch(haystack, needle) {
  let hi = 0;
  for (let ni = 0; ni < needle.length; ni++) {
    const ch = needle[ni];
    const found = haystack.indexOf(ch, hi);
    if (found === -1) return false;
    hi = found + 1;
  }
  return true;
}

// ═══ Legacy compatibility ═══
// The original search.js had initSearch() which wired DOM directly.
// We keep this export so app.js does not break, but it now delegates to
// the WP-3 search overlay. The old inline search DOM (#searchOv etc.)
// still works through this bridge.

/**
 * Legacy init — kept for backward compatibility.
 * The WP-3 search overlay (search-overlay.js) replaces the inline search UI.
 * @param {Function} navigateFn
 */
export function initSearch(navigateFn) {
  _legacyOnNavigate = navigateFn;

  // Build index from current state
  _buildLegacyIndex();

  // Rebuild when nodes change
  subscribe('nodes', () => _buildLegacyIndex());
  subscribe('sysNodes', () => _buildLegacyIndex());
}

function _buildLegacyIndex() {
  const nodes = [];

  // Architecture nodes
  if (state.sysNodes) {
    state.sysNodes.forEach(n => {
      nodes.push({
        id: n.id, label: n.label, sub: n.sub, group: n.g,
        type: 'main', nodeType: 'package', parentId: null,
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
            id: n.id, label: n.label, sub: n.sub, group: sm.color,
            type: 'sub', nodeType: 'file', parentId: pid,
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
        id: n.id, label: n.text, sub: n.layerName || '',
        group: 'klib', type: 'klib', nodeType: 'knowledge', parentId: null,
        detail: (n.why || '') + ' ' + (n.technologies || []).join(' '),
      });
    });
  }

  buildSearchIndex(nodes);
}
