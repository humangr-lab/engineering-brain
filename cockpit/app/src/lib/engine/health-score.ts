/**
 * Code Health Score Engine — composite quality metrics with gamification.
 * Pure engine module (no React dependency).
 *
 * Scoring model inspired by CodeScene, SonarQube CaYC, and CodeClimate:
 *   35% Cognitive Complexity
 *   20% Churn Risk (change frequency × complexity)
 *   15% Duplication (similar-structure detection)
 *   15% Test Coverage proxy (test file presence + assertion density)
 *   10% Structural Health (fan-in/fan-out balance, layering violations)
 *    5% Ownership Clarity (single-owner vs many-hands)
 *
 * All scores normalized to 0–100 (higher = healthier).
 */

import type { Node, Edge } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface HealthScore {
  /** Overall score 0–100 */
  overall: number;
  /** Letter grade A–F */
  grade: HealthGrade;
  /** Per-dimension scores (each 0–100) */
  dimensions: HealthDimensions;
  /** Hotspot nodes (high churn × high complexity) */
  hotspots: Hotspot[];
  /** Achievement badges earned */
  achievements: Achievement[];
  /** Trend direction vs previous snapshot */
  trend: "improving" | "stable" | "declining";
  /** Delta from previous score (-100 to +100) */
  delta: number;
  /** Per-node scores for heatmap overlay */
  nodeScores: Map<string, number>;
}

export type HealthGrade = "A+" | "A" | "B" | "C" | "D" | "F";

export interface HealthDimensions {
  complexity: number;
  churnRisk: number;
  duplication: number;
  coverage: number;
  structure: number;
  ownership: number;
}

export interface Hotspot {
  nodeId: string;
  label: string;
  churn: number;       // 0–1 normalized
  complexity: number;  // 0–1 normalized
  score: number;       // churn × complexity (higher = worse hotspot)
  quadrant: "refactor" | "monitor" | "stable" | "dead";
}

export interface Achievement {
  id: string;
  title: string;
  description: string;
  icon: string;       // emoji
  unlocked: boolean;
  progress: number;    // 0–1
}

// ─── Weights ─────────────────────────────────────────────────────────────────

const WEIGHTS = {
  complexity: 0.35,
  churnRisk: 0.20,
  duplication: 0.15,
  coverage: 0.15,
  structure: 0.10,
  ownership: 0.05,
} as const;

// ─── Grade Thresholds ────────────────────────────────────────────────────────

function toGrade(score: number): HealthGrade {
  if (score >= 95) return "A+";
  if (score >= 80) return "A";
  if (score >= 65) return "B";
  if (score >= 50) return "C";
  if (score >= 35) return "D";
  return "F";
}

// ─── Grade Color (OKLCH for 3D scene) ────────────────────────────────────────

export function gradeColor(grade: HealthGrade): string {
  switch (grade) {
    case "A+": return "oklch(75% 0.22 150)";  // vivid green
    case "A":  return "oklch(72% 0.19 165)";  // emerald
    case "B":  return "oklch(72% 0.15 195)";  // teal
    case "C":  return "oklch(75% 0.18 85)";   // amber
    case "D":  return "oklch(65% 0.20 45)";   // orange
    case "F":  return "oklch(60% 0.22 25)";   // red
  }
}

/** Hex color for use in Canvas/SVG contexts */
export function gradeHex(grade: HealthGrade): string {
  switch (grade) {
    case "A+": return "#22c55e";
    case "A":  return "#10b981";
    case "B":  return "#06b6d4";
    case "C":  return "#f59e0b";
    case "D":  return "#f97316";
    case "F":  return "#ef4444";
  }
}

// ─── Core Scoring ────────────────────────────────────────────────────────────

/** Compute full health score from graph data */
export function computeHealthScore(
  nodes: Node[],
  edges: Edge[],
  previousScore?: number,
): HealthScore {
  if (nodes.length === 0) {
    return emptyScore();
  }

  // Build adjacency for structural analysis
  const inDegree = new Map<string, number>();
  const outDegree = new Map<string, number>();
  for (const n of nodes) {
    inDegree.set(n.id, 0);
    outDegree.set(n.id, 0);
  }
  for (const e of edges) {
    inDegree.set(e.to, (inDegree.get(e.to) ?? 0) + 1);
    outDegree.set(e.from, (outDegree.get(e.from) ?? 0) + 1);
  }

  // 1. Complexity score (inversely proportional to avg edge density)
  const avgDegree = edges.length * 2 / Math.max(nodes.length, 1);
  const complexityRaw = Math.max(0, 100 - avgDegree * 8);
  const complexity = clamp(complexityRaw, 0, 100);

  // 2. Churn risk (based on freshness metadata if available, else estimate from structure)
  const churnRisk = computeChurnRisk(nodes);

  // 3. Duplication (detect near-duplicate node clusters by text similarity)
  const duplication = computeDuplicationScore(nodes);

  // 4. Coverage proxy (presence of test-related nodes)
  const coverage = computeCoverageProxy(nodes, edges);

  // 5. Structural health (fan-in/fan-out balance + layering)
  const structure = computeStructuralHealth(nodes, edges, inDegree, outDegree);

  // 6. Ownership clarity
  const ownership = computeOwnership(nodes);

  // Weighted composite
  const overall = Math.round(
    WEIGHTS.complexity * complexity +
    WEIGHTS.churnRisk * churnRisk +
    WEIGHTS.duplication * duplication +
    WEIGHTS.coverage * coverage +
    WEIGHTS.structure * structure +
    WEIGHTS.ownership * ownership
  );

  const dimensions: HealthDimensions = {
    complexity,
    churnRisk,
    duplication,
    coverage,
    structure,
    ownership,
  };

  // Hotspot analysis
  const hotspots = computeHotspots(nodes, edges, inDegree, outDegree);

  // Per-node scores
  const nodeScores = computeNodeScores(nodes, edges, inDegree, outDegree);

  // Achievements
  const achievements = evaluateAchievements(overall, dimensions, nodes, edges, hotspots);

  // Trend
  const delta = previousScore !== undefined ? overall - previousScore : 0;
  const trend = delta > 2 ? "improving" : delta < -2 ? "declining" : "stable";

  return {
    overall,
    grade: toGrade(overall),
    dimensions,
    hotspots,
    achievements,
    trend,
    delta,
    nodeScores,
  };
}

// ─── Dimension Calculators ───────────────────────────────────────────────────

function computeChurnRisk(nodes: Node[]): number {
  // Use freshness if available, otherwise estimate
  const freshnessValues = nodes
    .map((n) => n.freshness)
    .filter((f): f is number => f !== undefined && f !== null);

  if (freshnessValues.length > 0) {
    const avgFreshness = freshnessValues.reduce((a, b) => a + b, 0) / freshnessValues.length;
    // High freshness = recently changed = higher churn risk
    // Invert: high freshness → lower health score
    return clamp(Math.round((1 - avgFreshness) * 100), 0, 100);
  }

  // Fallback: estimate from node diversity (more diverse types = better organized = less churn)
  const types = new Set(nodes.map((n) => n.type));
  const diversity = types.size / Math.max(nodes.length, 1);
  return clamp(Math.round(50 + diversity * 200), 0, 100);
}

function computeDuplicationScore(nodes: Node[]): number {
  // Detect potential duplicates via normalized text similarity
  const texts = nodes.map((n) => normalizeText(n.text));
  let duplicates = 0;
  const seen = new Map<string, number>();

  for (const text of texts) {
    const key = text.slice(0, 30); // first 30 chars as fingerprint
    seen.set(key, (seen.get(key) ?? 0) + 1);
  }

  for (const count of seen.values()) {
    if (count > 1) duplicates += count - 1;
  }

  const dupRate = duplicates / Math.max(nodes.length, 1);
  // Lower duplication = higher score
  return clamp(Math.round((1 - dupRate) * 100), 0, 100);
}

function computeCoverageProxy(nodes: Node[], _edges: Edge[]): number {
  // Look for test-related nodes
  const testNodes = nodes.filter(
    (n) =>
      n.text.toLowerCase().includes("test") ||
      n.type === "test" ||
      n.id.includes("test") ||
      n.id.includes("spec")
  );

  const codeNodes = nodes.filter(
    (n) =>
      n.type === "module" ||
      n.type === "function" ||
      n.type === "class" ||
      n.type === "component"
  );

  if (codeNodes.length === 0) return 75; // no code nodes = neutral

  const coverageRatio = testNodes.length / codeNodes.length;
  // Ideal: ~0.5 test-to-code ratio
  const normalized = Math.min(coverageRatio / 0.5, 1);
  return clamp(Math.round(normalized * 100), 0, 100);
}

function computeStructuralHealth(
  nodes: Node[],
  _edges: Edge[],
  inDegree: Map<string, number>,
  outDegree: Map<string, number>,
): number {
  if (nodes.length === 0) return 75;

  // Fan-in/fan-out balance: penalize extreme imbalance
  let balanceScore = 0;
  let count = 0;

  for (const node of nodes) {
    const fanIn = inDegree.get(node.id) ?? 0;
    const fanOut = outDegree.get(node.id) ?? 0;
    const total = fanIn + fanOut;
    if (total === 0) continue;

    // Ideal balance: neither too many incoming nor outgoing
    const ratio = Math.min(fanIn, fanOut) / Math.max(fanIn, fanOut, 1);
    balanceScore += ratio;
    count++;
  }

  const avgBalance = count > 0 ? balanceScore / count : 0.5;

  // Layer utilization: check if nodes use multiple layers
  const layers = new Set(nodes.map((n) => n.layer));
  const layerBonus = Math.min(layers.size / 4, 1) * 20; // up to 20 bonus for good layering

  return clamp(Math.round(avgBalance * 80 + layerBonus), 0, 100);
}

function computeOwnership(nodes: Node[]): number {
  // Check metadata for author information
  const authors = new Set<string>();
  for (const n of nodes) {
    const author = n.metadata?.author as string | undefined;
    if (author) authors.add(author);
  }

  if (authors.size === 0) return 60; // unknown = neutral-ish

  // Clear ownership (1–3 authors) is healthier than too many
  if (authors.size <= 3) return 90;
  if (authors.size <= 6) return 75;
  if (authors.size <= 10) return 60;
  return 45;
}

// ─── Hotspot Detection ───────────────────────────────────────────────────────

function computeHotspots(
  nodes: Node[],
  _edges: Edge[],
  inDegree: Map<string, number>,
  outDegree: Map<string, number>,
): Hotspot[] {
  const maxDegree = Math.max(
    1,
    ...Array.from(inDegree.values()),
    ...Array.from(outDegree.values()),
  );

  const hotspots: Hotspot[] = nodes.map((node) => {
    const fanIn = inDegree.get(node.id) ?? 0;
    const fanOut = outDegree.get(node.id) ?? 0;
    const totalDegree = fanIn + fanOut;

    // Complexity proxy: degree centrality + type weight
    const typeWeight = node.type === "module" ? 1.2 : node.type === "class" ? 1.1 : 1.0;
    const complexityNorm = clamp((totalDegree / maxDegree) * typeWeight, 0, 1);

    // Churn proxy: freshness (1 = just changed, 0 = stable)
    const churnNorm = node.freshness ?? 0.3;

    // Hotspot score = churn × complexity (CodeScene model)
    const score = churnNorm * complexityNorm;

    // Quadrant classification
    let quadrant: Hotspot["quadrant"];
    if (churnNorm > 0.5 && complexityNorm > 0.5) quadrant = "refactor";
    else if (churnNorm > 0.5 && complexityNorm <= 0.5) quadrant = "monitor";
    else if (churnNorm <= 0.5 && complexityNorm > 0.5) quadrant = "dead";
    else quadrant = "stable";

    return {
      nodeId: node.id,
      label: node.text,
      churn: churnNorm,
      complexity: complexityNorm,
      score,
      quadrant,
    };
  });

  // Sort by hotspot score descending, return top 20
  return hotspots
    .sort((a, b) => b.score - a.score)
    .slice(0, 20);
}

// ─── Per-Node Scores ─────────────────────────────────────────────────────────

function computeNodeScores(
  nodes: Node[],
  _edges: Edge[],
  inDegree: Map<string, number>,
  outDegree: Map<string, number>,
): Map<string, number> {
  const scores = new Map<string, number>();
  for (const node of nodes) {
    const fanIn = inDegree.get(node.id) ?? 0;
    const fanOut = outDegree.get(node.id) ?? 0;

    // Node health: balanced connections, good confidence, reasonable freshness
    const degreeBalance = 1 - Math.abs(fanIn - fanOut) / (Math.max(fanIn, fanOut, 1) * 2);
    const confidence = node.confidence ?? 0.5;
    const freshness = 1 - (node.freshness ?? 0.3);

    const nodeScore = Math.round(
      degreeBalance * 30 + confidence * 40 + freshness * 30
    );
    scores.set(node.id, clamp(nodeScore, 0, 100));
  }

  return scores;
}

// ─── Achievements (Gamification) ─────────────────────────────────────────────

const ACHIEVEMENT_DEFS = [
  {
    id: "first_scan",
    title: "First Scan",
    description: "Analyzed your first codebase",
    icon: "🔍",
    check: () => true,
    progress: () => 1,
  },
  {
    id: "clean_code",
    title: "Clean Code",
    description: "Overall health score above 80",
    icon: "✨",
    check: (score: number) => score >= 80,
    progress: (score: number) => Math.min(score / 80, 1),
  },
  {
    id: "pristine",
    title: "Pristine",
    description: "Overall health score above 95 (A+ grade)",
    icon: "💎",
    check: (score: number) => score >= 95,
    progress: (score: number) => Math.min(score / 95, 1),
  },
  {
    id: "zero_hotspots",
    title: "Zero Hotspots",
    description: "No refactor-quadrant hotspots",
    icon: "🧊",
    check: (_: number, __: HealthDimensions, ___: Node[], ____: Edge[], hotspots: Hotspot[]) =>
      hotspots.filter((h) => h.quadrant === "refactor").length === 0,
    progress: (_: number, __: HealthDimensions, ___: Node[], ____: Edge[], hotspots: Hotspot[]) => {
      const refactors = hotspots.filter((h) => h.quadrant === "refactor").length;
      return refactors === 0 ? 1 : Math.max(0, 1 - refactors / 10);
    },
  },
  {
    id: "well_tested",
    title: "Well Tested",
    description: "Test coverage proxy above 75",
    icon: "🧪",
    check: (_: number, dims: HealthDimensions) => dims.coverage >= 75,
    progress: (_: number, dims: HealthDimensions) => Math.min(dims.coverage / 75, 1),
  },
  {
    id: "layered",
    title: "Well Layered",
    description: "Structural health above 80",
    icon: "🏗️",
    check: (_: number, dims: HealthDimensions) => dims.structure >= 80,
    progress: (_: number, dims: HealthDimensions) => Math.min(dims.structure / 80, 1),
  },
  {
    id: "big_codebase",
    title: "Enterprise Scale",
    description: "Analyzed 1000+ nodes",
    icon: "🏢",
    check: (_: number, __: HealthDimensions, nodes: Node[]) => nodes.length >= 1000,
    progress: (_: number, __: HealthDimensions, nodes: Node[]) => Math.min(nodes.length / 1000, 1),
  },
  {
    id: "connected",
    title: "Fully Connected",
    description: "Every node has at least one edge",
    icon: "🔗",
    check: (_: number, __: HealthDimensions, nodes: Node[], edges: Edge[]) => {
      const connected = new Set<string>();
      for (const e of edges) {
        connected.add(e.from);
        connected.add(e.to);
      }
      return nodes.every((n) => connected.has(n.id));
    },
    progress: (_: number, __: HealthDimensions, nodes: Node[], edges: Edge[]) => {
      const connected = new Set<string>();
      for (const e of edges) {
        connected.add(e.from);
        connected.add(e.to);
      }
      return nodes.length > 0 ? connected.size / nodes.length : 0;
    },
  },
] as const;

function evaluateAchievements(
  overall: number,
  dimensions: HealthDimensions,
  nodes: Node[],
  edges: Edge[],
  hotspots: Hotspot[],
): Achievement[] {
  return ACHIEVEMENT_DEFS.map((def) => ({
    id: def.id,
    title: def.title,
    description: def.description,
    icon: def.icon,
    unlocked: def.check(overall, dimensions, nodes, edges, hotspots),
    progress: def.progress(overall, dimensions, nodes, edges, hotspots),
  }));
}

// ─── Sparkline Data ──────────────────────────────────────────────────────────

export interface SparklinePoint {
  timestamp: number;
  score: number;
}

/** Generate sparkline data from score history (stored in localStorage) */
export function getScoreHistory(projectId: string): SparklinePoint[] {
  try {
    const raw = localStorage.getItem(`ontology-health-history:${projectId}`);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/** Append a score to history */
export function appendScoreHistory(
  projectId: string,
  score: number,
  maxPoints = 30,
): void {
  const history = getScoreHistory(projectId);
  history.push({ timestamp: Date.now(), score });
  // Keep last N points
  const trimmed = history.slice(-maxPoints);
  try {
    localStorage.setItem(
      `ontology-health-history:${projectId}`,
      JSON.stringify(trimmed),
    );
  } catch {
    // localStorage full — ignore
  }
}

// ─── Badge SVG Generation ────────────────────────────────────────────────────

/** Generate a shields.io-compatible SVG badge */
export function generateBadgeSvg(score: number, grade: HealthGrade): string {
  const color = gradeHex(grade).replace("#", "");
  const label = "health";
  const message = `${grade} (${score})`;
  const labelWidth = label.length * 7 + 10;
  const messageWidth = message.length * 7 + 10;
  const totalWidth = labelWidth + messageWidth;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${totalWidth}" height="20" role="img" aria-label="${label}: ${message}">
  <title>${label}: ${message}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="${totalWidth}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="${labelWidth}" height="20" fill="#555"/>
    <rect x="${labelWidth}" width="${messageWidth}" height="20" fill="#${color}"/>
    <rect width="${totalWidth}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="11">
    <text x="${labelWidth / 2}" y="14" fill="#010101" fill-opacity=".3">${label}</text>
    <text x="${labelWidth / 2}" y="13">${label}</text>
    <text x="${labelWidth + messageWidth / 2}" y="14" fill="#010101" fill-opacity=".3">${message}</text>
    <text x="${labelWidth + messageWidth / 2}" y="13">${message}</text>
  </g>
</svg>`;
}

// ─── Utilities ───────────────────────────────────────────────────────────────

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function normalizeText(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function emptyScore(): HealthScore {
  return {
    overall: 0,
    grade: "F",
    dimensions: {
      complexity: 0,
      churnRisk: 0,
      duplication: 0,
      coverage: 0,
      structure: 0,
      ownership: 0,
    },
    hotspots: [],
    achievements: [],
    trend: "stable",
    delta: 0,
    nodeScores: new Map(),
  };
}
