/* ═══════════════ THEME — Light/Dark toggle ═══════════════
   Integrates with design/theme-loader.js for OKLCH token system.
   Loads theme YAML, applies CSS custom properties + JS mirror. */

import { state, subscribe } from './state.js';
import { loadTheme } from './design/theme-loader.js';

let _onThemeChange = null;
let _themeLoading = false;

/**
 * Map theme mode to YAML filename.
 */
const THEME_MAP = {
  dark: 'midnight',
  light: 'daylight',
};

/**
 * Initialize theme system.
 * @param {Function} [onMaterialThemeSwitch] - callback for Three.js material updates
 */
export function initTheme(onMaterialThemeSwitch) {
  _onThemeChange = onMaterialThemeSwitch;

  // Load saved preference
  const saved = localStorage.getItem('cockpit-theme') || 'light';
  _applyTheme(saved);

  // Wire up toggle button
  const btn = document.getElementById('bgBtn');
  if (btn) {
    btn.addEventListener('click', toggleTheme);
  }

  // React to state changes
  subscribe('theme', (newTheme) => _applyTheme(newTheme));
}

export function toggleTheme() {
  state.theme = state.theme === 'dark' ? 'light' : 'dark';
}

async function _applyTheme(theme) {
  if (_themeLoading) return;
  _themeLoading = true;

  state.theme = theme;
  localStorage.setItem('cockpit-theme', theme);

  // Load theme YAML -> CSS custom properties + JS mirror
  const themeName = THEME_MAP[theme] || 'daylight';
  await loadTheme(themeName);

  // The loadTheme function already sets body.dark class and fires theme-changed event.
  // The theme-changed event is picked up by engine.js to update 3D scene.

  // Update toggle button text
  const btn = document.getElementById('bgBtn');
  if (btn) {
    btn.textContent = theme === 'dark' ? '\u2600 Light BG' : '\u263E Dark BG';
  }

  // Notify Three.js materials (legacy callback, in addition to the event)
  if (_onThemeChange) _onThemeChange(theme);

  _themeLoading = false;
}

export function isDark() {
  return state.theme === 'dark';
}
