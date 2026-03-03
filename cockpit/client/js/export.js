/* ====== EXPORT -- Static HTML export ======
   Creates a self-contained HTML file with inlined JS/CSS/data.
   Can be triggered from a button or programmatically.          */

/**
 * Export the current cockpit as a standalone HTML file.
 * Inlines all necessary data so it works offline without a server.
 *
 * @param {object} cockpitData - The loaded cockpit data from loader.js
 * @param {object} [options]
 * @param {string} [options.filename='cockpit-export.html']
 * @param {boolean} [options.download=true] - Auto-trigger download
 * @returns {string} The generated HTML string
 */
export function exportStaticHTML(cockpitData, options = {}) {
  const { filename = 'cockpit-export.html', download = true } = options;

  const title = cockpitData.title || 'Ontology Cockpit';
  const description = cockpitData.description || '';
  const graphJson = JSON.stringify(cockpitData.graphData, null, 2);
  const schemaJson = cockpitData.cockpitSchema
    ? JSON.stringify(cockpitData.cockpitSchema, null, 2)
    : 'null';

  const stats = cockpitData.stats || [];
  const legend = cockpitData.legend || [];

  const statsHtml = stats.map(s =>
    `<div class="stat"><span class="n">${s.value}</span><span class="l">${s.label}</span></div>`
  ).join('\n    ');

  const legendHtml = legend.map(l =>
    `<div class="legend-item active" data-edge="${l.edge_type}"><div class="legend-dot" style="background:${l.color}"></div>${l.label}</div>`
  ).join('\n    ');

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="cockpit-static" content="true">
  <title>${_escapeHtml(title)} -- Ontology Cockpit</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    /* Minimal embedded styles for standalone export */
    :root {
      --bg: #0f1117; --bg2: #161922; --text: #e2e4e9; --muted: #8b95aa;
      --green: #34d399; --blue: #6b8fff; --purple: #9b7cff; --cyan: #5eead4;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); overflow: hidden; }
    .header { position: fixed; top: 0; left: 0; right: 0; z-index: 10; display: flex; align-items: center; gap: 10px; padding: 12px 20px; background: rgba(15,17,23,0.85); backdrop-filter: blur(12px); }
    .header h1 { font-size: 16px; font-weight: 600; }
    .header .sub { font-size: 13px; color: var(--muted); }
    .header .pipe { color: var(--muted); }
    .header .hex { color: var(--purple); font-size: 18px; }
    .stats-bar { position: fixed; bottom: 0; left: 0; right: 0; z-index: 10; display: flex; justify-content: center; gap: 32px; padding: 10px; background: rgba(15,17,23,0.85); backdrop-filter: blur(12px); }
    .stat { text-align: center; }
    .stat .n { display: block; font-size: 18px; font-weight: 600; color: var(--cyan); }
    .stat .l { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
    .legend { position: fixed; bottom: 50px; left: 16px; z-index: 10; display: flex; flex-direction: column; gap: 6px; }
    .legend-item { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--muted); cursor: pointer; }
    .legend-dot { width: 8px; height: 8px; border-radius: 50%; }
    .hint { position: fixed; bottom: 50px; left: 50%; transform: translateX(-50%); z-index: 10; font-size: 12px; color: var(--muted); opacity: 0.6; }
    #sc { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; }
    .export-badge { position: fixed; top: 50px; right: 16px; z-index: 10; font-size: 10px; color: var(--muted); background: var(--bg2); padding: 4px 8px; border-radius: 4px; border: 1px solid rgba(139,149,170,0.2); }
  </style>
</head>
<body>
<div class="header">
  <span class="hex">&#x2B21;</span>
  <h1>${_escapeHtml(title)}</h1>
  <span class="pipe">|</span>
  <span class="sub">${_escapeHtml(description)}</span>
</div>

<div id="sc"></div>
<div class="hint">Click any object to explore &middot; Drag to rotate &middot; Scroll to zoom</div>

<div class="stats-bar">
    ${statsHtml}
</div>

<div class="legend" id="legend">
    ${legendHtml}
</div>

<div class="export-badge">Static Export</div>

<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.162.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.162.0/examples/jsm/"
  }
}
</script>

<script type="module">
// ── Embedded graph data ──
const GRAPH_DATA = ${graphJson};

const COCKPIT_SCHEMA = ${schemaJson};

// ── Minimal static renderer ──
import * as T from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const container = document.getElementById('sc');
const w = window.innerWidth, h = window.innerHeight;

// Scene
const scene = new T.Scene();
scene.background = new T.Color(0x0f1117);

// Camera
const cam = new T.PerspectiveCamera(45, w / h, 0.1, 200);
cam.position.set(15, 20, 15);

// Renderer
const renderer = new T.WebGLRenderer({ antialias: true });
renderer.setSize(w, h);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
container.appendChild(renderer.domElement);

// Controls
const ctrl = new OrbitControls(cam, renderer.domElement);
ctrl.enableDamping = true;
ctrl.dampingFactor = 0.08;

// Lights
scene.add(new T.AmbientLight(0xffffff, 0.4));
const dir = new T.DirectionalLight(0xffffff, 0.7);
dir.position.set(10, 15, 10);
scene.add(dir);

// Ground
const ground = new T.Mesh(
  new T.PlaneGeometry(60, 60),
  new T.MeshStandardMaterial({ color: 0x161922, roughness: 0.9 })
);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.01;
scene.add(ground);

// Nodes
const nodes = GRAPH_DATA.nodes || [];
const edges = GRAPH_DATA.edges || [];
const schemaNodes = COCKPIT_SCHEMA?.nodes || {};
const groupColors = { source: 0x34d399, layer: 0x6b8fff, module: 0x9b7cff, consumer: 0x5eead4 };

for (const n of nodes) {
  const props = n.properties || {};
  const over = schemaNodes[n.id] || {};
  const group = over.group || n.group || 'module';
  const color = groupColors[group] || 0x9b7cff;
  const x = over.x ?? props.x ?? 0;
  const z = over.z ?? props.z ?? 0;
  const isHero = over.hero || props.hero || false;
  const s = isHero ? 0.6 : 0.35;

  const mesh = new T.Mesh(
    new T.SphereGeometry(s, 16, 16),
    new T.MeshStandardMaterial({ color, metalness: 0.3, roughness: 0.5, emissive: color, emissiveIntensity: 0.1 })
  );
  mesh.position.set(x, s + 0.5, z);
  scene.add(mesh);

  // Label sprite
  const canvas = document.createElement('canvas');
  canvas.width = 256; canvas.height = 64;
  const ctx = canvas.getContext('2d');
  ctx.font = '20px Inter, sans-serif';
  ctx.fillStyle = '#e2e4e9';
  ctx.textAlign = 'center';
  ctx.fillText(n.label || n.id, 128, 30);
  const tex = new T.CanvasTexture(canvas);
  const sprite = new T.Sprite(new T.SpriteMaterial({ map: tex, transparent: true }));
  sprite.scale.set(3, 0.75, 1);
  sprite.position.set(x, s + 1.5, z);
  scene.add(sprite);
}

// Edges
const posMap = {};
for (const n of nodes) {
  const props = n.properties || {};
  const over = schemaNodes[n.id] || {};
  posMap[n.id] = {
    x: over.x ?? props.x ?? 0,
    y: 1.0,
    z: over.z ?? props.z ?? 0,
  };
}

const edgeColorMap = { green: 0x34d399, blue: 0x6b8fff, purple: 0x9b7cff, cyan: 0x5eead4, white: 0x8899bb };
for (const e of edges) {
  const from = posMap[e.from || e.f];
  const to = posMap[e.to || e.t];
  if (!from || !to) continue;
  const color = edgeColorMap[(e.properties?.color) || (e.c) || 'white'] || 0x8899bb;
  const points = [new T.Vector3(from.x, from.y, from.z), new T.Vector3(to.x, to.y, to.z)];
  const geo = new T.BufferGeometry().setFromPoints(points);
  const line = new T.Line(geo, new T.LineBasicMaterial({ color, transparent: true, opacity: 0.4 }));
  scene.add(line);
}

// Animation loop
function animate() {
  requestAnimationFrame(animate);
  ctrl.update();
  renderer.render(scene, cam);
}
animate();

// Resize
window.addEventListener('resize', () => {
  const w2 = window.innerWidth, h2 = window.innerHeight;
  cam.aspect = w2 / h2;
  cam.updateProjectionMatrix();
  renderer.setSize(w2, h2);
});
</script>
</body>
</html>`;

  if (download) {
    _downloadFile(html, filename, 'text/html');
  }

  return html;
}

/**
 * Trigger a file download in the browser.
 */
function _downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function _escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
