import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock state.js before importing search.js
vi.mock('../state.js', () => ({
  state: {
    nodes: [],
    sysNodes: [],
    sysDetails: {},
    submaps: {},
    nodeDetails: {},
  },
  subscribe: vi.fn(),
}));

const { buildSearchIndex, searchNodes, initSearch } = await import('../search.js');

describe('buildSearchIndex', () => {
  it('builds index from node array', () => {
    buildSearchIndex([
      { id: 'auth', label: 'Auth Service', sub: 'Handles authentication', group: 'core', type: 'main', nodeType: 'package', detail: 'OAuth2' },
    ]);
    const results = searchNodes('auth');
    expect(results.length).toBeGreaterThan(0);
    expect(results[0].id).toBe('auth');
  });

  it('ignores non-array input', () => {
    buildSearchIndex(null);
    // Should not throw, and previous index should remain
  });
});

describe('searchNodes', () => {
  beforeEach(() => {
    buildSearchIndex([
      { id: 'auth_service', label: 'Auth Service', sub: 'Authentication', group: 'core', type: 'main', nodeType: 'package', detail: 'OAuth2 provider' },
      { id: 'user_db', label: 'User Database', sub: 'PostgreSQL', group: 'data', type: 'main', nodeType: 'package', detail: 'Primary store' },
      { id: 'api_gateway', label: 'API Gateway', sub: 'REST/gRPC', group: 'infra', type: 'main', nodeType: 'file', detail: 'Rate limiting' },
      { id: 'cache', label: 'Cache Layer', sub: 'Redis', group: 'infra', type: 'main', nodeType: 'class', detail: 'In-memory' },
      { id: 'monitor', label: 'Monitor', sub: 'Metrics', group: 'ops', type: 'main', nodeType: 'function', detail: 'Prometheus' },
    ]);
  });

  it('returns exact ID match with score 100', () => {
    const results = searchNodes('auth_service');
    expect(results[0].id).toBe('auth_service');
    expect(results[0]._score).toBe(100);
  });

  it('scores label-starts-with at 50+', () => {
    const results = searchNodes('Auth');
    const auth = results.find(r => r.id === 'auth_service');
    expect(auth).toBeDefined();
    expect(auth._score).toBeGreaterThanOrEqual(50);
  });

  it('scores label-contains at 30+', () => {
    const results = searchNodes('Gateway');
    const gw = results.find(r => r.id === 'api_gateway');
    expect(gw).toBeDefined();
    expect(gw._score).toBeGreaterThanOrEqual(30);
  });

  it('returns up to 20 results max', () => {
    // Build a large index
    const nodes = Array.from({ length: 50 }, (_, i) => ({
      id: `node_${i}`, label: `Node ${i}`, sub: 'test', group: 'g',
      type: 'main', nodeType: 'package', detail: 'detail',
    }));
    buildSearchIndex(nodes);
    const results = searchNodes('node');
    expect(results.length).toBeLessThanOrEqual(20);
  });

  it('returns first 10 items when query is empty', () => {
    const results = searchNodes('');
    expect(results.length).toBeLessThanOrEqual(10);
  });

  it('applies type filter', () => {
    const results = searchNodes('', 'file');
    expect(results.every(r => r.nodeType === 'file')).toBe(true);
  });

  it('filter=all returns all types', () => {
    const results = searchNodes('', 'all');
    expect(results.length).toBe(5);
  });

  it('fuzzy matches when no direct match', () => {
    // "aser" fuzzy matches "Auth Service" → a...s...e...r
    const results = searchNodes('aser');
    // Should find something via fuzzy
    expect(results.length).toBeGreaterThan(0);
  });

  it('is case-insensitive', () => {
    const upper = searchNodes('AUTH');
    const lower = searchNodes('auth');
    expect(upper[0].id).toBe(lower[0].id);
  });

  it('matches on sub text', () => {
    const results = searchNodes('Redis');
    const cache = results.find(r => r.id === 'cache');
    expect(cache).toBeDefined();
  });

  it('matches on detail text', () => {
    const results = searchNodes('Prometheus');
    const mon = results.find(r => r.id === 'monitor');
    expect(mon).toBeDefined();
  });

  it('sorts results by score descending', () => {
    const results = searchNodes('api');
    for (let i = 1; i < results.length; i++) {
      expect(results[i - 1]._score).toBeGreaterThanOrEqual(results[i]._score);
    }
  });
});
