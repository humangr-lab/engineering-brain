import { describe, it, expect } from 'vitest';
import { selectLayout } from '../../inference/layout-selector.js';
import { makeNodes } from '../helpers.js';

describe('selectLayout', () => {
  it('returns grid for small graphs (< 10 nodes)', () => {
    const nodes = makeNodes(5);
    const result = selectLayout('force', nodes, []);
    expect(result.layout).toBe('grid');
    expect(result.confidence).toBe(0.7);
  });

  it('maps microservices to orbital (10-50 nodes)', () => {
    const nodes = makeNodes(30);
    const result = selectLayout('microservices', nodes, []);
    expect(result.layout).toBe('orbital');
    expect(result.confidence).toBe(0.9);
  });

  it('overrides orbital to force when > 50 nodes', () => {
    const nodes = makeNodes(60);
    const result = selectLayout('microservices', nodes, []);
    expect(result.layout).toBe('force');
    expect(result.confidence).toBe(0.7);
  });

  it('maps monolith to tree', () => {
    const nodes = makeNodes(15);
    const result = selectLayout('monolith', nodes, []);
    expect(result.layout).toBe('tree');
  });

  it('maps pipeline to pipeline', () => {
    const nodes = makeNodes(15);
    const result = selectLayout('pipeline', nodes, []);
    expect(result.layout).toBe('pipeline');
  });

  it('maps network to force', () => {
    const nodes = makeNodes(15);
    const result = selectLayout('network', nodes, []);
    expect(result.layout).toBe('force');
  });

  it('maps knowledge_graph to force', () => {
    const nodes = makeNodes(15);
    const result = selectLayout('knowledge_graph', nodes, []);
    expect(result.layout).toBe('force');
  });

  it('maps blank to force', () => {
    const nodes = makeNodes(15);
    const result = selectLayout('blank', nodes, []);
    expect(result.layout).toBe('force');
  });

  it('overrides to tree for tree-like structure', () => {
    const nodes = [
      { id: 'root', label: 'Root', type: 'module' },
      ...Array.from({ length: 15 }, (_, i) => ({
        id: `c${i}`, label: `C${i}`, type: 'file', parent: 'root',
      })),
    ];
    // Every node has parent=root, avg children = 15 → not tree-like (>2.5)
    // Need tree-like: avg children <= 2.5
    const treeNodes = [
      { id: 'r', label: 'R', type: 'module' },
      { id: 'a', label: 'A', type: 'module', parent: 'r' },
      { id: 'b', label: 'B', type: 'module', parent: 'r' },
      { id: 'a1', label: 'A1', type: 'file', parent: 'a' },
      { id: 'a2', label: 'A2', type: 'file', parent: 'a' },
      { id: 'b1', label: 'B1', type: 'file', parent: 'b' },
      { id: 'b2', label: 'B2', type: 'file', parent: 'b' },
      { id: 'a1x', label: 'A1x', type: 'function', parent: 'a1' },
      { id: 'a1y', label: 'A1y', type: 'function', parent: 'a1' },
      { id: 'b1x', label: 'B1x', type: 'function', parent: 'b1' },
    ];
    const result = selectLayout('network', treeNodes, []);
    expect(result.layout).toBe('tree');
    expect(result.confidence).toBe(0.8);
  });
});
