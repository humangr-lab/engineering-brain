/**
 * WebXR Mode — VR/AR support for Three.js scene.
 * Provides utilities for entering immersive sessions
 * (Apple Vision Pro, Meta Quest, etc.)
 *
 * Uses Three.js WebXR API — no additional dependencies.
 */

import type * as THREE from "three";

export interface XRStatus {
  available: boolean;
  vrSupported: boolean;
  arSupported: boolean;
  sessionActive: boolean;
  sessionType: "immersive-vr" | "immersive-ar" | null;
}

/** Check WebXR availability */
export async function checkXRSupport(): Promise<XRStatus> {
  const status: XRStatus = {
    available: false,
    vrSupported: false,
    arSupported: false,
    sessionActive: false,
    sessionType: null,
  };

  if (!("xr" in navigator)) return status;

  const xr = (navigator as Navigator & { xr: XRSystem }).xr;
  status.available = true;

  try {
    status.vrSupported = await xr.isSessionSupported("immersive-vr");
  } catch {
    // VR not supported
  }

  try {
    status.arSupported = await xr.isSessionSupported("immersive-ar");
  } catch {
    // AR not supported
  }

  return status;
}

/** Configure a Three.js renderer for WebXR */
export function enableXR(renderer: THREE.WebGLRenderer): void {
  renderer.xr.enabled = true;
}

/** Enter immersive VR session */
export async function enterVR(
  renderer: THREE.WebGLRenderer,
): Promise<XRSession | null> {
  if (!("xr" in navigator)) return null;

  const xr = (navigator as Navigator & { xr: XRSystem }).xr;
  const supported = await xr.isSessionSupported("immersive-vr");
  if (!supported) return null;

  try {
    const session = await xr.requestSession("immersive-vr", {
      optionalFeatures: ["local-floor", "bounded-floor", "hand-tracking"],
    });
    renderer.xr.setSession(session);
    return session;
  } catch {
    return null;
  }
}

/** Enter immersive AR session */
export async function enterAR(
  renderer: THREE.WebGLRenderer,
): Promise<XRSession | null> {
  if (!("xr" in navigator)) return null;

  const xr = (navigator as Navigator & { xr: XRSystem }).xr;
  const supported = await xr.isSessionSupported("immersive-ar");
  if (!supported) return null;

  try {
    const session = await xr.requestSession("immersive-ar", {
      optionalFeatures: ["local-floor", "hit-test", "hand-tracking"],
    });
    renderer.xr.setSession(session);
    return session;
  } catch {
    return null;
  }
}

/** Exit any active XR session */
export async function exitXR(
  renderer: THREE.WebGLRenderer,
): Promise<void> {
  const session = renderer.xr.getSession();
  if (session) {
    await session.end();
  }
}

/** Scale the graph scene for comfortable VR viewing */
export function configureXRScene(
  scene: THREE.Object3D,
  nodeCount: number,
): void {
  // Scale down large graphs to fit in ~3m sphere for VR
  const targetRadius = 2; // meters
  const estimatedSpan = Math.cbrt(nodeCount) * 5;
  const scale = targetRadius / Math.max(estimatedSpan, 1);

  scene.scale.setScalar(scale);
  scene.position.set(0, 1.5, -2); // eye level, slightly forward
}

/**
 * Create XR controller ray for node selection.
 * Returns a raycaster configured from the XR controller.
 */
export function createXRRay(
  controller: THREE.Object3D,
  THREE_lib: { Raycaster: new () => THREE.Raycaster; Vector3: new () => THREE.Vector3 },
): THREE.Raycaster {
  const raycaster = new THREE_lib.Raycaster();
  const tempMatrix = controller.matrixWorld;
  const origin = new THREE_lib.Vector3();
  const direction = new THREE_lib.Vector3();

  origin.setFromMatrixPosition(tempMatrix);
  direction.set(0, 0, -1).applyMatrix4(tempMatrix).sub(origin).normalize();

  raycaster.set(origin, direction);
  return raycaster;
}

/** VR controller button bindings */
export interface XRBindings {
  /** Trigger press — select node */
  onSelect: (controller: THREE.Object3D) => void;
  /** Squeeze — toggle earthquake on selected node */
  onSqueeze?: (controller: THREE.Object3D) => void;
  /** Thumbstick — navigate through layers */
  onThumbstick?: (axes: { x: number; y: number }) => void;
}

/** Attach event listeners to XR controllers */
export function bindXRControllers(
  renderer: THREE.WebGLRenderer,
  scene: THREE.Scene,
  bindings: XRBindings,
): () => void {
  const controller0 = renderer.xr.getController(0);
  const controller1 = renderer.xr.getController(1);

  scene.add(controller0);
  scene.add(controller1);

  // Three.js XRTargetRaySpace uses its own event system — use generic handlers
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const selectHandler = (event: any) => {
    bindings.onSelect(event.target as THREE.Object3D);
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const squeezeHandler = (event: any) => {
    bindings.onSqueeze?.(event.target as THREE.Object3D);
  };

  controller0.addEventListener("select", selectHandler);
  controller1.addEventListener("select", selectHandler);

  if (bindings.onSqueeze) {
    controller0.addEventListener("squeeze", squeezeHandler);
    controller1.addEventListener("squeeze", squeezeHandler);
  }

  // Cleanup
  return () => {
    controller0.removeEventListener("select", selectHandler);
    controller1.removeEventListener("select", selectHandler);
    controller0.removeEventListener("squeeze", squeezeHandler);
    controller1.removeEventListener("squeeze", squeezeHandler);
    scene.remove(controller0);
    scene.remove(controller1);
  };
}
