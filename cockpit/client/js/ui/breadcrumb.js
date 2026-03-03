/* ═══════════════ WP-3: BREADCRUMB — Clickable drill-down trail ═══════════════
   Subscribes to state.drillStack and renders System > Module > File > Symbol.
   Each segment is clickable to navigate back to that drill level.           */

import { state, subscribe } from '../state.js';

let _container = null;
let _onNavigate = null;

/**
 * Initialize breadcrumb system.
 * @param {Function} navigateFn - (level: number) => void, called when user clicks a breadcrumb segment
 */
export function initBreadcrumb(navigateFn) {
  _onNavigate = navigateFn || null;
  _container = document.getElementById('wp3Breadcrumb');
  if (!_container) return;

  // Subscribe to drill stack changes
  subscribe('drillStack', (stack) => updateBreadcrumb(stack));
  subscribe('breadcrumb', (crumbs) => {
    if (crumbs && crumbs.length) updateBreadcrumb(crumbs);
  });

  // Subscribe to submap changes (existing submap system)
  subscribe('inSubmap', () => _updateFromSubmap());
  subscribe('currentSubmap', () => _updateFromSubmap());

  // ═══ WP-4: Subscribe to drill level changes for breadcrumb bar visibility ═══
  subscribe('drillLevel', (level) => {
    const bar = _container?.closest('.wp3-breadcrumb-bar');
    if (bar) {
      bar.classList.toggle('wp3-bc-visible', level > 0 || (state.drillStack && state.drillStack.length > 0));
    }
  });

  // Render initial state
  _updateFromSubmap();
}

/**
 * Update breadcrumb from the current drill stack or breadcrumb array.
 * @param {Array} stack - Array of {id, label, level} objects
 */
export function updateBreadcrumb(stack) {
  if (!_container) return;

  // Always start with "System" as root
  const segments = [{ id: null, label: 'System', level: 0 }];

  if (Array.isArray(stack)) {
    stack.forEach((item, i) => {
      segments.push({
        id: item.id || item,
        label: item.label || item.id || item,
        level: i + 1,
      });
    });
  }

  _render(segments);
}

/**
 * Build breadcrumb from the current submap state (backward compat).
 */
function _updateFromSubmap() {
  if (!_container) return;

  const segments = [{ id: null, label: 'System', level: 0 }];

  if (state.inSubmap && state.currentSubmap) {
    const sm = state.submaps[state.currentSubmap];
    segments.push({
      id: state.currentSubmap,
      label: sm?.title || state.currentSubmap,
      level: 1,
    });
  }

  // If drillStack has items, prefer that over submap-based breadcrumb
  if (state.drillStack && state.drillStack.length > 0) {
    return; // drillStack subscription already handles this
  }

  _render(segments);
}

/**
 * Render breadcrumb segments into the DOM container.
 * @param {Array} segments - [{id, label, level}]
 */
function _render(segments) {
  if (!_container) return;

  _container.innerHTML = '';

  segments.forEach((seg, i) => {
    const isLast = i === segments.length - 1;

    // Separator (except before first)
    if (i > 0) {
      const sep = document.createElement('span');
      sep.className = 'wp3-bc-sep';
      sep.textContent = '\u203A'; // single right-pointing angle quotation mark
      _container.appendChild(sep);
    }

    // Segment
    const el = document.createElement('span');
    el.className = 'wp3-bc-seg' + (isLast ? ' wp3-bc-current' : '');
    el.textContent = seg.label;
    el.dataset.level = seg.level;
    if (seg.id) el.dataset.id = seg.id;

    if (!isLast) {
      el.tabIndex = 0;
      el.role = 'link';
      el.addEventListener('click', () => _navigateToLevel(seg, i));
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          _navigateToLevel(seg, i);
        }
      });
    }

    _container.appendChild(el);
  });

  // Show/hide breadcrumb bar based on whether we have more than just "System"
  const bar = _container.closest('.wp3-breadcrumb-bar');
  if (bar) {
    bar.classList.toggle('wp3-bc-visible', segments.length > 0);
  }
}

/**
 * Navigate to a specific breadcrumb level.
 */
function _navigateToLevel(seg, index) {
  if (_onNavigate) {
    _onNavigate(index, seg);
  }
}
