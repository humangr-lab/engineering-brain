/* ═══════════════ WP-A11Y: ARIA MANAGER — Live regions and landmark management ═══════════════
   Creates and manages ARIA live regions for screen reader announcements.
   Sets up landmark roles and labels on key UI elements.

   Exports: initAriaManager(), announce(message) */

import { state, subscribe } from '../state.js';

/** @type {HTMLElement|null} */
let _liveRegion = null;

/** @type {number} */
let _announceTimer = 0;

/**
 * Initialize ARIA landmarks and live region.
 * - Creates an aria-live="polite" region for dynamic announcements.
 * - Sets landmark roles on major page sections.
 * - Labels icon-only buttons.
 */
export function initAriaManager() {
  _createLiveRegion();
  _setLandmarks();
  _labelButtons();
  _wireStateAnnouncements();
}

/**
 * Announce a message to screen readers via the live region.
 * Debounced: rapid calls within 100ms are collapsed to the latest message.
 * @param {string} message - Text to announce
 */
export function announce(message) {
  if (!_liveRegion || !message) return;

  // Clear any pending announcement
  clearTimeout(_announceTimer);

  // Brief delay allows the DOM to settle before announcing
  _announceTimer = setTimeout(() => {
    // Reset content to ensure re-announcement of identical text
    _liveRegion.textContent = '';
    requestAnimationFrame(() => {
      _liveRegion.textContent = message;
    });
  }, 100);
}

// ── Internal ──

/**
 * Create the off-screen aria-live region element.
 */
function _createLiveRegion() {
  // Check if already exists (e.g., added in HTML)
  _liveRegion = document.getElementById('a11yLive');
  if (_liveRegion) return;

  _liveRegion = document.createElement('div');
  _liveRegion.id = 'a11yLive';
  _liveRegion.setAttribute('role', 'status');
  _liveRegion.setAttribute('aria-live', 'polite');
  _liveRegion.setAttribute('aria-atomic', 'true');
  // Visually hidden but readable by screen readers
  _liveRegion.className = 'sr-only';
  document.body.appendChild(_liveRegion);
}

/**
 * Set ARIA landmark roles on major page sections.
 */
function _setLandmarks() {
  // Canvas container -- the main content area
  const canvas = document.getElementById('sc');
  if (canvas) {
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'Interactive 3D ontology map. Use keyboard to navigate nodes.');
    canvas.setAttribute('tabindex', '0');
  }

  // Header -- banner/navigation landmark
  const header = document.querySelector('.header');
  if (header) {
    header.setAttribute('role', 'banner');
  }

  // Detail panel -- complementary
  const dp = document.getElementById('dp');
  if (dp) {
    dp.setAttribute('role', 'complementary');
    dp.setAttribute('aria-label', 'Node detail panel');
  }

  // Stats bar
  const stats = document.querySelector('.stats-bar');
  if (stats) {
    stats.setAttribute('role', 'region');
    stats.setAttribute('aria-label', 'Graph statistics');
  }

  // Search overlay
  const searchOv = document.getElementById('wp3SearchOv');
  if (searchOv) {
    searchOv.setAttribute('role', 'dialog');
    searchOv.setAttribute('aria-label', 'Search nodes');
    searchOv.setAttribute('aria-modal', 'true');
  }

  // Modal overlay
  const modalOv = document.getElementById('modalOv');
  if (modalOv) {
    modalOv.setAttribute('role', 'dialog');
    modalOv.setAttribute('aria-label', 'Node details');
    modalOv.setAttribute('aria-modal', 'true');
  }

  // Knowledge Library overlay
  const klibOv = document.getElementById('klibOv');
  if (klibOv) {
    klibOv.setAttribute('role', 'dialog');
    klibOv.setAttribute('aria-label', 'Knowledge Library');
    klibOv.setAttribute('aria-modal', 'true');
  }

  // Doc overlay
  const docOv = document.getElementById('docOv');
  if (docOv) {
    docOv.setAttribute('role', 'dialog');
    docOv.setAttribute('aria-label', 'Documentation map');
    docOv.setAttribute('aria-modal', 'true');
  }

  // Legend
  const legend = document.getElementById('legend');
  if (legend) {
    legend.setAttribute('role', 'group');
    legend.setAttribute('aria-label', 'Edge type visibility toggles');
  }
}

/**
 * Add aria-labels to icon-only and unclear buttons.
 */
function _labelButtons() {
  // Close buttons (X icon)
  _labelEl('#dpX', 'Close detail panel');
  _labelEl('#modalX', 'Close modal');
  _labelEl('#klibX', 'Close Knowledge Library');
  _labelEl('#docOvX', 'Close documentation map');
  _labelEl('#docViewerX', 'Close document viewer');

  // Navigation buttons
  _labelEl('#klibBack', 'Navigate back in Knowledge Library');
  _labelEl('#klibFwd', 'Navigate forward in Knowledge Library');
  _labelEl('#backBtn', 'Back to main map');

  // Feature buttons
  _labelEl('#bgBtn', 'Toggle background theme');
  _labelEl('#klibBtn', 'Open Knowledge Library');
  _labelEl('#docMapBtn', 'Open documentation map');
  _labelEl('#tourBtn', 'Start guided tour');

  // Layout buttons
  const layoutBtns = document.querySelectorAll('.layout-btn');
  layoutBtns.forEach(btn => {
    const layout = btn.dataset.layout;
    if (layout && !btn.getAttribute('aria-label')) {
      btn.setAttribute('aria-label', `Switch to ${layout} layout`);
    }
  });

  // View toggle buttons
  const viewBtns = document.querySelectorAll('.view-btn');
  viewBtns.forEach(btn => {
    const view = btn.dataset.view;
    if (view && !btn.getAttribute('aria-label')) {
      btn.setAttribute('aria-label', `Switch to ${view.toUpperCase()} view`);
    }
  });

  // Legend items -- make them keyboard-interactive
  const legendItems = document.querySelectorAll('.legend-item');
  legendItems.forEach(item => {
    item.setAttribute('role', 'checkbox');
    item.setAttribute('aria-checked', item.classList.contains('active') ? 'true' : 'false');
    item.setAttribute('tabindex', '0');

    const label = item.textContent.trim();
    item.setAttribute('aria-label', `Toggle ${label} edge visibility`);

    // Keyboard activation
    item.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        item.click();
      }
    });

    // Update aria-checked when toggled
    const observer = new MutationObserver(() => {
      item.setAttribute('aria-checked', item.classList.contains('active') ? 'true' : 'false');
    });
    observer.observe(item, { attributes: true, attributeFilter: ['class'] });
  });

  // Search input labeling
  const searchInput = document.getElementById('wp3SearchInput');
  if (searchInput && !searchInput.getAttribute('aria-label')) {
    searchInput.setAttribute('aria-label', 'Search nodes, modules, and layers');
  }
}

/**
 * Helper: set aria-label on an element if it exists.
 */
function _labelEl(selector, label) {
  const el = document.querySelector(selector);
  if (el) el.setAttribute('aria-label', label);
}

/**
 * Wire up automatic announcements from state changes.
 */
function _wireStateAnnouncements() {
  // Announce selected node
  subscribe('selectedNode', (nodeId) => {
    if (!nodeId) return; // Don't announce deselection -- too noisy
    const node = state.sysNodes?.find(n => n.id === nodeId);
    if (node) {
      const type = node.g || 'node';
      announce(`Selected: ${node.label}, type: ${type}`);
    } else {
      announce(`Selected node: ${nodeId}`);
    }
  });

  // Announce drill level changes
  subscribe('inSubmap', (inSubmap) => {
    if (inSubmap) {
      const submap = state.submaps?.[state.currentSubmap];
      const title = submap?.title || state.currentSubmap;
      announce(`Drilled into ${title}. Press Escape or Back button to return.`);
    } else {
      announce('Returned to main map');
    }
  });

  // Announce overlay open/close
  subscribe('klibOpen', (open) => {
    if (open) announce('Knowledge Library opened');
  });

  subscribe('searchOverlayOpen', (open) => {
    if (open) announce('Search overlay opened. Type to search.');
  });
}
