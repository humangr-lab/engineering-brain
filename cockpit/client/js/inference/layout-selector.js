/* ====== LAYOUT SELECTOR -- Stage 2 of inference pipeline ======
   Maps detected template to a spatial layout algorithm.
   Includes size-based and topology-based overrides.            */

const TEMPLATE_LAYOUT_MAP = {
  microservices:  'orbital',
  monolith:       'tree',
  pipeline:       'pipeline',
  network:        'force',
  hierarchy:      'tree',
  layered:        'layered',
  knowledge_graph: 'force',
  blank:          'force',
};

/**
 * Select layout algorithm based on template and graph characteristics.
 * @param {string} template - Detected template name
 * @param {Array} nodes
 * @param {Array} edges
 * @returns {{ layout: string, confidence: number }}
 */
export function selectLayout(template, nodes, edges) {
  const defaultLayout = TEMPLATE_LAYOUT_MAP[template] || 'force';
  const nodeCount = nodes.length;

  // Rule 1: Very small graphs -> grid
  if (nodeCount < 10) {
    return { layout: 'grid', confidence: 0.7 };
  }

  // Rule 2: Orbital does not scale beyond ~50 nodes
  if (defaultLayout === 'orbital' && nodeCount > 50) {
    return { layout: 'force', confidence: 0.7 };
  }

  // Rule 3: Tree-like structure
  if (_isTreeLike(nodes, edges)) {
    return { layout: 'tree', confidence: 0.8 };
  }

  // No override: template default
  return { layout: defaultLayout, confidence: 0.9 };
}

/**
 * Detect if graph is tree-like: avg children per parent <= 2.5
 */
function _isTreeLike(nodes, edges) {
  const childrenCount = {};

  // From parent field
  for (const n of nodes) {
    if (n.parent) {
      childrenCount[n.parent] = (childrenCount[n.parent] || 0) + 1;
    }
  }

  // From CONTAINS edges
  for (const e of edges) {
    if (e.type === 'CONTAINS') {
      childrenCount[e.from] = (childrenCount[e.from] || 0) + 1;
    }
  }

  const parentIds = Object.keys(childrenCount);
  if (!parentIds.length) return false;

  const avgChildren = Object.values(childrenCount).reduce((s, v) => s + v, 0) / parentIds.length;
  return avgChildren <= 2.5;
}
