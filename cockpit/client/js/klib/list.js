/* ═══════════════ KLIB LIST — Center panel: 6 group-by renderers ═══════════════
   SOTA: Virtualized-ready, proper event delegation, no inline handlers.       */

import { state } from '../state.js';
import { LAYERS, LAYER_BY_ID, SEVERITY_ORDER, SEVERITY_COLORS, EDGE_TYPES, EDGE_CATEGORIES } from '../schema.js';
import { navigateToNode } from './klib.js';

/**
 * Render the node list grouped by the current mode.
 * @param {Array} nodes - filtered nodes
 * @param {string} groupBy - 'layer'|'severity'|'tag'|'taxonomy'|'edges'|'sources'
 */
export function renderList(nodes, groupBy) {
  const container = document.getElementById('klibNodeList');
  if (!container) return;

  if (nodes.length === 0) {
    container.innerHTML = '<div class="klib-empty"><div class="klib-empty-icon">\u2205</div><div class="klib-empty-text">No nodes match filters</div></div>';
    return;
  }

  switch (groupBy) {
    case 'layer':     _renderByLayer(container, nodes); break;
    case 'severity':  _renderBySeverity(container, nodes); break;
    case 'tag':       _renderByTag(container, nodes); break;
    case 'taxonomy':  _renderByTaxonomy(container, nodes); break;
    case 'edges':     _renderByEdges(container, nodes); break;
    case 'sources':   _renderBySources(container, nodes); break;
    default:          _renderByLayer(container, nodes);
  }

  // Event delegation (single listener, no inline onclick)
  _wireListEvents(container);
}

/* ── Event Delegation ─────────────────────────────────── */

function _wireListEvents(container) {
  // Remove old listener
  container.removeEventListener('click', _handleListClick);
  // Add fresh one
  container.addEventListener('click', _handleListClick);
}

function _handleListClick(e) {
  const container = e.currentTarget;

  // Node item click
  const item = e.target.closest('.kn-item');
  if (item && item.dataset.id) {
    container.querySelectorAll('.kn-item').forEach(x => x.classList.remove('selected'));
    item.classList.add('selected');
    navigateToNode(item.dataset.id);
    return;
  }

  // Group header toggle
  const groupHead = e.target.closest('.kn-group-head');
  if (groupHead) {
    groupHead.parentElement.classList.toggle('open');
    return;
  }

  // Edge card toggle
  const edgeCard = e.target.closest('.kt-edge-card');
  if (edgeCard) {
    edgeCard.classList.toggle('open');
    return;
  }

  // Edge node click (inside edges view)
  const edgeNode = e.target.closest('.kt-edge-node');
  if (edgeNode && edgeNode.dataset.id) {
    navigateToNode(edgeNode.dataset.id);
    return;
  }
}

/* ── Node Item Renderer ───────────────────────────────── */

function _nodeItem(n) {
  const layer = LAYER_BY_ID[n.layer];
  const sev = (n.severity || 'info').toUpperCase();
  const conf = Math.round((n.confidence || 0) * 100);
  const confColor = conf >= 80 ? 'var(--green)' : conf >= 50 ? 'var(--amber)' : 'var(--red)';
  const text = n.text || n.id || 'Untitled';
  const techs = (n.technologies || []).slice(0, 3).join(' \u00b7 ');

  return `<div class="kn-item" data-id="${n.id}">
    <div class="kn-dot" style="background:${layer?.color || '#888'}"></div>
    <div class="kn-body">
      <div class="kn-title">${_esc(text)}</div>
      ${techs ? `<div class="kn-techs">${_esc(techs)}</div>` : ''}
    </div>
    <div class="kn-sev ${sev}">${sev}</div>
    <div class="kn-conf" style="color:${confColor}">${conf}%</div>
  </div>`;
}

function _esc(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ── Group Renderers ──────────────────────────────────── */

function _groupHtml(name, color, count, nodes, open = false) {
  return `<div class="kn-group${open ? ' open' : ''}">
    <div class="kn-group-head">
      <div class="kn-group-accent" style="background:${color}"></div>
      <div class="kn-group-name">${_esc(name)}</div>
      <div class="kn-group-cnt">${count.toLocaleString()}</div>
      <div class="kn-group-chevron">\u25B8</div>
    </div>
    <div class="kn-group-items">
      ${nodes.map(_nodeItem).join('')}
    </div>
  </div>`;
}

function _renderByLayer(container, nodes) {
  let html = '';
  LAYERS.forEach(l => {
    const layerNodes = nodes.filter(n => n.layer === l.id);
    if (!layerNodes.length) return;
    html += _groupHtml(l.name, l.color, layerNodes.length, layerNodes, true);
  });
  container.innerHTML = html;
}

function _renderBySeverity(container, nodes) {
  let html = '';
  SEVERITY_ORDER.forEach(sev => {
    const sevNodes = nodes.filter(n => (n.severity || 'info').toUpperCase() === sev);
    if (!sevNodes.length) return;
    html += _groupHtml(sev, SEVERITY_COLORS[sev], sevNodes.length, sevNodes, sev === 'CRITICAL' || sev === 'HIGH');
  });
  container.innerHTML = html;
}

function _renderByTag(container, nodes) {
  const tagMap = {};
  nodes.forEach(n => {
    const tags = [...(n.technologies || []), ...(n.domains || [])];
    if (tags.length === 0) {
      tagMap['untagged'] = tagMap['untagged'] || [];
      tagMap['untagged'].push(n);
    }
    tags.forEach(t => {
      tagMap[t] = tagMap[t] || [];
      tagMap[t].push(n);
    });
  });

  const sorted = Object.entries(tagMap).sort((a, b) => b[1].length - a[1].length);
  let html = '';
  sorted.slice(0, 50).forEach(([tag, tagNodes]) => {
    html += _groupHtml(tag, 'var(--purple)', tagNodes.length, tagNodes);
  });
  container.innerHTML = html;
}

function _renderByTaxonomy(container, nodes) {
  const domainMap = {};
  nodes.forEach(n => {
    const domains = n.domains?.length ? n.domains : ['general'];
    domains.forEach(d => {
      domainMap[d] = domainMap[d] || [];
      domainMap[d].push(n);
    });
  });

  const sorted = Object.entries(domainMap).sort((a, b) => b[1].length - a[1].length);
  let html = '';
  sorted.forEach(([domain, domNodes]) => {
    html += _groupHtml(domain, 'var(--blue)', domNodes.length, domNodes);
  });
  container.innerHTML = html;
}

/**
 * FIXED: Edges view now shows actual nodes grouped by their edge type connections,
 * not just schema metadata. Shows which nodes participate in each edge type.
 */
function _renderByEdges(container, nodes) {
  // Build a map: edge type → list of involved nodes (from filtered set)
  const nodeIds = new Set(nodes.map(n => n.id));
  const edgeTypeNodes = {};

  for (const edge of (state.edges || [])) {
    const type = edge.type || 'UNKNOWN';
    // Only include edges where at least one end is in the filtered set
    const srcIn = nodeIds.has(edge.from);
    const tgtIn = nodeIds.has(edge.to);
    if (!srcIn && !tgtIn) continue;

    if (!edgeTypeNodes[type]) edgeTypeNodes[type] = new Set();
    if (srcIn) edgeTypeNodes[type].add(edge.from);
    if (tgtIn) edgeTypeNodes[type].add(edge.to);
  }

  // Resolve node IDs to actual node objects
  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  let html = '';

  EDGE_CATEGORIES.forEach(cat => {
    const edgeTypesInCat = Object.entries(EDGE_TYPES)
      .filter(([, v]) => v.cat === cat);

    if (!edgeTypesInCat.length) return;

    let catHasNodes = false;
    let catHtml = '';

    edgeTypesInCat.forEach(([typeName, typeInfo]) => {
      const nodeIdsForType = edgeTypeNodes[typeName];
      if (!nodeIdsForType || nodeIdsForType.size === 0) return;

      const typeNodes = [];
      for (const id of nodeIdsForType) {
        const n = nodeMap.get(id);
        if (n) typeNodes.push(n);
      }
      if (!typeNodes.length) return;

      catHasNodes = true;
      typeNodes.sort((a, b) => (b.confidence || 0) - (a.confidence || 0));

      catHtml += `<div class="kt-edge-card">
        <div class="kt-edge-card-head">
          <div class="kt-edge-card-dot" style="background:${typeInfo.color}"></div>
          <div class="kt-edge-card-name">${typeName}</div>
          <div class="kt-edge-card-count">${typeNodes.length.toLocaleString()}</div>
          <div class="kt-edge-card-chevron">\u25B8</div>
        </div>
        <div class="kt-edge-detail">
          <div class="kt-edge-desc">${_esc(typeInfo.desc)}</div>
          <div class="kt-edge-nodes">
            ${typeNodes.slice(0, 50).map(n => {
              const layer = LAYER_BY_ID[n.layer];
              return `<div class="kt-edge-node kn-item" data-id="${n.id}">
                <div class="kn-dot" style="background:${layer?.color || '#888'}"></div>
                <div class="kn-title">${_esc(n.text || n.id)}</div>
              </div>`;
            }).join('')}
            ${typeNodes.length > 50 ? `<div class="kt-edge-more">+${typeNodes.length - 50} more</div>` : ''}
          </div>
        </div>
      </div>`;
    });

    if (catHasNodes) {
      const catColor = edgeTypesInCat[0]?.[1]?.color || '#888';
      html += `<div class="kt-edge-section">
        <div class="kt-edge-head">
          <div class="kt-edge-dot" style="background:${catColor}"></div>
          <div class="kt-edge-cat" style="color:${catColor}">${_esc(cat)}</div>
        </div>
        ${catHtml}
      </div>`;
    }
  });

  if (!html) {
    html = '<div class="klib-empty"><div class="klib-empty-icon">\u2205</div><div class="klib-empty-text">No edge connections found</div></div>';
  }

  container.innerHTML = html;
}

function _renderBySources(container, nodes) {
  const typeMap = {};
  nodes.forEach(n => {
    const type = n.type || 'Unknown';
    typeMap[type] = typeMap[type] || [];
    typeMap[type].push(n);
  });

  const sorted = Object.entries(typeMap).sort((a, b) => b[1].length - a[1].length);
  let html = '';
  sorted.forEach(([type, typeNodes]) => {
    html += _groupHtml(type, 'var(--green)', typeNodes.length, typeNodes);
  });
  container.innerHTML = html;
}
