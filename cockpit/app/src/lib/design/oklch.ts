/**
 * OKLCH color utilities for Three.js materials.
 * Ported from client/js/design/oklch.js — pure functions, zero dependencies.
 */

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

function linearToSrgb(c: number): number {
  return c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
}

function srgbToLinear(c: number): number {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/**
 * Convert OKLCH to linear sRGB via OKLab.
 * @param L Lightness 0..1
 * @param C Chroma >= 0
 * @param H Hue in degrees
 */
function oklchToLinearRgb(L: number, C: number, H: number): [number, number, number] {
  const hRad = (H * Math.PI) / 180;
  const a = C * Math.cos(hRad);
  const b = C * Math.sin(hRad);

  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b;

  const l = l_ * l_ * l_;
  const m = m_ * m_ * m_;
  const s = s_ * s_ * s_;

  const R = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const G = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const B = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s;

  return [R, G, B];
}

/** Convert OKLCH values to a hex color string. */
export function oklchToHex(l: number, c: number, h: number): string {
  const [R, G, B] = oklchToLinearRgb(l / 100, c, h);
  const r = clamp(Math.round(linearToSrgb(clamp(R, 0, 1)) * 255), 0, 255);
  const g = clamp(Math.round(linearToSrgb(clamp(G, 0, 1)) * 255), 0, 255);
  const b = clamp(Math.round(linearToSrgb(clamp(B, 0, 1)) * 255), 0, 255);
  return "#" + ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1);
}

/** Convert OKLCH values to an integer for Three.js. */
export function oklchToInt(l: number, c: number, h: number): number {
  const [R, G, B] = oklchToLinearRgb(l / 100, c, h);
  const r = clamp(Math.round(linearToSrgb(clamp(R, 0, 1)) * 255), 0, 255);
  const g = clamp(Math.round(linearToSrgb(clamp(G, 0, 1)) * 255), 0, 255);
  const b = clamp(Math.round(linearToSrgb(clamp(B, 0, 1)) * 255), 0, 255);
  return (r << 16) | (g << 8) | b;
}

/** Convert hex color string to OKLCH. */
export function hexToOklch(hex: string): { l: number; c: number; h: number } {
  hex = hex.replace(/^#/, "");
  if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
  const num = parseInt(hex, 16);
  const r = srgbToLinear(((num >> 16) & 0xff) / 255);
  const g = srgbToLinear(((num >> 8) & 0xff) / 255);
  const b = srgbToLinear((num & 0xff) / 255);

  // linear sRGB -> LMS -> OKLab -> OKLCH
  const lms_l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b;
  const lms_m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b;
  const lms_s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b;
  const l_ = Math.cbrt(lms_l);
  const m_ = Math.cbrt(lms_m);
  const s_ = Math.cbrt(lms_s);
  const L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_;
  const a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_;
  const bLab = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_;
  const C = Math.sqrt(a * a + bLab * bLab);
  let H = (Math.atan2(bLab, a) * 180) / Math.PI;
  if (H < 0) H += 360;
  return { l: L * 100, c: C, h: H };
}

/** Generate a categorical palette of n equidistant hues. */
export function generateCategoricalPalette(
  n: number,
  opts: { lightness?: number; chroma?: number; startHue?: number } = {}
) {
  const { lightness = 65, chroma = 0.15, startHue = 0 } = opts;
  const step = 360 / n;
  return Array.from({ length: n }, (_, i) => {
    const h = (startHue + i * step) % 360;
    return {
      h,
      oklch: `oklch(${lightness}% ${chroma} ${h})`,
      hex: oklchToHex(lightness, chroma, h),
      int: oklchToInt(lightness, chroma, h),
    };
  });
}

/** Parse an oklch() CSS string into components. */
export function parseOklch(str: string): { l: number; c: number; h: number } | null {
  if (!str || typeof str !== "string") return null;
  const m = str.match(/oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s*\)/);
  if (!m) return null;
  return { l: parseFloat(m[1]), c: parseFloat(m[2]), h: parseFloat(m[3]) };
}
