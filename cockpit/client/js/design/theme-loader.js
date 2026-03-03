/* ═══════════════ THEME LOADER ═══════════════
   Parse theme YAML -> CSS custom properties + JS mirror for Three.js.
   Fires 'theme-changed' CustomEvent on every switch.

   Exports: loadTheme, getThemeValue, getThemeInt, themeMirror */

import { oklchToHex, oklchToInt, parseOklch } from './oklch.js';

/**
 * JS mirror object — flat key:value store for Three.js consumption.
 * Keys are CSS property names without '--' prefix.
 * Values include .raw (original string), .hex, .int (for colors), .num (for numbers).
 */
export const themeMirror = {};

/** Currently loaded theme name */
let _currentTheme = '';

/** Cache parsed YAML to avoid re-fetch */
const _themeCache = {};

/* ── Minimal YAML Parser ─────────────────────────────────────────── */

/**
 * Parse theme YAML text into a flat token map.
 * Handles nested objects, arrays, scalars. Not a full YAML parser.
 * @param {string} text - Raw YAML content
 * @returns {object} Nested JS object
 */
function _parseYaml(text) {
  const lines = text.split('\n');
  return _yamlParseObj(lines, 0, 0).value;
}

function _yamlParseObj(lines, startIdx, baseIndent) {
  const result = {};
  let i = startIdx;
  while (i < lines.length) {
    const raw = lines[i].replace(/\r$/, '');
    const trimmed = raw.trim();
    if (!trimmed || trimmed.startsWith('#')) { i++; continue; }
    const indent = raw.length - raw.trimStart().length;
    if (indent < baseIndent && i > startIdx) break;
    if (indent > baseIndent && i > startIdx) { i++; continue; }
    if (trimmed.startsWith('- ')) break;
    const ci = trimmed.indexOf(':');
    if (ci === -1) { i++; continue; }
    const key = trimmed.substring(0, ci).trim();
    const valStr = trimmed.substring(ci + 1).trim();
    if (valStr === '' || valStr === '|' || valStr === '>') {
      const next = _nextNonEmpty(lines, i + 1);
      if (next < lines.length) {
        const nl = lines[next].replace(/\r$/, '');
        const ni = nl.length - nl.trimStart().length;
        const nt = nl.trim();
        if (ni > indent && nt.startsWith('- ')) {
          const arr = _yamlParseArr(lines, next, ni);
          result[key] = arr.value; i = arr.nextIdx; continue;
        } else if (ni > indent) {
          const nested = _yamlParseObj(lines, next, ni);
          result[key] = nested.value; i = nested.nextIdx; continue;
        }
      }
      result[key] = null; i++;
    } else {
      result[key] = _scalar(valStr); i++;
    }
  }
  return { value: result, nextIdx: i };
}

function _yamlParseArr(lines, startIdx, baseIndent) {
  const result = [];
  let i = startIdx;
  while (i < lines.length) {
    const raw = lines[i].replace(/\r$/, '');
    const trimmed = raw.trim();
    if (!trimmed || trimmed.startsWith('#')) { i++; continue; }
    const indent = raw.length - raw.trimStart().length;
    if (indent < baseIndent) break;
    if (!trimmed.startsWith('- ')) break;
    const content = trimmed.substring(2).trim();
    result.push(_scalar(content));
    i++;
  }
  return { value: result, nextIdx: i };
}

function _nextNonEmpty(lines, from) {
  for (let i = from; i < lines.length; i++) {
    const t = lines[i].trim();
    if (t && !t.startsWith('#')) return i;
  }
  return lines.length;
}

function _scalar(s) {
  if (s === '' || s === 'null' || s === '~') return null;
  if (s === 'true') return true;
  if (s === 'false') return false;
  if ((s.startsWith("'") && s.endsWith("'")) || (s.startsWith('"') && s.endsWith('"')))
    return s.slice(1, -1);
  // Strip inline comments: '  0.25  # max 0.3' => '0.25'
  const commentIdx = s.indexOf('#');
  const clean = commentIdx > 0 ? s.substring(0, commentIdx).trim() : s;
  const num = Number(clean);
  if (!isNaN(num) && clean !== '') return num;
  // Could still have inline comment on string values
  return commentIdx > 0 ? clean : s;
}

/* ── Flatten nested YAML into CSS custom properties ───────────────── */

/**
 * Flatten a parsed theme object into { '--token-name': value } map.
 * Handles colors.surface.surface-0 -> --surface-0, materials.metalness-high -> --mat-metalness-high, etc.
 */
function _flatten(parsed) {
  const tokens = {};

  // Mode marker
  tokens['--mode'] = parsed.mode || 'dark';

  // Colors
  const colors = parsed.colors || {};
  _flattenColorSection(colors.surface, tokens);
  if (colors.text) {
    tokens['--text-primary'] = colors.text.primary;
    tokens['--text-secondary'] = colors.text.secondary;
    tokens['--text-tertiary'] = colors.text.tertiary;
  }
  if (colors.accent) {
    for (const [name, val] of Object.entries(colors.accent)) {
      tokens[`--accent-${name}`] = val;
    }
  }
  if (colors.border) {
    tokens['--border-default'] = colors.border.default;
    tokens['--border-emphasis'] = colors.border.emphasis;
  }
  if (Array.isArray(colors.categorical)) {
    colors.categorical.forEach((val, i) => { tokens[`--cat-${i}`] = val; });
  }
  if (colors.status) {
    for (const [k, v] of Object.entries(colors.status)) {
      tokens[`--status-${k}`] = v;
    }
  }
  if (colors.severity) {
    for (const [k, v] of Object.entries(colors.severity)) {
      tokens[`--severity-${k}`] = v;
    }
  }

  // Spacing
  if (parsed.spacing) {
    for (const [k, v] of Object.entries(parsed.spacing)) {
      tokens[`--${k}`] = v;
    }
  }

  // Typography
  const typo = parsed.typography || {};
  for (const [k, v] of Object.entries(typo)) {
    tokens[`--${k}`] = v;
  }

  // Radii
  if (parsed.radii) {
    for (const [k, v] of Object.entries(parsed.radii)) {
      tokens[`--${k}`] = v;
    }
  }

  // Shadows
  if (parsed.shadows) {
    for (const [k, v] of Object.entries(parsed.shadows)) {
      tokens[`--${k}`] = v;
    }
  }

  // Motion
  if (parsed.motion) {
    for (const [k, v] of Object.entries(parsed.motion)) {
      tokens[`--${k}`] = v;
    }
  }

  // Materials (prefixed with --mat-)
  if (parsed.materials) {
    for (const [k, v] of Object.entries(parsed.materials)) {
      tokens[`--mat-${k}`] = v;
    }
  }

  return tokens;
}

function _flattenColorSection(section, tokens) {
  if (!section) return;
  for (const [k, v] of Object.entries(section)) {
    tokens[`--${k}`] = v;
  }
}

/* ── Mirror builder (for Three.js) ────────────────────────────────── */

/**
 * Build the JS mirror from token map.
 * For oklch() values, pre-computes hex and int.
 * For numeric values, stores as .num.
 */
function _buildMirror(tokens) {
  // Clear mirror
  for (const k in themeMirror) delete themeMirror[k];

  for (const [prop, val] of Object.entries(tokens)) {
    const key = prop.replace(/^--/, '');
    const entry = { raw: val };

    if (typeof val === 'string') {
      const parsed = parseOklch(val);
      if (parsed) {
        entry.hex = oklchToHex(parsed.l, parsed.c, parsed.h);
        entry.int = oklchToInt(parsed.l, parsed.c, parsed.h);
      }
    } else if (typeof val === 'number') {
      entry.num = val;
    }

    themeMirror[key] = entry;
  }
}

/* ── Public API ────────────────────────────────────────────────────── */

/**
 * Load and apply a theme by name.
 * Fetches themes/{name}.yaml, parses it, sets CSS custom properties,
 * builds the JS mirror, and fires 'theme-changed' event.
 * @param {string} name - Theme name, e.g. 'midnight' or 'daylight'
 */
export async function loadTheme(name) {
  let parsed = _themeCache[name];

  if (!parsed) {
    try {
      const resp = await fetch(`/themes/${name}.yaml`);
      if (!resp.ok) throw new Error(`Theme fetch failed: ${resp.status}`);
      const text = await resp.text();
      parsed = _parseYaml(text);
      _themeCache[name] = parsed;
    } catch (err) {
      console.warn(`[theme-loader] Failed to load theme "${name}":`, err);
      return;
    }
  }

  const tokens = _flatten(parsed);
  const root = document.documentElement;

  // Apply all CSS custom properties
  for (const [prop, val] of Object.entries(tokens)) {
    if (val != null) root.style.setProperty(prop, String(val));
  }

  // Toggle dark class
  if (parsed.mode === 'dark') {
    document.body.classList.add('dark');
  } else {
    document.body.classList.remove('dark');
  }

  // Build JS mirror for Three.js
  _buildMirror(tokens);

  _currentTheme = name;

  // Fire event for Three.js and other listeners
  window.dispatchEvent(new CustomEvent('theme-changed', {
    detail: { name, mode: parsed.mode, mirror: themeMirror },
  }));
}

/**
 * Get the raw CSS custom property value for a token.
 * @param {string} token - Token name without '--', e.g. 'surface-0' or 'mat-metalness-high'
 * @returns {string | undefined}
 */
export function getThemeValue(token) {
  const entry = themeMirror[token];
  return entry ? String(entry.raw) : undefined;
}

/**
 * Get the integer color value for a token (for Three.js).
 * @param {string} token - Token name without '--', e.g. 'accent-blue' or 'cat-5'
 * @returns {number | undefined}
 */
export function getThemeInt(token) {
  const entry = themeMirror[token];
  return entry ? entry.int : undefined;
}

/**
 * Get the numeric value for a token (for material properties).
 * @param {string} token - Token name without '--', e.g. 'mat-metalness-mid'
 * @returns {number | undefined}
 */
export function getThemeNum(token) {
  const entry = themeMirror[token];
  if (!entry) return undefined;
  if (entry.num !== undefined) return entry.num;
  const n = parseFloat(entry.raw);
  return isNaN(n) ? undefined : n;
}

/**
 * Get the hex color string for a token.
 * @param {string} token - Token name without '--', e.g. 'accent-blue'
 * @returns {string | undefined}
 */
export function getThemeHex(token) {
  const entry = themeMirror[token];
  return entry ? entry.hex : undefined;
}

/**
 * Returns the current theme name.
 */
export function currentThemeName() {
  return _currentTheme;
}
