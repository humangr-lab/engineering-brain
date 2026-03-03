/* ═══════════════ LABELS — CSS2D labels for 3D scene ═══════════════ */

import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

/**
 * Create a pill label for a main map node.
 * @returns {CSS2DObject}
 */
export function createPillLabel(node) {
  const el = document.createElement('div');
  el.className = `pill-label ${node.g || 'module'}${node.hero ? ' hero' : ''}`;
  el.textContent = node.label;
  const obj = new CSS2DObject(el);
  obj.position.set(0, 1.2, 0);
  return obj;
}

/**
 * Create a sub-label (smaller text below main label).
 * @returns {CSS2DObject}
 */
export function createSubLabel(text) {
  const el = document.createElement('div');
  el.className = 'sub-3d';
  el.textContent = text;
  const obj = new CSS2DObject(el);
  obj.position.set(0, 0.75, 0);
  return obj;
}

/**
 * Create an "auto-pilot" badge for self-improving modules.
 * @returns {CSS2DObject}
 */
export function createAutoPill() {
  const el = document.createElement('div');
  el.className = 'auto-pill';
  el.textContent = 'SELF-IMPROVING';
  const obj = new CSS2DObject(el);
  obj.position.set(0, 0.5, 0);
  return obj;
}

/**
 * Create a glassmorphism info card for submap nodes.
 * Shows title, subtitle, confidence bar, up to 3 KV tags, CORE badge for hero.
 * @param {object} node  - Submap node data { label, sub, hero, ... }
 * @param {string} smColor - Submap zone color ('source'|'layer'|'module'|'consumer')
 * @param {object} [nd]  - Node details from ND data { conf, kv, ... }
 * @returns {CSS2DObject}
 */
export function createSubmapCard(node, smColor, nd) {
  const el = document.createElement('div');
  el.className = `submap-card ${smColor || 'module'}${node.hero ? ' hero' : ''}`;

  // Title
  const title = document.createElement('div');
  title.className = 'sc-title';
  title.textContent = node.label;
  el.appendChild(title);

  // Subtitle
  if (node.sub) {
    const sub = document.createElement('div');
    sub.className = 'sc-sub';
    sub.textContent = node.sub;
    el.appendChild(sub);
  }

  // Confidence bar
  if (nd && nd.conf != null) {
    const confWrap = document.createElement('div');
    confWrap.className = 'sc-conf';
    const confBar = document.createElement('div');
    confBar.className = 'sc-conf-bar';
    const sev = nd.conf < 0.1 ? 'none' : nd.conf < 0.2 ? 'low' : nd.conf < 0.4 ? 'moderate' : 'high';
    confBar.classList.add(sev);
    confBar.style.width = `${Math.min(nd.conf * 100, 100)}%`;
    confWrap.appendChild(confBar);
    el.appendChild(confWrap);
  }

  // KV tags (up to 3)
  if (nd && nd.kv) {
    const tags = document.createElement('div');
    tags.className = 'sc-tags';
    Object.entries(nd.kv).slice(0, 3).forEach(([k, v]) => {
      const tag = document.createElement('span');
      tag.className = 'sc-tag';
      tag.textContent = `${k}: ${v}`;
      tags.appendChild(tag);
    });
    el.appendChild(tags);
  }

  // CORE badge for hero
  if (node.hero) {
    const badge = document.createElement('div');
    badge.className = 'sc-hero-badge';
    badge.textContent = 'CORE';
    el.appendChild(badge);
  }

  const obj = new CSS2DObject(el);
  return obj;
}
