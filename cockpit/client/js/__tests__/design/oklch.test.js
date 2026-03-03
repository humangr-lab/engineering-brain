import { describe, it, expect } from 'vitest';
import {
  oklchToHex,
  oklchToInt,
  hexToOklch,
  generateCategoricalPalette,
  parseOklch,
} from '../../design/oklch.js';

describe('oklchToHex', () => {
  it('returns a valid 7-char hex string', () => {
    const hex = oklchToHex(65, 0.15, 225);
    expect(hex).toMatch(/^#[0-9a-f]{6}$/);
  });

  it('returns consistent results for same input', () => {
    expect(oklchToHex(65, 0.15, 0)).toBe(oklchToHex(65, 0.15, 0));
  });

  it('produces different colors for different hues', () => {
    const h0 = oklchToHex(65, 0.15, 0);
    const h120 = oklchToHex(65, 0.15, 120);
    const h240 = oklchToHex(65, 0.15, 240);
    expect(h0).not.toBe(h120);
    expect(h120).not.toBe(h240);
  });

  it('handles zero lightness (near black)', () => {
    const hex = oklchToHex(0, 0, 0);
    expect(hex).toMatch(/^#[0-9a-f]{6}$/);
    // Should be very dark
    const int = parseInt(hex.slice(1), 16);
    expect(int).toBeLessThan(0x333333);
  });

  it('handles full lightness (near white)', () => {
    const hex = oklchToHex(100, 0, 0);
    expect(hex).toMatch(/^#[0-9a-f]{6}$/);
    const int = parseInt(hex.slice(1), 16);
    expect(int).toBeGreaterThan(0xcccccc);
  });

  it('handles zero chroma (achromatic)', () => {
    const hex = oklchToHex(50, 0, 0);
    expect(hex).toMatch(/^#[0-9a-f]{6}$/);
    // Achromatic: R ≈ G ≈ B
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    expect(Math.abs(r - g)).toBeLessThan(5);
    expect(Math.abs(g - b)).toBeLessThan(5);
  });
});

describe('oklchToInt', () => {
  it('returns a non-negative integer', () => {
    const int = oklchToInt(65, 0.15, 225);
    expect(Number.isInteger(int)).toBe(true);
    expect(int).toBeGreaterThanOrEqual(0);
    expect(int).toBeLessThanOrEqual(0xffffff);
  });

  it('matches oklchToHex conversion', () => {
    const hex = oklchToHex(65, 0.15, 180);
    const int = oklchToInt(65, 0.15, 180);
    const fromHex = parseInt(hex.slice(1), 16);
    expect(int).toBe(fromHex);
  });
});

describe('hexToOklch', () => {
  it('returns l, c, h properties', () => {
    const result = hexToOklch('#ff0000');
    expect(result).toHaveProperty('l');
    expect(result).toHaveProperty('c');
    expect(result).toHaveProperty('h');
  });

  it('handles hex with # prefix', () => {
    const result = hexToOklch('#6b8fff');
    expect(result.l).toBeGreaterThan(0);
  });

  it('handles hex without # prefix', () => {
    const result = hexToOklch('6b8fff');
    expect(result.l).toBeGreaterThan(0);
  });

  it('handles 3-char hex shorthand', () => {
    const full = hexToOklch('#ff0000');
    const short = hexToOklch('#f00');
    expect(full.l).toBeCloseTo(short.l, 1);
    expect(full.h).toBeCloseTo(short.h, 1);
  });

  it('round-trips oklchToHex → hexToOklch approximately', () => {
    const l = 65, c = 0.15, h = 225;
    const hex = oklchToHex(l, c, h);
    const back = hexToOklch(hex);
    // Approximate due to clamping and quantization
    expect(back.l).toBeCloseTo(l, -1);
    expect(back.c).toBeCloseTo(c, 1);
  });

  it('returns high lightness for white', () => {
    const result = hexToOklch('#ffffff');
    expect(result.l).toBeGreaterThan(90);
  });

  it('returns low lightness for black', () => {
    const result = hexToOklch('#000000');
    expect(result.l).toBeLessThan(5);
  });
});

describe('generateCategoricalPalette', () => {
  it('returns n entries', () => {
    const palette = generateCategoricalPalette(5);
    expect(palette.length).toBe(5);
  });

  it('each entry has h, oklch, hex, int', () => {
    const palette = generateCategoricalPalette(3);
    for (const entry of palette) {
      expect(entry).toHaveProperty('h');
      expect(entry).toHaveProperty('oklch');
      expect(entry).toHaveProperty('hex');
      expect(entry).toHaveProperty('int');
    }
  });

  it('distributes hues equidistantly', () => {
    const palette = generateCategoricalPalette(4);
    // 4 colors: 0, 90, 180, 270
    expect(palette[0].h).toBeCloseTo(0, 1);
    expect(palette[1].h).toBeCloseTo(90, 1);
    expect(palette[2].h).toBeCloseTo(180, 1);
    expect(palette[3].h).toBeCloseTo(270, 1);
  });

  it('respects startHue option', () => {
    const palette = generateCategoricalPalette(2, { startHue: 45 });
    expect(palette[0].h).toBeCloseTo(45, 1);
    expect(palette[1].h).toBeCloseTo(225, 1);
  });

  it('respects lightness and chroma options', () => {
    const p1 = generateCategoricalPalette(1, { lightness: 50, chroma: 0.10 });
    const p2 = generateCategoricalPalette(1, { lightness: 80, chroma: 0.20 });
    // Different params → different colors
    expect(p1[0].hex).not.toBe(p2[0].hex);
  });
});

describe('parseOklch', () => {
  it('parses valid oklch() CSS string', () => {
    const result = parseOklch('oklch(65% 0.15 225)');
    expect(result).toEqual({ l: 65, c: 0.15, h: 225 });
  });

  it('returns null for invalid input', () => {
    expect(parseOklch(null)).toBeNull();
    expect(parseOklch('')).toBeNull();
    expect(parseOklch('rgb(255,0,0)')).toBeNull();
    expect(parseOklch(42)).toBeNull();
  });

  it('handles whitespace variations', () => {
    const result = parseOklch('oklch( 70%  0.20  180 )');
    expect(result).toEqual({ l: 70, c: 0.20, h: 180 });
  });
});
