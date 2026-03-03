/* ═══════════════ OKLCH UTILITIES ═══════════════
   Convert between OKLCH and hex/int for Three.js materials.
   Uses CSS Color Level 4 oklch() for CSS, manual conversion for JS. */

/**
 * Clamp value to [min, max].
 */
function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

/**
 * Convert linear sRGB component to gamma-corrected sRGB.
 */
function linearToSrgb(c) {
  return c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
}

/**
 * Convert gamma-corrected sRGB component to linear.
 */
function srgbToLinear(c) {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/**
 * Convert OKLCH to linear sRGB via OKLab.
 * @param {number} L  - Lightness 0..1 (from percentage / 100)
 * @param {number} C  - Chroma >= 0
 * @param {number} H  - Hue in degrees
 * @returns {[number, number, number]} linear RGB in [0..1]
 */
function oklchToLinearRgb(L, C, H) {
  const hRad = (H * Math.PI) / 180;
  const a = C * Math.cos(hRad);
  const b = C * Math.sin(hRad);

  // OKLab -> LMS (approximate)
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b;

  const l = l_ * l_ * l_;
  const m = m_ * m_ * m_;
  const s = s_ * s_ * s_;

  // LMS -> linear sRGB
  const R = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const G = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const B = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s;

  return [R, G, B];
}

/**
 * Convert linear sRGB to OKLab then to OKLCH.
 * @param {number} R - linear R [0..1]
 * @param {number} G - linear G [0..1]
 * @param {number} B - linear B [0..1]
 * @returns {{ l: number, c: number, h: number }} L in [0..1], C >= 0, H in degrees
 */
function linearRgbToOklch(R, G, B) {
  // linear sRGB -> LMS
  const l = 0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B;
  const m = 0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B;
  const s = 0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B;

  const l_ = Math.cbrt(l);
  const m_ = Math.cbrt(m);
  const s_ = Math.cbrt(s);

  const L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_;
  const a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_;
  const b = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_;

  const C = Math.sqrt(a * a + b * b);
  let H = (Math.atan2(b, a) * 180) / Math.PI;
  if (H < 0) H += 360;

  return { l: L, c: C, h: H };
}

/**
 * Convert OKLCH values to a hex color string.
 * @param {number} l  - Lightness as percentage (0-100)
 * @param {number} c  - Chroma (e.g. 0.15)
 * @param {number} h  - Hue in degrees (0-360)
 * @returns {string} Hex color string, e.g. '#6b8fff'
 */
export function oklchToHex(l, c, h) {
  const [R, G, B] = oklchToLinearRgb(l / 100, c, h);
  const r = clamp(Math.round(linearToSrgb(clamp(R, 0, 1)) * 255), 0, 255);
  const g = clamp(Math.round(linearToSrgb(clamp(G, 0, 1)) * 255), 0, 255);
  const b = clamp(Math.round(linearToSrgb(clamp(B, 0, 1)) * 255), 0, 255);
  return '#' + ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1);
}

/**
 * Convert OKLCH values to an integer for Three.js.
 * @param {number} l  - Lightness as percentage (0-100)
 * @param {number} c  - Chroma (e.g. 0.15)
 * @param {number} h  - Hue in degrees (0-360)
 * @returns {number} Integer color value, e.g. 0x6b8fff
 */
export function oklchToInt(l, c, h) {
  const [R, G, B] = oklchToLinearRgb(l / 100, c, h);
  const r = clamp(Math.round(linearToSrgb(clamp(R, 0, 1)) * 255), 0, 255);
  const g = clamp(Math.round(linearToSrgb(clamp(G, 0, 1)) * 255), 0, 255);
  const b = clamp(Math.round(linearToSrgb(clamp(B, 0, 1)) * 255), 0, 255);
  return (r << 16) | (g << 8) | b;
}

/**
 * Convert hex color string to OKLCH.
 * @param {string} hex - Hex color string, e.g. '#6b8fff' or '6b8fff'
 * @returns {{ l: number, c: number, h: number }} l as percentage (0-100), c, h in degrees
 */
export function hexToOklch(hex) {
  hex = hex.replace(/^#/, '');
  if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
  const num = parseInt(hex, 16);
  const r = srgbToLinear(((num >> 16) & 0xff) / 255);
  const g = srgbToLinear(((num >> 8) & 0xff) / 255);
  const b = srgbToLinear((num & 0xff) / 255);
  const { l, c, h } = linearRgbToOklch(r, g, b);
  return { l: l * 100, c, h };
}

/**
 * Generate a categorical palette of n equidistant hues.
 * @param {number} n  - Number of colors
 * @param {object} [opts]
 * @param {number} [opts.lightness=65] - OKLCH lightness percentage
 * @param {number} [opts.chroma=0.15]  - OKLCH chroma
 * @param {number} [opts.startHue=0]   - Starting hue in degrees
 * @returns {Array<{ h: number, oklch: string, hex: string, int: number }>}
 */
export function generateCategoricalPalette(n, opts = {}) {
  const { lightness = 65, chroma = 0.15, startHue = 0 } = opts;
  const step = 360 / n;
  const palette = [];
  for (let i = 0; i < n; i++) {
    const h = (startHue + i * step) % 360;
    palette.push({
      h,
      oklch: `oklch(${lightness}% ${chroma} ${h})`,
      hex: oklchToHex(lightness, chroma, h),
      int: oklchToInt(lightness, chroma, h),
    });
  }
  return palette;
}

/**
 * Parse an oklch() CSS string into components.
 * Handles: "oklch(65% 0.15 225)" => { l: 65, c: 0.15, h: 225 }
 * @param {string} str
 * @returns {{ l: number, c: number, h: number } | null}
 */
export function parseOklch(str) {
  if (!str || typeof str !== 'string') return null;
  const m = str.match(/oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s*\)/);
  if (!m) return null;
  return { l: parseFloat(m[1]), c: parseFloat(m[2]), h: parseFloat(m[3]) };
}
