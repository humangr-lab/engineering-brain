/* ═══════════════ DETAIL PANEL — Right side panel for 3D map nodes ═══════════════ */

import { state, subscribe } from '../state.js';

let _selectedId = null;

/**
 * Initialize detail panel.
 */
export function initDetailPanel() {
  const closeBtn = document.getElementById('dpX');
  if (closeBtn) closeBtn.addEventListener('click', closePanel);

  subscribe('selectedNode', (nodeId) => {
    if (nodeId) openPanel(nodeId);
    else closePanel();
  });
}

export function openPanel(id) {
  if (_selectedId === id) { closePanel(); return; }
  _selectedId = id;

  const detail = state.sysDetails[id];
  const node = state.sysNodes.find(n => n.id === id);
  if (!detail) return;

  const container = document.getElementById('dpC');
  if (!container) return;

  let html = `<div class="dp-tp ${node?.g || 'module'}">${detail.tp}</div>`;
  html += `<div class="dp-t">${detail.t}</div>`;
  if (node?.auto) html += '<div class="dp-ab">Self-Improving Module</div>';
  html += '<div class="dp-hr"></div>';
  html += `<div class="dp-d">${detail.d}</div>`;
  html += '<div class="dp-hr"></div>';

  if (detail.m) {
    for (const [k, v] of Object.entries(detail.m)) {
      html += `<div class="dp-m"><span class="dp-mk">${k}</span><span class="dp-mv">${v}</span></div>`;
    }
  }

  container.innerHTML = html;
  document.getElementById('dp')?.classList.add('open');
}

export function closePanel() {
  _selectedId = null;
  document.getElementById('dp')?.classList.remove('open');
}
