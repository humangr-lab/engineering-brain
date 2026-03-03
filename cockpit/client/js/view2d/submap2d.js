/* ═══════════════ 2D SUBMAP — SVG Drill-Down ═══════════════
   Same visual language as main map: shapes, pills, orbital.
   Platform background, confidence rings, animated edges.
   ═════════════════════════════════════════════════════════ */

const GC = {
  source:   { hex: '#34d399', rgb: '52,211,153', pill: 'rgba(40,160,110,.85)' },
  layer:    { hex: '#6b8fff', rgb: '107,143,255', pill: 'rgba(90,120,220,.85)' },
  module:   { hex: '#9b7cff', rgb: '155,124,255', pill: 'rgba(120,95,210,.85)' },
  consumer: { hex: '#5eead4', rgb: '94,234,212', pill: 'rgba(60,180,170,.85)' },
};

const EC = { green: '#34d399', blue: '#6b8fff', purple: '#9b7cff', cyan: '#5eead4', white: '#8899bb' };

let _nodeEls = new Map();
let _edgeEls = [];
let _smNodes = [];
let _smEdges = [];
let _callbacks = null;
let _savedMainContent = '';

// ── Public API ──

export function renderSubmap(svgEl, submapData, nodeDetails, smColor, callbacks) {
  _callbacks = callbacks;
  _smNodes = submapData.nodes || [];
  _smEdges = submapData.edges || [];
  _savedMainContent = svgEl.innerHTML;

  svgEl.innerHTML = '';
  _nodeEls.clear();
  _edgeEls = [];

  const gc = GC[smColor] || GC.module;
  const SCALE = 22;

  const pad = 130;
  const xs = _smNodes.map(n => n.x);
  const zs = _smNodes.map(n => n.z);
  const minX = Math.min(...xs) - 4;
  const maxX = Math.max(...xs) + 4;
  const minZ = Math.min(...zs) - 4;
  const maxZ = Math.max(...zs) + 4;
  const vbX = minX * SCALE - pad;
  const vbY = minZ * SCALE - pad;
  const vbW = (maxX - minX) * SCALE + pad * 2;
  const vbH = (maxZ - minZ) * SCALE + pad * 2;

  svgEl.setAttribute('viewBox', `${vbX} ${vbY} ${vbW} ${vbH}`);

  // ── Defs ──
  const defs = _el('defs');
  _addGridPattern(defs, 'v2d-grid-sm');
  _addArrowMarkers(defs, 'arr-sm');
  _addGlowFilter(defs, 'v2d-glow-sm', 4);
  svgEl.appendChild(defs);

  // Background
  svgEl.appendChild(_el('rect', { x: vbX, y: vbY, width: vbW, height: vbH, fill: 'url(#v2d-grid-sm)' }));

  // Platform
  const pp = 50;
  svgEl.appendChild(_el('rect', {
    class: 'v2d-platform',
    x: minX * SCALE - pp, y: minZ * SCALE - pp,
    width: (maxX - minX) * SCALE + pp * 2,
    height: (maxZ - minZ) * SCALE + pp * 2,
    rx: 20, fill: `rgba(${gc.rgb},0.04)`,
    stroke: `rgba(${gc.rgb},0.1)`, 'stroke-width': 1,
  }));

  const wrapper = _el('g', { class: 'v2d-submap-enter' });

  // ── Edges ──
  const posMap = new Map();
  _smNodes.forEach(n => posMap.set(n.id, { x: n.x * SCALE, y: n.z * SCALE }));

  const edgeG = _el('g');
  _smEdges.forEach(e => {
    const from = posMap.get(e.f);
    const to = posMap.get(e.t);
    if (!from || !to) return;
    const el = _el('path', {
      d: _bezier(from, to),
      class: `v2d-edge v2d-edge--${e.c}`,
      'data-from': e.f, 'data-to': e.t,
      'marker-end': `url(#arr-sm-${e.c})`,
    });
    edgeG.appendChild(el);
    _edgeEls.push({ el, from: e.f, to: e.t });
  });
  wrapper.appendChild(edgeG);

  // ── Nodes ──
  const nodeG = _el('g');
  _smNodes.forEach((n, i) => {
    const isHero = !!n.hero;
    const r = isHero ? 12 : 7;
    const cx = n.x * SCALE;
    const cy = n.z * SCALE;

    const outer = _el('g', { transform: `translate(${cx},${cy})` });
    const inner = _el('g', { class: 'v2d-node', 'data-id': n.id, style: `--i:${i}` });

    // Ground ring
    inner.appendChild(_el('circle', {
      cx: 0, cy: 0, r: r + 3,
      fill: 'none', stroke: gc.hex, 'stroke-width': 0.5, opacity: 0.12,
    }));

    // Glow (hero)
    if (isHero) {
      inner.appendChild(_el('circle', {
        cx: 0, cy: 0, r: r + 2,
        fill: gc.hex, opacity: 0.08,
        filter: 'url(#v2d-glow-sm)',
      }));
    }

    // Shape body
    inner.appendChild(_el('circle', {
      cx: 0, cy: 0, r,
      fill: `rgba(${gc.rgb},0.15)`,
      stroke: gc.hex, 'stroke-width': isHero ? 1.8 : 1,
      class: 'v2d-shape',
    }));

    // Inner detail circle
    inner.appendChild(_el('circle', { cx: 0, cy: 0, r: r * 0.4, fill: gc.hex, opacity: 0.2 }));

    // Confidence ring
    const nd = nodeDetails?.[n.id];
    if (nd?.conf != null) {
      const confColor = nd.conf < 0.1 ? '#34d399' : nd.conf < 0.2 ? '#f59e0b' : nd.conf < 0.4 ? '#f97316' : '#ef4444';
      const arcEnd = Math.min(nd.conf, 1) * Math.PI * 2;
      const cr = r + 1;
      // SVG arc
      if (arcEnd > 0.01) {
        const x1 = Math.sin(0) * cr;
        const y1 = -Math.cos(0) * cr;
        const x2 = Math.sin(arcEnd) * cr;
        const y2 = -Math.cos(arcEnd) * cr;
        const large = arcEnd > Math.PI ? 1 : 0;
        inner.appendChild(_el('path', {
          d: `M${x1},${y1} A${cr},${cr} 0 ${large} 1 ${x2},${y2}`,
          fill: 'none', stroke: confColor, 'stroke-width': 2,
          'stroke-linecap': 'round', opacity: 0.7,
        }));
      }
    }

    // Pill label
    const labelY = -(r + 8);
    const pillW = n.label.length * 5.8 + 18;
    const pillH = isHero ? 18 : 15;
    const pillG = _el('g', { transform: `translate(0,${labelY})` });
    pillG.appendChild(_el('rect', {
      x: -pillW / 2, y: -pillH / 2, width: pillW, height: pillH,
      rx: pillH / 2, fill: gc.pill, opacity: isHero ? 1 : 0.9,
    }));
    pillG.appendChild(_textEl(n.label, {
      x: 0, y: 1, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
      class: 'v2d-pill-text' + (isHero ? ' hero' : ''),
    }));
    inner.appendChild(pillG);

    // Subtitle
    inner.appendChild(_textEl(n.sub, {
      x: 0, y: r + 12, 'text-anchor': 'middle', class: 'v2d-sub-text',
    }));

    // Events
    outer.style.cursor = 'pointer';
    outer.addEventListener('mouseenter', ev => {
      _highlight(n.id);
      if (_callbacks?.onSubNodeHover) _callbacks.onSubNodeHover(n, ev);
    });
    outer.addEventListener('mouseleave', () => {
      _clearHighlight();
      if (_callbacks?.onSubNodeLeave) _callbacks.onSubNodeLeave();
    });
    outer.addEventListener('click', () => {
      if (_callbacks?.onSubNodeClick) _callbacks.onSubNodeClick(n.id);
    });

    outer.appendChild(inner);
    nodeG.appendChild(outer);
    _nodeEls.set(n.id, inner);
  });
  wrapper.appendChild(nodeG);
  svgEl.appendChild(wrapper);

  requestAnimationFrame(() => _nodeEls.forEach(el => el.classList.add('enter')));
}

export function exitSubmap2d(svgEl) {
  const w = svgEl.querySelector('.v2d-submap-enter');
  if (w) { w.classList.remove('v2d-submap-enter'); w.classList.add('v2d-submap-exit'); }
  setTimeout(() => {
    svgEl.innerHTML = _savedMainContent;
    _savedMainContent = '';
    _nodeEls.clear();
    _edgeEls = [];
    _smNodes = [];
    _smEdges = [];
  }, 200);
}

// ── Focus+Context ──

function _highlight(nodeId) {
  const conn = new Set([nodeId]);
  _smEdges.forEach(e => { if (e.f === nodeId) conn.add(e.t); if (e.t === nodeId) conn.add(e.f); });
  _nodeEls.forEach((el, id) => {
    el.classList.remove('focused', 'connected', 'dimmed');
    if (id === nodeId) el.classList.add('focused');
    else if (conn.has(id)) el.classList.add('connected');
    else el.classList.add('dimmed');
  });
  _edgeEls.forEach(({ el, from, to }) => {
    el.classList.remove('highlighted', 'dimmed');
    if (from === nodeId || to === nodeId) el.classList.add('highlighted');
    else el.classList.add('dimmed');
  });
}

function _clearHighlight() {
  _nodeEls.forEach(el => el.classList.remove('focused', 'connected', 'dimmed'));
  _edgeEls.forEach(({ el }) => el.classList.remove('highlighted', 'dimmed'));
}

// ── Helpers ──

function _bezier(from, to) {
  const dx = to.x - from.x, dy = to.y - from.y;
  const d = Math.sqrt(dx * dx + dy * dy);
  if (d < 1) return `M${from.x},${from.y}L${to.x},${to.y}`;
  const c = Math.min(d * 0.18, 25);
  const nx = -dy / d * c, ny = dx / d * c;
  return `M${from.x},${from.y} Q${(from.x + to.x) / 2 + nx * 0.5},${(from.y + to.y) / 2 + ny * 0.5} ${to.x},${to.y}`;
}

function _addGridPattern(defs, id) {
  const p = _el('pattern', { id, width: 24, height: 24, patternUnits: 'userSpaceOnUse' });
  p.appendChild(_el('circle', { cx: 12, cy: 12, r: 0.6, fill: 'rgba(255,255,255,0.03)' }));
  defs.appendChild(p);
}
function _addArrowMarkers(defs, prefix) {
  for (const [n, c] of Object.entries(EC)) {
    const m = _el('marker', { id: `${prefix}-${n}`, viewBox: '0 0 8 6', refX: 7, refY: 3, markerWidth: 7, markerHeight: 5, orient: 'auto-start-reverse' });
    m.appendChild(_el('path', { d: 'M0 0L8 3L0 6Z', fill: c, opacity: '0.5' }));
    defs.appendChild(m);
  }
}
function _addGlowFilter(defs, id, blur) {
  const f = _el('filter', { id, x: '-50%', y: '-50%', width: '200%', height: '200%' });
  f.appendChild(_el('feGaussianBlur', { stdDeviation: String(blur), result: 'b' }));
  const mg = _el('feMerge');
  mg.appendChild(_el('feMergeNode', { in: 'b' }));
  mg.appendChild(_el('feMergeNode', { in: 'SourceGraphic' }));
  f.appendChild(mg);
  defs.appendChild(f);
}
function _el(tag, attrs) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}
function _textEl(t, attrs) {
  const el = _el('text', attrs);
  el.textContent = t;
  return el;
}
