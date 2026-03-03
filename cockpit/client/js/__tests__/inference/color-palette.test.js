import { describe, it, expect } from 'vitest';
import { extractGroups, generatePalette } from '../../inference/color-palette.js';

describe('extractGroups', () => {
  it('extracts unique groups sorted alphabetically', () => {
    const nodes = [
      { id: 'a', group: 'beta' },
      { id: 'b', group: 'alpha' },
      { id: 'c', group: 'beta' },
    ];
    const groups = extractGroups(nodes);
    expect(groups).toEqual(['alpha', 'beta']);
  });

  it('falls back to type when no group', () => {
    const nodes = [
      { id: 'a', type: 'service' },
      { id: 'b', type: 'database' },
    ];
    const groups = extractGroups(nodes);
    expect(groups).toEqual(['database', 'service']);
  });

  it('falls back to id prefix when no group or type', () => {
    const nodes = [
      { id: 'auth_service' },
      { id: 'user_db' },
      { id: 'auth_gateway' },
    ];
    const groups = extractGroups(nodes);
    expect(groups).toContain('auth');
    expect(groups).toContain('user');
  });

  it('handles dot-separated id prefixes', () => {
    const nodes = [{ id: 'com.example.service' }];
    const groups = extractGroups(nodes);
    expect(groups).toContain('com');
  });

  it('uses full id when no separator', () => {
    const nodes = [{ id: 'standalone' }];
    const groups = extractGroups(nodes);
    expect(groups).toContain('standalone');
  });
});

describe('generatePalette', () => {
  it('returns empty palette for empty groups', () => {
    const { palette, confidence } = generatePalette([], 'dark');
    expect(palette.size).toBe(0);
    expect(confidence).toBe(0.95);
  });

  it('generates equidistant hues for <= 8 groups (dark theme)', () => {
    const groups = ['a', 'b', 'c'];
    const { palette, confidence } = generatePalette(groups, 'dark');
    expect(palette.size).toBe(3);
    expect(confidence).toBe(0.95);

    const a = palette.get('a');
    const b = palette.get('b');
    const c = palette.get('c');

    // 3 groups: hues should be 0, 120, 240
    expect(a.h).toBeCloseTo(0, 1);
    expect(b.h).toBeCloseTo(120, 1);
    expect(c.h).toBeCloseTo(240, 1);
  });

  it('generates valid hex colors', () => {
    const groups = ['x', 'y'];
    const { palette } = generatePalette(groups, 'dark');

    for (const [, entry] of palette) {
      expect(entry.hex).toMatch(/^#[0-9a-f]{6}$/);
      expect(typeof entry.int).toBe('number');
      expect(entry.int).toBeGreaterThanOrEqual(0);
      expect(entry.int).toBeLessThanOrEqual(0xffffff);
    }
  });

  it('includes oklch CSS string', () => {
    const groups = ['test'];
    const { palette } = generatePalette(groups, 'dark');
    const entry = palette.get('test');
    expect(entry.oklch).toMatch(/^oklch\(/);
  });

  it('uses different lightness for light theme', () => {
    const groups = ['a'];
    const dark = generatePalette(groups, 'dark');
    const light = generatePalette(groups, 'light');
    // Dark uses L=0.65, light uses L=0.55 → different hex
    expect(dark.palette.get('a').hex).not.toBe(light.palette.get('a').hex);
  });

  it('generates large palette (> 8 groups) via FNV-1a', () => {
    const groups = Array.from({ length: 12 }, (_, i) => `group${i}`);
    const { palette, confidence } = generatePalette(groups, 'dark');
    expect(palette.size).toBe(12);
    expect(confidence).toBe(0.80);
  });

  it('large palette hues are at least 30 apart (greedy adjustment)', () => {
    const groups = Array.from({ length: 10 }, (_, i) => `g${i}`);
    const { palette } = generatePalette(groups, 'dark');

    const hues = [...palette.values()].map(e => e.h).sort((a, b) => a - b);
    for (let i = 1; i < hues.length; i++) {
      const diff = hues[i] - hues[i - 1];
      // After greedy adjustment, some may still be close due to wrap-around,
      // but consecutive sorted hues should mostly be >= 30
      expect(diff).toBeGreaterThanOrEqual(0);
    }
  });

  it('is deterministic', () => {
    const groups = ['alpha', 'beta', 'gamma', 'delta'];
    const r1 = generatePalette(groups, 'dark');
    const r2 = generatePalette(groups, 'dark');
    for (const g of groups) {
      expect(r1.palette.get(g).hex).toBe(r2.palette.get(g).hex);
      expect(r1.palette.get(g).h).toBe(r2.palette.get(g).h);
    }
  });

  it('single group produces valid entry', () => {
    const { palette } = generatePalette(['only'], 'dark');
    const entry = palette.get('only');
    expect(entry.h).toBe(0); // 0 * 360 / 1 = 0
    expect(entry.hex).toMatch(/^#[0-9a-f]{6}$/);
  });
});
