/* ═══════════════ PLATFORMS — Zone platforms, ground pads ═══════════════ */

import * as T from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

export const platSurfs = [];
export const platEdges = [];
export const platIsMain = [];
export const rimMats = [];

/**
 * Create a platform (hexagonal pad) for grouping nodes.
 */
export function mkPlat(scene, w, d, x, z, label, isMain, tgt, zoneColor) {
  const g = new T.Group();
  const sh = new T.Shape();
  const hw = w / 2, hd = d / 2;
  const r = Math.min(hw, hd) * 0.2;
  sh.moveTo(-hw + r, -hd);
  sh.lineTo(hw - r, -hd);
  sh.quadraticCurveTo(hw, -hd, hw, -hd + r);
  sh.lineTo(hw, hd - r);
  sh.quadraticCurveTo(hw, hd, hw - r, hd);
  sh.lineTo(-hw + r, hd);
  sh.quadraticCurveTo(-hw, hd, -hw, hd - r);
  sh.lineTo(-hw, -hd + r);
  sh.quadraticCurveTo(-hw, -hd, -hw + r, -hd);

  const extG = new T.ExtrudeGeometry(sh, { depth: 0.08, bevelEnabled: false });
  const surfMat = new T.MeshStandardMaterial({
    color: zoneColor || 0xe0e2e8,
    metalness: 0.08,
    roughness: 0.8,
    transparent: true,
    opacity: 0.7,
  });
  const surf = new T.Mesh(extG, surfMat);
  surf.rotation.x = -Math.PI / 2;
  g.add(surf);
  platSurfs.push(surf);
  platIsMain.push(isMain);

  // Rim edge
  const edgeG = new T.EdgesGeometry(extG, 15);
  const rimColor = isMain ? 0xb0b4c4 : 0xc4c8d0;
  const rimMat = new T.LineBasicMaterial({ color: rimColor, transparent: true, opacity: 0.4 });
  const edge = new T.LineSegments(edgeG, rimMat);
  edge.rotation.x = -Math.PI / 2;
  g.add(edge);
  platEdges.push(edge);
  rimMats.push(rimMat);

  // Label
  if (label) {
    const el = document.createElement('div');
    el.className = isMain ? 'plat-label main' : 'plat-label';
    el.textContent = label;
    const lbl = new CSS2DObject(el);
    lbl.position.set(0, 0.02, hd + 0.6);
    g.add(lbl);
  }

  g.position.set(x, 0, z);
  scene.add(g);
  return g;
}

/**
 * Radial gradient canvas texture for the ground disc.
 * Light gray center → slightly darker edge, with subtle concentric ring lines.
 */
function _makeGroundTexture(size) {
  const c = document.createElement('canvas');
  c.width = size; c.height = size;
  const ctx = c.getContext('2d');
  const cx = size / 2, cy = size / 2, maxR = size / 2;

  // Radial gradient fill — light gray center to slightly darker edge
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR);
  grad.addColorStop(0.0, '#e8e9ed');
  grad.addColorStop(0.25, '#e4e5ea');
  grad.addColorStop(0.5, '#dfe0e6');
  grad.addColorStop(0.75, '#d8dae2');
  grad.addColorStop(1.0, '#d0d2dc');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, size, size);

  // Concentric ring lines at orbit positions (5, 10, 15, 20 in world units → mapped to texture)
  // Ground disc radius is 22 world units = maxR pixels
  const orbits = [5, 10, 15, 20];
  ctx.strokeStyle = 'rgba(180, 185, 200, 0.35)';
  ctx.lineWidth = 1.5;
  orbits.forEach(worldR => {
    const texR = (worldR / 22) * maxR;
    ctx.beginPath();
    ctx.arc(cx, cy, texR, 0, Math.PI * 2);
    ctx.stroke();
  });

  // Subtle radial lines (sector dividers, very faint)
  ctx.strokeStyle = 'rgba(180, 185, 200, 0.12)';
  ctx.lineWidth = 1;
  for (let i = 0; i < 12; i++) {
    const angle = (i / 12) * Math.PI * 2;
    const innerR = (5 / 22) * maxR;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * innerR, cy + Math.sin(angle) * innerR);
    ctx.lineTo(cx + Math.cos(angle) * maxR * 0.95, cy + Math.sin(angle) * maxR * 0.95);
    ctx.stroke();
  }

  const tex = new T.CanvasTexture(c);
  tex.colorSpace = T.SRGBColorSpace;
  return tex;
}

/**
 * Create the main ground disc with radial gradient and concentric rings.
 */
export function createGround(scene) {
  // Main ground disc with gradient texture
  const tex = _makeGroundTexture(512);
  const groundGeo = new T.CylinderGeometry(22, 22, 0.08, 32);
  const groundMat = new T.MeshLambertMaterial({ map: tex });
  const ground = new T.Mesh(groundGeo, groundMat);
  ground.position.y = 0.04;
  scene.add(ground);

  // Center pad — slightly lighter to highlight core
  const centerTex = _makeCenterTexture(256);
  const centerGeo = new T.CylinderGeometry(7, 7, 0.12, 24);
  const centerMat = new T.MeshLambertMaterial({ map: centerTex });
  const center = new T.Mesh(centerGeo, centerMat);
  center.position.y = 0.06;
  scene.add(center);

  return { ground, center };
}

/**
 * Center pad gradient — lighter, subtle ring at edge.
 */
function _makeCenterTexture(size) {
  const c = document.createElement('canvas');
  c.width = size; c.height = size;
  const ctx = c.getContext('2d');
  const cx = size / 2, cy = size / 2, maxR = size / 2;

  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR);
  grad.addColorStop(0.0, '#e2e0ea');
  grad.addColorStop(0.6, '#ddd8e6');
  grad.addColorStop(1.0, '#d4d0e0');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, size, size);

  // Edge ring
  ctx.strokeStyle = 'rgba(155, 124, 255, 0.15)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(cx, cy, maxR * 0.92, 0, Math.PI * 2);
  ctx.stroke();

  const tex = new T.CanvasTexture(c);
  tex.colorSpace = T.SRGBColorSpace;
  return tex;
}

/**
 * Create zone overlays (the 3 column regions).
 */
export function createZones(scene) {
  const zoneMats = [];
  const zoneConfigs = [
    { angle: -Math.PI / 3, color: 0x6b8fff, label: 'LAYERS', cssClass: 'layers' },
    { angle: Math.PI / 6, color: 0x9b7cff, label: 'PROCESSING', cssClass: 'processing' },
    { angle: Math.PI * 2 / 3, color: 0x34d399, label: 'LEARNING', cssClass: 'learning' },
  ];

  // Only column labels — no colored overlays, no divider line
  zoneConfigs.forEach(z => {
    const el = document.createElement('div');
    el.className = `col-label ${z.cssClass}`;
    el.textContent = z.label;
    const lbl = new CSS2DObject(el);
    const cx = Math.cos(z.angle + Math.PI / 6) * 18;
    const cz = Math.sin(z.angle + Math.PI / 6) * 18;
    lbl.position.set(cx, 0.2, cz);
    scene.add(lbl);
  });

  return zoneMats;
}
