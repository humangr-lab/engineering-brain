/* ═══════════════ CONNECTIONS — Tube geometry, particles ═══════════════ */

import * as T from 'three';
import { getCC } from './materials.js';

const EDGE_STYLE = {
  green:  { width: 0.06, dash: false, heightMul: 1.0 },
  blue:   { width: 0.05, dash: false, heightMul: 0.7 },
  purple: { width: 0.05, dash: true,  heightMul: 0.9 },
  cyan:   { width: 0.04, dash: false, heightMul: 0.6 },
  white:  { width: 0.03, dash: false, heightMul: 0.5 },
};

export const connections = [];

/**
 * Apply a vertex gradient from transparent to colored along tube length.
 */
function applyVertexGradient(geo, col) {
  const pos = geo.attributes.position;
  const count = pos.count;
  const colors = new Float32Array(count * 3);
  const r = ((col >> 16) & 255) / 255;
  const g = ((col >> 8) & 255) / 255;
  const b = (col & 255) / 255;
  for (let i = 0; i < count; i++) {
    const t = i / count;
    const a = Math.sin(t * Math.PI);
    colors[i * 3] = r * a;
    colors[i * 3 + 1] = g * a;
    colors[i * 3 + 2] = b * a;
  }
  geo.setAttribute('color', new T.BufferAttribute(colors, 3));
}

/**
 * Build connections (tube curves) between nodes.
 * @param {T.Scene} scene
 * @param {Array} edges - [{f, t, c}]
 * @param {Map} posMap - nodeId → {x, y, z}
 */
export function buildConnections(scene, edges, posMap) {
  // Clear existing
  connections.forEach(c => {
    if (c.tube) scene.remove(c.tube);
    if (c.particles) scene.remove(c.particles);
  });
  connections.length = 0;

  const CC = getCC();

  edges.forEach(e => {
    const from = posMap.get(e.f);
    const to = posMap.get(e.t);
    if (!from || !to) return;

    const style = EDGE_STYLE[e.c] || EDGE_STYLE.white;
    const col = CC[e.c] || CC.white;

    const mid = new T.Vector3(
      (from.x + to.x) / 2,
      (from.y + to.y) / 2 + style.heightMul * 1.5,
      (from.z + to.z) / 2,
    );

    const curve = new T.QuadraticBezierCurve3(
      new T.Vector3(from.x, from.y, from.z),
      mid,
      new T.Vector3(to.x, to.y, to.z),
    );

    const tubeGeo = new T.TubeGeometry(curve, 16, style.width, 4, false);
    applyVertexGradient(tubeGeo, col);

    const tubeMat = new T.MeshStandardMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.65,
      metalness: 0.2,
      roughness: 0.6,
    });

    if (style.dash) {
      tubeMat.opacity = 0.4;
    }

    const tube = new T.Mesh(tubeGeo, tubeMat);
    scene.add(tube);

    // Particle on curve
    const pGeo = new T.SphereGeometry(0.04, 6, 4);
    const pMat = new T.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.5 });
    const particle = new T.Mesh(pGeo, pMat);
    scene.add(particle);

    connections.push({
      tube,
      particles: particle,
      curve,
      t: Math.random(),
      speed: 0.003 + Math.random() * 0.003,
      color: e.c,
    });
  });
}

/**
 * Animate connection particles along curves.
 */
export function tickConnections() {
  connections.forEach(c => {
    if (!c.tube.visible) return;
    c.t = (c.t + c.speed) % 1;
    const pt = c.curve.getPoint(c.t);
    c.particles.position.copy(pt);
  });
}

/**
 * Toggle visibility of connections by color type.
 */
export function toggleConnectionType(colorType, visible) {
  connections.forEach(c => {
    if (c.color === colorType) {
      c.tube.visible = visible;
      c.particles.visible = visible;
    }
  });
}

/* ═══════════════ SUBMAP CONNECTIONS — CatmullRom, arrows, dual particles ═══════════════ */

const _GROUP_TO_EDGE = { source: 'green', layer: 'blue', module: 'purple', consumer: 'cyan' };

/**
 * Build submap connections with CatmullRom curves, arrow heads, and 2 particles per edge.
 * @param {T.Object3D} parent - Group to add meshes to
 * @param {Array} edges - [{f, t, c}]
 * @param {Map} posMap - nodeId → {x, y, z}
 * @param {string} smColor - Submap zone color ('source'|'layer'|'module'|'consumer')
 * @returns {Array} subConns for tickSubmapConnections
 */
export function buildSubmapConnections(parent, edges, posMap, smColor) {
  const CC = getCC();
  const subConns = [];

  edges.forEach((e, idx) => {
    const from = posMap.get(e.f);
    const to = posMap.get(e.t);
    if (!from || !to) return;

    const edgeColor = e.c || _GROUP_TO_EDGE[smColor] || 'purple';
    const style = EDGE_STYLE[edgeColor] || EDGE_STYLE.white;
    const col = CC[edgeColor] || CC.purple;

    // Per-edge offset to avoid overlap
    const offset = (idx % 3 - 1) * 0.1;

    const p0 = new T.Vector3(from.x, from.y, from.z);
    const p3 = new T.Vector3(to.x, to.y, to.z);
    const midX = (from.x + to.x) / 2;
    const midZ = (from.z + to.z) / 2;
    const midY = (from.y + to.y) / 2;

    const p1 = new T.Vector3(
      from.x + (midX - from.x) * 0.4 + offset,
      midY + style.heightMul * 1.8,
      from.z + (midZ - from.z) * 0.4 + offset,
    );
    const p2 = new T.Vector3(
      to.x + (midX - to.x) * 0.4 - offset,
      midY + style.heightMul * 1.8,
      to.z + (midZ - to.z) * 0.4 - offset,
    );

    const curve = new T.CatmullRomCurve3([p0, p1, p2, p3]);

    // Emissive tube
    const tubeGeo = new T.TubeGeometry(curve, 20, style.width * 0.8, 4, false);
    applyVertexGradient(tubeGeo, col);

    const tubeMat = new T.MeshStandardMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.7,
      metalness: 0.2,
      roughness: 0.5,
      emissive: new T.Color(col),
      emissiveIntensity: 0.15,
    });

    const tube = new T.Mesh(tubeGeo, tubeMat);
    parent.add(tube);

    // Arrow head at 80% along curve
    const arrowPos = curve.getPoint(0.8);
    const arrowTan = curve.getTangent(0.8).normalize();
    const coneGeo = new T.ConeGeometry(0.08, 0.22, 6);
    const coneMat = new T.MeshStandardMaterial({
      color: col,
      emissive: col,
      emissiveIntensity: 0.35,
      metalness: 0.3,
      roughness: 0.4,
    });
    const cone = new T.Mesh(coneGeo, coneMat);
    cone.position.copy(arrowPos);
    cone.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), arrowTan);
    parent.add(cone);

    // 2 animated particles per edge
    const particles = [];
    for (let pi = 0; pi < 2; pi++) {
      const pGeo = new T.SphereGeometry(0.045, 6, 4);
      const pMat = new T.MeshStandardMaterial({
        color: col,
        emissive: col,
        emissiveIntensity: 0.9,
      });
      const particle = new T.Mesh(pGeo, pMat);
      parent.add(particle);
      particles.push({
        mesh: particle,
        t: pi * 0.5,
        speed: 0.004 + Math.random() * 0.003,
      });
    }

    subConns.push({ tube, cone, curve, particles, color: edgeColor });
  });

  return subConns;
}

/**
 * Advance submap connection particles along their curves.
 * @param {Array} subConns - from buildSubmapConnections
 */
export function tickSubmapConnections(subConns) {
  subConns.forEach(c => {
    c.particles.forEach(p => {
      p.t = (p.t + p.speed) % 1;
      const pt = c.curve.getPoint(p.t);
      p.mesh.position.copy(pt);
    });
  });
}
