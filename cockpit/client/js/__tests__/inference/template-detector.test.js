import { describe, it, expect } from 'vitest';
import { extractFeatures, detectTemplate } from '../../inference/template-detector.js';
import { makeNodes, makeChain, loadGraphData } from '../helpers.js';

describe('extractFeatures', () => {
  it('returns all expected feature keys', () => {
    const nodes = makeNodes(5);
    const edges = [{ from: 'n0', to: 'n1', type: 'CALLS' }];
    const F = extractFeatures(nodes, edges);

    expect(F).toHaveProperty('edgeTypeDistribution');
    expect(F).toHaveProperty('nodeTypeHistogram');
    expect(F).toHaveProperty('graphDensity');
    expect(F).toHaveProperty('hierarchyDepth');
    expect(F).toHaveProperty('avgDegree');
    expect(F).toHaveProperty('clusteringCoefficient');
    expect(F).toHaveProperty('hasContainment');
    expect(F).toHaveProperty('hasProtocols');
    expect(F).toHaveProperty('uniqueEdgeTypes');
    expect(F).toHaveProperty('uniqueNodeTypes');
    expect(F).toHaveProperty('maxChainLength');
    expect(F).toHaveProperty('nodeGroups');
  });

  it('computes density for directed graph', () => {
    const nodes = makeNodes(3);
    // 3 nodes, max directed edges = 3*(3-1)=6, we have 2 → density = 2/6
    const edges = [
      { from: 'n0', to: 'n1' },
      { from: 'n1', to: 'n2' },
    ];
    const F = extractFeatures(nodes, edges);
    expect(F.graphDensity).toBeCloseTo(2 / 6, 5);
  });

  it('excludes self-loops from density', () => {
    const nodes = makeNodes(2);
    const edges = [
      { from: 'n0', to: 'n1' },
      { from: 'n0', to: 'n0' }, // self-loop
    ];
    const F = extractFeatures(nodes, edges);
    // 1 effective edge / (2*1) = 0.5
    expect(F.graphDensity).toBeCloseTo(0.5, 5);
  });

  it('detects containment from parent field', () => {
    const nodes = [
      { id: 'root', label: 'Root', type: 'module' },
      { id: 'child', label: 'Child', type: 'file', parent: 'root' },
    ];
    const F = extractFeatures(nodes, []);
    expect(F.hasContainment).toBe(true);
    expect(F.hierarchyDepth).toBeGreaterThanOrEqual(1);
  });

  it('detects containment from CONTAINS edges', () => {
    const nodes = makeNodes(3);
    const edges = [{ from: 'n0', to: 'n1', type: 'CONTAINS' }];
    const F = extractFeatures(nodes, edges);
    expect(F.hasContainment).toBe(true);
  });

  it('detects protocol edge types', () => {
    const nodes = makeNodes(2);
    const edges = [{ from: 'n0', to: 'n1', type: 'HTTP' }];
    const F = extractFeatures(nodes, edges);
    expect(F.hasProtocols).toBe(true);
  });

  it('counts unique edge and node types', () => {
    const nodes = [
      { id: 'a', label: 'A', type: 'service' },
      { id: 'b', label: 'B', type: 'database' },
      { id: 'c', label: 'C', type: 'service' },
    ];
    const edges = [
      { from: 'a', to: 'b', type: 'CALLS' },
      { from: 'a', to: 'c', type: 'HTTP' },
    ];
    const F = extractFeatures(nodes, edges);
    expect(F.uniqueEdgeTypes).toBe(2);
    expect(F.uniqueNodeTypes).toBe(2);
  });

  it('computes node groups from group field', () => {
    const nodes = [
      { id: 'a', label: 'A', group: 'alpha' },
      { id: 'b', label: 'B', group: 'beta' },
      { id: 'c', label: 'C', group: 'alpha' },
    ];
    const F = extractFeatures(nodes, []);
    expect(F.nodeGroups).toBeInstanceOf(Set);
    expect(F.nodeGroups.size).toBe(2);
    expect(F.nodeGroups.has('alpha')).toBe(true);
    expect(F.nodeGroups.has('beta')).toBe(true);
  });
});

describe('detectTemplate', () => {
  it('returns blank for empty nodes', () => {
    const result = detectTemplate([], []);
    expect(result.template).toBe('blank');
    expect(result.confidence).toBe(0.5);
  });

  it('returns all expected keys', () => {
    const nodes = makeNodes(15);
    const edges = [{ from: 'n0', to: 'n1', type: 'CALLS' }];
    const result = detectTemplate(nodes, edges);

    expect(result).toHaveProperty('template');
    expect(result).toHaveProperty('confidence');
    expect(result).toHaveProperty('features');
    expect(result).toHaveProperty('allScores');
    expect(typeof result.template).toBe('string');
    expect(result.confidence).toBeGreaterThanOrEqual(0);
    expect(result.confidence).toBeLessThanOrEqual(1);
  });

  it('scores all 8 templates', () => {
    const nodes = makeNodes(15);
    // Need edges to form connected components >= 3 nodes, otherwise
    // disconnected single-node components are all filtered and allScores = { blank }
    const edges = Array.from({ length: 14 }, (_, i) => ({
      from: `n${i}`, to: `n${i + 1}`,
    }));
    const result = detectTemplate(nodes, edges);
    const templates = Object.keys(result.allScores);
    expect(templates).toContain('microservices');
    expect(templates).toContain('monolith');
    expect(templates).toContain('pipeline');
    expect(templates).toContain('network');
    expect(templates).toContain('hierarchy');
    expect(templates).toContain('layered');
    expect(templates).toContain('knowledge_graph');
    expect(templates).toContain('blank');
  });

  it('detects hierarchy template for tree-structured data', () => {
    const nodes = [
      { id: 'root', label: 'Root', type: 'module' },
      { id: 'c1', label: 'C1', type: 'module', parent: 'root' },
      { id: 'c2', label: 'C2', type: 'module', parent: 'root' },
      { id: 'c3', label: 'C3', type: 'module', parent: 'root' },
      { id: 'gc1', label: 'GC1', type: 'file', parent: 'c1' },
      { id: 'gc2', label: 'GC2', type: 'file', parent: 'c1' },
      { id: 'gc3', label: 'GC3', type: 'file', parent: 'c2' },
      { id: 'gc4', label: 'GC4', type: 'file', parent: 'c2' },
      { id: 'gc5', label: 'GC5', type: 'file', parent: 'c3' },
      { id: 'gc6', label: 'GC6', type: 'file', parent: 'c3' },
      { id: 'ggc1', label: 'GGC1', type: 'function', parent: 'gc1' },
      { id: 'ggc2', label: 'GGC2', type: 'function', parent: 'gc2' },
    ];
    const edges = [
      { from: 'root', to: 'c1', type: 'CONTAINS' },
      { from: 'root', to: 'c2', type: 'CONTAINS' },
      { from: 'root', to: 'c3', type: 'CONTAINS' },
      { from: 'c1', to: 'gc1', type: 'CONTAINS' },
      { from: 'c1', to: 'gc2', type: 'CONTAINS' },
      { from: 'c2', to: 'gc3', type: 'CONTAINS' },
      { from: 'c2', to: 'gc4', type: 'CONTAINS' },
      { from: 'c3', to: 'gc5', type: 'CONTAINS' },
      { from: 'c3', to: 'gc6', type: 'CONTAINS' },
      { from: 'gc1', to: 'ggc1', type: 'CONTAINS' },
      { from: 'gc2', to: 'ggc2', type: 'CONTAINS' },
    ];
    const result = detectTemplate(nodes, edges);
    expect(result.allScores.hierarchy).toBeGreaterThan(result.allScores.blank);
  });

  it('scores knowledge_graph higher for KG edge types', () => {
    const nodes = makeNodes(15);
    const edges = [
      { from: 'n0', to: 'n1', type: 'RELATES' },
      { from: 'n1', to: 'n2', type: 'SUPPORTS' },
      { from: 'n2', to: 'n3', type: 'CONTRADICTS' },
      { from: 'n3', to: 'n4', type: 'INFORMS' },
      { from: 'n4', to: 'n5', type: 'GROUNDS' },
      { from: 'n5', to: 'n6', type: 'VALIDATES' },
      { from: 'n6', to: 'n7', type: 'DERIVED_FROM' },
    ];
    const result = detectTemplate(nodes, edges);
    expect(result.allScores.knowledge_graph).toBeGreaterThan(result.allScores.blank);
  });

  it('is deterministic — same input produces same output', () => {
    const { nodes, edges } = loadGraphData();
    const r1 = detectTemplate(nodes, edges);
    const r2 = detectTemplate(nodes, edges);
    expect(r1.template).toBe(r2.template);
    expect(r1.confidence).toBe(r2.confidence);
    expect(r1.allScores).toEqual(r2.allScores);
  });

  it('handles disconnected components', () => {
    const nodes = [
      // Component 1: 5 nodes
      ...makeNodes(5),
      // Component 2: 5 nodes (isolated)
      ...makeNodes(5, {}).map((n, i) => ({ ...n, id: `m${i}`, group: 'other' })),
    ];
    const edges = [
      { from: 'n0', to: 'n1' },
      { from: 'n1', to: 'n2' },
      { from: 'm0', to: 'm1' },
      { from: 'm1', to: 'm2' },
    ];
    const result = detectTemplate(nodes, edges);
    expect(result.template).toBeDefined();
    expect(result.confidence).toBeGreaterThan(0);
  });

  it('works on real engineering-brain data', () => {
    const { nodes, edges } = loadGraphData();
    const result = detectTemplate(nodes, edges);
    expect(result.template).toBeDefined();
    expect(result.confidence).toBeGreaterThan(0);
    expect(result.features.nodeGroups).toBeInstanceOf(Set);
  });
});
