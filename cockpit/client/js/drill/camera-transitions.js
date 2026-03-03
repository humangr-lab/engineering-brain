/* ═══════════════ WP-4: CAMERA TRANSITIONS — Smooth drill navigation ═══════════════
   Duration: 350ms (Material Design 3)
   Easing: cubic-bezier(0.2, 0, 0, 1) -- emphasized easing
   Rotation: SLERP for quaternion interpolation (Shoemake 1985)
   Path: Arc for depth changes (sin-based lift to prevent clipping)

   Per-level camera presets:
     L0: perspective, 80u distance, 60deg FOV, OrbitControls
     L1: perspective, 30u distance, 55deg FOV, OrbitControls
     L2: perspective, 12u distance, 50deg FOV, restricted pan
     L3: orthographic, 5u distance, scroll only
     L4: orthographic, 5u distance, text cursor

   References:
     - docs/research/F-06_fractal_drill_down.md Sections 5, 8.3
     - docs/design/wireframes.md Screen 2                                          */

import * as T from 'three';
import { cam, ctrl } from '../scene/engine.js';
import { state } from '../state.js';
import { LEVELS } from './zoom-manager.js';

/* ── Constants ── */

const DRILL_DURATION = 350;   // ms, Material Design 3

/**
 * Material Design 3 emphasized easing: cubic-bezier(0.2, 0, 0, 1)
 * Pre-computed Bezier curve evaluation for performance.
 */
function _emphasizedEase(t) {
  // cubic-bezier(0.2, 0, 0, 1) approximation via rational polynomial
  // For exact cubic bezier, we solve the parametric form.
  // Simplified: fast start, smooth decelerate landing.
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return _cubicBezier(0.2, 0, 0, 1, t);
}

/**
 * Evaluate cubic-bezier(x1, y1, x2, y2) at parameter t.
 * Uses Newton-Raphson to invert the x(t) -> t mapping, then evaluates y(t).
 */
function _cubicBezier(x1, y1, x2, y2, x) {
  // Solve for t where bezierX(t) = x
  let t = x; // initial guess
  for (let i = 0; i < 8; i++) {
    const bx = _bezierComponent(x1, x2, t);
    const dx = _bezierDerivative(x1, x2, t);
    if (Math.abs(dx) < 1e-6) break;
    t -= (bx - x) / dx;
    t = Math.max(0, Math.min(1, t));
  }
  return _bezierComponent(y1, y2, t);
}

function _bezierComponent(p1, p2, t) {
  // B(t) = 3(1-t)^2*t*p1 + 3(1-t)*t^2*p2 + t^3
  const t2 = t * t;
  const t3 = t2 * t;
  const mt = 1 - t;
  const mt2 = mt * mt;
  return 3 * mt2 * t * p1 + 3 * mt * t2 * p2 + t3;
}

function _bezierDerivative(p1, p2, t) {
  const mt = 1 - t;
  return 3 * mt * mt * p1 + 6 * mt * t * (p2 - p1) + 3 * t * t * (1 - p2);
}

/**
 * Camera presets per drill level.
 * L0-L2: perspective (3D spatial relationships matter).
 * L3-L4: orthographic (code is 2D, perspective distortion harmful).
 */
export const CAMERA_PRESETS = {
  [LEVELS.SYSTEM]: {
    distance: 80,
    fov: 60,
    type: 'perspective',
    position: new T.Vector3(12, 18, 12),
    lookAt: new T.Vector3(0, 0, 0),
  },
  [LEVELS.MODULE]: {
    distance: 30,
    fov: 55,
    type: 'perspective',
    position: new T.Vector3(0, 20, 20),
    lookAt: new T.Vector3(0, 0, 0),
  },
  [LEVELS.FILE]: {
    distance: 12,
    fov: 50,
    type: 'perspective',
    position: new T.Vector3(0, 10, 8),
    lookAt: new T.Vector3(0, 0, 0),
  },
  [LEVELS.FUNCTION]: {
    distance: 5,
    fov: null, // orthographic
    type: 'orthographic',
    position: new T.Vector3(0, 5, 0),
    lookAt: new T.Vector3(0, 0, 0),
  },
  [LEVELS.CODE]: {
    distance: 5,
    fov: null, // orthographic
    type: 'orthographic',
    position: new T.Vector3(0, 5, 0),
    lookAt: new T.Vector3(0, 0, 0),
  },
};

/* ── Public API ── */

/**
 * Smoothly transition the camera between two configurations.
 * Uses SLERP for rotation and arc path for position.
 * @param {object} from - {position: Vector3, quaternion: Quaternion, target: Vector3}
 * @param {object} to - {position: Vector3, quaternion: Quaternion, target: Vector3}
 * @param {number} [duration=350] - Transition duration in ms
 * @returns {Promise<void>}
 */
export function transitionCamera(from, to, duration = DRILL_DURATION) {
  return new Promise(resolve => {
    const startPos = from.position.clone();
    const endPos = to.position.clone();
    const startTarget = from.target.clone();
    const endTarget = to.target.clone();
    const startQuat = from.quaternion ? from.quaternion.clone() : cam.quaternion.clone();
    const endQuat = to.quaternion ? to.quaternion.clone() : _computeQuaternion(endPos, endTarget);

    // Arc height: 20-30% of lateral displacement
    const lateralDist = Math.sqrt(
      (endPos.x - startPos.x) ** 2 + (endPos.z - startPos.z) ** 2
    );
    const arcHeight = lateralDist * 0.25;

    const startTime = performance.now();

    function step() {
      const elapsed = performance.now() - startTime;
      const rawT = Math.min(elapsed / duration, 1);
      const t = _emphasizedEase(rawT);

      // Arc path for position
      const arcLift = Math.sin(Math.PI * rawT) * arcHeight;
      cam.position.lerpVectors(startPos, endPos, t);
      cam.position.y += arcLift;

      // SLERP for rotation
      cam.quaternion.slerpQuaternions(startQuat, endQuat, t);

      // Orbit target
      ctrl.target.lerpVectors(startTarget, endTarget, t);
      cam.updateProjectionMatrix();

      if (rawT < 1) {
        requestAnimationFrame(step);
      } else {
        // Snap to final values
        cam.position.copy(endPos);
        cam.quaternion.copy(endQuat);
        ctrl.target.copy(endTarget);
        cam.updateProjectionMatrix();
        resolve();
      }
    }

    requestAnimationFrame(step);
  });
}

/**
 * Fly the camera to a specific node at a target drill level.
 * Computes start/end configs from the current camera state and level presets.
 * @param {string|null} nodeId - Target node ID (null for system origin)
 * @param {number} level - Target drill level (0-4)
 * @param {object|null} nodeData - Node data with position info
 * @returns {Promise<void>}
 */
export function flyToNode(nodeId, level, nodeData) {
  const preset = CAMERA_PRESETS[level] || CAMERA_PRESETS[LEVELS.SYSTEM];

  // Compute target lookAt from node position or default
  const targetLookAt = _getNodeWorldPosition(nodeId, nodeData);

  // Compute target camera position relative to the lookAt point
  const targetPos = new T.Vector3(
    targetLookAt.x + preset.position.x,
    targetLookAt.y + preset.position.y,
    targetLookAt.z + preset.position.z
  );

  // For L0 (system view), use absolute preset positions
  if (level === LEVELS.SYSTEM) {
    targetPos.copy(preset.position);
    targetLookAt.copy(preset.lookAt);
  }

  // Build from/to configs
  const from = {
    position: cam.position.clone(),
    quaternion: cam.quaternion.clone(),
    target: ctrl.target.clone(),
  };

  const to = {
    position: targetPos,
    quaternion: _computeQuaternion(targetPos, targetLookAt),
    target: targetLookAt,
  };

  return transitionCamera(from, to, DRILL_DURATION);
}

/* ── Helpers ── */

/**
 * Get the world position of a node for camera targeting.
 */
function _getNodeWorldPosition(nodeId, nodeData) {
  if (!nodeId) return new T.Vector3(0, 0, 0);

  // Try nodeData first
  if (nodeData) {
    if (nodeData.x != null && nodeData.z != null) {
      return new T.Vector3(nodeData.x, nodeData.y || 1, nodeData.z);
    }
    if (nodeData.position) {
      return new T.Vector3(nodeData.position.x || 0, nodeData.position.y || 1, nodeData.position.z || 0);
    }
  }

  // Try state nodes
  const stateNodes = state?.sysNodes || [];
  const node = stateNodes.find(n => n.id === nodeId);
  if (node && node.x != null && node.z != null) {
    return new T.Vector3(node.x, node.y || 1, node.z);
  }

  // Fallback to orbit target
  return ctrl.target.clone();
}

/**
 * Compute the quaternion for a camera looking from `pos` at `target`.
 */
function _computeQuaternion(pos, target) {
  const dummy = new T.Object3D();
  dummy.position.copy(pos);
  dummy.lookAt(target);
  dummy.updateMatrixWorld();
  return dummy.quaternion.clone();
}

