/* ====== COLOR PALETTE -- Stage 3 of inference pipeline ======
   Generates categorical colors for node groups.
   OKLCH equidistant for <=8 groups, FNV-1a hash for >8.       */

import type { GraphDataNode } from "@/lib/api";

export interface GroupColor {
  h: number;
  oklch: string;
  hex: string;
  int: number;
}

export interface PaletteResult {
  palette: Map<string, GroupColor>;
  confidence: number;
}

export function extractGroups(nodes: GraphDataNode[]): string[] {
  const groups = new Set<string>();
  for (const n of nodes) {
    if (n.group) {
      groups.add(n.group);
    } else if (n.type) {
      groups.add(n.type);
    } else {
      const prefix = n.id.includes("_")
        ? n.id.split("_")[0]
        : n.id.includes(".")
          ? n.id.split(".")[0]
          : n.id;
      groups.add(prefix);
    }
  }
  return [...groups].sort();
}

export function generatePalette(
  groups: string[],
  theme: "dark" | "light" = "dark",
): PaletteResult {
  if (groups.length === 0) {
    return { palette: new Map(), confidence: 0.95 };
  }
  if (groups.length <= 8) {
    return generateSmallPalette(groups, theme);
  }
  return generateLargePalette(groups, theme);
}

// ── Small palette: equidistant OKLCH hues ──

function generateSmallPalette(
  groups: string[],
  theme: "dark" | "light",
): PaletteResult {
  const k = groups.length;
  const L = theme === "dark" ? 0.65 : 0.55;
  const C = 0.15;
  const palette = new Map<string, GroupColor>();

  for (let i = 0; i < k; i++) {
    const H = (i * 360.0) / k % 360;
    palette.set(groups[i], {
      h: H,
      oklch: `oklch(${L} ${C} ${H.toFixed(1)})`,
      hex: oklchToHex(L, C, H),
      int: oklchToInt(L, C, H),
    });
  }

  return { palette, confidence: 0.95 };
}

// ── Large palette: FNV-1a hash + greedy adjustment ──

function generateLargePalette(
  groups: string[],
  theme: "dark" | "light",
): PaletteResult {
  const L = theme === "dark" ? 0.65 : 0.55;
  const C = 0.15;
  const MIN_HUE_SEP = 30.0;

  const hues: Record<string, number> = {};
  for (const group of groups) {
    hues[group] = fnv1a(group) % 360;
  }

  // Iterative greedy adjustment — re-sort and adjust until stable (max 3 passes)
  // Single pass can cascade: pushing group[i] into group[i+1]'s territory
  for (let pass = 0; pass < 3; pass++) {
    const sorted = [...groups].sort((a, b) => hues[a] - hues[b]);
    let changed = false;

    for (let i = 1; i < sorted.length; i++) {
      const prevHue = hues[sorted[i - 1]];
      const currHue = hues[sorted[i]];
      if (Math.abs(currHue - prevHue) < MIN_HUE_SEP) {
        hues[sorted[i]] = (prevHue + MIN_HUE_SEP) % 360;
        changed = true;
      }
    }

    // Wrap-around check
    if (sorted.length >= 2) {
      const firstHue = hues[sorted[0]];
      const lastHue = hues[sorted[sorted.length - 1]];
      if (360.0 - lastHue + firstHue < MIN_HUE_SEP) {
        hues[sorted[sorted.length - 1]] = (firstHue - MIN_HUE_SEP + 360) % 360;
        changed = true;
      }
    }

    if (!changed) break;
  }

  // Fallback: if >12 groups exhaust 360° of hue space, reduce MIN_HUE_SEP
  // 360 / MIN_HUE_SEP = max 12 groups with 30° separation
  // For >12 groups, collisions are inevitable — accept reduced separation

  const palette = new Map<string, GroupColor>();
  for (const group of groups) {
    const H = hues[group];
    palette.set(group, {
      h: H,
      oklch: `oklch(${L} ${C} ${H.toFixed(1)})`,
      hex: oklchToHex(L, C, H),
      int: oklchToInt(L, C, H),
    });
  }

  return { palette, confidence: 0.8 };
}

// ── FNV-1a hash (deterministic, non-cryptographic) ──

function fnv1a(str: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

// ── OKLCH to hex/int (approximate via HSL intermediary) ──

function oklchToHex(L: number, C: number, H: number): string {
  const hslH = H;
  const hslS = Math.min(C / 0.2, 1.0);
  const hslL = L;
  return hslToHex(hslH, hslS, hslL);
}

function oklchToInt(L: number, C: number, H: number): number {
  const hex = oklchToHex(L, C, H);
  return parseInt(hex.slice(1), 16);
}

function hslToHex(h: number, s: number, l: number): string {
  h = h / 360;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => {
    const k = (n + h * 12) % 12;
    const c = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * Math.max(0, Math.min(1, c)));
  };
  const r = f(0),
    g = f(8),
    b = f(4);
  return (
    "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)
  );
}
