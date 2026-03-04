/* ═══════════════ DETAIL PANEL — Right side panel for 3D map nodes ═══════════════ */

import { state, subscribe } from '../state.js';
import { enterSubmap } from '../scene/submaps.js';

let _selectedId = null;
let _openModalCb = null;

/**
 * Initialize detail panel.
 * @param {Function} [openModal] - callback for opening node modals
 */
export function initDetailPanel(openModal) {
  _openModalCb = openModal || null;
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

  const submap = state.submaps?.[id];
  const hasSubmap = submap && submap.nodes && submap.nodes.length > 0;
  const edges = _getEdges(id);
  const hasEdges = edges.length > 0;

  // Tab bar
  let html = '<div class="dp-tabs">';
  html += '<button class="dp-tab active" data-tab="overview">Overview</button>';
  if (hasSubmap) html += '<button class="dp-tab" data-tab="submap">Submap</button>';
  if (hasEdges) html += '<button class="dp-tab" data-tab="edges">Edges</button>';
  html += '</div>';

  // Overview tab
  html += '<div class="dp-tab-content active" data-tab="overview">';
  html += `<div class="dp-tp ${node?.g || 'module'}">${detail.tp}</div>`;
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
  html += '</div>';

  // Submap tab
  if (hasSubmap) {
    html += '<div class="dp-tab-content" data-tab="submap">';
    html += `<div class="dp-sub-title">${submap.title || id}</div>`;
    html += `<div class="dp-sub-count">${submap.nodes.length} sub-nodes</div>`;
    html += '<div class="dp-hr"></div>';
    submap.nodes.forEach(sn => {
      const label = typeof sn === 'string' ? sn : (sn.label || sn.id || sn);
      const snId = typeof sn === 'string' ? sn : (sn.id || sn);
      html += `<div class="dp-sub-node" data-subnode="${snId}" data-parent="${id}">${label}</div>`;
    });
    html += `<button class="dp-enter-submap" data-id="${id}">Enter Submap \u2192</button>`;
    html += '</div>';
  }

  // Edges tab
  if (hasEdges) {
    html += '<div class="dp-tab-content" data-tab="edges">';
    const incoming = edges.filter(e => e.t === id);
    const outgoing = edges.filter(e => e.f === id);

    if (outgoing.length) {
      html += '<div class="dp-edge-section">OUTGOING</div>';
      outgoing.forEach(e => {
        const targetNode = state.sysNodes.find(n => n.id === e.t);
        const label = targetNode?.label || e.t;
        html += `<div class="dp-edge-item"><span class="dp-edge-type">${e.tp || e.type || ''}</span><span class="dp-edge-target">\u2192 ${label}</span></div>`;
      });
    }
    if (incoming.length) {
      html += '<div class="dp-edge-section">INCOMING</div>';
      incoming.forEach(e => {
        const sourceNode = state.sysNodes.find(n => n.id === e.f);
        const label = sourceNode?.label || e.f;
        html += `<div class="dp-edge-item"><span class="dp-edge-type">${e.tp || e.type || ''}</span><span class="dp-edge-target">\u2190 ${label}</span></div>`;
      });
    }
    html += '</div>';
  }

  container.innerHTML = html;

  // Wire tab clicks
  container.addEventListener('click', _onTabClick);

  document.getElementById('dp')?.classList.add('open');
}

function _onTabClick(e) {
  const tab = e.target.closest('.dp-tab');
  const enterBtn = e.target.closest('.dp-enter-submap');
  const container = document.getElementById('dpC');
  if (!container) return;

  if (tab) {
    const tabName = tab.dataset.tab;
    container.querySelectorAll('.dp-tab').forEach(t => t.classList.remove('active'));
    container.querySelectorAll('.dp-tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    const content = container.querySelector(`.dp-tab-content[data-tab="${tabName}"]`);
    if (content) content.classList.add('active');
    return;
  }

  if (enterBtn) {
    const id = enterBtn.dataset.id;
    if (id) {
      closePanel();
      enterSubmap(id, state.submaps, state.nodeDetails, _openModalCb);
    }
  }
}

function _getEdges(nodeId) {
  if (!state.sysEdges) return [];
  return state.sysEdges.filter(e => e.f === nodeId || e.t === nodeId);
}

export function closePanel() {
  _selectedId = null;
  const container = document.getElementById('dpC');
  if (container) container.removeEventListener('click', _onTabClick);
  document.getElementById('dp')?.classList.remove('open');
}
