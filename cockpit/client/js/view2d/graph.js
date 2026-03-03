/* ═══════════════ 2D GRAPH — SVG Ontology Map ═══════════════
   Mirrors the 3D view: group-colored shapes, pill labels,
   subtitles, orbital layout, glow heroes, animated edges.
   Pure SVG, zero WebGL.
   ════════════════════════════════════════════════════════════ */

const GC = {
  source:   { hex: '#34d399', rgb: '52,211,153', pill: 'rgba(40,160,110,.85)' },
  layer:    { hex: '#6b8fff', rgb: '107,143,255', pill: 'rgba(90,120,220,.85)' },
  module:   { hex: '#9b7cff', rgb: '155,124,255', pill: 'rgba(120,95,210,.85)' },
  consumer: { hex: '#5eead4', rgb: '94,234,212', pill: 'rgba(60,180,170,.85)' },
};

const EC = { green: '#34d399', blue: '#6b8fff', purple: '#9b7cff', cyan: '#5eead4', white: '#8899bb' };

/* ── Simplified 2D icon paths per shape (centered at 0,0 — scale ~1) ── */
const SHAPE_PATHS = {
  brain:     'M-4-2C-4-5 0-7 2-6 4-5 6-3 5 0 4 2 3 4 1 5-1 5-3 4-5 2-5 0-4-2Z',
  gauge:     'M-5 0A5 5 0 0 1 5 0L3 0A3 3 0 0 0-3 0Z M0-4L1-1-1-1Z',
  tree:      'M0-6L4-1H1V3H-1V-1H-4Z',
  hub:       'M0-5V-2M0 2V5M-5 0H-2M2 0H5M-3.5-3.5L-1.5-1.5M1.5 1.5L3.5 3.5M3.5-3.5L1.5-1.5M-1.5 1.5L-3.5 3.5',
  sphere:    '', // will be <circle>
  monument:  'M-2 5H2L3-5H-3Z',
  pillars:   'M-4 5V-3M0 5V-5M4 5V-3M-5 5H5M-5-3H5',
  gear:      'M0-5L1.5-3.5 3.5-3.5 3.5-1.5 5 0 3.5 1.5 3.5 3.5 1.5 3.5 0 5-1.5 3.5-3.5 3.5-3.5 1.5-5 0-3.5-1.5-3.5-3.5-1.5-3.5Z',
  gate:      'M-5 4V-2A5 5 0 0 1 5-2V4',
  database:  'M-4-3C-4-5 4-5 4-3V3C4 5-4 5-4 3ZM-4-1C-4 1 4 1 4-1M-4 1C-4 3 4 3 4 1',
  hourglass: 'M-3-5H3L0 0L3 5H-3L0 0Z',
  prism:     'M0-5L5 4H-5Z',
  stairs:    'M-5 5H-2V2H1V-1H4V-4H5',
  nexus:     'M0-4L4 0 0 4-4 0Z M0-4V4M-4 0H4',
  graph:     'M-3-3L3-1M-3-3L-1 3M3-1L-1 3M3-1L2 4',
  screens:   'M-5-3H5V3H-5ZM-2 3V5M2 3V5M-3 5H3',
  rack:      'M-3-5H3V5H-3ZM-3-2H3M-3 1H3',
  conveyor:  'M-5 0H5M2-2L5 0 2 2M-2-2L-5 0-2 2',
  monitor:   'M-5-3H5V2H-5ZM0 2V4M-3 4H3',
  warehouse: 'M-5 4V-1L0-4L5-1V4Z',
  factory:   'M-5 5V-2L-2-5V-2L1-5V5ZM1 5V-1H5V5Z',
  satellite: 'M-4 4L0 0M0 0L4-4M-2-2L2 2M-3-1L1 3',
  terminal:  'M-5-4H5V4H-5ZM-3-2L-1 0-3 2M0 2H3',
  dyson_book:'M-4-5H3C5-5 5-3 3-3H-4V3H3C5 3 5 5 3 5H-4Z',
  dial:      'M0-5A5 5 0 1 1 0 5A5 5 0 1 1 0-5ZM0-3V0L2 2',
  vault:     'M-5-4H5V4H-5ZM-2-2A2 2 0 1 1-2 2A2 2 0 1 1-2-2M0 0H3',
};

let _svg = null;
let _nodesData = [];
let _edgesData = [];
let _callbacks = null;
let _nodeEls = new Map();
let _edgeEls = [];
const SCALE = 20;

// ── Public API ──

export function renderMainGraph(svgEl, nodes, edges, details, submaps, callbacks) {
  _svg = svgEl;
  _nodesData = nodes;
  _edgesData = edges;
  _callbacks = callbacks;
  _nodeEls.clear();
  _edgeEls = [];

  const pad = 140;
  const xs = nodes.map(n => n.x);
  const zs = nodes.map(n => n.z);
  const minX = Math.min(...xs) - 6;
  const maxX = Math.max(...xs) + 6;
  const minZ = Math.min(...zs) - 6;
  const maxZ = Math.max(...zs) + 6;
  const vbX = minX * SCALE - pad;
  const vbY = minZ * SCALE - pad;
  const vbW = (maxX - minX) * SCALE + pad * 2;
  const vbH = (maxZ - minZ) * SCALE + pad * 2;

  _svg.setAttribute('viewBox', `${vbX} ${vbY} ${vbW} ${vbH}`);

  // ── Defs ──
  const defs = _el('defs');
  _addGridPattern(defs, 'v2d-grid');
  _addArrowMarkers(defs, 'arr');
  _addGlowFilter(defs, 'v2d-glow', 4);
  _addGlowFilter(defs, 'v2d-glow-soft', 6);
  _svg.appendChild(defs);

  // ── Background ──
  _svg.appendChild(_el('rect', { x: vbX, y: vbY, width: vbW, height: vbH, fill: 'url(#v2d-grid)' }));

  // ── Orbit rings ──
  const og = _el('g');
  [5, 10, 15, 20].forEach(r => og.appendChild(_el('circle', { cx: 0, cy: 0, r: r * SCALE, class: 'v2d-orbit' })));
  _svg.appendChild(og);

  // ── Edges ──
  const posMap = new Map();
  nodes.forEach(n => posMap.set(n.id, { x: n.x * SCALE, y: n.z * SCALE }));

  const edgeG = _el('g');
  edges.forEach(e => {
    const from = posMap.get(e.f);
    const to = posMap.get(e.t);
    if (!from || !to) return;
    const el = _el('path', {
      d: _bezier(from, to),
      class: `v2d-edge v2d-edge--${e.c}`,
      'data-from': e.f, 'data-to': e.t,
      'marker-end': `url(#arr-${e.c})`,
    });
    edgeG.appendChild(el);
    _edgeEls.push({ el, from: e.f, to: e.t });
  });
  _svg.appendChild(edgeG);

  // ── Nodes ──
  const nodeG = _el('g');
  nodes.forEach((n, i) => {
    const gc = GC[n.g] || GC.module;
    const isHero = !!n.hero;
    const r = isHero ? 14 : 8;
    const cx = n.x * SCALE;
    const cy = n.z * SCALE;

    // Outer: position. Inner: animation target
    const outer = _el('g', { transform: `translate(${cx},${cy})` });
    const inner = _el('g', { class: 'v2d-node', 'data-id': n.id, style: `--i:${i}` });

    // Ground pad (subtle ring)
    inner.appendChild(_el('circle', {
      cx: 0, cy: 0, r: r + 4,
      fill: 'none', stroke: gc.hex, 'stroke-width': 0.5,
      opacity: 0.15,
    }));

    // Contact shadow
    inner.appendChild(_el('ellipse', {
      cx: 0, cy: 2, rx: r * 0.8, ry: r * 0.25,
      fill: 'black', opacity: 0.1,
    }));

    // Main shape glow (hero only)
    if (isHero) {
      inner.appendChild(_el('circle', {
        cx: 0, cy: 0, r: r + 2,
        fill: gc.hex, opacity: 0.08,
        filter: 'url(#v2d-glow-soft)',
      }));
    }

    // Shape body (circle with gradient-like fill)
    const body = _el('circle', {
      cx: 0, cy: 0, r,
      fill: `rgba(${gc.rgb},0.15)`,
      stroke: gc.hex, 'stroke-width': isHero ? 2 : 1.2,
      class: 'v2d-shape',
    });
    if (isHero) body.setAttribute('filter', 'url(#v2d-glow)');
    inner.appendChild(body);

    // Inner icon path
    const iconScale = isHero ? 1.5 : 0.9;
    const pathD = SHAPE_PATHS[n.sh];
    if (pathD && n.sh !== 'sphere' && n.sh !== 'hub') {
      inner.appendChild(_el('path', {
        d: pathD,
        fill: 'none', stroke: gc.hex, 'stroke-width': 0.8,
        opacity: 0.6,
        transform: `scale(${iconScale})`,
      }));
    } else if (n.sh === 'hub') {
      // Hub is strokes only
      inner.appendChild(_el('path', {
        d: SHAPE_PATHS.hub,
        fill: 'none', stroke: gc.hex, 'stroke-width': 0.8,
        opacity: 0.6,
        transform: `scale(${iconScale})`,
      }));
      inner.appendChild(_el('circle', { cx: 0, cy: 0, r: 1.5 * iconScale, fill: gc.hex, opacity: 0.5 }));
    } else {
      // sphere or fallback — just inner circle
      inner.appendChild(_el('circle', { cx: 0, cy: 0, r: r * 0.45, fill: gc.hex, opacity: 0.2 }));
    }

    // ── Pill label (above shape) ──
    const labelY = -(r + 8);
    const labelText = n.label;
    const pillW = labelText.length * 6.5 + 20;
    const pillH = isHero ? 20 : 16;
    const pillG = _el('g', { transform: `translate(0,${labelY})` });

    // Pill background
    pillG.appendChild(_el('rect', {
      x: -pillW / 2, y: -pillH / 2,
      width: pillW, height: pillH, rx: pillH / 2,
      fill: isHero ? gc.pill : gc.pill,
      opacity: isHero ? 1 : 0.9,
      class: 'v2d-pill-bg',
    }));
    if (isHero) {
      // Glow behind hero pill
      pillG.appendChild(_el('rect', {
        x: -pillW / 2 - 2, y: -pillH / 2 - 2,
        width: pillW + 4, height: pillH + 4, rx: (pillH + 4) / 2,
        fill: gc.hex, opacity: 0.15,
        filter: 'url(#v2d-glow)',
      }));
    }
    // Pill text
    pillG.appendChild(_textEl(labelText, {
      x: 0, y: 1,
      'text-anchor': 'middle', 'dominant-baseline': 'middle',
      class: 'v2d-pill-text' + (isHero ? ' hero' : ''),
    }));
    inner.appendChild(pillG);

    // ── Subtitle (below shape) ──
    inner.appendChild(_textEl(n.sub, {
      x: 0, y: r + 14,
      'text-anchor': 'middle',
      class: 'v2d-sub-text',
    }));

    // ── Auto indicator ──
    if (n.auto) {
      // Antenna
      inner.appendChild(_el('line', {
        x1: 0, y1: -(r - 2), x2: 0, y2: -(r + 2),
        stroke: '#34d399', 'stroke-width': 1,
      }));
      // Pulsing dot
      inner.appendChild(_el('circle', {
        cx: 0, cy: -(r + 3), r: 1.8,
        fill: '#34d399', class: 'v2d-auto-dot',
      }));
    }

    // ── Events ──
    outer.style.cursor = 'pointer';
    outer.addEventListener('mouseenter', ev => {
      highlightNode(n.id);
      if (_callbacks?.onNodeHover) _callbacks.onNodeHover(n, ev);
    });
    outer.addEventListener('mouseleave', () => {
      clearHighlight();
      if (_callbacks?.onNodeLeave) _callbacks.onNodeLeave();
    });
    outer.addEventListener('click', () => {
      if (_callbacks?.onNodeClick) _callbacks.onNodeClick(n.id);
    });

    outer.appendChild(inner);
    nodeG.appendChild(outer);
    _nodeEls.set(n.id, inner);
  });
  _svg.appendChild(nodeG);
}

export function highlightNode(nodeId) {
  const connected = new Set([nodeId]);
  _edgesData.forEach(e => {
    if (e.f === nodeId) connected.add(e.t);
    if (e.t === nodeId) connected.add(e.f);
  });
  _nodeEls.forEach((el, id) => {
    el.classList.remove('focused', 'connected', 'dimmed');
    if (id === nodeId) el.classList.add('focused');
    else if (connected.has(id)) el.classList.add('connected');
    else el.classList.add('dimmed');
  });
  _edgeEls.forEach(({ el, from, to }) => {
    el.classList.remove('highlighted', 'dimmed');
    if (from === nodeId || to === nodeId) el.classList.add('highlighted');
    else el.classList.add('dimmed');
  });
}

export function clearHighlight() {
  _nodeEls.forEach(el => el.classList.remove('focused', 'connected', 'dimmed'));
  _edgeEls.forEach(({ el }) => el.classList.remove('highlighted', 'dimmed'));
}

export function triggerEntry() {
  _nodeEls.forEach(el => {
    el.classList.remove('enter');
    void el.getBBox(); // force reflow in SVG context
    el.classList.add('enter');
  });
}

export function destroy() {
  _nodeEls.clear();
  _edgeEls = [];
  _nodesData = [];
  _edgesData = [];
  _callbacks = null;
  if (_svg) _svg.innerHTML = '';
}

// ── Shared helpers ──

function _bezier(from, to) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const dist = Math.sqrt(dx * dx + dy * dy);
  if (dist < 1) return `M${from.x},${from.y}L${to.x},${to.y}`;
  const c = Math.min(dist * 0.18, 30);
  const nx = -dy / dist * c;
  const ny = dx / dist * c;
  const mx = (from.x + to.x) / 2 + nx * 0.5;
  const my = (from.y + to.y) / 2 + ny * 0.5;
  return `M${from.x},${from.y} Q${mx},${my} ${to.x},${to.y}`;
}

function _addGridPattern(defs, id) {
  const p = _el('pattern', { id, width: 24, height: 24, patternUnits: 'userSpaceOnUse' });
  p.appendChild(_el('circle', { cx: 12, cy: 12, r: 0.6, fill: 'rgba(255,255,255,0.03)' }));
  defs.appendChild(p);
}

function _addArrowMarkers(defs, prefix) {
  for (const [name, color] of Object.entries(EC)) {
    const m = _el('marker', {
      id: `${prefix}-${name}`, viewBox: '0 0 8 6', refX: 7, refY: 3,
      markerWidth: 7, markerHeight: 5, orient: 'auto-start-reverse',
    });
    m.appendChild(_el('path', { d: 'M0 0L8 3L0 6Z', fill: color, opacity: '0.5' }));
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

function _textEl(txt, attrs) {
  const el = _el('text', attrs);
  el.textContent = txt;
  return el;
}
