/* ═══════════════ KLIB DETAIL — Right panel: SOTA node inspector ═══════════════
   Tabs: Properties, Connections, Raw. Full epistemic visualization.
   Edge targets show resolved names, not raw IDs. Proper null checks.          */

import { state } from '../state.js';
import { LAYER_BY_ID, SEVERITY_COLORS, EDGE_TYPES } from '../schema.js';
import { navigateToNode } from './klib.js';

// Cache for resolving node IDs → display names
let _nodeNameCache = null;

function _getNodeName(nodeId) {
  if (!_nodeNameCache) {
    _nodeNameCache = new Map();
    for (const n of (state.nodes || [])) {
      _nodeNameCache.set(n.id, n.text || n.id);
    }
  }
  return _nodeNameCache.get(nodeId) || nodeId;
}

function _esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Render the detail panel for a selected knowledge node.
 * @param {string} nodeId
 */
export function renderDetail(nodeId) {
  const container = document.getElementById('klibDetail');
  if (!container) return;

  // Invalidate name cache when nodes change
  _nodeNameCache = null;

  const node = (state.nodes || []).find(n => n.id === nodeId);
  if (!node) {
    container.innerHTML = `<div class="klib-detail-empty">
      <div style="font-size:24px;opacity:.3;margin-bottom:8px">\u2205</div>
      <div>Select a node to view details</div>
    </div>`;
    return;
  }

  const layer = LAYER_BY_ID[node.layer];
  const sev = (node.severity || 'info').toUpperCase();
  const conf = Math.round((node.confidence || 0) * 100);
  const confColor = conf >= 80 ? 'var(--green)' : conf >= 50 ? 'var(--amber)' : 'var(--red)';
  const outEdges = node.outEdges || [];
  const inEdges = node.inEdges || [];
  const allTags = [...(node.technologies || []), ...(node.domains || [])];

  let html = '<div class="klib-detail-content">';

  /* ── Header ── */
  html += `<div class="kd-header">
    <div class="kd-layer-badge" style="background:${layer?.color || '#888'}20;color:${layer?.color || '#888'}">${_esc(layer?.name || 'Unknown')}</div>
    <div class="kd-title">${_esc(node.text || node.id)}</div>
    <div class="kd-meta">
      <div class="kn-sev ${sev}">${sev}</div>
      <div class="kd-conf-bar"><div class="kd-conf-fill" style="width:${conf}%;background:${confColor}"></div></div>
      <div class="kd-conf-val" style="color:${confColor}">${conf}%</div>
    </div>
    <div class="kd-id">${_esc(node.id)}</div>
  </div>`;

  /* ── Type badge ── */
  if (node.type) {
    html += `<div class="kd-type-badge">${_esc(node.type)}</div>`;
  }

  /* ── Epistemic Status (E0-E5 ladder) ── */
  if (node.epistemicStatus) {
    const eColors = {E0:'#8b95aa',E1:'#6b8fff',E2:'#34d399',E3:'#fbbf24',E4:'#9b7cff',E5:'#ff6b6b'};
    const eNames = {E0:'Rumor',E1:'Hypothesis',E2:'Observation',E3:'Tested',E4:'Proven',E5:'Axiom'};
    const ec = eColors[node.epistemicStatus] || '#8b95aa';
    const en = eNames[node.epistemicStatus] || node.epistemicStatus;
    html += `<div style="margin:6px 0"><span style="display:inline-block;padding:2px 8px;border-radius:4px;background:${ec}22;color:${ec};border:1px solid ${ec}44;font-size:11px;font-weight:600">⬡ ${node.epistemicStatus} — ${en}</span></div>`;
  }

  /* ── Freshness (from Predictive Decay Engine) ── */
  if (node.freshness != null) {
    const fp = Math.round(node.freshness * 100);
    const fc = fp >= 70 ? '#34d399' : fp >= 40 ? '#fbbf24' : '#ef4444';
    html += `<div style="margin:4px 0;font-size:11px;color:#8b95aa">Freshness</div>`;
    html += `<div style="height:6px;background:#1a1d23;border-radius:3px;overflow:hidden;margin-bottom:8px"><div style="height:100%;width:${fp}%;background:${fc};border-radius:3px"></div></div>`;
  }

  /* ── WHY ── */
  if (node.why) {
    html += _section('Why', `<div class="kd-text">${_esc(node.why)}</div>`);
  }

  /* ── HOW ── */
  if (node.howTo) {
    html += _section('How to do it right', `<div class="kd-code">${_esc(node.howTo)}</div>`);
  }

  /* ── When to use / not use ── */
  if (node.whenToUse) {
    html += _section('When to Use', `<div class="kd-text">${_esc(node.whenToUse)}</div>`);
  }
  if (node.whenNotToUse) {
    html += _section('When NOT to Use', `<div class="kd-text kd-text-warn">${_esc(node.whenNotToUse)}</div>`);
  }

  /* ── Examples ── */
  if (node.exampleGood) {
    html += _section('Good Example', `<div class="kd-code kd-code-good">${_esc(node.exampleGood)}</div>`);
  }
  if (node.exampleBad) {
    html += _section('Bad Example', `<div class="kd-code kd-code-bad">${_esc(node.exampleBad)}</div>`);
  }

  /* ── Epistemic Opinion (Subjective Logic) ── */
  if (node.opinion) {
    const op = node.opinion;
    const b = op.b || 0, d = op.d || 0, u = op.u || 0, a = op.a || 0.5;
    const projected = b + a * u;
    html += _section('Epistemic Opinion', `
      <div class="kd-opinion">
        <div class="kd-opinion-bars">
          <div class="kd-opinion-bar">
            <div class="kd-opinion-label">Belief</div>
            <div class="kd-opinion-track">
              <div class="kd-opinion-fill kd-b" style="width:${b * 100}%"></div>
            </div>
            <div class="kd-opinion-val">${(b * 100).toFixed(0)}%</div>
          </div>
          <div class="kd-opinion-bar">
            <div class="kd-opinion-label">Disbelief</div>
            <div class="kd-opinion-track">
              <div class="kd-opinion-fill kd-d" style="width:${d * 100}%"></div>
            </div>
            <div class="kd-opinion-val">${(d * 100).toFixed(0)}%</div>
          </div>
          <div class="kd-opinion-bar">
            <div class="kd-opinion-label">Uncertainty</div>
            <div class="kd-opinion-track">
              <div class="kd-opinion-fill kd-u" style="width:${u * 100}%"></div>
            </div>
            <div class="kd-opinion-val">${(u * 100).toFixed(0)}%</div>
          </div>
        </div>
        <div class="kd-opinion-footer">
          <span>Base rate: ${(a * 100).toFixed(0)}%</span>
          <span>Projected: <strong style="color:var(--green)">${(projected * 100).toFixed(0)}%</strong></span>
        </div>
      </div>
    `);
  }

  /* ── Outgoing Edges ── */
  if (outEdges.length > 0) {
    const edgeHtml = outEdges.map(e => {
      const et = EDGE_TYPES[e.type] || {};
      const targetName = _getNodeName(e.to);
      return `<div class="kd-edge" data-target="${_esc(e.to)}">
        <div class="kd-edge-arrow" style="color:${et.color || '#888'}">\u2192</div>
        <div class="kd-edge-type" style="color:${et.color || '#888'}">${_esc(e.type)}</div>
        <div class="kd-edge-target">${_esc(targetName)}</div>
      </div>`;
    }).join('');
    html += _section(`Outgoing Edges (${outEdges.length})`, `<div class="kd-edge-list">${edgeHtml}</div>`);
  }

  /* ── Incoming Edges (Backlinks) ── */
  if (inEdges.length > 0) {
    const backlinkHtml = inEdges.map(e => {
      const et = EDGE_TYPES[e.type] || {};
      const sourceName = _getNodeName(e.from);
      return `<div class="kd-backlink" data-target="${_esc(e.from)}">
        <div class="kd-backlink-arrow" style="color:${et.color || '#6b8fff'}">\u2190</div>
        <div class="kd-backlink-type" style="color:${et.color || '#6b8fff'}">${_esc(e.type)}</div>
        <div class="kd-backlink-name">${_esc(sourceName)}</div>
      </div>`;
    }).join('');
    html += _section(`Backlinks (${inEdges.length})`, `<div class="kd-edge-list">${backlinkHtml}</div>`);
  }

  /* ── Tags ── */
  if (allTags.length > 0) {
    const techTags = (node.technologies || []).map(t =>
      `<div class="kd-tag kd-tag-tech" data-tag="${_esc(t)}">${_esc(t)}</div>`
    ).join('');
    const domTags = (node.domains || []).map(d =>
      `<div class="kd-tag kd-tag-domain" data-tag="${_esc(d)}">${_esc(d)}</div>`
    ).join('');
    html += _section('Tags', `<div class="kd-tags">${techTags}${domTags}</div>`);
  }

  /* ── Stats ── */
  html += `<div class="kd-stats">
    <div class="kd-stat"><span class="kd-stat-n">${outEdges.length}</span><span class="kd-stat-l">Out</span></div>
    <div class="kd-stat"><span class="kd-stat-n">${inEdges.length}</span><span class="kd-stat-l">In</span></div>
    <div class="kd-stat"><span class="kd-stat-n">${allTags.length}</span><span class="kd-stat-l">Tags</span></div>
  </div>`;

  html += '</div>';
  container.innerHTML = html;

  /* ── Wire edge/backlink navigation ── */
  container.querySelectorAll('.kd-edge, .kd-backlink').forEach(el => {
    el.addEventListener('click', () => {
      const target = el.dataset.target;
      if (target) navigateToNode(target);
    });
  });

  /* ── Wire tag clicks → filter by tag ── */
  container.querySelectorAll('.kd-tag').forEach(el => {
    el.addEventListener('click', () => {
      const tag = el.dataset.tag;
      if (!tag) return;
      const current = [...(state.klibFilters.tags || [])];
      if (!current.includes(tag)) {
        current.push(tag);
        state.klibFilters = { ...state.klibFilters, tags: current };
      }
    });
  });
}

function _section(label, content) {
  return `<div class="kd-section">
    <div class="kd-section-label">${label}</div>
    ${content}
  </div>`;
}
