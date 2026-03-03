/* ====== TEMPLATE DETECTOR -- Stage 1 of inference pipeline ======
   Extracts structural features from graph, scores 8 candidate templates.
   Deterministic: same input always produces same output.            */

/**
 * Extract structural features from a graph.
 * @param {Array} nodes
 * @param {Array} edges
 * @returns {object} Feature vector F
 */
export function extractFeatures(nodes, edges) {
  const N = nodes.length;
  const E = edges.length;

  // Filter self-loops for density/degree calculations
  const effectiveEdges = edges.filter(e => e.from !== e.to);

  // --- Edge type distribution ---
  const edgeTypeCounts = {};
  for (const e of edges) {
    const t = e.type || (e.properties?.color ? 'UNKNOWN' : 'UNKNOWN');
    edgeTypeCounts[t] = (edgeTypeCounts[t] || 0) + 1;
  }
  const edgeTypeDistribution = {};
  for (const [t, c] of Object.entries(edgeTypeCounts)) {
    edgeTypeDistribution[t] = E > 0 ? c / E : 0;
  }

  // --- Node type histogram ---
  const nodeTypeCounts = {};
  for (const n of nodes) {
    const t = (n.type || '').toLowerCase();
    if (t) nodeTypeCounts[t] = (nodeTypeCounts[t] || 0) + 1;
  }
  const nodeTypeHistogram = {};
  for (const [t, c] of Object.entries(nodeTypeCounts)) {
    nodeTypeHistogram[t] = N > 0 ? c / N : 0;
  }

  // --- Graph density (directed) ---
  const graphDensity = N > 1 ? effectiveEdges.length / (N * (N - 1)) : 0;

  // --- Hierarchy depth (parent chains) ---
  const hierarchyDepth = _maxDepth(nodes);

  // --- Degree computation ---
  const inDeg = {};
  const outDeg = {};
  for (const n of nodes) {
    inDeg[n.id] = 0;
    outDeg[n.id] = 0;
  }
  for (const e of effectiveEdges) {
    outDeg[e.from] = (outDeg[e.from] || 0) + 1;
    inDeg[e.to] = (inDeg[e.to] || 0) + 1;
  }
  let totalDegree = 0;
  for (const n of nodes) {
    totalDegree += (inDeg[n.id] || 0) + (outDeg[n.id] || 0);
  }
  const avgDegree = N > 0 ? totalDegree / N : 0;

  // --- Clustering coefficient (transitivity) ---
  const clusteringCoefficient = _transitivity(nodes, effectiveEdges);

  // --- Containment detection ---
  const hasContainment = edges.some(e => e.type === 'CONTAINS') ||
                         nodes.some(n => n.parent);

  // --- Protocol detection ---
  const protocolTypes = new Set(['HTTP', 'GRPC', 'AMQP', 'MQTT', 'REST', 'WEBSOCKET']);
  const hasProtocols = edges.some(e => e.type && protocolTypes.has(e.type.toUpperCase()));

  // --- Unique type counts ---
  const uniqueEdgeTypes = new Set(
    edges.filter(e => e.type).map(e => e.type)
  ).size;
  const uniqueNodeTypes = new Set(
    nodes.filter(n => n.type).map(n => n.type)
  ).size;

  // --- Max chain length ---
  const maxChainLength = _approxMaxChainLength(nodes, effectiveEdges);

  // --- Node groups ---
  const nodeGroups = new Set();
  for (const n of nodes) {
    if (n.group) nodeGroups.add(n.group);
  }

  return {
    edgeTypeDistribution,
    nodeTypeHistogram,
    graphDensity,
    hierarchyDepth,
    avgDegree,
    clusteringCoefficient,
    hasContainment,
    hasProtocols,
    uniqueEdgeTypes,
    uniqueNodeTypes,
    maxChainLength,
    nodeGroups,
  };
}

/**
 * Detect template from graph data. Handles disconnected components.
 * @param {Array} nodes
 * @param {Array} edges
 * @returns {{ template: string, confidence: number, features: object, allScores: object }}
 */
export function detectTemplate(nodes, edges) {
  if (!nodes.length) {
    return { template: 'blank', confidence: 0.5, features: {}, allScores: { blank: 0.15 } };
  }

  const components = _findConnectedComponents(nodes, edges);

  if (components.length <= 1) {
    const F = extractFeatures(nodes, edges);
    const { template, confidence, allScores } = _detectFromFeatures(F, nodes.length);
    return { template, confidence, features: F, allScores };
  }

  // Disconnected: vote weighted by component size and confidence
  const votes = {};
  let combinedFeatures = null;

  for (const { compNodes, compEdges } of components) {
    if (compNodes.length < 3) continue;
    const F = extractFeatures(compNodes, compEdges);
    if (!combinedFeatures) combinedFeatures = F;
    const { template, confidence } = _detectFromFeatures(F, compNodes.length);
    votes[template] = (votes[template] || 0) + compNodes.length * confidence;
  }

  if (!Object.keys(votes).length) {
    const F = extractFeatures(nodes, edges);
    return { template: 'blank', confidence: 0.5, features: F, allScores: { blank: 0.15 } };
  }

  const winner = Object.entries(votes).sort((a, b) => b[1] - a[1])[0];
  const total = Object.values(votes).reduce((s, v) => s + v, 0);
  const F = extractFeatures(nodes, edges);
  const allScores = _computeAllScores(F, nodes.length);

  return {
    template: winner[0],
    confidence: total > 0 ? winner[1] / total : 0.5,
    features: F,
    allScores,
  };
}

// ── Internal helpers ──

function _clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

function _detectFromFeatures(F, nodeCount) {
  const allScores = _computeAllScores(F, nodeCount);

  const sorted = Object.entries(allScores).sort((a, b) => b[1] - a[1]);
  const [winner, winnerScore] = sorted[0];
  const runnerUpScore = sorted[1][1];

  // Tie-break: margin < 0.1 -> blank
  if (winnerScore - runnerUpScore < 0.1) {
    return { template: 'blank', confidence: 0.5, allScores };
  }

  // Low absolute score guard
  if (winnerScore < 0.4) {
    return { template: 'blank', confidence: 0.5, allScores };
  }

  const totalScore = Object.values(allScores).reduce((s, v) => s + v, 0);
  const confidence = totalScore > 0 ? winnerScore / totalScore : 0.5;

  return { template: winner, confidence, allScores };
}

function _computeAllScores(F, nodeCount) {
  return {
    microservices:  _scoreMicroservices(F),
    monolith:       _scoreMonolith(F),
    pipeline:       _scorePipeline(F, nodeCount),
    network:        _scoreNetwork(F),
    hierarchy:      _scoreHierarchy(F),
    layered:        _scoreLayered(F),
    knowledge_graph: _scoreKnowledgeGraph(F),
    blank:          0.15,
  };
}

function _scoreMicroservices(F) {
  let s = 0;
  s += 0.35 * (F.hasProtocols ? 1 : 0);
  s += 0.25 * (F.nodeTypeHistogram.service || 0);
  s += 0.15 * (F.nodeTypeHistogram.api || 0);
  s += 0.10 * (F.nodeTypeHistogram.gateway || 0);
  s += 0.15 * Math.max(0, 1.0 - F.graphDensity / 0.3);
  return _clamp(s, 0, 1);
}

function _scoreMonolith(F) {
  let s = 0;
  s += 0.30 * (F.hasContainment ? 1 : 0);
  s += 0.25 * Math.min(F.hierarchyDepth / 3.0, 1.0);
  s += 0.20 * ((F.nodeTypeHistogram.file || 0) +
               (F.nodeTypeHistogram.class || 0) +
               (F.nodeTypeHistogram.function || 0));
  s += 0.15 * (1.0 - Math.min(F.uniqueNodeTypes / 6.0, 1.0));
  s += 0.10 * Math.min(F.hierarchyDepth / 4.0, 1.0);
  return _clamp(s, 0, 1);
}

function _scorePipeline(F, nodeCount) {
  const chainRatio = F.maxChainLength / Math.max(nodeCount, 1);
  let s = 0;
  s += 0.35 * Math.min(chainRatio / 0.5, 1.0);
  s += 0.25 * ((F.nodeTypeHistogram.stage || 0) +
               (F.nodeTypeHistogram.step || 0) +
               (F.nodeTypeHistogram.transform || 0));
  s += 0.20 * Math.max(0, 1.0 - F.clusteringCoefficient / 0.2);
  s += 0.20 * Math.max(0, 1.0 - F.avgDegree / 3.0);
  return _clamp(s, 0, 1);
}

function _scoreNetwork(F) {
  let s = 0;
  s += 0.30 * Math.min(F.graphDensity / 0.15, 1.0);
  s += 0.25 * ((F.edgeTypeDistribution.CALLS || 0) +
               (F.edgeTypeDistribution.HTTP || 0));
  s += 0.25 * Math.max(0, 1.0 - F.hierarchyDepth / 2.0);
  s += 0.20 * Math.min(F.avgDegree / 4.0, 1.0);
  return _clamp(s, 0, 1);
}

function _scoreHierarchy(F) {
  let s = 0;
  s += 0.35 * Math.min(F.hierarchyDepth / 2.0, 1.0);
  s += 0.30 * (F.edgeTypeDistribution.CONTAINS || 0);
  s += 0.20 * (F.hasContainment ? 1 : 0);
  const treeLike = F.clusteringCoefficient < 0.1 ? 1.0 : 0.5;
  s += 0.15 * treeLike;
  return _clamp(s, 0, 1);
}

function _scoreLayered(F) {
  const layerGroups = new Set(['frontend', 'backend', 'data', 'infra', 'presentation', 'domain', 'persistence']);
  const groupOverlap = F.nodeGroups.size > 0
    ? [...F.nodeGroups].filter(g => layerGroups.has(g)).length / layerGroups.size
    : 0;

  let s = 0;
  s += 0.30 * (F.nodeTypeHistogram.layer || 0);
  s += 0.30 * groupOverlap;
  s += 0.20 * Math.min(F.hierarchyDepth / 2.0, 1.0);
  s += 0.20 * Math.max(0, 1.0 - F.clusteringCoefficient / 0.3);
  return _clamp(s, 0, 1);
}

function _scoreKnowledgeGraph(F) {
  let s = 0;
  s += 0.30 * Math.min(F.uniqueEdgeTypes / 5.0, 1.0);

  const kgEdgeTypes = ['RELATES', 'INFORMS', 'GROUNDS', 'SUPPORTS',
                       'CONTRADICTS', 'DERIVED_FROM', 'VALIDATES'];
  let kgEdges = 0;
  for (const t of kgEdgeTypes) {
    kgEdges += F.edgeTypeDistribution[t] || 0;
  }
  s += 0.30 * Math.min(kgEdges / 0.4, 1.0);
  s += 0.20 * Math.min(F.uniqueNodeTypes / 4.0, 1.0);
  s += 0.20 * Math.min(F.avgDegree / 3.0, 1.0);
  return _clamp(s, 0, 1);
}

// ── Graph algorithms ──

function _maxDepth(nodes) {
  const parentMap = {};
  for (const n of nodes) {
    if (n.parent) parentMap[n.id] = n.parent;
  }
  if (!Object.keys(parentMap).length) return 0;

  // Find roots: nodes that are parents but not children
  const childIds = new Set(Object.keys(parentMap));
  const parentIds = new Set(Object.values(parentMap));
  const roots = [...parentIds].filter(id => !childIds.has(id));
  if (!roots.length) return 1; // Cycle or single-level

  let maxD = 0;
  for (const root of roots) {
    const children = Object.entries(parentMap)
      .filter(([, pid]) => pid === root)
      .map(([nid]) => nid);
    const queue = children.map(c => [c, 1]);

    while (queue.length) {
      const [nid, depth] = queue.shift();
      maxD = Math.max(maxD, depth);
      for (const [cid, pid] of Object.entries(parentMap)) {
        if (pid === nid) queue.push([cid, depth + 1]);
      }
    }
  }
  return maxD;
}

function _transitivity(nodes, edges) {
  // Build adjacency list (directed)
  const adj = {};
  for (const n of nodes) adj[n.id] = new Set();
  for (const e of edges) {
    if (!adj[e.from]) adj[e.from] = new Set();
    adj[e.from].add(e.to);
  }

  let closed = 0;
  let triplets = 0;

  for (const u of Object.keys(adj)) {
    for (const v of adj[u]) {
      const neighborsV = adj[v] || new Set();
      for (const w of neighborsV) {
        if (w !== u) {
          triplets++;
          if (adj[u].has(w)) closed++;
        }
      }
    }
  }

  return triplets > 0 ? closed / triplets : 0;
}

function _approxMaxChainLength(nodes, edges, maxDepthLimit = 50) {
  if (!nodes.length) return 0;

  const adj = {};
  const inDeg = {};
  for (const n of nodes) {
    adj[n.id] = [];
    inDeg[n.id] = 0;
  }
  for (const e of edges) {
    if (!adj[e.from]) adj[e.from] = [];
    adj[e.from].push(e.to);
    inDeg[e.to] = (inDeg[e.to] || 0) + 1;
  }

  // Sources: in-degree 0
  let sources = nodes.filter(n => (inDeg[n.id] || 0) === 0).map(n => n.id);
  if (!sources.length) sources = [nodes[0].id];

  // Limit to 10 sources for large graphs
  const searchSources = sources.slice(0, 10);
  let maxLen = 0;

  for (const src of searchSources) {
    const visited = new Set();
    const stack = [[src, 0]];
    while (stack.length) {
      const [node, depth] = stack.pop();
      if (depth > maxDepthLimit) continue;
      maxLen = Math.max(maxLen, depth);
      visited.add(node);
      for (const neighbor of (adj[node] || [])) {
        if (!visited.has(neighbor)) {
          stack.push([neighbor, depth + 1]);
        }
      }
    }
  }

  return maxLen;
}

function _findConnectedComponents(nodes, edges) {
  // Treat graph as undirected for component detection
  const adj = {};
  for (const n of nodes) adj[n.id] = new Set();
  for (const e of edges) {
    if (!adj[e.from]) adj[e.from] = new Set();
    if (!adj[e.to]) adj[e.to] = new Set();
    adj[e.from].add(e.to);
    adj[e.to].add(e.from);
  }

  const visited = new Set();
  const components = [];

  for (const n of nodes) {
    if (visited.has(n.id)) continue;
    const compNodeIds = new Set();
    const queue = [n.id];
    while (queue.length) {
      const curr = queue.shift();
      if (visited.has(curr)) continue;
      visited.add(curr);
      compNodeIds.add(curr);
      for (const neighbor of (adj[curr] || [])) {
        if (!visited.has(neighbor)) queue.push(neighbor);
      }
    }
    const compNodes = nodes.filter(nd => compNodeIds.has(nd.id));
    const compEdges = edges.filter(e => compNodeIds.has(e.from) && compNodeIds.has(e.to));
    components.push({ compNodes, compEdges });
  }

  return components;
}
