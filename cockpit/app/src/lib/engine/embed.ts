/**
 * Embed Mode — generate embeddable iframe widgets for docs/blogs.
 * Pure engine module (no React dependency).
 *
 * Produces a self-contained HTML page with a minimal 3D viewer
 * that can be embedded via iframe.
 */

import type { Node, Edge } from "@/lib/api";

export interface EmbedOptions {
  /** Widget width (CSS value) */
  width: string;
  /** Widget height (CSS value) */
  height: string;
  /** Initial camera position */
  cameraDistance: number;
  /** Show node labels */
  showLabels: boolean;
  /** Auto-rotate */
  autoRotate: boolean;
  /** Background color (hex) */
  background: string;
  /** Accent color (hex) */
  accent: string;
  /** Max nodes to include (for size limit) */
  maxNodes: number;
  /** Interactive (orbit controls) vs static */
  interactive: boolean;
}

const DEFAULT_OPTIONS: EmbedOptions = {
  width: "100%",
  height: "400px",
  cameraDistance: 100,
  showLabels: true,
  autoRotate: true,
  background: "#0f172a",
  accent: "#10b981",
  maxNodes: 200,
  interactive: true,
};

/** Generate embed HTML for a subset of the graph */
export function generateEmbed(
  nodes: Node[],
  edges: Edge[],
  options: Partial<EmbedOptions> = {},
): string {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  // Limit nodes
  const limitedNodes = nodes.slice(0, opts.maxNodes);
  const nodeIds = new Set(limitedNodes.map((n) => n.id));
  const limitedEdges = edges.filter(
    (e) => nodeIds.has(e.from) && nodeIds.has(e.to),
  );

  // Serialize graph data — escape </script> to prevent XSS in embedded HTML
  const graphData = JSON.stringify({
    nodes: limitedNodes.map((n) => ({
      id: n.id,
      text: n.text,
      layer: n.layer,
      type: n.type,
    })),
    edges: limitedEdges.map((e) => ({
      from: e.from,
      to: e.to,
      type: e.type,
    })),
  }).replace(/<\/script/gi, "<\\/script");

  // Escape color options to prevent injection
  const safeBg = opts.background.replace(/[^#a-fA-F0-9]/g, "");
  const safeAccent = opts.accent.replace(/[^#a-fA-F0-9]/g, "");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ontology Map — Embed</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:${safeBg};overflow:hidden;font-family:system-ui,sans-serif}
canvas{display:block;width:100%;height:100vh}
#info{position:absolute;bottom:8px;right:8px;color:rgba(255,255,255,.4);font-size:10px}
#info a{color:${safeAccent};text-decoration:none}
#tooltip{position:absolute;display:none;background:rgba(0,0,0,.85);color:#fff;
  font-size:11px;padding:4px 8px;border-radius:4px;pointer-events:none;
  border:1px solid rgba(255,255,255,.1)}
</style>
</head>
<body>
<div id="tooltip"></div>
<div id="info">Powered by <a href="https://github.com/ontology-map" target="_blank">Ontology Map</a></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const GRAPH = ${graphData};
const ACCENT = new THREE.Color('${safeAccent}');
const BG = new THREE.Color('${safeBg}');
const SHOW_LABELS = ${opts.showLabels};
const AUTO_ROTATE = ${opts.autoRotate};
const INTERACTIVE = ${opts.interactive};
const CAM_DIST = ${opts.cameraDistance};

// Scene setup
const scene = new THREE.Scene();
scene.background = BG;
scene.fog = new THREE.FogExp2(BG, 0.008);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth/window.innerHeight, 0.1, 1000);
camera.position.set(0, CAM_DIST*0.5, CAM_DIST);

const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
document.body.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.autoRotate = AUTO_ROTATE;
controls.autoRotateSpeed = 0.5;
controls.enabled = INTERACTIVE;

// Lighting
scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dir = new THREE.DirectionalLight(0xffffff, 0.8);
dir.position.set(50, 80, 40);
scene.add(dir);

// Nodes — instanced spheres
const N = GRAPH.nodes.length;
const geo = new THREE.SphereGeometry(0.8, 16, 12);
const mat = new THREE.MeshStandardMaterial({color:ACCENT, roughness:0.6, metalness:0.2});
const mesh = new THREE.InstancedMesh(geo, mat, N);
scene.add(mesh);

// Simple force layout — random initial, spring relaxation
const positions = GRAPH.nodes.map(() => ({
  x: (Math.random()-0.5)*60,
  y: (Math.random()-0.5)*40,
  z: (Math.random()-0.5)*60,
}));

// Index for edges
const idxMap = new Map();
GRAPH.nodes.forEach((n,i) => idxMap.set(n.id, i));

// Basic spring layout (10 iterations)
for (let iter=0; iter<10; iter++) {
  // Repulsion
  for (let i=0; i<N; i++) {
    for (let j=i+1; j<N; j++) {
      const dx=positions[i].x-positions[j].x;
      const dy=positions[i].y-positions[j].y;
      const dz=positions[i].z-positions[j].z;
      const d2=dx*dx+dy*dy+dz*dz+0.01;
      const f=200/d2;
      positions[i].x+=dx*f*0.01;positions[i].y+=dy*f*0.01;positions[i].z+=dz*f*0.01;
      positions[j].x-=dx*f*0.01;positions[j].y-=dy*f*0.01;positions[j].z-=dz*f*0.01;
    }
  }
  // Attraction (edges)
  for (const e of GRAPH.edges) {
    const si=idxMap.get(e.from), ti=idxMap.get(e.to);
    if (si===undefined||ti===undefined) continue;
    const dx=positions[ti].x-positions[si].x;
    const dy=positions[ti].y-positions[si].y;
    const dz=positions[ti].z-positions[si].z;
    positions[si].x+=dx*0.02;positions[si].y+=dy*0.02;positions[si].z+=dz*0.02;
    positions[ti].x-=dx*0.02;positions[ti].y-=dy*0.02;positions[ti].z-=dz*0.02;
  }
}

// Apply positions
const dummy = new THREE.Object3D();
const layerColors = [0x10b981, 0x6366f1, 0xf59e0b, 0xef4444, 0x06b6d4, 0x8b5cf6];
for (let i=0; i<N; i++) {
  dummy.position.set(positions[i].x, positions[i].y, positions[i].z);
  dummy.updateMatrix();
  mesh.setMatrixAt(i, dummy.matrix);
  const c = new THREE.Color(layerColors[GRAPH.nodes[i].layer % layerColors.length]);
  mesh.setColorAt(i, c);
}
mesh.instanceMatrix.needsUpdate = true;
if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;

// Edges — lines
const edgeGeo = new THREE.BufferGeometry();
const edgeVerts = [];
for (const e of GRAPH.edges) {
  const si=idxMap.get(e.from), ti=idxMap.get(e.to);
  if (si===undefined||ti===undefined) continue;
  edgeVerts.push(positions[si].x,positions[si].y,positions[si].z);
  edgeVerts.push(positions[ti].x,positions[ti].y,positions[ti].z);
}
edgeGeo.setAttribute('position', new THREE.Float32BufferAttribute(edgeVerts, 3));
const edgeMat = new THREE.LineBasicMaterial({color:0xffffff, opacity:0.15, transparent:true});
scene.add(new THREE.LineSegments(edgeGeo, edgeMat));

// Resize
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth/window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// Animate
function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();
</script>
</body>
</html>`;
}

/** Generate an iframe embed tag */
export function generateEmbedTag(
  options: Partial<EmbedOptions> = {},
): string {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  return `<iframe src="embed.html" width="${opts.width}" height="${opts.height}" frameborder="0" allow="accelerometer" style="border:none;border-radius:8px"></iframe>`;
}

/** Generate a share URL with encoded graph data */
export function generateShareUrl(
  baseUrl: string,
  nodes: Node[],
  edges: Edge[],
  maxNodes: number = 50,
): string {
  const limited = nodes.slice(0, maxNodes);
  const nodeIds = new Set(limited.map((n) => n.id));
  const limitedEdges = edges.filter(
    (e) => nodeIds.has(e.from) && nodeIds.has(e.to),
  );

  const data = {
    n: limited.map((n) => [n.id, n.text, n.layer]),
    e: limitedEdges.map((e) => [e.from, e.to]),
  };

  // btoa() only handles Latin-1. Encode via TextEncoder for Unicode safety.
  const jsonStr = JSON.stringify(data);
  const bytes = new TextEncoder().encode(jsonStr);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  const encoded = btoa(binary);
  return `${baseUrl}/embed?d=${encodeURIComponent(encoded)}`;
}
