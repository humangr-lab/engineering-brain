import { describe, it, expect, beforeEach, vi } from 'vitest';
import { DrillCache, getCache } from '../../drill/data-cache.js';

describe('DrillCache', () => {
  let cache;

  beforeEach(() => {
    cache = new DrillCache({ perLevelCapacity: 4 });
  });

  // ── Basic get/set/has ──

  it('stores and retrieves data by level + nodeId', () => {
    cache.set(0, 'nodeA', { data: 'hello' });
    expect(cache.get(0, 'nodeA')).toEqual({ data: 'hello' });
  });

  it('returns undefined for cache miss', () => {
    expect(cache.get(0, 'nonexistent')).toBeUndefined();
  });

  it('has() returns true for cached items', () => {
    cache.set(1, 'x', 'value');
    expect(cache.has(1, 'x')).toBe(true);
    expect(cache.has(1, 'y')).toBe(false);
  });

  it('returns false for uncached level', () => {
    expect(cache.has(99, 'x')).toBe(false);
    expect(cache.get(99, 'x')).toBeUndefined();
  });

  // ── LRU eviction ──

  it('evicts oldest entry when at capacity', () => {
    // Capacity is 4
    cache.set(0, 'a', 1);
    cache.set(0, 'b', 2);
    cache.set(0, 'c', 3);
    cache.set(0, 'd', 4);
    // Now at capacity, adding 'e' should evict 'a'
    cache.set(0, 'e', 5);
    expect(cache.has(0, 'a')).toBe(false);
    expect(cache.has(0, 'e')).toBe(true);
  });

  it('accessing an item refreshes its position (LRU)', () => {
    cache.set(0, 'a', 1);
    cache.set(0, 'b', 2);
    cache.set(0, 'c', 3);
    cache.set(0, 'd', 4);
    // Access 'a' to refresh it
    cache.get(0, 'a');
    // Now 'b' is oldest, adding 'e' should evict 'b'
    cache.set(0, 'e', 5);
    expect(cache.has(0, 'a')).toBe(true);
    expect(cache.has(0, 'b')).toBe(false);
  });

  // ── Level isolation ──

  it('isolates data between levels', () => {
    cache.set(0, 'x', 'level0');
    cache.set(1, 'x', 'level1');
    expect(cache.get(0, 'x')).toBe('level0');
    expect(cache.get(1, 'x')).toBe('level1');
  });

  // ── clear ──

  it('clears a specific level', () => {
    cache.set(0, 'a', 1);
    cache.set(1, 'b', 2);
    cache.clear(0);
    expect(cache.has(0, 'a')).toBe(false);
    expect(cache.has(1, 'b')).toBe(true);
  });

  it('clears all levels when no argument', () => {
    cache.set(0, 'a', 1);
    cache.set(1, 'b', 2);
    cache.set(2, 'c', 3);
    cache.clear();
    expect(cache.has(0, 'a')).toBe(false);
    expect(cache.has(1, 'b')).toBe(false);
    expect(cache.has(2, 'c')).toBe(false);
  });

  // ── stats ──

  it('reports correct stats', () => {
    cache.set(0, 'a', 1);
    cache.set(0, 'b', 2);
    cache.set(1, 'c', 3);
    const stats = cache.stats();
    expect(stats.totalEntries).toBe(3);
    expect(stats.perLevel[0]).toBe(2);
    expect(stats.perLevel[1]).toBe(1);
    expect(stats.pendingPrefetch).toBe(0);
  });

  // ── prefetch ──

  it('prefetch calls fetch function and caches result', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ data: 'fetched' });
    cache.setFetchFunction(fetchFn);

    await cache.prefetch(0, 'nodeX');

    expect(fetchFn).toHaveBeenCalledWith(0, 'nodeX');
    expect(cache.get(0, 'nodeX')).toEqual({ data: 'fetched' });
  });

  it('prefetch skips if already cached', async () => {
    const fetchFn = vi.fn().mockResolvedValue('new');
    cache.setFetchFunction(fetchFn);
    cache.set(0, 'nodeX', 'existing');

    await cache.prefetch(0, 'nodeX');

    expect(fetchFn).not.toHaveBeenCalled();
    expect(cache.get(0, 'nodeX')).toBe('existing');
  });

  it('prefetch deduplicates concurrent requests', async () => {
    let resolveFirst;
    const fetchFn = vi.fn().mockImplementation(() => {
      return new Promise(resolve => { resolveFirst = resolve; });
    });
    cache.setFetchFunction(fetchFn);

    const p1 = cache.prefetch(0, 'nodeX');
    const p2 = cache.prefetch(0, 'nodeX');

    resolveFirst('result');
    await Promise.all([p1, p2]);

    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it('prefetch handles errors gracefully', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error('network error'));
    cache.setFetchFunction(fetchFn);

    // Should not throw
    await cache.prefetch(0, 'nodeX');
    expect(cache.has(0, 'nodeX')).toBe(false);
  });

  // ── getOrFetch ──

  it('getOrFetch returns cached data without fetching', async () => {
    const fetchFn = vi.fn();
    cache.setFetchFunction(fetchFn);
    cache.set(0, 'nodeX', 'cached');

    const result = await cache.getOrFetch(0, 'nodeX');
    expect(result).toBe('cached');
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it('getOrFetch fetches and caches on miss', async () => {
    const fetchFn = vi.fn().mockResolvedValue('fresh');
    cache.setFetchFunction(fetchFn);

    const result = await cache.getOrFetch(0, 'nodeX');
    expect(result).toBe('fresh');
    expect(cache.get(0, 'nodeX')).toBe('fresh');
  });

  it('getOrFetch returns undefined when no fetch function', async () => {
    const result = await cache.getOrFetch(0, 'nodeX');
    expect(result).toBeUndefined();
  });
});

describe('getCache', () => {
  it('returns a DrillCache instance', () => {
    const cache = getCache();
    expect(cache).toBeInstanceOf(DrillCache);
  });

  it('returns the same singleton', () => {
    const a = getCache();
    const b = getCache();
    expect(a).toBe(b);
  });
});
