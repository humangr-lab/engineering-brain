/* ═══════════════ SUBMAPS — Drill-down into system nodes ═══════════════ */

import * as T from 'three';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { scene, cam, ren, composer } from './engine.js';
import { setPalette, matFactory, getNeon } from './materials.js';
import { mkObj } from './shapes.js';
import { createPillLabel, createSubLabel, createAutoPill } from './labels.js';
import { connections, buildSubmapConnections, tickSubmapConnections } from './connections.js';
import { animateCamera } from './layout.js';
import { setClickables, hoveredItemId } from './interaction.js';
import { registerSubmapTick, clearSubmapTick } from './animation.js';
import { isDark } from '../theme.js';
import { state } from '../state.js';

/* ── Module state ── */
let _mainGroup = null;
let _mainIcons = [];
let _subGroup = null;
let _savedConnections = [];
let _subCss2dElements = [];
let _subNodeData = [];
let _subConns = [];
let _savedBloomStrength = 0.25;
let _savedFogDensity = 0.008;
let _lastEnterArgs = null;

const _UI_SELECTORS = [
  '.header', '.hint', '.stats-bar', '.legend', '.layout-btns',
  '.tour-btn', '.bg-toggle', '.klib-btn', '.doc-map-btn', '.view-toggle',
];

function _setMainUIVisible(visible) {
  const display = visible ? '' : 'none';
  _UI_SELECTORS.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => { el.style.display = display; });
  });
}

function _setMainGroupVisible(visible) {
  if (!_mainGroup) return;
  _mainGroup.traverse(obj => { obj.visible = visible; });
  scene.traverse(obj => {
    if (obj.element instanceof HTMLElement && obj.element.classList.contains('col-label')) {
      obj.visible = visible;
    }
  });
}

export function setMainGroup(group, icons) { _mainGroup = group; _mainIcons = icons; }

/* ═══════════════ HELPERS ═══════════════ */

function _elasticOut(t) {
  return Math.sin(-13 * (t + 1) * Math.PI / 2) * Math.pow(2, -10 * t) + 1;
}

function _getBloomPass() {
  return composer.passes.find(p => p instanceof UnrealBloomPass);
}

/* ═══════════════ PLATFORM + PARTICLES ═══════════════ */

function _createDefaultPlatform(parent, zoneColor) {
  const dk = isDark();
  const w = 48, d = 22, g = new T.Group();
  const sh = new T.Shape();
  const hw = w / 2, hd = d / 2, r = Math.min(hw, hd) * 0.15;
  sh.moveTo(-hw + r, -hd); sh.lineTo(hw - r, -hd);
  sh.quadraticCurveTo(hw, -hd, hw, -hd + r); sh.lineTo(hw, hd - r);
  sh.quadraticCurveTo(hw, hd, hw - r, hd); sh.lineTo(-hw + r, hd);
  sh.quadraticCurveTo(-hw, hd, -hw, hd - r); sh.lineTo(-hw, -hd + r);
  sh.quadraticCurveTo(-hw, -hd, -hw + r, -hd);
  const extG = new T.ExtrudeGeometry(sh, { depth: 0.08, bevelEnabled: false });
  const surfMat = new T.MeshStandardMaterial({
    color: zoneColor || (dk ? 0x1e2030 : 0xe0e2e8),
    metalness: 0.08, roughness: 0.8, transparent: true, opacity: 0.7,
  });
  const surf = new T.Mesh(extG, surfMat); surf.rotation.x = -Math.PI / 2; g.add(surf);
  const rimMat = new T.LineBasicMaterial({ color: dk ? 0x404860 : 0xb0b4c4, transparent: true, opacity: 0.4 });
  const edge = new T.LineSegments(new T.EdgesGeometry(extG, 15), rimMat);
  edge.rotation.x = -Math.PI / 2; g.add(edge);
  parent.add(g);
  return g;
}

function _createAmbientParticles(parent) {
  const dk = isDark();
  const count = 120, positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 30;
    positions[i * 3 + 1] = Math.random() * 6 + 0.5;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 18;
  }
  const geo = new T.BufferGeometry();
  geo.setAttribute('position', new T.BufferAttribute(positions, 3));
  const mat = new T.PointsMaterial({
    color: dk ? 0x6b8fff : 0x9b7cff, size: 0.06,
    transparent: true, opacity: dk ? 0.4 : 0.25, sizeAttenuation: true,
  });
  const points = new T.Points(geo, mat);
  parent.add(points);
  return { points };
}

/* ═══════════════ SUBMAP TICK ═══════════════ */

let _particles = null;

function _submapTick(time) {
  const hovered = hoveredItemId;

  _subNodeData.forEach(nd => {
    const isHovered = hovered === nd.id;

    nd.targetScale = isHovered ? 1.06 : 1.0;
    nd.currentScale += (nd.targetScale - nd.currentScale) * 0.08;
    nd.group.scale.setScalar(nd.currentScale);

    // Floating bob
    nd.group.position.y = nd.baseY + Math.sin(time * 0.6 + nd.phase) * 0.08;

    // Hero rotation
    if (nd.hero && nd.shape) {
      nd.shape.rotation.y = time * 0.08;
    }

    // Ring pulse on hover
    if (nd.ring && isHovered) {
      nd.ring.scale.setScalar(1 + Math.sin(time * 4) * 0.1);
    } else if (nd.ring) {
      nd.ring.scale.setScalar(1);
    }
  });

  // Animate particles
  if (_particles) {
    const pos = _particles.points.geometry.attributes.position;
    const arr = pos.array;
    for (let i = 0; i < arr.length; i += 3) {
      arr[i + 1] += Math.sin(time * 0.3 + i) * 0.002;
      if (arr[i + 1] > 8) arr[i + 1] = 0.5;
    }
    pos.needsUpdate = true;
  }

  tickSubmapConnections(_subConns);
}

/* ═══════════════ ENTRY ANIMATION ═══════════════ */

function _animateEntry(onConnectionsReady) {
  const sorted = [..._subNodeData].sort((a, b) => {
    if (a.hero && !b.hero) return -1;
    if (!a.hero && b.hero) return 1;
    return Math.sqrt(a.targetX ** 2 + a.targetZ ** 2) - Math.sqrt(b.targetX ** 2 + b.targetZ ** 2);
  });

  const stagger = 80, duration = 600;
  const totalTime = sorted.length * stagger + duration;

  sorted.forEach((nd, i) => {
    const delay = i * stagger;
    nd.group.position.set(nd.targetX, nd.baseY, nd.targetZ);
    nd.group.scale.setScalar(0.001);

    const t0 = performance.now() + delay;

    function step() {
      const now = performance.now();
      if (now < t0) { requestAnimationFrame(step); return; }
      const t = Math.min((now - t0) / duration, 1);
      const ease = _elasticOut(t);
      nd.group.scale.setScalar(Math.max(ease, 0.001));
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });

  setTimeout(onConnectionsReady, totalTime);
}

/* ═══════════════ ENTER SUBMAP ═══════════════ */

export function enterSubmap(nodeId, submaps, nodeDetails, openModal) {
  const smData = submaps[nodeId];
  if (!smData) return;

  _lastEnterArgs = { nodeId, submaps, nodeDetails, openModal };
  state.inSubmap = true;
  state.currentSubmap = nodeId;

  if (_savedConnections.length === 0) {
    _savedConnections = connections.splice(0, connections.length);
  }
  _setMainGroupVisible(false);
  _setMainUIVisible(false);

  const bloom = _getBloomPass();
  if (bloom) {
    _savedBloomStrength = bloom.strength;
    bloom.strength = 0.2;
  }
  _savedFogDensity = scene.fog.density;
  scene.fog.density = 0.008;

  _subGroup = new T.Group();
  _subCss2dElements = [];
  _subNodeData = [];
  _subConns = [];
  _particles = null;
  scene.add(_subGroup);

  const smColor = smData.color || 'module';
  const neonColor = getNeon(smColor);
  const dk = isDark();

  _particles = _createAmbientParticles(_subGroup);

  // ── Build nodes ──
  const posMap = new Map();
  const clickables = [];

  smData.nodes.forEach(n => {
    const isHero = !!n.hero;
    const nd = nodeDetails[n.id];

    setPalette(n.sh || 'sphere', smColor);

    const nodeGroup = new T.Group();
    const nx = n.x * 1.2, nz = n.z * 1.2;

    const s = isHero ? 4.5 : 3.0;
    const shape = mkObj(n.sh || 'sphere', s, matFactory);
    shape.position.y = s * 0.38;
    nodeGroup.add(shape);

    const proxy = new T.Mesh(
      new T.BoxGeometry(s * 1, s * 0.9, s * 0.8),
      new T.MeshBasicMaterial({ visible: false }),
    );
    proxy.position.y = s * 0.38;
    proxy.userData = { id: n.id, subNode: true, parentId: nodeId };
    nodeGroup.add(proxy);

    // Ground pad
    const padR = s * 0.45;
    const pad = new T.Mesh(
      new T.CylinderGeometry(padR, padR, 0.03, 12),
      new T.MeshStandardMaterial({
        color: dk ? 0x2a2e3a : 0xc8ccd4, metalness: 0.1, roughness: 0.8,
        transparent: true, opacity: 0.35,
      }),
    );
    pad.position.y = 0.015;
    nodeGroup.add(pad);

    // Pad ring
    const ring = new T.Mesh(
      new T.RingGeometry(padR - 0.02, padR, 16),
      new T.MeshBasicMaterial({ color: neonColor, transparent: true, opacity: dk ? 0.35 : 0.2, side: T.DoubleSide }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.02;
    nodeGroup.add(ring);

    // Confidence ring
    let confRing = null;
    if (nd && nd.conf != null) {
      const confAngle = Math.PI * 2 * Math.min(nd.conf, 1);
      const confColor = nd.conf < 0.1 ? 0x34d399
        : nd.conf < 0.2 ? 0xfbbf24
        : nd.conf < 0.4 ? 0xf97316 : 0xef4444;
      confRing = new T.Mesh(
        new T.TorusGeometry(padR + 0.04, 0.025, 6, 16, confAngle || 0.01),
        new T.MeshStandardMaterial({ color: confColor, emissive: confColor, emissiveIntensity: 0.3 }),
      );
      confRing.rotation.x = -Math.PI / 2;
      confRing.position.y = 0.03;
      nodeGroup.add(confRing);
    }

    // Contact shadow
    const cShadow = new T.Mesh(
      new T.CircleGeometry(s * 0.4, 12),
      new T.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.12, depthWrite: false }),
    );
    cShadow.rotation.x = -Math.PI / 2;
    cShadow.position.y = 0.005;
    nodeGroup.add(cShadow);

    // Labels
    const label = createPillLabel({ ...n, g: smColor });
    label.position.set(0, s * 0.38 + (isHero ? 1.4 : 1.0), 0);
    nodeGroup.add(label);
    _subCss2dElements.push(label.element);

    if (n.sub) {
      const subLabel = createSubLabel(n.sub);
      subLabel.position.set(0, -0.15, 0);
      nodeGroup.add(subLabel);
      _subCss2dElements.push(subLabel.element);
    }

    if (isHero) {
      const corePill = createAutoPill();
      corePill.element.textContent = 'CORE';
      corePill.position.set(0, s * 0.38 + 1.0, 0);
      nodeGroup.add(corePill);
      _subCss2dElements.push(corePill.element);
    }

    nodeGroup.position.set(nx, 0, nz);
    _subGroup.add(nodeGroup);

    posMap.set(n.id, { x: nx, y: 0, z: nz });

    clickables.push({ mesh: proxy, id: n.id, data: { ...n, _parentId: nodeId } });

    _subNodeData.push({
      group: nodeGroup, shape, proxy, pad, ring,
      glow: null, glass: null, confRing,
      id: n.id, hero: isHero,
      phase: Math.random() * Math.PI * 2,
      baseY: 0, targetX: nx, targetZ: nz,
      currentScale: 1, targetScale: 1,
      currentGlow: 0, targetGlow: 0,
    });
  });

  setClickables(clickables);

  _animateEntry(() => {
    _subConns = buildSubmapConnections(_subGroup, smData.edges, posMap, smColor);
  });

  registerSubmapTick(_submapTick);

  // Camera
  animateCamera({ x: 0, y: 20, z: 20 }, { x: 0, y: 0, z: 0 }, 600);

  // Show controls
  const backBtn = document.getElementById('backBtn');
  const subHeader = document.getElementById('subHeader');
  const subTitle = document.getElementById('subTitle');
  if (backBtn) backBtn.style.display = 'flex';
  if (subHeader) subHeader.style.display = 'flex';
  if (subTitle) subTitle.textContent = smData.title;
}

/* ═══════════════ EXIT SUBMAP ═══════════════ */

export function exitSubmap() {
  if (!_subGroup) return;

  state.inSubmap = false;
  state.currentSubmap = null;
  _lastEnterArgs = null;
  clearSubmapTick();

  const reversed = _subNodeData.slice().reverse();
  const exitStagger = 40, exitDuration = 300;
  const totalExitTime = reversed.length * exitStagger + exitDuration;

  reversed.forEach((nd, i) => {
    const delay = i * exitStagger;
    const startScale = nd.currentScale;
    const t0 = performance.now() + delay;

    function step() {
      const now = performance.now();
      if (now < t0) { requestAnimationFrame(step); return; }
      const t = Math.min((now - t0) / exitDuration, 1);
      const ease = 1 - Math.pow(1 - t, 2);
      nd.group.scale.setScalar(startScale * (1 - ease));
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });

  setTimeout(_cleanup, totalExitTime + 50);

  animateCamera({ x: 12, y: 18, z: 12 }, { x: 0, y: 0, z: 0 }, 800);

  const bloom = _getBloomPass();
  if (bloom) bloom.strength = _savedBloomStrength;
  scene.fog.density = _savedFogDensity;

  const backBtn = document.getElementById('backBtn');
  const subHeader = document.getElementById('subHeader');
  if (backBtn) backBtn.style.display = 'none';
  if (subHeader) subHeader.style.display = 'none';
}

/* ═══════════════ CLEANUP ═══════════════ */

function _cleanup() {
  if (!_subGroup) return;

  scene.remove(_subGroup);
  for (const el of _subCss2dElements) {
    if (el.parentNode) el.parentNode.removeChild(el);
  }
  _subCss2dElements = [];

  _subGroup.traverse(obj => {
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
      else obj.material.dispose();
    }
  });
  _subGroup = null;
  _subNodeData = [];
  _subConns = [];
  _particles = null;

  connections.length = 0;
  connections.push(..._savedConnections);
  _savedConnections = [];

  _setMainGroupVisible(true);
  _setMainUIVisible(true);

  setClickables(_mainIcons.map(i => ({ mesh: i.mesh, id: i.id, data: i.data })));
}

/* ═══════════════ WP-4: L1 Drill Renderer Adapter ═══════════════
   Exposes the submap rendering logic as an L1 renderer for the
   fractal drill FSM. Keeps the original enterSubmap/exitSubmap
   as fallback for schema-defined submaps without the drill system. */

/**
 * Render a submap as an L1 drill view.
 * This is an adapter that calls enterSubmap internally but returns
 * the submap data for the drill system to manage.
 * @param {string} nodeId - The system-level node ID that has a submap
 * @param {object} submapData - Submap data (nodes, edges, color, title)
 * @returns {{ nodes: Array, edges: Array, cleanup: Function }}
 */
export function renderAsL1(nodeId, submapData) {
  if (!submapData) return null;

  // Return the submap data in a form the drill system can use
  return {
    id: nodeId,
    label: submapData.title || nodeId,
    nodes: submapData.nodes || [],
    edges: submapData.edges || [],
    color: submapData.color || 'module',
    cleanup: () => {
      // If the drill system needs to clean up, it can call this
      if (_subGroup) _cleanup();
    },
  };
}
