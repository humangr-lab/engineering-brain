/* ====== SHAPE MAPPER -- Stage 4 of inference pipeline ======
   Maps node.type to shape name via keyword lookup table.
   18 entries ordered by specificity. Fallback: sphere.       */

/**
 * Keyword -> shape lookup table.
 * Sorted by priority (specificity). First match wins.
 * All shape names reference shapes.js (26 shapes).
 */
const SHAPE_TABLE = [
  { keywords: ['database', 'db', 'store', 'datastore'],                shape: 'database',  confidence: 0.95 },
  { keywords: ['service'],                                             shape: 'gear',      confidence: 0.95 },
  { keywords: ['api', 'gateway', 'endpoint'],                          shape: 'gate',      confidence: 0.90 },
  { keywords: ['queue', 'stream', 'kafka', 'broker', 'message'],       shape: 'conveyor',  confidence: 0.90 },
  { keywords: ['file', 'source'],                                      shape: 'terminal',  confidence: 0.85 },
  { keywords: ['class', 'model', 'entity'],                            shape: 'prism',     confidence: 0.85 },
  { keywords: ['function', 'method', 'handler'],                       shape: 'sphere',    confidence: 0.80 },
  { keywords: ['module', 'package', 'library'],                        shape: 'vault',     confidence: 0.85 },
  { keywords: ['config', 'env', 'settings', 'secret'],                 shape: 'dial',      confidence: 0.80 },
  { keywords: ['test', 'spec', 'suite'],                               shape: 'gauge',     confidence: 0.80 },
  { keywords: ['layer', 'tier'],                                       shape: 'stairs',    confidence: 0.90 },
  { keywords: ['user', 'person', 'actor', 'client'],                   shape: 'sphere',    confidence: 0.85 },
  { keywords: ['monitor', 'dashboard', 'metric'],                      shape: 'monitor',   confidence: 0.85 },
  { keywords: ['pipeline', 'workflow', 'dag'],                         shape: 'conveyor',  confidence: 0.85 },
  { keywords: ['network', 'cluster', 'mesh'],                          shape: 'nexus',     confidence: 0.85 },
  { keywords: ['graph', 'ontology', 'knowledge'],                      shape: 'graph',     confidence: 0.90 },
  { keywords: ['cache', 'redis', 'memcached'],                         shape: 'hub',       confidence: 0.85 },
  { keywords: ['container', 'pod', 'docker'],                          shape: 'rack',      confidence: 0.85 },
];

const DEFAULT_SHAPE = { shape: 'sphere', confidence: 0.60 };

/**
 * Map each node to a shape name based on its type field.
 * @param {Array} nodes
 * @returns {{ shapes: Map<string, string>, confidence: number }}
 */
export function mapShapes(nodes) {
  const shapes = new Map();
  const confidences = [];

  for (const n of nodes) {
    const nodeType = (n.type || '').toLowerCase();
    let matched = false;

    for (const entry of SHAPE_TABLE) {
      if (entry.keywords.some(kw => nodeType.includes(kw))) {
        shapes.set(n.id, entry.shape);
        confidences.push(entry.confidence);
        matched = true;
        break;
      }
    }

    if (!matched) {
      shapes.set(n.id, DEFAULT_SHAPE.shape);
      confidences.push(DEFAULT_SHAPE.confidence);
    }
  }

  const avgConf = confidences.length > 0
    ? confidences.reduce((s, v) => s + v, 0) / confidences.length
    : 0.60;

  return { shapes, confidence: avgConf };
}
