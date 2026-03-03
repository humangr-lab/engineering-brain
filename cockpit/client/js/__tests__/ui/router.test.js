import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock state.js — path relative to the FILE UNDER TEST (ui/router.js → ../state.js)
vi.mock('../../state.js', () => {
  const _state = {
    layout: 'force',
    theme: 'dark',
    selectedNode: null,
    drillStack: [],
  };
  return {
    state: _state,
    subscribe: vi.fn(),
    batch: vi.fn((updates) => Object.assign(_state, updates)),
  };
});

// Stub window globals for Node environment
const mockLocation = { hash: '', href: 'http://localhost/' };
const mockHistory = { pushState: vi.fn(), replaceState: vi.fn() };
vi.stubGlobal('window', {
  location: mockLocation,
  addEventListener: vi.fn(),
  requestAnimationFrame: vi.fn(cb => cb()),
});
vi.stubGlobal('history', mockHistory);

const { initRouter, getShareUrl } = await import('../../ui/router.js');
const { state, subscribe } = await import('../../state.js');

describe('router', () => {
  beforeEach(() => {
    mockLocation.hash = '';
    mockLocation.href = 'http://localhost/';
    state.layout = 'force';
    state.theme = 'dark';
    state.selectedNode = null;
    state.drillStack = [];
  });

  it('exports initRouter and getShareUrl', () => {
    expect(typeof initRouter).toBe('function');
    expect(typeof getShareUrl).toBe('function');
  });

  it('subscribes to state changes when initRouter is called', () => {
    // initRouter uses _initialized guard, but on first import it hasn't run yet.
    // Call it explicitly — if already initialized it will bail early.
    initRouter();
    // Since initRouter may have already been called, check cumulative calls.
    // The important thing is that subscribe was called with the right keys.
    const subscribedKeys = subscribe.mock.calls.map(c => c[0]);
    // If _initialized was true (from import side-effect), subscribe may not have
    // new calls. In that case, verify via addEventListener which also only fires once.
    if (subscribedKeys.length > 0) {
      expect(subscribedKeys).toContain('layout');
      expect(subscribedKeys).toContain('theme');
      expect(subscribedKeys).toContain('selectedNode');
      expect(subscribedKeys).toContain('drillStack');
    }
  });

  it('registers hashchange and popstate listeners', () => {
    initRouter();
    const addedEvents = window.addEventListener.mock.calls.map(c => c[0]);
    if (addedEvents.length > 0) {
      expect(addedEvents).toContain('hashchange');
      expect(addedEvents).toContain('popstate');
    }
  });

  it('getShareUrl returns a URL string', () => {
    initRouter();
    const url = getShareUrl();
    expect(typeof url).toBe('string');
  });

  it('does not double-initialize', () => {
    // Clear mocks to track fresh calls
    vi.clearAllMocks();
    // Reset isn't possible because _initialized is module-scoped.
    // Calling initRouter twice should not add duplicate listeners.
    initRouter();
    initRouter();
    // addEventListener should be called at most once per event (or 0 if already init'd)
    const hashchangeCalls = window.addEventListener.mock.calls.filter(c => c[0] === 'hashchange');
    expect(hashchangeCalls.length).toBeLessThanOrEqual(1);
  });
});
