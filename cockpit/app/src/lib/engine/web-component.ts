/**
 * Web Component — <ontology-map> custom element.
 * Self-contained embeddable widget (~45KB, no Three.js dependency).
 *
 * Uses Canvas 2D with a lightweight force simulation for the graph.
 * Designed for embedding in docs, blogs, READMEs.
 *
 * Usage:
 *   <script src="https://ontology-map.dev/widget.js"></script>
 *   <ontology-map data-url="https://..." width="600" height="400"></ontology-map>
 *
 * Or with inline data:
 *   <ontology-map data-nodes='[...]' data-edges='[...]'></ontology-map>
 */

// ─── Types ───────────────────────────────────────────────────────────────────

interface WidgetNode {
  id: string;
  text: string;
  layer: number;
  type: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface WidgetEdge {
  from: string;
  to: string;
  type: string;
}

interface WidgetOptions {
  width: number;
  height: number;
  background: string;
  accentColor: string;
  showLabels: boolean;
  interactive: boolean;
  autoRotate: boolean;
  maxNodes: number;
}

// ─── Layer Colors ────────────────────────────────────────────────────────────

const LAYER_COLORS: Record<number, string> = {
  0: "#10b981", // axioms — emerald
  1: "#06b6d4", // principles — cyan
  2: "#8b5cf6", // patterns — violet
  3: "#ec4899", // rules — magenta
  4: "#f59e0b", // evidence — amber
  5: "#6366f1", // context — indigo
};

const DEFAULT_COLOR = "#64748b";

// ─── Force Simulation ────────────────────────────────────────────────────────

/** @internal Used by generateStandaloneHtml — position init logic duplicated in widget string */
export function initPositions(nodes: WidgetNode[], width: number, height: number): void {
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;

  for (let i = 0; i < nodes.length; i++) {
    const angle = (2 * Math.PI * i) / nodes.length;
    nodes[i].x = cx + radius * Math.cos(angle) + (Math.random() - 0.5) * 20;
    nodes[i].y = cy + radius * Math.sin(angle) + (Math.random() - 0.5) * 20;
    nodes[i].vx = 0;
    nodes[i].vy = 0;
  }
}

/** @internal Used by generateStandaloneHtml — force sim logic duplicated in widget string */
export function simulateForces(
  nodes: WidgetNode[],
  edges: WidgetEdge[],
  width: number,
  height: number,
  iterations = 50,
): void {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const repulsion = 800;
  const attraction = 0.005;
  const damping = 0.85;
  const centerForce = 0.01;
  const cx = width / 2;
  const cy = height / 2;

  for (let iter = 0; iter < iterations; iter++) {
    // Repulsion (all pairs)
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const d2 = dx * dx + dy * dy + 1;
        const f = repulsion / d2;
        const fx = dx * f;
        const fy = dy * f;
        nodes[i].vx += fx;
        nodes[i].vy += fy;
        nodes[j].vx -= fx;
        nodes[j].vy -= fy;
      }
    }

    // Attraction (edges)
    for (const edge of edges) {
      const source = nodeMap.get(edge.from);
      const target = nodeMap.get(edge.to);
      if (!source || !target) continue;

      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const fx = dx * attraction;
      const fy = dy * attraction;
      source.vx += fx;
      source.vy += fy;
      target.vx -= fx;
      target.vy -= fy;
    }

    // Center gravity
    for (const node of nodes) {
      node.vx += (cx - node.x) * centerForce;
      node.vy += (cy - node.y) * centerForce;
    }

    // Apply velocities with damping
    for (const node of nodes) {
      node.vx *= damping;
      node.vy *= damping;
      node.x += node.vx;
      node.y += node.vy;

      // Bounds
      node.x = Math.max(20, Math.min(width - 20, node.x));
      node.y = Math.max(20, Math.min(height - 20, node.y));
    }
  }
}

// ─── Canvas Rendering ────────────────────────────────────────────────────────

/** @internal Used by generateStandaloneHtml — render logic duplicated in widget string */
export function render(
  ctx: CanvasRenderingContext2D,
  nodes: WidgetNode[],
  edges: WidgetEdge[],
  options: WidgetOptions,
  hoveredNodeId: string | null,
  time: number,
): void {
  const { width, height, background, showLabels } = options;
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const dpr = window.devicePixelRatio || 1;

  // Clear
  ctx.clearRect(0, 0, width * dpr, height * dpr);
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, width * dpr, height * dpr);

  ctx.save();
  ctx.scale(dpr, dpr);

  // Subtle rotation for auto-rotate (transform around center)
  if (options.autoRotate) {
    const angle = time * 0.0001;
    ctx.translate(width / 2, height / 2);
    ctx.rotate(angle);
    ctx.translate(-width / 2, -height / 2);
  }

  // Draw edges
  ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
  ctx.lineWidth = 0.5;
  for (const edge of edges) {
    const from = nodeMap.get(edge.from);
    const to = nodeMap.get(edge.to);
    if (!from || !to) continue;

    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
  }

  // Draw nodes
  for (const node of nodes) {
    const color = LAYER_COLORS[node.layer] ?? DEFAULT_COLOR;
    const isHovered = node.id === hoveredNodeId;
    const radius = isHovered ? 5 : 3;

    // Glow
    if (isHovered) {
      ctx.shadowColor = color;
      ctx.shadowBlur = 12;
    }

    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
    ctx.fill();

    ctx.shadowBlur = 0;

    // Label
    if (showLabels && (isHovered || nodes.length < 50)) {
      ctx.fillStyle = isHovered ? "#ffffff" : "rgba(255, 255, 255, 0.4)";
      ctx.font = `${isHovered ? 11 : 9}px system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText(node.text, node.x, node.y - radius - 4);
    }
  }

  // Watermark
  ctx.fillStyle = "rgba(255, 255, 255, 0.15)";
  ctx.font = "9px system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.fillText("Ontology Map", width - 8, height - 8);

  ctx.restore();
}

// ─── Generate Widget Script ──────────────────────────────────────────────────

/**
 * Generate the self-contained widget JS that registers <ontology-map>.
 * This is the output for `widget.js`.
 */
export function generateWidgetScript(): string {
  // The entire Web Component as a string (self-contained, no dependencies)
  return `(function(){
"use strict";

const LAYER_COLORS = ${JSON.stringify(LAYER_COLORS)};
const DEFAULT_COLOR = "${DEFAULT_COLOR}";

class OntologyMap extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._nodes = [];
    this._edges = [];
    this._hoveredNode = null;
    this._animId = null;
  }

  static get observedAttributes() {
    return ["width", "height", "data-url", "data-nodes", "data-edges", "background", "accent", "labels", "interactive", "max-nodes"];
  }

  connectedCallback() {
    this._setup();
    this._loadData();
  }

  disconnectedCallback() {
    if (this._animId) cancelAnimationFrame(this._animId);
  }

  attributeChangedCallback() {
    this._setup();
    this._loadData();
  }

  _setup() {
    const w = parseInt(this.getAttribute("width") || "600");
    const h = parseInt(this.getAttribute("height") || "400");
    const bg = this.getAttribute("background") || "#0f172a";
    const dpr = window.devicePixelRatio || 1;

    this.shadowRoot.innerHTML = \`
      <style>
        :host { display: inline-block; border-radius: 8px; overflow: hidden; }
        canvas { display: block; width: \${w}px; height: \${h}px; cursor: crosshair; }
      </style>
      <canvas width="\${w * dpr}" height="\${h * dpr}"></canvas>
    \`;

    this._canvas = this.shadowRoot.querySelector("canvas");
    this._ctx = this._canvas.getContext("2d");
    this._width = w;
    this._height = h;
    this._bg = bg;
    this._showLabels = this.getAttribute("labels") !== "false";
    this._interactive = this.getAttribute("interactive") !== "false";
    this._maxNodes = parseInt(this.getAttribute("max-nodes") || "200");

    if (this._interactive) {
      this._canvas.addEventListener("mousemove", (e) => this._onMouseMove(e));
      this._canvas.addEventListener("click", (e) => this._onClick(e));
    }
  }

  async _loadData() {
    const url = this.getAttribute("data-url");
    const nodesAttr = this.getAttribute("data-nodes");
    const edgesAttr = this.getAttribute("data-edges");

    if (url) {
      try {
        const res = await fetch(url);
        const data = await res.json();
        this._setData(data.nodes || [], data.edges || []);
      } catch (err) {
        console.warn("ontology-map: failed to load data from URL", err);
      }
    } else if (nodesAttr && edgesAttr) {
      try {
        this._setData(JSON.parse(nodesAttr), JSON.parse(edgesAttr));
      } catch (err) {
        console.warn("ontology-map: failed to parse inline data", err);
      }
    }
  }

  _setData(rawNodes, rawEdges) {
    const limited = rawNodes.slice(0, this._maxNodes);
    const ids = new Set(limited.map(n => n.id));

    this._nodes = limited.map(n => ({
      id: n.id,
      text: n.text || n.label || n.id,
      layer: n.layer || 0,
      type: n.type || "node",
      x: 0, y: 0, vx: 0, vy: 0
    }));

    this._edges = rawEdges
      .filter(e => ids.has(e.from) && ids.has(e.to))
      .map(e => ({ from: e.from, to: e.to, type: e.type || "" }));

    this._layout();
    this._startRender();
  }

  _layout() {
    const nodes = this._nodes;
    const edges = this._edges;
    const w = this._width;
    const h = this._height;
    const nodeMap = new Map(nodes.map(n => [n.id, n]));

    // Initial circular layout
    const cx = w / 2, cy = h / 2;
    const r = Math.min(w, h) * 0.35;
    nodes.forEach((n, i) => {
      const a = (2 * Math.PI * i) / nodes.length;
      n.x = cx + r * Math.cos(a) + (Math.random() - 0.5) * 20;
      n.y = cy + r * Math.sin(a) + (Math.random() - 0.5) * 20;
    });

    // Force simulation (50 iterations)
    for (let iter = 0; iter < 50; iter++) {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const d2 = dx * dx + dy * dy + 1;
          const f = 800 / d2;
          nodes[i].vx += dx * f; nodes[i].vy += dy * f;
          nodes[j].vx -= dx * f; nodes[j].vy -= dy * f;
        }
      }
      for (const e of edges) {
        const s = nodeMap.get(e.from), t = nodeMap.get(e.to);
        if (!s || !t) continue;
        const dx = t.x - s.x, dy = t.y - s.y;
        s.vx += dx * 0.005; s.vy += dy * 0.005;
        t.vx -= dx * 0.005; t.vy -= dy * 0.005;
      }
      for (const n of nodes) {
        n.vx += (cx - n.x) * 0.01; n.vy += (cy - n.y) * 0.01;
        n.vx *= 0.85; n.vy *= 0.85;
        n.x += n.vx; n.y += n.vy;
        n.x = Math.max(20, Math.min(w - 20, n.x));
        n.y = Math.max(20, Math.min(h - 20, n.y));
      }
    }
  }

  _startRender() {
    if (this._animId) cancelAnimationFrame(this._animId);
    const tick = (time) => {
      this._render(time);
      this._animId = requestAnimationFrame(tick);
    };
    this._animId = requestAnimationFrame(tick);
  }

  _render(time) {
    const ctx = this._ctx;
    const dpr = window.devicePixelRatio || 1;
    const w = this._width, h = this._height;
    const nodeMap = new Map(this._nodes.map(n => [n.id, n]));

    ctx.clearRect(0, 0, w * dpr, h * dpr);
    ctx.fillStyle = this._bg;
    ctx.fillRect(0, 0, w * dpr, h * dpr);
    ctx.save();
    ctx.scale(dpr, dpr);

    // Edges
    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.lineWidth = 0.5;
    for (const e of this._edges) {
      const s = nodeMap.get(e.from), t = nodeMap.get(e.to);
      if (!s || !t) continue;
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
      ctx.stroke();
    }

    // Nodes
    for (const n of this._nodes) {
      const color = LAYER_COLORS[n.layer] || DEFAULT_COLOR;
      const hovered = this._hoveredNode === n.id;
      const r = hovered ? 5 : 3;
      if (hovered) { ctx.shadowColor = color; ctx.shadowBlur = 12; }
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      if (this._showLabels && (hovered || this._nodes.length < 50)) {
        ctx.fillStyle = hovered ? "#fff" : "rgba(255,255,255,0.4)";
        ctx.font = (hovered ? "11" : "9") + "px system-ui,sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(n.text, n.x, n.y - r - 4);
      }
    }

    // Watermark
    ctx.fillStyle = "rgba(255,255,255,0.15)";
    ctx.font = "9px system-ui,sans-serif";
    ctx.textAlign = "right";
    ctx.fillText("Ontology Map", w - 8, h - 8);
    ctx.restore();
  }

  _onMouseMove(e) {
    const rect = this._canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    let found = null;
    for (const n of this._nodes) {
      const dx = n.x - x, dy = n.y - y;
      if (dx * dx + dy * dy < 100) { found = n.id; break; }
    }
    this._hoveredNode = found;
    this._canvas.style.cursor = found ? "pointer" : "crosshair";
  }

  _onClick(e) {
    if (this._hoveredNode) {
      this.dispatchEvent(new CustomEvent("node-click", {
        detail: { nodeId: this._hoveredNode },
        bubbles: true
      }));
    }
  }
}

if (!customElements.get("ontology-map")) {
  customElements.define("ontology-map", OntologyMap);
}
})();`;
}

/**
 * Generate a self-contained HTML file with the widget.
 * Used for the "Export as HTML" feature.
 */
export function generateStandaloneHtml(
  nodes: { id: string; text: string; layer: number; type: string }[],
  edges: { from: string; to: string; type: string }[],
  title = "Ontology Map",
): string {
  const nodesJson = JSON.stringify(nodes).replace(/</g, "\\u003c");
  const edgesJson = JSON.stringify(edges).replace(/</g, "\\u003c");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${title}</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f172a;display:flex;align-items:center;justify-content:center;min-height:100vh}
ontology-map{border-radius:12px;box-shadow:0 25px 50px -12px rgba(0,0,0,.5)}
</style>
</head>
<body>
<ontology-map
  width="800"
  height="600"
  data-nodes='${nodesJson}'
  data-edges='${edgesJson}'
  labels="true"
  interactive="true"
></ontology-map>
<script>
${generateWidgetScript()}
</script>
</body>
</html>`;
}
