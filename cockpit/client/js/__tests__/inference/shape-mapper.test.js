import { describe, it, expect } from 'vitest';
import { mapShapes } from '../../inference/shape-mapper.js';
import { makeTypedNodes } from '../helpers.js';

describe('mapShapes', () => {
  it('maps database types to database shape', () => {
    const nodes = makeTypedNodes([
      ['a', 'database'], ['b', 'db'], ['c', 'datastore'], ['d', 'store'],
    ]);
    const { shapes } = mapShapes(nodes);
    expect(shapes.get('a')).toBe('database');
    expect(shapes.get('b')).toBe('database');
    expect(shapes.get('c')).toBe('database');
    expect(shapes.get('d')).toBe('database');
  });

  it('maps service to gear', () => {
    const nodes = makeTypedNodes([['svc', 'service']]);
    const { shapes } = mapShapes(nodes);
    expect(shapes.get('svc')).toBe('gear');
  });

  it('maps api/gateway/endpoint to gate', () => {
    const nodes = makeTypedNodes([
      ['a', 'api'], ['g', 'gateway'], ['e', 'endpoint'],
    ]);
    const { shapes } = mapShapes(nodes);
    expect(shapes.get('a')).toBe('gate');
    expect(shapes.get('g')).toBe('gate');
    expect(shapes.get('e')).toBe('gate');
  });

  it('maps queue/stream/kafka/broker/message to conveyor', () => {
    const nodes = makeTypedNodes([
      ['q', 'queue'], ['s', 'stream'], ['k', 'kafka'],
    ]);
    const { shapes } = mapShapes(nodes);
    expect(shapes.get('q')).toBe('conveyor');
    expect(shapes.get('s')).toBe('conveyor');
    expect(shapes.get('k')).toBe('conveyor');
  });

  it('maps class/model/entity to prism', () => {
    const nodes = makeTypedNodes([['c', 'class'], ['m', 'model']]);
    const { shapes } = mapShapes(nodes);
    expect(shapes.get('c')).toBe('prism');
    expect(shapes.get('m')).toBe('prism');
  });

  it('maps module/package/library to vault', () => {
    const nodes = makeTypedNodes([['m', 'module'], ['p', 'package']]);
    const { shapes } = mapShapes(nodes);
    expect(shapes.get('m')).toBe('vault');
    expect(shapes.get('p')).toBe('vault');
  });

  it('maps graph/ontology/knowledge to graph', () => {
    const nodes = makeTypedNodes([['g', 'graph'], ['o', 'ontology']]);
    const { shapes } = mapShapes(nodes);
    expect(shapes.get('g')).toBe('graph');
    expect(shapes.get('o')).toBe('graph');
  });

  it('maps container/pod/docker to rack', () => {
    const nodes = makeTypedNodes([['c', 'container'], ['d', 'docker']]);
    const { shapes } = mapShapes(nodes);
    expect(shapes.get('c')).toBe('rack');
    expect(shapes.get('d')).toBe('rack');
  });

  it('falls back to sphere for unknown types', () => {
    const nodes = makeTypedNodes([['x', 'unknown'], ['y', 'custom']]);
    const { shapes, confidence } = mapShapes(nodes);
    expect(shapes.get('x')).toBe('sphere');
    expect(shapes.get('y')).toBe('sphere');
    expect(confidence).toBe(0.60);
  });

  it('is case-insensitive', () => {
    const nodes = makeTypedNodes([['a', 'DATABASE'], ['b', 'Service']]);
    const { shapes } = mapShapes(nodes);
    expect(shapes.get('a')).toBe('database');
    expect(shapes.get('b')).toBe('gear');
  });

  it('matches substrings (e.g., "my_database" includes "database")', () => {
    const nodes = makeTypedNodes([['x', 'my_database_cluster']]);
    const { shapes } = mapShapes(nodes);
    expect(shapes.get('x')).toBe('database');
  });

  it('uses priority order — first match wins', () => {
    // "db_service" contains both "db" (database→database) and "service" (→gear)
    // "db" should match first since database is higher priority
    const nodes = makeTypedNodes([['x', 'db_service']]);
    const { shapes } = mapShapes(nodes);
    expect(shapes.get('x')).toBe('database');
  });

  it('computes average confidence', () => {
    const nodes = makeTypedNodes([
      ['a', 'database'],  // 0.95
      ['b', 'unknown'],   // 0.60 (default)
    ]);
    const { confidence } = mapShapes(nodes);
    expect(confidence).toBeCloseTo((0.95 + 0.60) / 2, 5);
  });
});
