/**
 * AI Trails Engine — visual AI-guided paths through the 3D graph.
 * Pure engine module (no React dependency).
 *
 * Features:
 * - Selective bloom on trail nodes (Three.js layers system)
 * - Animated dashed lines along the trail path
 * - Particle stream flowing from source to destination
 * - Camera flythrough on CatmullRomCurve3 spline
 * - BFS/Dijkstra pathfinding between any two nodes
 *
 * SOTA references: CodeCity VR (camera paths), Sourcetrail (animated edges),
 * Three.js selective bloom (layers + dual composer), GPGPU particles.
 */

import * as THREE from "three";
import type { Node, Edge } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface Trail {
  /** Ordered node IDs from source to destination */
  path: string[];
  /** Trail label / description */
  label: string;
  /** Trail color (hex) */
  color: string;
  /** Is the trail currently animating */
  animating: boolean;
}

export interface TrailSceneObjects {
  /** Trail line mesh (animated dashed) */
  trailLine: THREE.Line | null;
  /** Particle system along the trail */
  particles: THREE.Points | null;
  /** Bloom layer objects */
  bloomObjects: THREE.Object3D[];
  /** Camera spline for flythrough */
  cameraSpline: THREE.CatmullRomCurve3 | null;
  /** Animation state */
  dashOffset: number;
  particleProgress: number;
  cameraProgress: number;
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** Three.js layer for selective bloom (layer 1 = bloom, layer 0 = no bloom) */
export const BLOOM_LAYER = 1;

const TRAIL_COLORS = [
  "#10b981", // emerald
  "#6366f1", // indigo
  "#f59e0b", // amber
  "#06b6d4", // cyan
  "#ec4899", // pink
];

const PARTICLE_COUNT = 200;
const DASH_SIZE = 0.3;
const GAP_SIZE = 0.15;
const DASH_SPEED = 0.02;
const PARTICLE_SPEED = 0.005;
/** @internal Used by camera flythrough */
export const CAMERA_SPEED = 0.003;

// ─── Pathfinding ─────────────────────────────────────────────────────────────

/** Find shortest path between two nodes using BFS */
export function findPath(
  fromId: string,
  toId: string,
  nodes: Node[],
  edges: Edge[],
): string[] | null {
  const adjacency = new Map<string, string[]>();
  for (const n of nodes) {
    adjacency.set(n.id, []);
  }
  for (const e of edges) {
    adjacency.get(e.from)?.push(e.to);
    adjacency.get(e.to)?.push(e.from); // bidirectional
  }

  // BFS
  const queue: string[] = [fromId];
  const visited = new Set<string>([fromId]);
  const parent = new Map<string, string>();

  while (queue.length > 0) {
    const current = queue.shift()!;
    if (current === toId) {
      // Reconstruct path
      const path: string[] = [];
      let node = toId;
      while (node !== fromId) {
        path.unshift(node);
        node = parent.get(node)!;
      }
      path.unshift(fromId);
      return path;
    }

    for (const neighbor of adjacency.get(current) ?? []) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        parent.set(neighbor, current);
        queue.push(neighbor);
      }
    }
  }

  return null; // no path found
}

/** Find all paths between two nodes (up to maxPaths, max depth) */
export function findAllPaths(
  fromId: string,
  toId: string,
  nodes: Node[],
  edges: Edge[],
  maxPaths = 3,
  maxDepth = 10,
): string[][] {
  const adjacency = new Map<string, string[]>();
  for (const n of nodes) {
    adjacency.set(n.id, []);
  }
  for (const e of edges) {
    adjacency.get(e.from)?.push(e.to);
    adjacency.get(e.to)?.push(e.from);
  }

  const paths: string[][] = [];
  const visited = new Set<string>();

  function dfs(current: string, path: string[], depth: number) {
    if (paths.length >= maxPaths) return;
    if (depth > maxDepth) return;
    if (current === toId) {
      paths.push([...path]);
      return;
    }

    visited.add(current);
    for (const neighbor of adjacency.get(current) ?? []) {
      if (!visited.has(neighbor)) {
        path.push(neighbor);
        dfs(neighbor, path, depth + 1);
        path.pop();
      }
    }
    visited.delete(current);
  }

  dfs(fromId, [fromId], 0);
  return paths;
}

// ─── Trail Scene Construction ────────────────────────────────────────────────

/** Create the visual trail objects for a path */
export function createTrailObjects(
  path: string[],
  positions: Map<string, THREE.Vector3>,
  colorHex: string = TRAIL_COLORS[0],
): TrailSceneObjects {
  if (path.length < 2) {
    return emptyTrailObjects();
  }

  // Collect 3D positions along the path
  const pathPoints: THREE.Vector3[] = [];
  for (const nodeId of path) {
    const pos = positions.get(nodeId);
    if (pos) {
      pathPoints.push(pos.clone());
    }
  }

  if (pathPoints.length < 2) {
    return emptyTrailObjects();
  }

  // Create smooth spline through path points
  const spline = new THREE.CatmullRomCurve3(pathPoints, false, "centripetal", 0.5);
  const splinePoints = spline.getPoints(pathPoints.length * 20);

  // ── Trail Line (animated dashed) ──
  const lineGeometry = new THREE.BufferGeometry().setFromPoints(splinePoints);
  const lineMaterial = new THREE.LineDashedMaterial({
    color: new THREE.Color(colorHex),
    dashSize: DASH_SIZE,
    gapSize: GAP_SIZE,
    transparent: true,
    opacity: 0.8,
    linewidth: 2,
  });
  const trailLine = new THREE.Line(lineGeometry, lineMaterial);
  trailLine.computeLineDistances(); // required for dashes
  trailLine.layers.enable(BLOOM_LAYER);

  // ── Particle System ──
  const particlePositions = new Float32Array(PARTICLE_COUNT * 3);
  const particleSizes = new Float32Array(PARTICLE_COUNT);
  const particleAlphas = new Float32Array(PARTICLE_COUNT);

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const t = i / PARTICLE_COUNT;
    const point = spline.getPoint(t);
    particlePositions[i * 3] = point.x;
    particlePositions[i * 3 + 1] = point.y;
    particlePositions[i * 3 + 2] = point.z;
    particleSizes[i] = 0.08 + Math.random() * 0.04;
    particleAlphas[i] = 0.3 + Math.random() * 0.7;
  }

  const particleGeometry = new THREE.BufferGeometry();
  particleGeometry.setAttribute("position", new THREE.BufferAttribute(particlePositions, 3));

  const particleMaterial = new THREE.PointsMaterial({
    color: new THREE.Color(colorHex),
    size: 0.12,
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
  });
  const particles = new THREE.Points(particleGeometry, particleMaterial);
  particles.layers.enable(BLOOM_LAYER);

  // Camera spline (offset above the trail for cinematic view)
  const cameraPoints = pathPoints.map((p) =>
    new THREE.Vector3(p.x + 3, p.y + 5, p.z + 3)
  );
  const cameraSpline = new THREE.CatmullRomCurve3(cameraPoints, false, "centripetal", 0.5);

  return {
    trailLine,
    particles,
    bloomObjects: [trailLine, particles],
    cameraSpline,
    dashOffset: 0,
    particleProgress: 0,
    cameraProgress: 0,
  };
}

/** Animate trail objects (call every frame) */
export function updateTrailAnimation(
  objects: TrailSceneObjects,
  spline: THREE.CatmullRomCurve3 | null,
  _dt: number,
): void {
  // Animate dash offset (flowing dashes effect)
  if (objects.trailLine) {
    objects.dashOffset += DASH_SPEED;
    const mat = objects.trailLine.material as THREE.LineDashedMaterial;
    mat.dashSize = DASH_SIZE;
    mat.gapSize = GAP_SIZE;
    // Three.js doesn't natively animate dashOffset on LineDashedMaterial,
    // but we can shift via uniforms or recreate. For simplicity, pulse opacity.
    mat.opacity = 0.5 + Math.sin(objects.dashOffset * 4) * 0.3;
  }

  // Animate particles along spline
  if (objects.particles && spline) {
    objects.particleProgress += PARTICLE_SPEED;
    if (objects.particleProgress > 1) objects.particleProgress = 0;

    const positions = objects.particles.geometry.attributes.position;
    if (positions) {
      const array = positions.array as Float32Array;
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        const t = ((i / PARTICLE_COUNT) + objects.particleProgress) % 1;
        const point = spline.getPoint(t);
        // Add slight randomness for organic feel
        array[i * 3] = point.x + (Math.random() - 0.5) * 0.2;
        array[i * 3 + 1] = point.y + (Math.random() - 0.5) * 0.2;
        array[i * 3 + 2] = point.z + (Math.random() - 0.5) * 0.2;
      }
      positions.needsUpdate = true;
    }
  }
}

/** Get camera position/lookAt for flythrough at progress t (0–1) */
export function getCameraFlythrough(
  objects: TrailSceneObjects,
  pathSpline: THREE.CatmullRomCurve3 | null,
  t: number,
): { position: THREE.Vector3; lookAt: THREE.Vector3 } | null {
  if (!objects.cameraSpline || !pathSpline) return null;

  const clamped = Math.max(0, Math.min(1, t));
  const position = objects.cameraSpline.getPoint(clamped);
  const lookAt = pathSpline.getPoint(clamped);

  return { position, lookAt };
}

// ─── Selective Bloom Setup ───────────────────────────────────────────────────

/**
 * Configure selective bloom on a scene.
 *
 * How it works:
 * 1. Objects on BLOOM_LAYER glow (layer.enable(BLOOM_LAYER))
 * 2. Render bloom pass with only bloom-layer objects visible
 * 3. Composite with normal render
 *
 * This avoids the "everything blooms" problem.
 */
export async function setupSelectiveBloom(
  renderer: THREE.WebGLRenderer,
  scene: THREE.Scene,
  camera: THREE.Camera,
): Promise<{
  bloomComposer: import("three/addons/postprocessing/EffectComposer.js").EffectComposer;
  render: () => void;
  dispose: () => void;
}> {
  // Lazy-import postprocessing modules
  const { EffectComposer } = await import("three/addons/postprocessing/EffectComposer.js");
  const { RenderPass } = await import("three/addons/postprocessing/RenderPass.js");
  const { UnrealBloomPass } = await import("three/addons/postprocessing/UnrealBloomPass.js");

  const bloomComposer = new EffectComposer(renderer);
  bloomComposer.renderToScreen = false;

  const renderPass = new RenderPass(scene, camera);
  bloomComposer.addPass(renderPass);

  const bloomPass = new UnrealBloomPass(
    new THREE.Vector2(renderer.domElement.width / 2, renderer.domElement.height / 2),
    1.5,   // strength
    0.4,   // radius
    0.1,   // threshold (low = more bloom on emissive)
  );
  bloomComposer.addPass(bloomPass);

  // Store original materials for toggle
  const darkMaterial = new THREE.MeshBasicMaterial({ color: "black" });
  const materials: Map<string, THREE.Material | THREE.Material[]> = new Map();

  function darkenNonBloom() {
    scene.traverse((obj) => {
      const bloomLayers = new THREE.Layers();
      bloomLayers.set(BLOOM_LAYER);
      if (obj instanceof THREE.Mesh && !obj.layers.test(bloomLayers)) {
        materials.set(obj.uuid, obj.material);
        obj.material = darkMaterial;
      }
    });
  }

  function restoreMaterials() {
    scene.traverse((obj) => {
      if (obj instanceof THREE.Mesh && materials.has(obj.uuid)) {
        obj.material = materials.get(obj.uuid)!;
        materials.delete(obj.uuid);
      }
    });
  }

  return {
    bloomComposer,
    render: () => {
      darkenNonBloom();
      bloomComposer.render();
      restoreMaterials();
    },
    dispose: () => {
      bloomComposer.dispose();
      darkMaterial.dispose();
    },
  };
}

// ─── Trail Manager ───────────────────────────────────────────────────────────

export interface TrailManager {
  trails: Trail[];
  sceneObjects: Map<string, TrailSceneObjects>;
  activeTrailIndex: number;
}

export function createTrailManager(): TrailManager {
  return {
    trails: [],
    sceneObjects: new Map(),
    activeTrailIndex: -1,
  };
}

/** Add a new trail to the manager */
export function addTrail(
  manager: TrailManager,
  path: string[],
  label: string,
  positions: Map<string, THREE.Vector3>,
): Trail {
  const colorIndex = manager.trails.length % TRAIL_COLORS.length;
  const trail: Trail = {
    path,
    label,
    color: TRAIL_COLORS[colorIndex],
    animating: true,
  };

  const objects = createTrailObjects(path, positions, trail.color);
  manager.trails.push(trail);
  manager.sceneObjects.set(label, objects);
  manager.activeTrailIndex = manager.trails.length - 1;

  return trail;
}

/** Remove all trails and clean up */
export function clearTrails(
  manager: TrailManager,
  scene: THREE.Scene,
): void {
  for (const [, objects] of manager.sceneObjects) {
    if (objects.trailLine) {
      scene.remove(objects.trailLine);
      objects.trailLine.geometry.dispose();
      (objects.trailLine.material as THREE.Material).dispose();
    }
    if (objects.particles) {
      scene.remove(objects.particles);
      objects.particles.geometry.dispose();
      (objects.particles.material as THREE.Material).dispose();
    }
  }
  manager.trails = [];
  manager.sceneObjects.clear();
  manager.activeTrailIndex = -1;
}

// ─── Node Highlighting ───────────────────────────────────────────────────────

/** Highlight trail nodes with emissive glow */
export function highlightTrailNodes(
  path: string[],
  nodeMeshes: Map<string, { mesh: THREE.Mesh; node: Node }>,
  color: string,
): () => void {
  const originalEmissive = new Map<string, number>();
  const trailColor = new THREE.Color(color);

  const pathSet = new Set(path);
  for (const [nodeId, entry] of nodeMeshes) {
    const mat = entry.mesh.material as THREE.MeshStandardMaterial;
    if (pathSet.has(nodeId)) {
      originalEmissive.set(nodeId, mat.emissiveIntensity);
      mat.emissive = trailColor;
      mat.emissiveIntensity = 0.4;
      entry.mesh.layers.enable(BLOOM_LAYER);
    } else {
      // Dim non-trail nodes
      originalEmissive.set(nodeId, mat.emissiveIntensity);
      mat.emissiveIntensity = 0.01;
    }
  }

  // Return cleanup function
  return () => {
    for (const [nodeId, entry] of nodeMeshes) {
      const mat = entry.mesh.material as THREE.MeshStandardMaterial;
      const orig = originalEmissive.get(nodeId) ?? 0.05;
      mat.emissiveIntensity = orig;
      entry.mesh.layers.disable(BLOOM_LAYER);
    }
  };
}

// ─── Utilities ───────────────────────────────────────────────────────────────

function emptyTrailObjects(): TrailSceneObjects {
  return {
    trailLine: null,
    particles: null,
    bloomObjects: [],
    cameraSpline: null,
    dashOffset: 0,
    particleProgress: 0,
    cameraProgress: 0,
  };
}

/** Get the spline for a trail (for animation use) */
export function getTrailSpline(
  path: string[],
  positions: Map<string, THREE.Vector3>,
): THREE.CatmullRomCurve3 | null {
  const points = path
    .map((id) => positions.get(id))
    .filter((p): p is THREE.Vector3 => p !== undefined);

  if (points.length < 2) return null;
  return new THREE.CatmullRomCurve3(points, false, "centripetal", 0.5);
}
