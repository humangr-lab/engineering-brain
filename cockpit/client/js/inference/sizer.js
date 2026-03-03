/* ====== SIZER -- Stage 5 of inference pipeline ======
   Computes visual size scalar for each node.
   Priority: LOC > complexity > degree centrality > uniform.
   Normalization: transform -> z-score -> sigmoid -> [0.3, 3.0] */

const MIN_SIZE = 0.3;
const MAX_SIZE = 3.0;

/**
 * Compute sizes for all nodes.
 * @param {Array} nodes
 * @param {Array} edges
 * @returns {{ sizes: Map<string, number>, confidence: number }}
 */
export function computeSizes(nodes, edges) {
  if (!nodes.length) {
    return { sizes: new Map(), confidence: 0.5 };
  }

  const allNodeIds = new Set(nodes.map(n => n.id));

  // Collect metric sources per node
  const locValues = {};
  const complexityValues = {};

  for (const n of nodes) {
    const props = n.properties || {};
    if (props.loc != null && typeof props.loc === 'number') {
      locValues[n.id] = props.loc;
    }
    if (props.complexity != null && typeof props.complexity === 'number') {
      complexityValues[n.id] = props.complexity;
    }
  }

  // Degree centrality (always available)
  const degree = {};
  for (const n of nodes) degree[n.id] = 0;
  for (const e of edges) {
    if (e.from !== e.to) { // Exclude self-loops
      degree[e.from] = (degree[e.from] || 0) + 1;
      degree[e.to] = (degree[e.to] || 0) + 1;
    }
  }
  // Iterative max to avoid stack overflow on large graphs (>10K nodes)
  let maxDeg = 1;
  for (const d of Object.values(degree)) {
    if (d > maxDeg) maxDeg = d;
  }
  const centrality = {};
  for (const [nid, d] of Object.entries(degree)) {
    centrality[nid] = d / maxDeg;
  }

  const locCount = Object.keys(locValues).length;
  const compCount = Object.keys(complexityValues).length;
  let merged;
  let confidence;

  if (locCount >= nodes.length * 0.5) {
    // LOC covers >= 50% of nodes
    const locSizes = _sizeFromMetric(locValues, _log10);
    const fallbackIds = [...allNodeIds].filter(id => !(id in locValues));
    if (fallbackIds.length) {
      const fbValues = {};
      for (const id of fallbackIds) fbValues[id] = centrality[id] || 0;
      const fbSizes = _sizeFromMetric(fbValues, _identity);
      merged = new Map([...locSizes, ...fbSizes]);
    } else {
      merged = locSizes;
    }
    confidence = 0.85;

  } else if (locCount > 0) {
    // LOC covers < 50%
    const locSizes = _sizeFromMetric(locValues, _log10);
    const fallbackIds = [...allNodeIds].filter(id => !(id in locValues));
    const fbValues = {};
    for (const id of fallbackIds) fbValues[id] = centrality[id] || 0;
    const fbSizes = _sizeFromMetric(fbValues, _identity);
    merged = new Map([...locSizes, ...fbSizes]);
    confidence = 0.75;

  } else if (compCount > 0) {
    // Complexity available
    const compSizes = _sizeFromMetric(complexityValues, _identity);
    const fallbackIds = [...allNodeIds].filter(id => !(id in complexityValues));
    if (fallbackIds.length) {
      const fbValues = {};
      for (const id of fallbackIds) fbValues[id] = centrality[id] || 0;
      const fbSizes = _sizeFromMetric(fbValues, _identity);
      merged = new Map([...compSizes, ...fbSizes]);
    } else {
      merged = compSizes;
    }
    confidence = 0.80;

  } else if (maxDeg > 0) {
    // Degree centrality only
    merged = _sizeFromMetric(centrality, _identity);
    confidence = 0.70;

  } else {
    // No data: uniform
    merged = new Map();
    for (const n of nodes) merged.set(n.id, 1.0);
    confidence = 0.50;
  }

  return { sizes: merged, confidence };
}

// ── Normalization pipeline ──

function _sizeFromMetric(values, transform) {
  const transformed = {};
  for (const [nid, v] of Object.entries(values)) {
    transformed[nid] = transform(v);
  }

  const vals = Object.values(transformed);
  const mu = vals.reduce((s, v) => s + v, 0) / vals.length;
  const variance = vals.reduce((s, v) => s + (v - mu) ** 2, 0) / vals.length;
  const sigma = Math.sqrt(variance);

  // All values identical -> uniform size
  if (sigma < 1e-9) {
    const result = new Map();
    for (const nid of Object.keys(transformed)) result.set(nid, 1.0);
    return result;
  }

  // Z-score
  const zScores = {};
  for (const [nid, v] of Object.entries(transformed)) {
    zScores[nid] = (v - mu) / sigma;
  }

  // Sigmoid
  const sigmoid = {};
  for (const [nid, z] of Object.entries(zScores)) {
    sigmoid[nid] = 1.0 / (1.0 + Math.exp(-z));
  }

  // Linear map (0,1) -> [MIN_SIZE, MAX_SIZE]
  const result = new Map();
  for (const [nid, s] of Object.entries(sigmoid)) {
    const size = MIN_SIZE + s * (MAX_SIZE - MIN_SIZE);
    result.set(nid, Math.max(MIN_SIZE, Math.min(MAX_SIZE, size)));
  }

  return result;
}

function _log10(v) {
  return Math.log10(Math.max(v, 1));
}

function _identity(v) {
  return Number(v);
}
