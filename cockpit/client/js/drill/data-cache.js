/* ═══════════════ WP-4: DATA CACHE — LRU cache for drill data ═══════════════
   32 entries per level (configurable).
   Cache submap data, code content, symbol tables.
   Prefetch at 80% threshold (when approaching drill boundary).

   References:
     - docs/research/F-06_fractal_drill_down.md Section 8.5              */

/* ── LRU Cache Implementation ── */

/**
 * Simple LRU (Least Recently Used) cache.
 * Uses a Map for O(1) get/set and natural insertion order for eviction.
 */
class LRUCache {
  /**
   * @param {number} maxSize - Maximum entries before eviction
   */
  constructor(maxSize = 32) {
    this._maxSize = maxSize;
    this._map = new Map();
  }

  /**
   * Get a cached value. Returns undefined if not found.
   * Moves the entry to the end (most recently used).
   * @param {string} key
   * @returns {*}
   */
  get(key) {
    if (!this._map.has(key)) return undefined;
    const value = this._map.get(key);
    // Move to end (most recent)
    this._map.delete(key);
    this._map.set(key, value);
    return value;
  }

  /**
   * Set a cached value. Evicts oldest entry if at capacity.
   * @param {string} key
   * @param {*} value
   */
  set(key, value) {
    // If key exists, delete to re-insert at end
    if (this._map.has(key)) {
      this._map.delete(key);
    }

    // Evict oldest if at capacity
    if (this._map.size >= this._maxSize) {
      const oldestKey = this._map.keys().next().value;
      this._map.delete(oldestKey);
    }

    this._map.set(key, value);
  }

  /**
   * Check if a key exists in the cache.
   * @param {string} key
   * @returns {boolean}
   */
  has(key) {
    return this._map.has(key);
  }

  /**
   * Remove a specific key from the cache.
   * @param {string} key
   * @returns {boolean} true if the key was found and removed
   */
  delete(key) {
    return this._map.delete(key);
  }

  /**
   * Clear all entries.
   */
  clear() {
    this._map.clear();
  }

  /**
   * Get the current number of cached entries.
   * @returns {number}
   */
  get size() {
    return this._map.size;
  }
}

/* ── DrillCache: Level-aware cache manager ── */

/**
 * Cache manager for drill-down data, organized by level.
 * Each level has its own LRU cache with configurable capacity.
 */
export class DrillCache {
  /**
   * @param {object} [options]
   * @param {number} [options.perLevelCapacity=32] - Max entries per level
   * @param {number} [options.prefetchThreshold=0.8] - Threshold ratio for prefetch trigger
   */
  constructor(options = {}) {
    const capacity = options.perLevelCapacity || 32;
    this._prefetchThreshold = options.prefetchThreshold || 0.8;
    this._caches = new Map(); // level -> LRUCache
    this._pendingPrefetch = new Set(); // "level:nodeId" keys currently being prefetched
    this._fetchFn = null;

    // Pre-create caches for levels 0-4
    for (let level = 0; level <= 4; level++) {
      this._caches.set(level, new LRUCache(capacity));
    }
  }

  /**
   * Register a fetch function for cache misses and prefetch.
   * @param {Function} fn - async (level, nodeId) => data
   */
  setFetchFunction(fn) {
    this._fetchFn = fn;
  }

  /**
   * Get cached data for a specific level and node.
   * @param {number} level - Drill level (0-4)
   * @param {string} nodeId - Node identifier
   * @returns {*} Cached data or undefined
   */
  get(level, nodeId) {
    const cache = this._caches.get(level);
    if (!cache) return undefined;
    return cache.get(nodeId);
  }

  /**
   * Store data in the cache for a specific level and node.
   * @param {number} level - Drill level (0-4)
   * @param {string} nodeId - Node identifier
   * @param {*} data - Data to cache
   */
  set(level, nodeId, data) {
    const cache = this._caches.get(level);
    if (!cache) return;
    cache.set(nodeId, data);
  }

  /**
   * Check if data is cached for a level and node.
   * @param {number} level
   * @param {string} nodeId
   * @returns {boolean}
   */
  has(level, nodeId) {
    const cache = this._caches.get(level);
    return cache ? cache.has(nodeId) : false;
  }

  /**
   * Prefetch data for a node at a given level.
   * Non-blocking: fires the fetch and caches result when ready.
   * Prevents duplicate prefetch for the same level+node.
   * @param {number} level - Drill level
   * @param {string} nodeId - Node identifier
   */
  async prefetch(level, nodeId) {
    const key = `${level}:${nodeId}`;

    // Skip if already cached or already prefetching
    if (this.has(level, nodeId)) return;
    if (this._pendingPrefetch.has(key)) return;

    // Skip if no fetch function registered
    if (!this._fetchFn) return;

    this._pendingPrefetch.add(key);

    try {
      const data = await this._fetchFn(level, nodeId);
      if (data != null) {
        this.set(level, nodeId, data);
      }
    } catch (err) {
      console.warn(`[WP-4] Prefetch failed for L${level}:${nodeId}:`, err.message);
    } finally {
      this._pendingPrefetch.delete(key);
    }
  }

  /**
   * Get or fetch data. Returns cached data if available, otherwise fetches.
   * @param {number} level
   * @param {string} nodeId
   * @returns {Promise<*>}
   */
  async getOrFetch(level, nodeId) {
    const cached = this.get(level, nodeId);
    if (cached !== undefined) return cached;

    if (!this._fetchFn) return undefined;

    const data = await this._fetchFn(level, nodeId);
    if (data != null) {
      this.set(level, nodeId, data);
    }
    return data;
  }

  /**
   * Clear cache for a specific level, or all levels if level is not specified.
   * @param {number} [level]
   */
  clear(level) {
    if (level !== undefined) {
      const cache = this._caches.get(level);
      if (cache) cache.clear();
    } else {
      for (const cache of this._caches.values()) {
        cache.clear();
      }
    }
  }

  /**
   * Get cache statistics.
   * @returns {object} { totalEntries, perLevel: { [level]: count } }
   */
  stats() {
    let total = 0;
    const perLevel = {};
    for (const [level, cache] of this._caches) {
      perLevel[level] = cache.size;
      total += cache.size;
    }
    return { totalEntries: total, perLevel, pendingPrefetch: this._pendingPrefetch.size };
  }
}

/* ── Singleton ── */

let _globalCache = null;

/**
 * Get the global drill data cache singleton.
 * @returns {DrillCache}
 */
export function getCache() {
  if (!_globalCache) {
    _globalCache = new DrillCache();
  }
  return _globalCache;
}
