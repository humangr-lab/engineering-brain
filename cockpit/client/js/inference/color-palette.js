/* ====== COLOR PALETTE -- Stage 3 of inference pipeline ======
   Generates categorical colors for node groups.
   OKLCH equidistant for <=8 groups, FNV-1a hash for >8.       */

/**
 * Extract sorted group names from nodes.
 * Priority: node.group > node.type > id prefix.
 * @param {Array} nodes
 * @returns {string[]}
 */
export function extractGroups(nodes) {
  const groups = new Set();
  for (const n of nodes) {
    if (n.group) {
      groups.add(n.group);
    } else if (n.type) {
      groups.add(n.type);
    } else {
      // Fallback: derive from id prefix
      const prefix = n.id.includes('_') ? n.id.split('_')[0]
                   : n.id.includes('.') ? n.id.split('.')[0]
                   : n.id;
      groups.add(prefix);
    }
  }
  return [...groups].sort();
}

/**
 * Generate a color palette for the given groups.
 * @param {string[]} groups - Sorted array of group names
 * @param {string} theme - 'dark' or 'light'
 * @returns {{ palette: Map<string, object>, confidence: number }}
 */
export function generatePalette(groups, theme = 'dark') {
  if (groups.length === 0) {
    return { palette: new Map(), confidence: 0.95 };
  }
  if (groups.length <= 8) {
    return _generateSmallPalette(groups, theme);
  }
  return _generateLargePalette(groups, theme);
}

// ── Small palette: equidistant OKLCH hues ──

function _generateSmallPalette(groups, theme) {
  const k = groups.length;
  const L = theme === 'dark' ? 0.65 : 0.55;
  const C = 0.15;
  const palette = new Map();

  for (let i = 0; i < k; i++) {
    const H = (i * 360.0 / k) % 360;
    palette.set(groups[i], {
      h: H,
      oklch: `oklch(${L} ${C} ${H.toFixed(1)})`,
      hex: _oklchToHex(L, C, H),
      int: _oklchToInt(L, C, H),
    });
  }

  return { palette, confidence: 0.95 };
}

// ── Large palette: FNV-1a hash + greedy adjustment ──

function _generateLargePalette(groups, theme) {
  const L = theme === 'dark' ? 0.65 : 0.55;
  const C = 0.15;
  const MIN_HUE_SEP = 30.0;

  // Initial assignment via stable hash
  const hues = {};
  for (const group of groups) {
    hues[group] = _fnv1a(group) % 360;
  }

  // Greedy adjustment: sorted by hue, push apart if too close
  const sortedGroups = [...groups].sort((a, b) => hues[a] - hues[b]);
  for (let i = 1; i < sortedGroups.length; i++) {
    const prevHue = hues[sortedGroups[i - 1]];
    const currHue = hues[sortedGroups[i]];
    if (Math.abs(currHue - prevHue) < MIN_HUE_SEP) {
      hues[sortedGroups[i]] = (prevHue + MIN_HUE_SEP) % 360;
    }
  }

  // Wrap-around check: last vs first
  if (sortedGroups.length >= 2) {
    const firstHue = hues[sortedGroups[0]];
    const lastHue = hues[sortedGroups[sortedGroups.length - 1]];
    if ((360.0 - lastHue + firstHue) < MIN_HUE_SEP) {
      hues[sortedGroups[sortedGroups.length - 1]] = ((firstHue - MIN_HUE_SEP) + 360) % 360;
    }
  }

  const palette = new Map();
  for (const group of groups) {
    const H = hues[group];
    palette.set(group, {
      h: H,
      oklch: `oklch(${L} ${C} ${H.toFixed(1)})`,
      hex: _oklchToHex(L, C, H),
      int: _oklchToInt(L, C, H),
    });
  }

  return { palette, confidence: 0.80 };
}

// ── FNV-1a hash (deterministic, non-cryptographic) ──

function _fnv1a(str) {
  let hash = 0x811c9dc5; // FNV offset basis (32-bit)
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193); // FNV prime (32-bit)
  }
  return hash >>> 0; // Ensure unsigned
}

// ── OKLCH to hex/int (approximate conversion via HSL intermediary) ──
// True OKLCH->sRGB requires matrix transforms; here we use a visually
// close approximation mapping OKLCH H to HSL H (close for L~0.5-0.7).

function _oklchToHex(L, C, H) {
  // Map OKLCH lightness/chroma to HSL saturation/lightness
  const hslH = H;
  const hslS = Math.min(C / 0.20, 1.0); // Normalize chroma to [0,1]
  const hslL = L;
  return _hslToHex(hslH, hslS, hslL);
}

function _oklchToInt(L, C, H) {
  const hex = _oklchToHex(L, C, H);
  return parseInt(hex.slice(1), 16);
}

function _hslToHex(h, s, l) {
  h = h / 360;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => {
    const k = (n + h * 12) % 12;
    const c = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * Math.max(0, Math.min(1, c)));
  };
  const r = f(0), g = f(8), b = f(4);
  return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
}
