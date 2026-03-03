/* ═══════════════ MATERIALS — Theme-aware, cached ═══════════════
   Colors derived from design system tokens via theme-loader.
   Falls back to OKLCH-computed defaults when theme not loaded. */

import * as T from 'three';
import { oklchToInt } from '../design/oklch.js';
import { themeMirror, getThemeInt, getThemeNum } from '../design/theme-loader.js';

// ── Default OKLCH-derived colors (midnight theme fallback) ──

const _NEON_DEFAULTS = {
  source:   oklchToInt(65, 0.15, 135),   // green
  layer:    oklchToInt(65, 0.15, 225),   // blue
  module:   oklchToInt(65, 0.15, 315),   // purple
  consumer: oklchToInt(65, 0.15, 180),   // teal
};

// ── Palette generation from OKLCH categorical hues ──

/**
 * Generate a shape palette from a base OKLCH hue.
 * Derives dark/mid/light/accent tones by varying lightness.
 * @param {number} hue - OKLCH hue in degrees
 * @param {number} [chroma=0.08] - OKLCH chroma for the tonal variants
 * @returns {{ d: number, m: number, l: number, a: number }}
 */
function _paletteFromHue(hue, chroma = 0.08) {
  return {
    d: oklchToInt(33, chroma, hue),
    m: oklchToInt(44, chroma, hue),
    l: oklchToInt(60, chroma, hue),
    a: oklchToInt(65, 0.15, hue),
  };
}

// Shape-to-hue mapping (based on original palette analysis)
const _SHAPE_HUES = {
  brain:     270, gauge:     165, tree:      150, hub:       60,
  sphere:    290, monument:  0,   pillars:   0,   gear:      225,
  gate:      310, database:  240, hourglass: 65,  prism:     250,
  stairs:    0,   nexus:     265, graph:     235, dial:      0,
  vault:     40,  warehouse: 95,  factory:   0,   satellite: 240,
  terminal:  0,   screens:   255, rack:      0,   conveyor:  55,
  monitor:   250, dyson_book:295,
};

// Per-shape real-world palettes (procedurally generated from hues)
const PALETTES = {};
for (const [shape, hue] of Object.entries(_SHAPE_HUES)) {
  PALETTES[shape] = _paletteFromHue(hue);
}

let _currentNeon = _NEON_DEFAULTS.module;
let _currentPal = PALETTES.sphere || _paletteFromHue(270);
const _matCache = {};

/**
 * Get the current NEON color map, reading from theme mirror if available.
 */
function _getNeonMap() {
  return {
    source:   getThemeInt('mat-neon-source')   ?? _NEON_DEFAULTS.source,
    layer:    getThemeInt('mat-neon-layer')     ?? _NEON_DEFAULTS.layer,
    module:   getThemeInt('mat-neon-module')    ?? _NEON_DEFAULTS.module,
    consumer: getThemeInt('mat-neon-consumer')  ?? _NEON_DEFAULTS.consumer,
  };
}

/**
 * Get material property from theme or fallback.
 */
function _getMatProp(token, fallback) {
  return getThemeNum(token) ?? fallback;
}

/**
 * Set the active palette for subsequent material calls.
 */
export function setPalette(shape, group) {
  _currentPal = PALETTES[shape] || PALETTES.sphere || _paletteFromHue(270);
  const neonMap = _getNeonMap();
  _currentNeon = neonMap[group] || neonMap.module;
}

/**
 * Material factory — theme-aware materials for 3D icons.
 * Reads metalness/roughness from theme tokens when available.
 */
export const matFactory = {
  get palette() { return { ...(_currentPal) }; },
  dark: () => {
    const k = _currentPal.d + '_d';
    return _matCache[k] || (_matCache[k] = new T.MeshStandardMaterial({
      color: _currentPal.d,
      metalness: _getMatProp('mat-metalness-high', 0.30),
      roughness: _getMatProp('mat-roughness-mid', 0.55),
    }));
  },
  mid: () => {
    const k = _currentPal.m + '_m';
    return _matCache[k] || (_matCache[k] = new T.MeshStandardMaterial({
      color: _currentPal.m,
      metalness: _getMatProp('mat-metalness-mid', 0.25),
      roughness: _getMatProp('mat-roughness-mid', 0.50),
    }));
  },
  light: () => {
    const k = _currentPal.l + '_l';
    return _matCache[k] || (_matCache[k] = new T.MeshStandardMaterial({
      color: _currentPal.l,
      metalness: _getMatProp('mat-metalness-low', 0.18),
      roughness: _getMatProp('mat-roughness-low', 0.45),
    }));
  },
  accent: () => {
    const k = _currentPal.a + '_a';
    return _matCache[k] || (_matCache[k] = new T.MeshStandardMaterial({
      color: _currentPal.a,
      metalness: _getMatProp('mat-metalness-mid', 0.25),
      roughness: _getMatProp('mat-roughness-mid', 0.48),
    }));
  },
  screen: () => {
    const k = 'screen';
    return _matCache[k] || (_matCache[k] = new T.MeshStandardMaterial({
      color: getThemeInt('surface-1') ?? oklchToInt(18, 0.02, 260),
      metalness: 0.1,
      roughness: 0.8,
    }));
  },
};

/**
 * Get NEON color int for a group.
 */
export function getNeon(group) {
  const neonMap = _getNeonMap();
  return neonMap[group] || neonMap.module;
}

/**
 * Flush material cache on theme change.
 * Called by engine.js when theme-changed event fires.
 */
export function flushMaterialCache() {
  for (const k in _matCache) delete _matCache[k];
}

/**
 * Update materials for theme switch (dark/light).
 * Flushes cache so next calls use new theme token values.
 */
export function updateMaterialsForTheme(isDark) {
  flushMaterialCache();
}

// ── Connection colors (derived from theme tokens) ──

function _buildCC(prefix) {
  return {
    green:  getThemeInt(`mat-connection-green`)  ?? oklchToInt(75, 0.15, 150),
    blue:   getThemeInt(`mat-connection-blue`)   ?? oklchToInt(66, 0.14, 240),
    purple: getThemeInt(`mat-connection-purple`) ?? oklchToInt(63, 0.16, 300),
    cyan:   getThemeInt(`mat-connection-cyan`)   ?? oklchToInt(80, 0.10, 185),
    white:  getThemeInt(`mat-connection-muted`)  ?? oklchToInt(60, 0.03, 250),
  };
}

// Backward-compatible exports
export const CC_DARK = {
  get green()  { return getThemeInt('mat-connection-green')  ?? oklchToInt(75, 0.15, 150); },
  get blue()   { return getThemeInt('mat-connection-blue')   ?? oklchToInt(66, 0.14, 240); },
  get purple() { return getThemeInt('mat-connection-purple') ?? oklchToInt(63, 0.16, 300); },
  get cyan()   { return getThemeInt('mat-connection-cyan')   ?? oklchToInt(80, 0.10, 185); },
  get white()  { return getThemeInt('mat-connection-muted')  ?? oklchToInt(60, 0.03, 250); },
};

export const CC_LIGHT = {
  get green()  { return getThemeInt('mat-connection-green')  ?? oklchToInt(42, 0.15, 150); },
  get blue()   { return getThemeInt('mat-connection-blue')   ?? oklchToInt(40, 0.14, 240); },
  get purple() { return getThemeInt('mat-connection-purple') ?? oklchToInt(40, 0.16, 300); },
  get cyan()   { return getThemeInt('mat-connection-cyan')   ?? oklchToInt(42, 0.12, 185); },
  get white()  { return getThemeInt('mat-connection-muted')  ?? oklchToInt(50, 0.03, 250); },
};

let _CC = CC_LIGHT;
export function getCC() { return _CC; }
export function setCC(isDark) { _CC = isDark ? CC_DARK : CC_LIGHT; }

// ── Dynamic palette generation ──

/**
 * Register custom group NEON color from inference palette.
 * @param {string} group - Group name
 * @param {number} colorInt - Integer color value
 */
const _customNeon = {};
export function setGroupNeon(group, colorInt) {
  _customNeon[group] = colorInt;
}

/**
 * Generate a per-shape palette from an arbitrary base color.
 * Produces dark/medium/light/accent variants in the maquette style.
 * @param {number} baseColorInt - Base color as integer (e.g., 0x34d399)
 * @returns {{ d: number, m: number, l: number, a: number }}
 */
export function paletteFromColor(baseColorInt) {
  const base = new T.Color(baseColorInt);
  const hsl = {};
  base.getHSL(hsl);

  const d = new T.Color().setHSL(hsl.h, hsl.s * 0.3, Math.max(hsl.l * 0.4, 0.15));
  const m = new T.Color().setHSL(hsl.h, hsl.s * 0.4, Math.max(hsl.l * 0.55, 0.25));
  const l = new T.Color().setHSL(hsl.h, hsl.s * 0.5, Math.min(hsl.l * 0.75, 0.65));
  const a = base.clone();

  return {
    d: _colorToInt(d),
    m: _colorToInt(m),
    l: _colorToInt(l),
    a: _colorToInt(a),
  };
}

/**
 * Register a dynamically generated palette for a shape.
 * @param {string} shape - Shape name
 * @param {{ d: number, m: number, l: number, a: number }} palette
 */
export function registerPalette(shape, palette) {
  PALETTES[shape] = palette;
}

function _colorToInt(color) {
  return (Math.round(color.r * 255) << 16) |
         (Math.round(color.g * 255) << 8) |
         Math.round(color.b * 255);
}
