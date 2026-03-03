import { describe, it, expect } from 'vitest';
import { inferConfig } from '../../inference/engine.js';
import { loadGraphData, makeNodes, makeChain } from '../helpers.js';

describe('inferConfig', () => {
  it('returns blank config for empty graph', () => {
    const result = inferConfig({ nodes: [], edges: [] });
    expect(result.template).toBe('blank');
    expect(result.layout).toBe('force');
    expect(result.palette).toBeInstanceOf(Map);
    expect(result.palette.size).toBe(0);
    expect(result.shapes).toBeInstanceOf(Map);
    expect(result.sizes).toBeInstanceOf(Map);
    expect(result.confidence.total).toBe(0.5);
  });

  it('returns all expected top-level keys', () => {
    const { nodes, edges } = loadGraphData();
    const result = inferConfig({ nodes, edges });
    expect(result).toHaveProperty('template');
    expect(result).toHaveProperty('layout');
    expect(result).toHaveProperty('palette');
    expect(result).toHaveProperty('shapes');
    expect(result).toHaveProperty('sizes');
    expect(result).toHaveProperty('confidence');
    expect(result).toHaveProperty('features');
    expect(result).toHaveProperty('allScores');
  });

  it('confidence object has all 5 stage scores plus total', () => {
    const { nodes, edges } = loadGraphData();
    const result = inferConfig({ nodes, edges });
    expect(result.confidence).toHaveProperty('template');
    expect(result.confidence).toHaveProperty('layout');
    expect(result.confidence).toHaveProperty('palette');
    expect(result.confidence).toHaveProperty('shapes');
    expect(result.confidence).toHaveProperty('sizing');
    expect(result.confidence).toHaveProperty('total');
    expect(result.confidence.total).toBeGreaterThan(0);
    expect(result.confidence.total).toBeLessThanOrEqual(1);
  });

  it('is deterministic — same input produces identical output', () => {
    const data = loadGraphData();
    const r1 = inferConfig(data);
    const r2 = inferConfig(data);
    expect(r1.template).toBe(r2.template);
    expect(r1.layout).toBe(r2.layout);
    expect(r1.confidence.total).toBe(r2.confidence.total);
    // Compare palette hex values
    for (const [key, val] of r1.palette) {
      expect(r2.palette.get(key).hex).toBe(val.hex);
    }
  });

  it('normalizes { f, t } edge format to { from, to }', () => {
    const nodes = makeNodes(15);
    const edges = [{ f: 'n0', t: 'n1' }, { f: 'n1', t: 'n2' }];
    const result = inferConfig({ nodes, edges });
    expect(result.template).toBeDefined();
    expect(result.sizes.size).toBe(15);
  });

  it('handles missing edges gracefully', () => {
    const data = loadGraphData();
    const result = inferConfig({ nodes: data.nodes });
    expect(result.template).toBeDefined();
    expect(result.sizes.size).toBe(data.nodes.length);
  });

  it('respects theme option', () => {
    const data = loadGraphData();
    const dark = inferConfig(data, { theme: 'dark' });
    const light = inferConfig(data, { theme: 'light' });
    // Palette colors should differ between themes
    const firstGroup = [...dark.palette.keys()][0];
    if (firstGroup) {
      expect(dark.palette.get(firstGroup).hex).not.toBe(
        light.palette.get(firstGroup).hex
      );
    }
  });

  it('produces shapes and sizes for every node', () => {
    const { nodes, edges } = loadGraphData();
    const result = inferConfig({ nodes, edges });
    expect(result.shapes.size).toBe(nodes.length);
    expect(result.sizes.size).toBe(nodes.length);
  });
});
