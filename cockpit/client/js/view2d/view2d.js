/* ═══════════════ 2D VIEW — Top-Down Camera Mode ═══════════════
   No separate renderer. Just switches the existing Three.js
   orthographic camera to look straight down and locks rotation.
   Scroll = pan up/down. Ctrl+scroll = zoom. Drag = pan.
   ═════════════════════════════════════════════════════════════ */

import { state } from '../state.js';
import { cam, ctrl, ren } from '../scene/engine.js';
import { animateCamera, CAMERA_PRESETS } from '../scene/layout.js';
import * as T from 'three';

let _saved = null;
let _wheelHandler = null;

// ── Public API ──

export function initView2d() {
  // Nothing to initialize — reuses existing Three.js scene
}

export function show2d() {
  _saved = {
    pos: cam.position.clone(),
    target: ctrl.target.clone(),
    zoom: cam.zoom,
    minPolar: ctrl.minPolarAngle,
    maxPolar: ctrl.maxPolarAngle,
    enableRotate: ctrl.enableRotate,
    enableZoom: ctrl.enableZoom,
    screenSpacePanning: ctrl.screenSpacePanning,
    mouseButtons: { ...ctrl.mouseButtons },
  };

  state.viewMode = '2d';

  // Zoom in
  _animateZoom(cam.zoom, 2.2, 800);

  // Animate camera to top-down
  animateCamera(
    { x: 0, y: 45, z: 0.01 },
    { x: 0, y: 0, z: 0 },
    800,
  ).then(() => {
    // Lock top-down
    ctrl.minPolarAngle = 0;
    ctrl.maxPolarAngle = 0.01;
    ctrl.enableRotate = false;
    ctrl.screenSpacePanning = true;

    // Left-click drag = pan (instead of rotate)
    ctrl.mouseButtons = {
      LEFT: T.MOUSE.PAN,
      MIDDLE: T.MOUSE.PAN,
      RIGHT: T.MOUSE.PAN,
    };

    // Disable OrbitControls zoom (we handle scroll ourselves)
    ctrl.enableZoom = false;
  });

  // Custom wheel: scroll = pan, Ctrl/Cmd+scroll = zoom
  _wheelHandler = (e) => {
    if (state.viewMode !== '2d') return;
    e.preventDefault();

    if (e.ctrlKey || e.metaKey) {
      // Zoom
      const zoomDelta = e.deltaY > 0 ? 0.9 : 1.1;
      cam.zoom = Math.max(0.5, Math.min(8, cam.zoom * zoomDelta));
      cam.updateProjectionMatrix();
    } else {
      // Pan: scroll moves the camera in world XZ plane
      const panSpeed = 0.15 / cam.zoom;
      // deltaY = up/down → move in Z (world), deltaX = left/right → move in X
      cam.position.z += e.deltaY * panSpeed;
      ctrl.target.z += e.deltaY * panSpeed;
      cam.position.x += e.deltaX * panSpeed;
      ctrl.target.x += e.deltaX * panSpeed;
    }
  };
  ren.domElement.addEventListener('wheel', _wheelHandler, { passive: false });
}

export function hide2d() {
  state.viewMode = '3d';

  // Remove custom wheel handler
  if (_wheelHandler) {
    ren.domElement.removeEventListener('wheel', _wheelHandler);
    _wheelHandler = null;
  }

  // Restore controls
  if (_saved) {
    ctrl.minPolarAngle = _saved.minPolar;
    ctrl.maxPolarAngle = _saved.maxPolar;
    ctrl.enableRotate = _saved.enableRotate;
    ctrl.enableZoom = _saved.enableZoom;
    ctrl.screenSpacePanning = _saved.screenSpacePanning;
    ctrl.mouseButtons = _saved.mouseButtons;
  }

  // Animate zoom back
  _animateZoom(cam.zoom, _saved?.zoom || 1, 800);

  // Animate camera back
  const target = _saved
    ? { pos: { x: _saved.pos.x, y: _saved.pos.y, z: _saved.pos.z },
        lookAt: { x: _saved.target.x, y: _saved.target.y, z: _saved.target.z } }
    : CAMERA_PRESETS.default;

  animateCamera(target.pos, target.lookAt, 800);
  _saved = null;
}

export function is2dActive() {
  return state.viewMode === '2d';
}

// ── Helpers ──

function _animateZoom(from, to, duration) {
  const start = performance.now();
  function step() {
    const t = Math.min((performance.now() - start) / duration, 1);
    const ease = 1 - Math.pow(1 - t, 3);
    cam.zoom = from + (to - from) * ease;
    cam.updateProjectionMatrix();
    if (t < 1) requestAnimationFrame(step);
  }
  step();
}

