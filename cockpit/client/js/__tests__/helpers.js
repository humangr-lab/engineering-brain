/* ═══ Test helpers — shared fixtures & factories for unit tests ═══ */

import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Load the real engineering-brain graph_data.json fixture (32 nodes).
 * @returns {{ nodes: Array, edges: Array }}
 */
export function loadGraphData() {
  const p = resolve(__dirname, '../../../examples/engineering-brain/graph_data.json');
  return JSON.parse(readFileSync(p, 'utf-8'));
}

/**
 * Create N synthetic nodes with optional properties.
 * @param {number} n - number of nodes
 * @param {object} [overrides] - merged into every node
 * @returns {Array} nodes
 */
export function makeNodes(n, overrides = {}) {
  return Array.from({ length: n }, (_, i) => ({
    id: `n${i}`,
    label: `Node ${i}`,
    type: 'module',
    group: `g${i % 4}`,
    properties: {},
    ...overrides,
  }));
}

/**
 * Create a linear chain of edges: n0→n1→n2→…→n(len-1).
 * @param {number} len - chain length (creates len-1 edges)
 * @returns {{ nodes: Array, edges: Array }}
 */
export function makeChain(len) {
  const nodes = makeNodes(len);
  const edges = [];
  for (let i = 0; i < len - 1; i++) {
    edges.push({ from: `n${i}`, to: `n${i + 1}`, type: 'CALLS' });
  }
  return { nodes, edges };
}

/**
 * Create nodes with explicit types for shape-mapper testing.
 * @param {Array<[string, string]>} pairs - [[id, type], ...]
 * @returns {Array} nodes
 */
export function makeTypedNodes(pairs) {
  return pairs.map(([id, type]) => ({ id, label: id, type, group: 'test' }));
}

/**
 * Create nodes with LOC/complexity properties for sizer testing.
 * @param {Array<[string, number|null, number|null]>} specs - [[id, loc, complexity], ...]
 * @returns {Array} nodes
 */
export function makeMetricNodes(specs) {
  return specs.map(([id, loc, complexity]) => ({
    id,
    label: id,
    type: 'module',
    group: 'test',
    properties: {
      ...(loc != null ? { loc } : {}),
      ...(complexity != null ? { complexity } : {}),
    },
  }));
}
