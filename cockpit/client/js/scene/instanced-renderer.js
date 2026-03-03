/* ═══════════════ WP-PERF: INSTANCED RENDERER ═══════════════
   InstancedMesh manager for high-performance rendering of large graphs.
   Groups nodes by shape type (26 groups max) and renders each group
   as a single InstancedMesh draw call instead of N individual Groups.

   API:
     createInstancedScene(nodes, edges, sceneRef) → InstancedScene
     updateInstancePosition(scene, nodeId, position)
     updateInstanceColor(scene, nodeId, color)
     highlightInstance(scene, nodeId, emissive)
     disposeInstancedScene(scene)
   ════════════════════════════════════════════════════════════════ */

import * as T from 'three';
import { mkObj } from './shapes.js';
import { setPalette, matFactory, getCC } from './materials.js';

// ── All known shape types (from shapes.js) ─────────────────────────────
const ALL_SHAPES = [
  'warehouse', 'factory', 'satellite', 'terminal', 'monument', 'pillars',
  'gear', 'gate', 'database', 'hourglass', 'brain', 'dyson_book', 'gauge',
  'hub', 'tree', 'sphere', 'prism', 'stairs', 'nexus', 'graph', 'dial',
  'vault', 'screens', 'rack', 'conveyor', 'monitor',
];

// Temp objects reused across per-frame matrix updates (zero allocation)
const _tmpMatrix = new T.Matrix4();
const _tmpPos = new T.Vector3();
const _tmpQuat = new T.Quaternion();
const _tmpScale = new T.Vector3(1, 1, 1);
const _tmpColor = new T.Color();

/**
 * @typedef {Object} InstancedScene
 * @property {T.Group} group - Root group added to the Three.js scene
 * @property {Map<string, {shapeType: string, instanceIndex: number}>} nodeLookup
 * @property {Map<string, InstancedMesh>} meshes - shapeType → InstancedMesh
 * @property {Map<string, T.MeshStandardMaterial>} materials - shapeType → material
 * @property {Map<string, {x: number, y: number, z: number}>} positions
 * @property {Array} edgeMeshes - Edge line segments
 * @property {Function} dispose - Cleanup function
 */

// ── Geometry Cache ──────────────────────────────────────────────────────
// Build a merged BufferGeometry per shape type for instanced rendering.
// We create ONE representative Group via mkObj, then merge all child meshes
// into a single geometry with vertex colors encoding the material tint.
const _geoCache = new Map();
const _matCache = new Map();

/**
 * Build a merged geometry + shared material for a given shape type.
 * The merged geometry bakes all child mesh positions/orientations into vertices,
 * and uses vertex colors so we need only ONE draw call per shape type.
 *
 * @param {string} shapeType
 * @param {string} group - Node group for palette selection
 * @param {number} size - Base size scalar
 * @returns {{geometry: T.BufferGeometry, material: T.MeshStandardMaterial}}
 */
function _getOrBuildMergedShape(shapeType, group, size) {
  const cacheKey = `${shapeType}_${group}_${size.toFixed(2)}`;
  if (_geoCache.has(cacheKey)) {
    return { geometry: _geoCache.get(cacheKey), material: _matCache.get(cacheKey) };
  }

  // Set palette so mkObj picks up the right colors
  setPalette(shapeType, group);

  // Build a representative Group
  const representative = mkObj(shapeType, size, matFactory);

  // Collect all child meshes and their transforms
  const geometries = [];
  representative.traverse((child) => {
    if (child.isMesh && child.geometry) {
      // Clone geometry so we can bake transforms
      const geo = child.geometry.clone();

      // Bake child's local transform into vertices
      child.updateMatrixWorld(true);
      // For children of the Group, matrixWorld includes the group's identity
      // We want the child's position/rotation/scale relative to the Group
      const localMatrix = new T.Matrix4();
      localMatrix.compose(child.position, child.quaternion, child.scale);
      geo.applyMatrix4(localMatrix);

      // Encode material color as vertex colors
      const color = child.material?.color || new T.Color(0x808080);
      const count = geo.attributes.position.count;
      const colors = new Float32Array(count * 3);
      for (let i = 0; i < count; i++) {
        colors[i * 3] = color.r;
        colors[i * 3 + 1] = color.g;
        colors[i * 3 + 2] = color.b;
      }
      geo.setAttribute('color', new T.BufferAttribute(colors, 3));

      geometries.push(geo);
    }
  });

  // Merge all child geometries into one
  let merged;
  if (geometries.length === 0) {
    // Fallback: simple box
    merged = new T.BoxGeometry(size * 0.5, size * 0.5, size * 0.5);
    const count = merged.attributes.position.count;
    const colors = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      colors[i * 3] = 0.5;
      colors[i * 3 + 1] = 0.5;
      colors[i * 3 + 2] = 0.5;
    }
    merged.setAttribute('color', new T.BufferAttribute(colors, 3));
  } else if (geometries.length === 1) {
    merged = geometries[0];
  } else {
    merged = _mergeBufferGeometries(geometries);
  }

  // Shared material with vertex colors
  const material = new T.MeshStandardMaterial({
    vertexColors: true,
    metalness: 0.30,
    roughness: 0.50,
  });

  _geoCache.set(cacheKey, merged);
  _matCache.set(cacheKey, material);

  // Dispose the temporary representative
  representative.traverse((child) => {
    if (child.isMesh) {
      child.geometry?.dispose();
      // Don't dispose shared materials from matFactory cache
    }
  });

  return { geometry: merged, material };
}

/**
 * Merge multiple BufferGeometries into one.
 * All must have position and color attributes.
 */
function _mergeBufferGeometries(geometries) {
  let totalVerts = 0;
  let totalIndices = 0;

  // Count totals
  for (const geo of geometries) {
    totalVerts += geo.attributes.position.count;
    if (geo.index) {
      totalIndices += geo.index.count;
    } else {
      totalIndices += geo.attributes.position.count;
    }
  }

  const positions = new Float32Array(totalVerts * 3);
  const normals = new Float32Array(totalVerts * 3);
  const colors = new Float32Array(totalVerts * 3);
  const indices = new Uint32Array(totalIndices);

  let vertOffset = 0;
  let idxOffset = 0;

  for (const geo of geometries) {
    const pos = geo.attributes.position;
    const norm = geo.attributes.normal;
    const col = geo.attributes.color;
    const count = pos.count;

    // Copy positions
    for (let i = 0; i < count * 3; i++) {
      positions[vertOffset * 3 + i] = pos.array[i];
    }

    // Copy normals
    if (norm) {
      for (let i = 0; i < count * 3; i++) {
        normals[vertOffset * 3 + i] = norm.array[i];
      }
    }

    // Copy vertex colors
    if (col) {
      for (let i = 0; i < count * 3; i++) {
        colors[vertOffset * 3 + i] = col.array[i];
      }
    }

    // Copy indices (offset by vertOffset)
    if (geo.index) {
      for (let i = 0; i < geo.index.count; i++) {
        indices[idxOffset + i] = geo.index.array[i] + vertOffset;
      }
      idxOffset += geo.index.count;
    } else {
      for (let i = 0; i < count; i++) {
        indices[idxOffset + i] = vertOffset + i;
      }
      idxOffset += count;
    }

    vertOffset += count;
  }

  const merged = new T.BufferGeometry();
  merged.setAttribute('position', new T.BufferAttribute(positions, 3));
  merged.setAttribute('normal', new T.BufferAttribute(normals, 3));
  merged.setAttribute('color', new T.BufferAttribute(colors, 3));
  merged.setIndex(new T.BufferAttribute(indices.slice(0, idxOffset), 1));
  merged.computeVertexNormals();

  return merged;
}

// ═══════════════════════════════════════════════════════════════════════
// PUBLIC API
// ═══════════════════════════════════════════════════════════════════════

/**
 * Create an instanced scene from nodes and edges.
 * Groups all nodes by shape type, creates one InstancedMesh per type.
 *
 * @param {Array} nodes - [{id, x, z, label, g, sh, hero, ...}]
 * @param {Array} edges - [{f, t, c}]
 * @param {T.Scene} sceneRef - The Three.js scene to add the group to
 * @returns {InstancedScene}
 */
export function createInstancedScene(nodes, edges, sceneRef) {
  const group = new T.Group();
  group.name = 'instanced-root';

  /** @type {Map<string, {shapeType: string, instanceIndex: number}>} */
  const nodeLookup = new Map();

  /** @type {Map<string, T.InstancedMesh>} */
  const meshes = new Map();

  /** @type {Map<string, T.MeshStandardMaterial>} */
  const materials = new Map();

  /** @type {Map<string, {x: number, y: number, z: number}>} */
  const positionMap = new Map();

  // ── Step 1: Group nodes by shape type ─────────────────────────────
  /** @type {Map<string, Array>} */
  const shapeGroups = new Map();
  const visibleNodes = nodes.filter(n => !n.hidden);

  for (const n of visibleNodes) {
    const sh = n.sh || 'sphere';
    if (!shapeGroups.has(sh)) shapeGroups.set(sh, []);
    shapeGroups.get(sh).push(n);
  }

  // ── Step 2: Create one InstancedMesh per shape type ───────────────
  for (const [shapeType, shapeNodes] of shapeGroups) {
    const count = shapeNodes.length;
    // Use first node's group for palette; all instances share the merged geo
    const firstGroup = shapeNodes[0].g || 'module';
    // Use a representative size for the merged geometry
    const representativeSize = 2.0;

    const { geometry, material } = _getOrBuildMergedShape(shapeType, firstGroup, representativeSize);

    const instancedMesh = new T.InstancedMesh(geometry, material.clone(), count);
    instancedMesh.name = `instanced-${shapeType}`;
    instancedMesh.castShadow = false;
    instancedMesh.receiveShadow = false;

    // Enable per-instance colors
    instancedMesh.instanceColor = new T.InstancedBufferAttribute(
      new Float32Array(count * 3), 3,
    );

    // Set transforms for each instance
    for (let i = 0; i < count; i++) {
      const n = shapeNodes[i];

      // Compute node size (same logic as app.js _buildScene)
      const inferredSize = n._inferredSize || 1.0;
      const s = n.hero ? 4.5 : Math.max(1.5, inferredSize * 1.8 + 0.4);
      // Scale factor relative to representativeSize
      const scaleFactor = s / representativeSize;

      // Compute Y position (simplified from app.js)
      const baseY = n._inferredSize != null
        ? n._inferredSize * 0.5 + 0.5
        : 1.0;

      const x = n.x || (n.properties?.x ?? 0);
      const y = baseY + s * 0.38;
      const z = n.z || (n.properties?.z ?? 0);

      // Store position
      positionMap.set(n.id, { x, y, z });

      // Set instance matrix
      _tmpPos.set(x, y, z);
      _tmpQuat.identity();
      _tmpScale.set(scaleFactor, scaleFactor, scaleFactor);
      _tmpMatrix.compose(_tmpPos, _tmpQuat, _tmpScale);
      instancedMesh.setMatrixAt(i, _tmpMatrix);

      // Set instance color (use palette accent as tint indicator)
      setPalette(shapeType, n.g || 'module');
      const pal = matFactory.palette;
      _tmpColor.set(pal.m);
      instancedMesh.setColorAt(i, _tmpColor);

      // Register in lookup
      nodeLookup.set(n.id, { shapeType, instanceIndex: i });
    }

    instancedMesh.instanceMatrix.needsUpdate = true;
    if (instancedMesh.instanceColor) instancedMesh.instanceColor.needsUpdate = true;

    // Compute bounding sphere for frustum culling
    instancedMesh.computeBoundingSphere();

    meshes.set(shapeType, instancedMesh);
    materials.set(shapeType, instancedMesh.material);
    group.add(instancedMesh);
  }

  // ── Step 3: Build instanced edges (batched line segments) ─────────
  const edgeMeshes = _buildInstancedEdges(edges, positionMap, group);

  // ── Step 4: Add to scene ──────────────────────────────────────────
  sceneRef.add(group);

  const instancedScene = {
    group,
    nodeLookup,
    meshes,
    materials,
    positions: positionMap,
    edgeMeshes,
    nodeCount: visibleNodes.length,
    dispose: () => disposeInstancedScene(instancedScene),
  };

  return instancedScene;
}

/**
 * Build edges as batched line segments for minimal draw calls.
 * Uses a single LineSegments mesh for all edges.
 */
function _buildInstancedEdges(edges, posMap, parentGroup) {
  const CC = getCC();
  const validEdges = edges.filter(e => posMap.has(e.f) && posMap.has(e.t));

  if (validEdges.length === 0) return [];

  // One LineSegments mesh per color type for proper coloring
  const colorGroups = new Map();
  for (const e of validEdges) {
    const c = e.c || 'white';
    if (!colorGroups.has(c)) colorGroups.set(c, []);
    colorGroups.get(c).push(e);
  }

  const edgeMeshes = [];

  for (const [colorType, colorEdges] of colorGroups) {
    const positions = new Float32Array(colorEdges.length * 6); // 2 verts * 3 coords
    const col = CC[colorType] || CC.white;

    for (let i = 0; i < colorEdges.length; i++) {
      const e = colorEdges[i];
      const from = posMap.get(e.f);
      const to = posMap.get(e.t);

      positions[i * 6 + 0] = from.x;
      positions[i * 6 + 1] = from.y;
      positions[i * 6 + 2] = from.z;
      positions[i * 6 + 3] = to.x;
      positions[i * 6 + 4] = to.y;
      positions[i * 6 + 5] = to.z;
    }

    const geo = new T.BufferGeometry();
    geo.setAttribute('position', new T.BufferAttribute(positions, 3));

    const mat = new T.LineBasicMaterial({
      color: col,
      transparent: true,
      opacity: 0.45,
      linewidth: 1,
    });

    const lines = new T.LineSegments(geo, mat);
    lines.name = `instanced-edges-${colorType}`;
    parentGroup.add(lines);
    edgeMeshes.push({ mesh: lines, colorType });
  }

  return edgeMeshes;
}

/**
 * Update the position of a single node instance.
 *
 * @param {InstancedScene} iScene
 * @param {string} nodeId
 * @param {{x: number, y: number, z: number}} position
 */
export function updateInstancePosition(iScene, nodeId, position) {
  const entry = iScene.nodeLookup.get(nodeId);
  if (!entry) return;

  const mesh = iScene.meshes.get(entry.shapeType);
  if (!mesh) return;

  // Read current matrix to preserve scale and rotation
  mesh.getMatrixAt(entry.instanceIndex, _tmpMatrix);
  _tmpMatrix.decompose(_tmpPos, _tmpQuat, _tmpScale);

  // Update position
  _tmpPos.set(position.x, position.y, position.z);
  _tmpMatrix.compose(_tmpPos, _tmpQuat, _tmpScale);
  mesh.setMatrixAt(entry.instanceIndex, _tmpMatrix);
  mesh.instanceMatrix.needsUpdate = true;

  // Update stored position
  iScene.positions.set(nodeId, { ...position });
}

/**
 * Batch-update positions from a Float32Array (from Web Worker).
 * Layout: [x0, y0, z0, x1, y1, z1, ...]
 * Node order must match the order nodes were passed to createInstancedScene.
 *
 * @param {InstancedScene} iScene
 * @param {Array} nodeOrder - Array of node IDs in the same order as the Float32Array
 * @param {Float32Array} positionsArray - Flat xyz positions
 */
export function batchUpdatePositions(iScene, nodeOrder, positionsArray) {
  // Guard: ensure positionsArray has enough data for all nodes
  const maxIdx = Math.min(nodeOrder.length, Math.floor(positionsArray.length / 3));
  for (let i = 0; i < maxIdx; i++) {
    const nodeId = nodeOrder[i];
    const entry = iScene.nodeLookup.get(nodeId);
    if (!entry) continue;

    const x = positionsArray[i * 3];
    const y = positionsArray[i * 3 + 1];
    const z = positionsArray[i * 3 + 2];

    const mesh = iScene.meshes.get(entry.shapeType);
    if (!mesh) continue;

    mesh.getMatrixAt(entry.instanceIndex, _tmpMatrix);
    _tmpMatrix.decompose(_tmpPos, _tmpQuat, _tmpScale);
    _tmpPos.set(x, y, z);
    _tmpMatrix.compose(_tmpPos, _tmpQuat, _tmpScale);
    mesh.setMatrixAt(entry.instanceIndex, _tmpMatrix);

    iScene.positions.set(nodeId, { x, y, z });
  }

  // Mark all instanced meshes as needing update
  for (const mesh of iScene.meshes.values()) {
    mesh.instanceMatrix.needsUpdate = true;
  }
}

/**
 * Update the color of a single node instance.
 *
 * @param {InstancedScene} iScene
 * @param {string} nodeId
 * @param {number|T.Color} color - Hex int or THREE.Color
 */
export function updateInstanceColor(iScene, nodeId, color) {
  const entry = iScene.nodeLookup.get(nodeId);
  if (!entry) return;

  const mesh = iScene.meshes.get(entry.shapeType);
  if (!mesh || !mesh.instanceColor) return;

  _tmpColor.set(color);
  mesh.setColorAt(entry.instanceIndex, _tmpColor);
  mesh.instanceColor.needsUpdate = true;
}

/**
 * Highlight a node instance with emissive glow.
 *
 * @param {InstancedScene} iScene
 * @param {string} nodeId
 * @param {number|null} emissive - Hex color for emissive, or null to reset
 */
export function highlightInstance(iScene, nodeId, emissive) {
  const entry = iScene.nodeLookup.get(nodeId);
  if (!entry) return;

  const mat = iScene.materials.get(entry.shapeType);
  if (!mat) return;

  // Note: per-instance emissive is not natively supported by InstancedMesh.
  // We set the material-level emissive which affects ALL instances of this shape.
  // For selective highlighting, use updateInstanceColor with a bright color instead.
  if (emissive != null) {
    mat.emissive = new T.Color(emissive);
    mat.emissiveIntensity = 0.3;
  } else {
    mat.emissive = new T.Color(0x000000);
    mat.emissiveIntensity = 0;
  }
  mat.needsUpdate = true;
}

/**
 * Dispose all resources held by an instanced scene.
 *
 * @param {InstancedScene} iScene
 */
export function disposeInstancedScene(iScene) {
  if (!iScene || !iScene.group) return;

  // Dispose instanced meshes
  // Note: geometry comes from _geoCache and is shared -- do NOT dispose it.
  // Only dispose the cloned material and the InstancedMesh's own buffers.
  for (const mesh of iScene.meshes.values()) {
    mesh.material?.dispose();
    mesh.dispose(); // Disposes instanceMatrix and instanceColor buffers
  }

  // Dispose edge meshes
  for (const { mesh } of iScene.edgeMeshes) {
    mesh.geometry?.dispose();
    mesh.material?.dispose();
  }

  // Remove from parent
  if (iScene.group.parent) {
    iScene.group.parent.remove(iScene.group);
  }

  iScene.meshes.clear();
  iScene.materials.clear();
  iScene.nodeLookup.clear();
  iScene.positions.clear();
  iScene.edgeMeshes.length = 0;
}

/**
 * Get the draw call count for the instanced scene.
 * Useful for benchmarking.
 *
 * @param {InstancedScene} iScene
 * @returns {number}
 */
export function getInstancedDrawCallCount(iScene) {
  return iScene.meshes.size + iScene.edgeMeshes.length;
}
