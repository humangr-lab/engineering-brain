/* ═══════════════ STATS BAR — Top bar with animated counters ═══════════════ */

import { state, subscribe } from '../state.js';

/**
 * Initialize and update the stats bar with real data.
 */
export function initStatsBar() {
  // Update stats when data changes
  subscribe('stats', _updateStats);
  subscribe('nodes', _updateStats);

  // Initial update
  _updateStats();
}

function _updateStats() {
  const stats = state.stats || {};
  const nodeCount = stats.total_nodes || state.nodes.length || 0;
  const edgeTypes = Object.keys(stats.by_edge_type || {}).length || 24;
  const layers = 6;
  const seedSources = stats.seed_count || 158;
  const selfImproving = 7;
  const llmCalls = 0;

  _setTarget('Nodes', nodeCount);
  _setTarget('Edge Types', edgeTypes);
  _setTarget('Cortical Layers', layers);
  _setTarget('Seed Sources', seedSources);
  _setTarget('Self-Improving', selfImproving);
  _setTarget('LLM Calls', llmCalls);
}

function _setTarget(label, value) {
  const stats = document.querySelectorAll('.stat');
  stats.forEach(stat => {
    const lEl = stat.querySelector('.l');
    const nEl = stat.querySelector('.n');
    if (lEl && nEl && lEl.textContent === label) {
      nEl.dataset.t = String(value);
    }
  });
}

/**
 * Animate all stat counters from 0 to their target values.
 * ═══ WP-A11Y: Reduced Motion — instantly set values when motion reduced ═══
 */
export function animateCounters() {
  // WP-A11Y: Check reduced motion preference
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const els = document.querySelectorAll('.stat .n[data-t]');
  els.forEach(el => {
    const target = parseInt(el.dataset.t, 10);
    if (isNaN(target)) return;

    // WP-A11Y: Skip animation when reduced motion preferred
    if (reducedMotion) {
      el.textContent = target.toLocaleString();
      return;
    }

    const duration = 2000;
    const start = performance.now();

    function step() {
      const elapsed = performance.now() - start;
      const t = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(target * ease).toLocaleString();
      if (t < 1) requestAnimationFrame(step);
    }
    step();
  });
}
