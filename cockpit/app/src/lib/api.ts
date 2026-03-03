import { invoke } from "@tauri-apps/api/core";

// ─── Types (mirror Rust structs — camelCase from serde rename_all) ────────────

export interface EdgeRef {
  nodeId: string;
  type: string;
}

export interface Opinion {
  b: number;
  d: number;
  u: number;
  a: number;
}

export interface Node {
  id: string;
  type: string;
  layer: number;
  layerName: string;
  text: string;
  severity: string;
  confidence: number;
  technologies: string[];
  domains: string[];
  outEdges: EdgeRef[];
  inEdges: EdgeRef[];
  why?: string;
  howTo?: string;
  whenToUse?: string;
  opinion?: Opinion;
  epistemicStatus?: string;
  freshness?: number;
  metadata: Record<string, unknown>;
}

export interface Edge {
  from: string;
  to: string;
  type: string;
  weight?: number;
  edgeAlpha?: number;
  edgeBeta?: number;
  edgeConfidence?: number;
}

export interface LayerCount {
  layer: number;
  name: string;
  count: number;
}

export interface Stats {
  nodeCount: number;
  edgeCount: number;
  layerCounts: LayerCount[];
  version: number;
  technologies: string[];
  domains: string[];
}

export interface GraphSnapshot {
  nodes: Node[];
  edges: Edge[];
  version: number;
  stats: Stats;
}

export interface EpistemicStats {
  totalNodes: number;
  byStatus: { status: string; count: number }[];
  avgConfidence: number;
  atRiskCount: number;
}

export interface ReloadStatus {
  isReloading: boolean;
  reloadCount: number;
  lastError: string | null;
  lastDurationMs: number | null;
  seedsDir: string | null;
  watchedFiles: number;
}

// ─── Graph Queries ───────────────────────────────────────────────────────────

export async function getGraph(): Promise<GraphSnapshot> {
  return invoke<GraphSnapshot>("get_graph");
}

export async function getGraphVersion(): Promise<number> {
  return invoke<number>("get_graph_version");
}

export async function getStats(): Promise<Stats> {
  return invoke<Stats>("get_stats");
}

// ─── Node Queries ────────────────────────────────────────────────────────────

export async function getNodes(params?: {
  layer?: number;
  severity?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<Node[]> {
  return invoke<Node[]>("get_nodes", params);
}

export async function getNode(id: string): Promise<Node | null> {
  return invoke<Node | null>("get_node", { id });
}

// ─── Edge Queries ────────────────────────────────────────────────────────────

export async function getEdges(params?: {
  nodeId?: string;
  edgeType?: string;
}): Promise<Edge[]> {
  return invoke<Edge[]>("get_edges", params);
}

// ─── Epistemic Queries ───────────────────────────────────────────────────────

export async function getEpistemicStats(): Promise<EpistemicStats> {
  return invoke<EpistemicStats>("get_epistemic_stats");
}

export async function getAtRiskNodes(horizonDays?: number): Promise<Node[]> {
  return invoke<Node[]>("get_at_risk_nodes", { horizonDays });
}

// ─── Admin ───────────────────────────────────────────────────────────────────

export async function triggerReload(): Promise<string> {
  return invoke<string>("trigger_reload");
}

export async function getReloadStatus(): Promise<ReloadStatus> {
  return invoke<ReloadStatus>("get_reload_status");
}

// ─── Git ─────────────────────────────────────────────────────────────────────

export interface GitCommit {
  hash: string;
  shortHash: string;
  author: string;
  date: string;
  message: string;
  changedFiles: string[];
}

export async function getGitLog(
  path: string,
  maxCommits?: number,
): Promise<GitCommit[]> {
  return invoke<GitCommit[]>("get_git_log", { path, maxCommits });
}

export async function getChangedFiles(path: string): Promise<string[]> {
  return invoke<string[]>("get_changed_files", { path });
}

// ─── Health Score ─────────────────────────────────────────────────────────────

export interface HealthScoreResult {
  nodeCount: number;
  edgeCount: number;
  avgConfidence: number;
  layerCount: number;
  connectivityRatio: number;
}

export async function getHealthScore(): Promise<HealthScoreResult> {
  return invoke<HealthScoreResult>("get_health_score");
}

// ─── Project ─────────────────────────────────────────────────────────────────

export async function openProject(path: string): Promise<GraphSnapshot> {
  return invoke<GraphSnapshot>("open_project", { path });
}

// ─── Analyze Project (graph_data.json format for inference engine) ───────

export interface GraphDataNode {
  id: string;
  label?: string;
  type?: string;
  group?: string;
  parent?: string;
  properties?: {
    loc?: number;
    complexity?: number;
    x?: number;
    z?: number;
    subtitle?: string;
    hero?: boolean;
    auto?: boolean;
    description?: string;
    language?: string;
    path?: string;
  };
}

export interface GraphDataEdge {
  from: string;
  to: string;
  type?: string;
  properties?: {
    weight?: number;
    confidence?: number;
    color?: string;
    label?: string;
  };
}

export interface GraphData {
  nodes: GraphDataNode[];
  edges: GraphDataEdge[];
  metadata?: {
    name?: string;
    version?: string;
    generated_at?: string;
    generator?: string;
  };
}

export async function analyzeProject(path: string): Promise<GraphData> {
  return invoke<GraphData>("analyze_project", { path });
}
