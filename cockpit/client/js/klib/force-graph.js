/* ═══════════════ FORCE GRAPH — SOTA 3D Knowledge Graph ═══════════════
   3d-force-graph (vasturiano) + d3-force-3d.
   LAZY LOADED — modules download only when graph view is opened.
   Layout cached in localStorage — first load simulates, then instant.
   ═══════════════════════════════════════════════════════════════════ */

import { LAYERS, LAYER_BY_ID, EDGE_TYPES, SEVERITY_COLORS } from '../schema.js';
import { state } from '../state.js';
import { navigateToNode } from './klib.js';

/* ── Visual Config ────────────────────────────────────── */

const TAG_COLORS = { Tech: '#94a3b8', Domain: '#e8a948' };
const EDGE_COLORS = { IN_DOMAIN: '#e8a948', APPLIES_TO: '#60a5fa', USED_IN: '#5eead4' };
const LAYER_Y = { 0: -180, 1: -100, 2: -20, 3: 60 };
const LAYER_Y_STRENGTH = 0.04;

/* ── Lazy-loaded modules ──────────────────────────────── */

let _ForceGraph3D = null;
let _forceY = null;
let _libsReady = false;
let _libsLoading = false;

async function _ensureLibs() {
  if (_libsReady) return;
  if (_libsLoading) {
    // Wait for in-flight load
    while (!_libsReady) await new Promise(r => setTimeout(r, 50));
    return;
  }
  _libsLoading = true;
  const [fgMod, d3Mod] = await Promise.all([
    import('3d-force-graph'),
    import('d3-force-3d'),
  ]);
  _ForceGraph3D = fgMod.default;
  _forceY = d3Mod.forceY;
  _libsReady = true;
  _libsLoading = false;
}

/* ── State ─────────────────────────────────────────────── */

let _graph = null;
let _container = null;
let _hoverNode = null;
let _legendEl = null;
let _loadingEl = null;
let _adj = null;

/* ══════════════════════════════════════════════════════════
   PUBLIC API
   ══════════════════════════════════════════════════════════ */

export async function initForceGraph(rawNodes, rawEdges) {
  const container = document.getElementById('klibGraph');
  if (!container) return;
  destroyForceGraph();
  _container = container;

  // Show loading while libs download
  _showLoading('Loading 3D engine...');

  await _ensureLibs();

  const { nodes, links } = _prepareData(rawNodes, rawEdges);
  if (!nodes.length) { _hideLoading(); return; }

  /* ── Check layout cache ── */
  const cached = _loadCache(nodes, links);
  if (cached) {
    for (const n of nodes) {
      const p = cached[n.id];
      if (p) { n.x = p.x; n.y = p.y; n.z = p.z; }
    }
    _showLoading('Rendering...');
  } else {
    _showLoading('Calculating layout (first time only)...');
  }

  // Yield to browser to paint loading message
  await new Promise(r => requestAnimationFrame(r));

  /* ── Create graph ── */
  _graph = _ForceGraph3D({ controlType: 'orbit' })(container);

  _graph
    .backgroundColor('#000000')
    .showNavInfo(false)
    .width(container.clientWidth || 800)
    .height(container.clientHeight || 600);

  /* ── Nodes ── */
  _graph
    .nodeId('id')
    .nodeVal(n => n._isTag ? 1 + Math.log2(1 + n._ec) * 2.5 : 2)
    .nodeColor(n => _nodeColor(n))
    .nodeOpacity(0.9)
    .nodeResolution(6)
    .nodeLabel(n => _nodeTooltip(n));

  /* ── Links ── */
  _graph
    .linkSource('source')
    .linkTarget('target')
    .linkColor(l => _linkColor(l))
    .linkOpacity(0.25)
    .linkWidth(0)
    .linkDirectionalParticles(0)
    .linkLabel(l => _linkTooltip(l));

  /* ── Events ── */
  _graph
    .onNodeClick(_onNodeClick)
    .onNodeHover(_onNodeHover)
    .onNodeDragEnd(n => { n.fx = n.x; n.fy = n.y; n.fz = n.z; })
    .onBackgroundClick(_onBgClick);

  /* ── Physics ── */
  if (cached) {
    _graph
      .d3AlphaDecay(0.1)
      .d3VelocityDecay(0.6)
      .warmupTicks(0)
      .cooldownTicks(5)
      .cooldownTime(300);
  } else {
    _graph
      .d3AlphaDecay(0.02)
      .d3VelocityDecay(0.3)
      .warmupTicks(0)
      .cooldownTicks(500)
      .cooldownTime(20000)
      .onEngineStop(() => {
        _saveCache(_graph?.graphData()?.nodes, links);
      });
  }

  _graph.d3Force('layerY', _forceY()
    .y(n => n._isTag ? 0 : (LAYER_Y[n.layer] ?? 0))
    .strength(n => n._isTag ? 0 : LAYER_Y_STRENGTH)
  );
  _graph.d3Force('charge').strength(-30).distanceMax(250);
  _graph.d3Force('link').distance(40).strength(0.03);

  /* ── Load data ── */
  _graph.graphData({ nodes, links });

  _hideLoading();
  _createLegend(nodes, links);

  /* ── Camera ── */
  setTimeout(() => {
    if (_graph) _graph.cameraPosition({ x: 0, y: 300, z: 500 }, { x: 0, y: 0, z: 0 }, 0);
  }, 100);

  /* ── Resize ── */
  const ro = new ResizeObserver(() => {
    if (_graph && _container) _graph.width(_container.clientWidth).height(_container.clientHeight);
  });
  ro.observe(container);
  _graph._ro = ro;
}

export function destroyForceGraph() {
  if (_graph) {
    if (_graph._ro) { _graph._ro.disconnect(); _graph._ro = null; }
    _graph._destructor();
    _graph = null;
  }
  if (_legendEl) { _legendEl.remove(); _legendEl = null; }
  _hideLoading();
  if (_container) {
    while (_container.firstChild) _container.firstChild.remove();
    _container = null;
  }
  _hoverNode = null;
  _adj = null;
}

/* ══════════════════════════════════════════════════════════
   LOADING INDICATOR
   ══════════════════════════════════════════════════════════ */

function _showLoading(msg) {
  if (!_container) return;
  if (!_loadingEl) {
    _loadingEl = document.createElement('div');
    _loadingEl.className = 'fg-loading';
    _container.appendChild(_loadingEl);
  }
  _loadingEl.textContent = msg;
  _loadingEl.style.display = 'flex';
}

function _hideLoading() {
  if (_loadingEl) { _loadingEl.style.display = 'none'; }
}

/* ══════════════════════════════════════════════════════════
   RENDERING HELPERS
   ══════════════════════════════════════════════════════════ */

function _nodeColor(n) {
  if (n._isTag) return TAG_COLORS[n.type] || '#8899aa';
  return LAYER_BY_ID[n.layer]?.color || '#888';
}

function _linkColor(l) {
  return EDGE_COLORS[l.type] || (EDGE_TYPES[l.type] || {}).color || '#444';
}

function _esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function _nodeTooltip(n) {
  if (n._isTag) {
    const col = TAG_COLORS[n.type] || '#8899aa';
    return `<div style="text-align:center;font-family:Inter,system-ui;padding:6px 8px">
      <div style="font-size:8px;font-weight:700;color:${col};letter-spacing:1px;text-transform:uppercase;margin-bottom:3px">${n.type || 'Tag'}</div>
      <div style="font-weight:700;font-size:14px;color:#fff;margin-bottom:4px">${_esc(n.text || n.id)}</div>
      <div style="font-size:10px;color:#6b8fff">${n._ec} connections</div>
    </div>`;
  }
  const layer = LAYER_BY_ID[n.layer];
  const conf = Math.round((n.confidence || 0) * 100);
  const sev = (n.severity || 'info').toUpperCase();
  const sevCol = SEVERITY_COLORS[sev] || '#8b95aa';
  return `<div style="text-align:center;font-family:Inter,system-ui;max-width:320px;padding:6px 8px">
    <div style="font-size:8px;font-weight:700;color:${layer?.color || '#888'};letter-spacing:1px;text-transform:uppercase;margin-bottom:3px">${layer?.name || ''}</div>
    <div style="font-weight:700;font-size:13px;color:#fff;line-height:1.3;margin-bottom:6px">${_esc((n.text || n.id).slice(0, 120))}</div>
    <div style="display:flex;gap:8px;justify-content:center;align-items:center">
      <span style="font-size:8px;font-weight:700;padding:2px 6px;border-radius:3px;background:${sevCol}25;color:${sevCol}">${sev}</span>
      <span style="font-size:11px;font-weight:700;color:${conf >= 80 ? '#34d399' : conf >= 50 ? '#fbbf24' : '#ef4444'}">${conf}%</span>
      <span style="font-size:10px;color:#6b8fff">${n._ec} edges</span>
    </div>
    ${n.technologies?.length ? `<div style="font-size:9px;color:#5eead4;margin-top:4px">${n.technologies.slice(0, 6).join(' \u00b7 ')}</div>` : ''}
  </div>`;
}

function _linkTooltip(l) {
  const et = EDGE_TYPES[l.type] || {};
  const col = EDGE_COLORS[l.type] || et.color || '#888';
  return `<div style="font-family:Inter,system-ui;text-align:center;padding:4px 8px">
    <div style="font-size:11px;font-weight:700;color:${col}">${l.type || 'unknown'}</div>
    <div style="font-size:9px;color:#8b95aa">${et.desc || ''}</div>
  </div>`;
}

/* ══════════════════════════════════════════════════════════
   EVENTS
   ══════════════════════════════════════════════════════════ */

function _onNodeClick(node) {
  if (!node || !_graph) return;
  navigateToNode(node.id);
  const d = 80;
  _graph.cameraPosition(
    { x: node.x + d, y: node.y + d * 0.3, z: node.z + d },
    { x: node.x, y: node.y, z: node.z },
    1000
  );
}

function _onNodeHover(node) {
  if (!_container || !_graph) return;
  _container.style.cursor = node ? 'pointer' : 'grab';
  _hoverNode = node;

  if (node) {
    const neighbors = _adj?.[node.id];
    const conn = new Set([node.id]);
    if (neighbors) for (const nid of neighbors) conn.add(nid);

    _graph.nodeColor(n => conn.has(n.id) ? _nodeColor(n) : '#111118');
    _graph
      .linkWidth(l => {
        const src = typeof l.source === 'object' ? l.source.id : l.source;
        const tgt = typeof l.target === 'object' ? l.target.id : l.target;
        return (src === node.id || tgt === node.id) ? 2.5 : 0;
      })
      .linkColor(l => {
        const src = typeof l.source === 'object' ? l.source.id : l.source;
        const tgt = typeof l.target === 'object' ? l.target.id : l.target;
        return (src === node.id || tgt === node.id) ? _linkColor(l) : '#060608';
      });
  } else {
    _resetVisuals();
  }
}

function _onBgClick() {
  _hoverNode = null;
  _resetVisuals();
}

function _resetVisuals() {
  if (!_graph) return;
  _graph
    .nodeColor(n => _nodeColor(n))
    .linkWidth(0)
    .linkColor(l => _linkColor(l));
}

/* ══════════════════════════════════════════════════════════
   DATA PREPARATION
   ══════════════════════════════════════════════════════════ */

function _prepareData(rawNodes, rawEdges) {
  const idSet = new Set(rawNodes.map(n => n.id));

  const ec = {};
  const validEdges = [];
  for (const e of rawEdges) {
    if (!idSet.has(e.from) || !idSet.has(e.to) || e.from === e.to) continue;
    validEdges.push(e);
    ec[e.from] = (ec[e.from] || 0) + 1;
    ec[e.to] = (ec[e.to] || 0) + 1;
  }

  const nodes = rawNodes.map(n => ({
    id: n.id,
    text: n.text || n.id,
    layer: n.layer,
    severity: n.severity || 'info',
    confidence: n.confidence || 0.5,
    technologies: n.technologies || [],
    domains: n.domains || [],
    type: n.type || '',
    _isTag: n.layer === -1 || n.type === 'Tech' || n.type === 'Domain',
    _ec: ec[n.id] || 0,
  }));

  const links = validEdges.map(e => ({
    source: e.from,
    target: e.to,
    type: e.type || '',
  }));

  _adj = {};
  for (const l of links) {
    (_adj[l.source] || (_adj[l.source] = new Set())).add(l.target);
    (_adj[l.target] || (_adj[l.target] = new Set())).add(l.source);
  }

  return { nodes, links };
}

/* ══════════════════════════════════════════════════════════
   LEGEND OVERLAY
   ══════════════════════════════════════════════════════════ */

function _createLegend(nodes, links) {
  if (_legendEl) _legendEl.remove();

  const typeCounts = {};
  for (const n of nodes) {
    const key = n._isTag ? n.type : (LAYER_BY_ID[n.layer]?.shortName || `L${n.layer}`);
    typeCounts[key] = (typeCounts[key] || 0) + 1;
  }
  const edgeCounts = {};
  for (const l of links) edgeCounts[l.type] = (edgeCounts[l.type] || 0) + 1;

  const el = document.createElement('div');
  el.className = 'fg-legend';

  const layerItems = LAYERS.filter(ly => typeCounts[ly.shortName]).map(ly =>
    `<div class="fg-legend-item"><span class="fg-dot" style="background:${ly.color}"></span><span class="fg-lbl">${ly.shortName}</span><span class="fg-cnt">${(typeCounts[ly.shortName] || 0).toLocaleString()}</span></div>`
  ).join('');

  const tagItems = Object.entries(TAG_COLORS).filter(([t]) => typeCounts[t]).map(([t, col]) =>
    `<div class="fg-legend-item"><span class="fg-dot" style="background:${col}"></span><span class="fg-lbl">${t}</span><span class="fg-cnt">${(typeCounts[t] || 0).toLocaleString()}</span></div>`
  ).join('');

  const edgeItems = Object.entries(edgeCounts).sort((a, b) => b[1] - a[1]).map(([type, count]) => {
    const col = EDGE_COLORS[type] || (EDGE_TYPES[type] || {}).color || '#555';
    return `<div class="fg-legend-item"><span class="fg-line" style="background:${col}"></span><span class="fg-lbl">${type}</span><span class="fg-cnt">${count.toLocaleString()}</span></div>`;
  }).join('');

  el.innerHTML = `
    <div class="fg-legend-section"><div class="fg-legend-title">Nodes</div>${layerItems}${tagItems}</div>
    <div class="fg-legend-section"><div class="fg-legend-title">Edges</div>${edgeItems}</div>
    <div class="fg-legend-foot">${nodes.length.toLocaleString()} nodes &middot; ${links.length.toLocaleString()} edges</div>
  `;
  _container.appendChild(el);
  _legendEl = el;
}

/* ══════════════════════════════════════════════════════════
   LAYOUT CACHE — localStorage
   ══════════════════════════════════════════════════════════ */

const CACHE_PREFIX = 'fg-layout-';

function _cacheKey(nodes, links) {
  return CACHE_PREFIX + nodes.length + '-' + links.length;
}

function _loadCache(nodes, links) {
  try {
    const raw = localStorage.getItem(_cacheKey(nodes, links));
    if (!raw) return null;
    const positions = JSON.parse(raw);
    if (Object.keys(positions).length < nodes.length * 0.8) return null;
    return positions;
  } catch { return null; }
}

function _saveCache(graphNodes, links) {
  if (!graphNodes?.length) return;
  try {
    const positions = {};
    for (const n of graphNodes) {
      if (n.x !== undefined) positions[n.id] = { x: n.x, y: n.y, z: n.z };
    }
    const key = _cacheKey(graphNodes, links);
    localStorage.setItem(key, JSON.stringify(positions));
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k?.startsWith(CACHE_PREFIX) && k !== key) localStorage.removeItem(k);
    }
  } catch { /* quota */ }
}
