/* ═══════════════ THREE.JS ENGINE ═══════════════
   Renderer, camera, controls, EffectComposer, resize handler.
   Theme-aware: reads colors from design system tokens. */

import * as T from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { OutlinePass } from 'three/addons/postprocessing/OutlinePass.js';
// SMAAPass removed — using native MSAA instead (O1)
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { CONFIG } from '../config.js';
import { oklchToInt } from '../design/oklch.js';
import { getThemeInt, getThemeNum } from '../design/theme-loader.js';

export let scene, cam, ren, lr, ctrl, composer, outlinePass, envMap;

let W, H, animFrameId;
const _tickCallbacks = [];
let _bgLight, _bgDark;
let _aLight, _dLight, _fLight, _hLight, _rimLight;
let _bloomPass = null;

/* ── Radial gradient background ── */

function _makeGradientBg(stops) {
  const sz = 256;
  const c = document.createElement('canvas');
  c.width = sz; c.height = sz;
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(sz / 2, sz / 2, 0, sz / 2, sz / 2, sz * 0.72);
  stops.forEach(([pos, col]) => g.addColorStop(pos, col));
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, sz, sz);
  const tex = new T.CanvasTexture(c);
  tex.colorSpace = T.SRGBColorSpace;
  return tex;
}

/**
 * Build gradient backgrounds using design system surface tokens.
 */
function _buildGradients() {
  const root = document.documentElement;
  const cs = getComputedStyle(root);

  // Light mode gradient
  _bgLight = _makeGradientBg([
    [0.0, cs.getPropertyValue('--surface-0').trim() || 'oklch(98% 0.01 260)'],
    [0.3, cs.getPropertyValue('--surface-1').trim() || 'oklch(95% 0.01 260)'],
    [0.6, cs.getPropertyValue('--surface-2').trim() || 'oklch(91% 0.012 260)'],
    [1.0, cs.getPropertyValue('--surface-3').trim() || 'oklch(87% 0.015 260)'],
  ]);

  // Dark mode gradient
  _bgDark = _makeGradientBg([
    [0.0, 'oklch(18% 0.02 260)'],
    [0.3, 'oklch(13% 0.02 260)'],
    [0.6, 'oklch(8% 0.015 260)'],
    [1.0, 'oklch(4% 0.01 260)'],
  ]);
}

export function initEngine(container) {
  W = innerWidth; H = innerHeight;

  // Scene
  scene = new T.Scene();

  // Build gradient backgrounds
  _buildGradients();
  scene.background = _bgLight;
  scene.fog = new T.FogExp2(oklchToInt(93, 0.01, 260), 0.008);

  // Lights — good intensity for icon reflections
  const dirColorInt = getThemeInt('mat-directional-color') ?? oklchToInt(95, 0.01, 260);
  _aLight = new T.AmbientLight(dirColorInt, getThemeNum('mat-ambient-intensity') ?? 0.55);
  scene.add(_aLight);

  _dLight = new T.DirectionalLight(oklchToInt(98, 0.01, 50), 0.9);
  _dLight.position.set(8, 15, 10);
  scene.add(_dLight);

  _fLight = new T.DirectionalLight(oklchToInt(85, 0.01, 250), 0.35);
  _fLight.position.set(-5, 8, -8);
  scene.add(_fLight);

  // Hemisphere: ground color = black (no light from below the platform)
  _hLight = new T.HemisphereLight(dirColorInt, oklchToInt(0, 0, 0), 0.4);
  scene.add(_hLight);

  _rimLight = new T.DirectionalLight(oklchToInt(70, 0.05, 250), 0.3);
  _rimLight.position.set(-8, 5, 15);
  scene.add(_rimLight);

  // Camera (orthographic)
  const fd = CONFIG.ORTHO_FRUSTUM;
  const asp = W / H;
  cam = new T.OrthographicCamera(-fd * asp, fd * asp, fd, -fd, 0.1, 200);
  cam.position.set(12, 18, 12);
  cam.lookAt(0, 0, 0);

  // Renderer
  ren = new T.WebGLRenderer({ antialias: true });
  ren.setSize(W, H);
  ren.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  ren.shadowMap.enabled = false;
  ren.toneMapping = T.ACESFilmicToneMapping;
  ren.toneMappingExposure = 1.1;
  container.appendChild(ren.domElement);

  // Environment map — for icon reflections (platform uses LambertMaterial so unaffected)
  const pmremGen = new T.PMREMGenerator(ren);
  envMap = pmremGen.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environment = envMap;
  pmremGen.dispose();

  // CSS2D renderer (labels)
  lr = new CSS2DRenderer();
  lr.setSize(W, H);
  lr.domElement.style.position = 'absolute';
  lr.domElement.style.top = '0';
  lr.domElement.style.pointerEvents = 'none';
  container.appendChild(lr.domElement);

  // Controls
  ctrl = new OrbitControls(cam, ren.domElement);
  ctrl.enableDamping = true;
  ctrl.dampingFactor = 0.06;
  ctrl.maxPolarAngle = Math.PI / 2.2;
  ctrl.minPolarAngle = 0.2;

  // EffectComposer
  composer = new EffectComposer(ren);
  composer.addPass(new RenderPass(scene, cam));
  _bloomPass = new UnrealBloomPass(
    new T.Vector2(Math.floor(W / 4), Math.floor(H / 4)),
    CONFIG.BLOOM_STRENGTH, CONFIG.BLOOM_RADIUS, CONFIG.BLOOM_THRESHOLD,
  );
  composer.addPass(_bloomPass);
  outlinePass = new OutlinePass(new T.Vector2(W, H), scene, cam);
  outlinePass.edgeStrength = 3;
  outlinePass.edgeGlow = 0.5;
  outlinePass.edgeThickness = 1.2;
  outlinePass.visibleEdgeColor.set(getThemeInt('accent-purple') ?? oklchToInt(65, 0.15, 315));
  outlinePass.enabled = false;
  composer.addPass(outlinePass);
  composer.addPass(new OutputPass());

  // Listen for theme changes to update 3D scene
  window.addEventListener('theme-changed', _onThemeChanged);

  // Resize
  window.addEventListener('resize', _onResize);

  return { scene, cam, ren, lr, ctrl, composer, outlinePass, envMap };
}

function _onResize() {
  W = innerWidth; H = innerHeight;
  const fd = CONFIG.ORTHO_FRUSTUM;
  const asp = W / H;
  cam.left = -fd * asp; cam.right = fd * asp;
  cam.top = fd; cam.bottom = -fd;
  cam.updateProjectionMatrix();
  ren.setSize(W, H);
  lr.setSize(W, H);
  composer.setSize(W, H);
}

/**
 * Handle theme-changed event from theme-loader.
 */
function _onThemeChanged(e) {
  const isDark = e.detail?.mode === 'dark';
  _buildGradients();
  setThemeColors(isDark);

  // Update outline pass color
  if (outlinePass) {
    outlinePass.visibleEdgeColor.set(getThemeInt('accent-purple') ?? oklchToInt(65, 0.15, 315));
  }

  // Update bloom from theme
  if (_bloomPass) {
    _bloomPass.threshold = getThemeNum('mat-bloom-threshold') ?? CONFIG.BLOOM_THRESHOLD;
    _bloomPass.strength = getThemeNum('mat-bloom-strength') ?? CONFIG.BLOOM_STRENGTH;
    _bloomPass.radius = getThemeNum('mat-bloom-radius') ?? CONFIG.BLOOM_RADIUS;
  }
}

/**
 * Register a callback to be called every animation frame.
 */
export function onTick(cb) {
  _tickCallbacks.push(cb);
}

/**
 * Start the render loop.
 */
export function startLoop() {
  function tick() {
    animFrameId = requestAnimationFrame(tick);
    ctrl.update();
    _tickCallbacks.forEach(cb => cb());
    composer.render();
    lr.render(scene, cam);
  }
  tick();
}

/**
 * Stop the render loop.
 */
export function stopLoop() {
  if (animFrameId) cancelAnimationFrame(animFrameId);
}

/**
 * Set scene background and fog for theme.
 */
export function setThemeColors(isDark) {
  if (!scene) return;

  // Swap gradient background
  scene.background = isDark ? _bgDark : _bgLight;

  // Fog
  const fogColor = isDark
    ? oklchToInt(8, 0.015, 260)
    : oklchToInt(93, 0.01, 260);
  scene.fog.color.set(fogColor);

  // Read light intensities from theme mirror
  const ambientI = getThemeNum('mat-ambient-intensity');
  const directionalI = getThemeNum('mat-directional-intensity');

  // Adjust lights — dark mode: dimmer, NO light from below
  if (isDark) {
    _aLight.intensity = ambientI ?? 0.15;
    _dLight.intensity = directionalI ?? 0.35;
    _fLight.intensity = 0.1;
    _hLight.intensity = 0;
    _rimLight.intensity = 0.08;
  } else {
    _aLight.intensity = ambientI ?? 0.55;
    _dLight.intensity = directionalI ?? 0.9;
    _fLight.intensity = 0.35;
    _hLight.intensity = 0.4;
    _rimLight.intensity = 0.3;
  }
}

/**
 * Get performance metrics (stub for backward compat).
 */
export function getPerformanceMetrics() {
  return { fps: 0, drawCalls: 0, triangles: 0 };
}

/**
 * Adjust bloom intensity based on visible node count.
 * @param {number} count - Number of visible nodes
 */
export function adjustBloomForNodeCount(count) {
  if (!_bloomPass) return;
  // Reduce bloom for dense scenes to avoid visual noise
  const base = getThemeNum('mat-bloom-strength') ?? CONFIG.BLOOM_STRENGTH;
  _bloomPass.strength = count > 50 ? base * 0.7 : base;
}
