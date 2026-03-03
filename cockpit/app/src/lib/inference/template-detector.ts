/* ====== TEMPLATE DETECTOR -- Stage 1 of inference pipeline ======
   Extracts structural features from graph, scores 8 candidate templates.
   Deterministic: same input always produces same output.            */

import type { GraphDataNode } from "@/lib/api";

// ── Types ──

export interface NormalizedEdge {
  from: string;
  to: string;
  type?: string;
  properties: Record<string, unknown>;
}

export interface Features {
  edgeTypeDistribution: Record<string, number>;
  nodeTypeHistogram: Record<string, number>;
  graphDensity: number;
  hierarchyDepth: number;
  avgDegree: number;
  clusteringCoefficient: number;
  hasContainment: boolean;
  hasProtocols: boolean;
  uniqueEdgeTypes: number;
  uniqueNodeTypes: number;
  maxChainLength: number;
  nodeGroups: Set<string>;
}

export type TemplateName =
  | "microservices"
  | "monolith"
  | "pipeline"
  | "network"
  | "hierarchy"
  | "layered"
  | "knowledge_graph"
  | "blank";

export interface TemplateResult {
  template: TemplateName;
  confidence: number;
  features: Features | Record<string, never>;
  allScores: Record<string, number>;
}

// ── Public API ──

export function extractFeatures(
  nodes: GraphDataNode[],
  edges: NormalizedEdge[],
): Features {
  const N = nodes.length;
  const E = edges.length;

  const effectiveEdges = edges.filter((e) => e.from !== e.to);

  // Edge type distribution
  const edgeTypeCounts: Record<string, number> = {};
  for (const e of edges) {
    const t = e.type || "UNKNOWN";
    edgeTypeCounts[t] = (edgeTypeCounts[t] || 0) + 1;
  }
  const edgeTypeDistribution: Record<string, number> = {};
  for (const [t, c] of Object.entries(edgeTypeCounts)) {
    edgeTypeDistribution[t] = E > 0 ? c / E : 0;
  }

  // Node type histogram
  const nodeTypeCounts: Record<string, number> = {};
  for (const n of nodes) {
    const t = (n.type || "").toLowerCase();
    if (t) nodeTypeCounts[t] = (nodeTypeCounts[t] || 0) + 1;
  }
  const nodeTypeHistogram: Record<string, number> = {};
  for (const [t, c] of Object.entries(nodeTypeCounts)) {
    nodeTypeHistogram[t] = N > 0 ? c / N : 0;
  }

  // Graph density (directed)
  const graphDensity = N > 1 ? effectiveEdges.length / (N * (N - 1)) : 0;

  // Hierarchy depth
  const hierarchyDepth = maxDepth(nodes);

  // Degree computation
  const inDeg: Record<string, number> = {};
  const outDeg: Record<string, number> = {};
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

  // Clustering coefficient
  const clusteringCoefficient = transitivity(nodes, effectiveEdges);

  // Containment detection
  const hasContainment =
    edges.some((e) => e.type === "CONTAINS") ||
    nodes.some((n) => n.parent);

  // Protocol detection
  const protocolTypes = new Set([
    "HTTP",
    "GRPC",
    "AMQP",
    "MQTT",
    "REST",
    "WEBSOCKET",
  ]);
  const hasProtocols = edges.some(
    (e) => e.type != null && protocolTypes.has(e.type.toUpperCase()),
  );

  // Unique type counts
  const uniqueEdgeTypes = new Set(
    edges.filter((e) => e.type).map((e) => e.type),
  ).size;
  const uniqueNodeTypes = new Set(
    nodes.filter((n) => n.type).map((n) => n.type),
  ).size;

  // Max chain length
  const maxChainLength = approxMaxChainLength(nodes, effectiveEdges);

  // Node groups
  const nodeGroups = new Set<string>();
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

export function detectTemplate(
  nodes: GraphDataNode[],
  edges: NormalizedEdge[],
): TemplateResult {
  if (!nodes.length) {
    return {
      template: "blank",
      confidence: 0.5,
      features: {},
      allScores: { blank: 0.15 },
    };
  }

  const components = findConnectedComponents(nodes, edges);

  if (components.length <= 1) {
    const F = extractFeatures(nodes, edges);
    const { template, confidence, allScores } = detectFromFeatures(
      F,
      nodes.length,
    );
    return { template, confidence, features: F, allScores };
  }

  // Disconnected: vote weighted by component size and confidence
  const votes: Record<string, number> = {};

  for (const { compNodes, compEdges } of components) {
    if (compNodes.length < 3) continue;
    const F = extractFeatures(compNodes, compEdges);
    const { template, confidence } = detectFromFeatures(F, compNodes.length);
    votes[template] = (votes[template] || 0) + compNodes.length * confidence;
  }

  if (!Object.keys(votes).length) {
    const F = extractFeatures(nodes, edges);
    return {
      template: "blank",
      confidence: 0.5,
      features: F,
      allScores: { blank: 0.15 },
    };
  }

  const winner = Object.entries(votes).sort((a, b) => b[1] - a[1])[0];
  const total = Object.values(votes).reduce((s, v) => s + v, 0);
  const F = extractFeatures(nodes, edges);
  const allScores = computeAllScores(F, nodes.length);

  return {
    template: winner[0] as TemplateName,
    confidence: total > 0 ? winner[1] / total : 0.5,
    features: F,
    allScores,
  };
}

// ── Internal helpers ──

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function detectFromFeatures(
  F: Features,
  nodeCount: number,
): { template: TemplateName; confidence: number; allScores: Record<string, number> } {
  const allScores = computeAllScores(F, nodeCount);
  const sorted = Object.entries(allScores).sort((a, b) => b[1] - a[1]);
  const [winner, winnerScore] = sorted[0];
  const runnerUpScore = sorted[1][1];

  if (winnerScore - runnerUpScore < 0.1) {
    return { template: "blank", confidence: 0.5, allScores };
  }
  if (winnerScore < 0.4) {
    return { template: "blank", confidence: 0.5, allScores };
  }

  const totalScore = Object.values(allScores).reduce((s, v) => s + v, 0);
  const confidence = totalScore > 0 ? winnerScore / totalScore : 0.5;

  return { template: winner as TemplateName, confidence, allScores };
}

function computeAllScores(
  F: Features,
  nodeCount: number,
): Record<string, number> {
  return {
    microservices: scoreMicroservices(F),
    monolith: scoreMonolith(F),
    pipeline: scorePipeline(F, nodeCount),
    network: scoreNetwork(F),
    hierarchy: scoreHierarchy(F),
    layered: scoreLayered(F),
    knowledge_graph: scoreKnowledgeGraph(F),
    blank: 0.15,
  };
}

function scoreMicroservices(F: Features): number {
  let s = 0;
  s += 0.35 * (F.hasProtocols ? 1 : 0);
  s += 0.25 * (F.nodeTypeHistogram.service || 0);
  s += 0.15 * (F.nodeTypeHistogram.api || 0);
  s += 0.1 * (F.nodeTypeHistogram.gateway || 0);
  s += 0.15 * Math.max(0, 1.0 - F.graphDensity / 0.3);
  return clamp(s, 0, 1);
}

function scoreMonolith(F: Features): number {
  let s = 0;
  s += 0.3 * (F.hasContainment ? 1 : 0);
  s += 0.25 * Math.min(F.hierarchyDepth / 3.0, 1.0);
  s +=
    0.2 *
    ((F.nodeTypeHistogram.file || 0) +
      (F.nodeTypeHistogram.class || 0) +
      (F.nodeTypeHistogram.function || 0));
  s += 0.15 * (1.0 - Math.min(F.uniqueNodeTypes / 6.0, 1.0));
  s += 0.1 * Math.min(F.hierarchyDepth / 4.0, 1.0);
  return clamp(s, 0, 1);
}

function scorePipeline(F: Features, nodeCount: number): number {
  const chainRatio = F.maxChainLength / Math.max(nodeCount, 1);
  let s = 0;
  s += 0.35 * Math.min(chainRatio / 0.5, 1.0);
  s +=
    0.25 *
    ((F.nodeTypeHistogram.stage || 0) +
      (F.nodeTypeHistogram.step || 0) +
      (F.nodeTypeHistogram.transform || 0));
  s += 0.2 * Math.max(0, 1.0 - F.clusteringCoefficient / 0.2);
  s += 0.2 * Math.max(0, 1.0 - F.avgDegree / 3.0);
  return clamp(s, 0, 1);
}

function scoreNetwork(F: Features): number {
  let s = 0;
  s += 0.3 * Math.min(F.graphDensity / 0.15, 1.0);
  s +=
    0.25 *
    ((F.edgeTypeDistribution.CALLS || 0) +
      (F.edgeTypeDistribution.HTTP || 0));
  s += 0.25 * Math.max(0, 1.0 - F.hierarchyDepth / 2.0);
  s += 0.2 * Math.min(F.avgDegree / 4.0, 1.0);
  return clamp(s, 0, 1);
}

function scoreHierarchy(F: Features): number {
  let s = 0;
  s += 0.35 * Math.min(F.hierarchyDepth / 2.0, 1.0);
  s += 0.3 * (F.edgeTypeDistribution.CONTAINS || 0);
  s += 0.2 * (F.hasContainment ? 1 : 0);
  const treeLike = F.clusteringCoefficient < 0.1 ? 1.0 : 0.5;
  s += 0.15 * treeLike;
  return clamp(s, 0, 1);
}

function scoreLayered(F: Features): number {
  const layerGroups = new Set([
    "frontend",
    "backend",
    "data",
    "infra",
    "presentation",
    "domain",
    "persistence",
  ]);
  const groupOverlap =
    F.nodeGroups.size > 0
      ? [...F.nodeGroups].filter((g) => layerGroups.has(g)).length /
        layerGroups.size
      : 0;

  let s = 0;
  s += 0.3 * (F.nodeTypeHistogram.layer || 0);
  s += 0.3 * groupOverlap;
  s += 0.2 * Math.min(F.hierarchyDepth / 2.0, 1.0);
  s += 0.2 * Math.max(0, 1.0 - F.clusteringCoefficient / 0.3);
  return clamp(s, 0, 1);
}

function scoreKnowledgeGraph(F: Features): number {
  let s = 0;
  s += 0.3 * Math.min(F.uniqueEdgeTypes / 5.0, 1.0);

  const kgEdgeTypes = [
    "RELATES",
    "INFORMS",
    "GROUNDS",
    "SUPPORTS",
    "CONTRADICTS",
    "DERIVED_FROM",
    "VALIDATES",
  ];
  let kgEdges = 0;
  for (const t of kgEdgeTypes) {
    kgEdges += F.edgeTypeDistribution[t] || 0;
  }
  s += 0.3 * Math.min(kgEdges / 0.4, 1.0);
  s += 0.2 * Math.min(F.uniqueNodeTypes / 4.0, 1.0);
  s += 0.2 * Math.min(F.avgDegree / 3.0, 1.0);
  return clamp(s, 0, 1);
}

// ── Graph algorithms ──

function maxDepth(nodes: GraphDataNode[]): number {
  const parentMap: Record<string, string> = {};
  for (const n of nodes) {
    if (n.parent) parentMap[n.id] = n.parent;
  }
  if (!Object.keys(parentMap).length) return 0;

  const childIds = new Set(Object.keys(parentMap));
  const parentIds = new Set(Object.values(parentMap));
  const roots = [...parentIds].filter((id) => !childIds.has(id));
  if (!roots.length) return 1;

  // Pre-build parent → children index (avoids O(N^2) linear scan per BFS step)
  const childrenOf: Record<string, string[]> = {};
  for (const [childId, pid] of Object.entries(parentMap)) {
    if (!childrenOf[pid]) childrenOf[pid] = [];
    childrenOf[pid].push(childId);
  }

  let maxD = 0;
  for (const root of roots) {
    const kids = childrenOf[root] || [];
    const queue: [string, number][] = kids.map((c) => [c, 1]);
    const visited = new Set<string>([root]);

    while (queue.length) {
      const [nid, depth] = queue.shift()!;
      if (visited.has(nid)) continue; // break cycles
      visited.add(nid);
      maxD = Math.max(maxD, depth);
      for (const cid of childrenOf[nid] || []) {
        if (!visited.has(cid)) queue.push([cid, depth + 1]);
      }
    }
  }
  return maxD;
}

function transitivity(
  nodes: GraphDataNode[],
  edges: NormalizedEdge[],
): number {
  const adj: Record<string, Set<string>> = {};
  for (const n of nodes) adj[n.id] = new Set();
  for (const e of edges) {
    if (!adj[e.from]) adj[e.from] = new Set();
    adj[e.from].add(e.to);
  }

  let closed = 0;
  let triplets = 0;

  for (const u of Object.keys(adj)) {
    for (const v of adj[u]) {
      const neighborsV = adj[v] || new Set<string>();
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

function approxMaxChainLength(
  nodes: GraphDataNode[],
  edges: NormalizedEdge[],
  maxDepthLimit = 50,
): number {
  if (!nodes.length) return 0;

  const adj: Record<string, string[]> = {};
  const inDeg: Record<string, number> = {};
  for (const n of nodes) {
    adj[n.id] = [];
    inDeg[n.id] = 0;
  }
  for (const e of edges) {
    if (!adj[e.from]) adj[e.from] = [];
    adj[e.from].push(e.to);
    inDeg[e.to] = (inDeg[e.to] || 0) + 1;
  }

  let sources = nodes
    .filter((n) => (inDeg[n.id] || 0) === 0)
    .map((n) => n.id);
  if (!sources.length) sources = [nodes[0].id];

  const searchSources = sources.slice(0, 10);
  let maxLen = 0;

  for (const src of searchSources) {
    const visited = new Set<string>();
    const stack: [string, number][] = [[src, 0]];
    while (stack.length) {
      const [node, depth] = stack.pop()!;
      if (depth > maxDepthLimit) continue;
      maxLen = Math.max(maxLen, depth);
      visited.add(node);
      for (const neighbor of adj[node] || []) {
        if (!visited.has(neighbor)) {
          stack.push([neighbor, depth + 1]);
        }
      }
    }
  }

  return maxLen;
}

function findConnectedComponents(
  nodes: GraphDataNode[],
  edges: NormalizedEdge[],
): { compNodes: GraphDataNode[]; compEdges: NormalizedEdge[] }[] {
  const adj: Record<string, Set<string>> = {};
  for (const n of nodes) adj[n.id] = new Set();
  for (const e of edges) {
    if (!adj[e.from]) adj[e.from] = new Set();
    if (!adj[e.to]) adj[e.to] = new Set();
    adj[e.from].add(e.to);
    adj[e.to].add(e.from);
  }

  const visited = new Set<string>();
  const components: { compNodes: GraphDataNode[]; compEdges: NormalizedEdge[] }[] = [];

  for (const n of nodes) {
    if (visited.has(n.id)) continue;
    const compNodeIds = new Set<string>();
    const queue = [n.id];
    while (queue.length) {
      const curr = queue.shift()!;
      if (visited.has(curr)) continue;
      visited.add(curr);
      compNodeIds.add(curr);
      for (const neighbor of adj[curr] || []) {
        if (!visited.has(neighbor)) queue.push(neighbor);
      }
    }
    const compNodes = nodes.filter((nd) => compNodeIds.has(nd.id));
    const compEdges = edges.filter(
      (e) => compNodeIds.has(e.from) && compNodeIds.has(e.to),
    );
    components.push({ compNodes, compEdges });
  }

  return components;
}
