import { describe, it, expect } from 'vitest';
import { computeSizes } from '../../inference/sizer.js';
import { makeNodes, makeMetricNodes } from '../helpers.js';

describe('computeSizes', () => {
  it('returns empty Map for empty nodes', () => {
    const { sizes, confidence } = computeSizes([], []);
    expect(sizes.size).toBe(0);
    expect(confidence).toBe(0.5);
  });

  it('uses LOC when >= 50% of nodes have it', () => {
    const nodes = makeMetricNodes([
      ['a', 100, null],
      ['b', 500, null],
      ['c', 1000, null],
    ]);
    const { sizes, confidence } = computeSizes(nodes, []);
    expect(confidence).toBe(0.85);
    expect(sizes.size).toBe(3);
    // Higher LOC → larger size
    expect(sizes.get('c')).toBeGreaterThan(sizes.get('a'));
  });

  it('uses LOC with reduced confidence when < 50% coverage', () => {
    const nodes = makeMetricNodes([
      ['a', 100, null],
      ['b', null, null],
      ['c', null, null],
      ['d', null, null],
      ['e', null, null],
    ]);
    const edges = [{ from: 'b', to: 'c' }];
    const { confidence } = computeSizes(nodes, edges);
    expect(confidence).toBe(0.75);
  });

  it('uses complexity when no LOC available', () => {
    const nodes = makeMetricNodes([
      ['a', null, 5],
      ['b', null, 15],
      ['c', null, 30],
    ]);
    const { sizes, confidence } = computeSizes(nodes, []);
    expect(confidence).toBe(0.80);
    expect(sizes.get('c')).toBeGreaterThan(sizes.get('a'));
  });

  it('uses degree centrality when no LOC or complexity', () => {
    const nodes = makeNodes(4);
    const edges = [
      { from: 'n0', to: 'n1' },
      { from: 'n0', to: 'n2' },
      { from: 'n0', to: 'n3' },
    ];
    const { sizes, confidence } = computeSizes(nodes, edges);
    expect(confidence).toBe(0.70);
    // n0 has degree 3, others have degree 1 → n0 should be largest
    expect(sizes.get('n0')).toBeGreaterThan(sizes.get('n3'));
  });

  it('returns uniform sizes when no edges and no metrics (degree centrality fallback)', () => {
    const nodes = makeNodes(3);
    const { sizes, confidence } = computeSizes(nodes, []);
    // maxDeg initialized to 1 even with 0 edges → enters degree centrality branch (0.70)
    // All centrality values are 0 → sigma < 1e-9 → uniform size 1.0
    expect(confidence).toBe(0.70);
    expect(sizes.get('n0')).toBe(1.0);
    expect(sizes.get('n1')).toBe(1.0);
    expect(sizes.get('n2')).toBe(1.0);
  });

  it('clamps all sizes to [0.3, 3.0]', () => {
    const nodes = makeMetricNodes([
      ['tiny', 1, null],
      ['huge', 100000, null],
      ['mid', 500, null],
    ]);
    const { sizes } = computeSizes(nodes, []);
    for (const [, size] of sizes) {
      expect(size).toBeGreaterThanOrEqual(0.3);
      expect(size).toBeLessThanOrEqual(3.0);
    }
  });

  it('handles uniform metrics (all same LOC)', () => {
    const nodes = makeMetricNodes([
      ['a', 100, null],
      ['b', 100, null],
      ['c', 100, null],
    ]);
    const { sizes } = computeSizes(nodes, []);
    // All same LOC → sigma = 0 → uniform size = 1.0
    expect(sizes.get('a')).toBe(1.0);
    expect(sizes.get('b')).toBe(1.0);
  });

  it('excludes self-loops from degree computation', () => {
    const nodes = makeNodes(2);
    const edges = [
      { from: 'n0', to: 'n0' }, // self-loop
      { from: 'n0', to: 'n1' },
    ];
    const { sizes } = computeSizes(nodes, edges);
    // Self-loop excluded, so n0 and n1 each have degree 1
    expect(sizes.get('n0')).toBeCloseTo(sizes.get('n1'), 5);
  });

  it('handles 10K nodes without error', () => {
    const nodes = makeNodes(10000);
    const edges = Array.from({ length: 5000 }, (_, i) => ({
      from: `n${i}`, to: `n${i + 1}`,
    }));
    const { sizes, confidence } = computeSizes(nodes, edges);
    expect(sizes.size).toBe(10000);
    expect(confidence).toBe(0.70);
  });

  it('uses log10 transform for LOC', () => {
    const nodes = makeMetricNodes([
      ['a', 10, null],
      ['b', 100, null],
      ['c', 10000, null],
    ]);
    const { sizes } = computeSizes(nodes, []);
    // log10(10)=1, log10(100)=2, log10(10000)=4
    // Size differences should be more compressed than raw LOC
    const ratio = (sizes.get('c') - sizes.get('a')) / (sizes.get('b') - sizes.get('a'));
    // Without log: ratio would be (9990/90)=111, with log: (3/1)=3
    expect(ratio).toBeLessThan(10);
  });
});
