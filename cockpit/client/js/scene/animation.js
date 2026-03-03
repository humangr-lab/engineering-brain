/* ═══════════════ ANIMATION — Render loop tick callbacks ═══════════════ */

import * as T from 'three';
import { tickConnections } from './connections.js';

let _icons = [];
let _heroIcons = [];
let _autoIcons = [];
let _time = 0;
let _submapTickFn = null;

// ═══ WP-A11Y: Reduced Motion ═══
let _reducedMotion = false;
const _motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
_reducedMotion = _motionQuery.matches;
_motionQuery.addEventListener('change', (e) => { _reducedMotion = e.matches; });

/**
 * Whether reduced motion is currently preferred.
 * @returns {boolean}
 */
export function isReducedMotion() { return _reducedMotion; }

/**
 * Register icons for animation.
 * @param {Array} icons - [{mesh, id, data}]
 */
export function registerIcons(icons) {
  _icons = icons;
  _heroIcons = icons.filter(i => i.data?.hero);
  _autoIcons = icons.filter(i => i.data?.auto);
}

/**
 * Register a callback that replaces main-map animation during submap.
 * @param {Function} fn - (time: number) => void
 */
export function registerSubmapTick(fn) {
  _submapTickFn = fn;
}

/**
 * Clear the submap tick callback (on exit).
 */
export function clearSubmapTick() {
  _submapTickFn = null;
}

/**
 * Main animation tick — called every frame.
 */
export function tick() {
  _time += 0.016; // ~60fps

  // If submap tick is active, delegate and skip main-map animation
  if (_submapTickFn) {
    // ═══ WP-A11Y: Reduced Motion ═══
    // Skip decorative submap animations when reduced motion preferred
    if (!_reducedMotion) {
      _submapTickFn(_time);
    } else {
      // Still tick connections for data flow clarity (essential animation)
      tickConnections();
    }
    return;
  }

  // ═══ WP-A11Y: Reduced Motion ═══
  // When reduced motion is preferred, skip decorative breathing, rotation, pulse
  if (!_reducedMotion) {
    // Subtle breathe for all icons
    _icons.forEach(icon => {
      if (!icon.mesh) return;
      const breathe = 1 + Math.sin(_time * 1.5 + icon.mesh.position.x) * 0.008;
      icon.mesh.scale.setScalar(icon.baseScale * breathe);
    });

    // Hero icons — slow rotation
    _heroIcons.forEach(icon => {
      if (!icon.mesh) return;
      icon.mesh.rotation.y += 0.003;
    });

    // Auto (self-improving) icons — glow pulse
    _autoIcons.forEach(icon => {
      if (!icon.mesh) return;
      const pulse = 0.5 + Math.sin(_time * 2 + icon.mesh.position.z) * 0.5;
      icon.mesh.scale.setScalar(icon.baseScale * (1 + pulse * 0.02));
    });
  }

  // Connection particles — kept even in reduced motion (essential data flow)
  // but at reduced speed
  if (!_reducedMotion) {
    tickConnections();
  }
}

/**
 * Stats counter animation (the bottom bar numbers).
 * ═══ WP-A11Y: Reduced Motion — instantly set values when motion reduced ═══
 */
export function animateCounters() {
  const els = document.querySelectorAll('.stat .n[data-t]');
  els.forEach(el => {
    const target = parseInt(el.dataset.t, 10);
    if (isNaN(target)) return;

    // WP-A11Y: Skip animation when reduced motion preferred
    if (_reducedMotion) {
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
