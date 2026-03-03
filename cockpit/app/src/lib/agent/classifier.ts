/**
 * LLM Node Classifier — enhances graph nodes with semantic metadata.
 *
 * Uses the existing BYOK provider (Anthropic/OpenAI) to batch-classify nodes,
 * adding richer types, groups, subtitles, and descriptions.
 *
 * Runs entirely in-browser via direct API calls. No server needed.
 * Falls back gracefully when no API key is configured.
 */

import {
  initProvider,
  isConfigured,
  getProvider,
  type ProviderName,
} from "./provider";
import type { GraphData, GraphDataNode } from "@/lib/api";

// ── Types ──

export interface ClassifiedNode {
  id: string;
  enhancedType?: string;
  group?: string;
  subtitle?: string;
  description?: string;
  shape?: string;
}

export interface ClassificationResult {
  nodes: ClassifiedNode[];
  classified: number;
  skipped: number;
  error?: string;
}

interface ClassifierOptions {
  batchSize?: number;
  onProgress?: (done: number, total: number) => void;
  signal?: AbortSignal;
}

// ── Storage keys ──

const ENRICHMENT_KEY = "ontology-map-enrichment-enabled";
const STORAGE_KEY = "ontology-map-api-key";
const STORAGE_PROVIDER = "ontology-map-provider";

// ── Settings helpers ──

export function isEnrichmentEnabled(): boolean {
  try {
    return localStorage.getItem(ENRICHMENT_KEY) === "true";
  } catch {
    return false;
  }
}

export function setEnrichmentEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(ENRICHMENT_KEY, enabled ? "true" : "false");
  } catch {
    // localStorage unavailable
  }
}

export function getStoredProvider(): ProviderName | null {
  try {
    return localStorage.getItem(STORAGE_PROVIDER) as ProviderName | null;
  } catch {
    return null;
  }
}

export function getStoredMaskedKey(): string | null {
  try {
    const key = localStorage.getItem(STORAGE_KEY);
    if (!key) return null;
    if (key.length < 12) return "****";
    return key.slice(0, 5) + "..." + key.slice(-4);
  } catch {
    return null;
  }
}

// ── Classification ──

const BATCH_SIZE = 20;

const CLASSIFICATION_PROMPT = `You are a software architecture classifier. Given a list of code elements from a project, classify each one.

For each node, provide:
- enhancedType: a more specific type (e.g., "REST Controller", "ORM Model", "Config Module", "Test Suite", "Utility Library")
- group: semantic grouping (e.g., "api", "data", "auth", "config", "testing", "ui", "core", "infrastructure")
- subtitle: a one-line description (5-10 words)
- description: a brief explanation (1-2 sentences)
- shape: the best 3D shape from this list: warehouse, factory, satellite, terminal, monument, pillars, gear, gate, database, hourglass, brain, dyson_book, gauge, hub, tree, sphere, prism, stairs, nexus, graph, dial, vault, screens, rack, conveyor, monitor

Respond with a JSON array. Each item must have "id" matching the input node ID.

Example response:
[
  {"id": "src.models.user", "enhancedType": "ORM Model", "group": "data", "subtitle": "User data model", "description": "SQLAlchemy model for user accounts with auth fields.", "shape": "database"},
  {"id": "src.api.routes", "enhancedType": "REST Controller", "group": "api", "subtitle": "API route definitions", "description": "FastAPI router with CRUD endpoints for the main resources.", "shape": "gate"}
]

ONLY output the JSON array. No markdown, no explanation.`;

/**
 * Classify graph nodes using the configured LLM provider.
 * Returns enriched metadata for each node.
 *
 * Gracefully returns empty result when:
 * - No API key configured
 * - Enrichment disabled
 * - API error (partial results returned)
 */
export async function classifyNodes(
  graphData: GraphData,
  options: ClassifierOptions = {},
): Promise<ClassificationResult> {
  initProvider();

  if (!isConfigured() || !isEnrichmentEnabled()) {
    return { nodes: [], classified: 0, skipped: graphData.nodes.length };
  }

  const { batchSize = BATCH_SIZE, onProgress, signal } = options;
  const allNodes = graphData.nodes;
  const results: ClassifiedNode[] = [];
  let errors = 0;

  // Process in batches
  for (let i = 0; i < allNodes.length; i += batchSize) {
    if (signal?.aborted) break;

    const batch = allNodes.slice(i, i + batchSize);
    try {
      const classified = await classifyBatch(batch, signal);
      results.push(...classified);
    } catch {
      errors += batch.length;
    }

    onProgress?.(Math.min(i + batchSize, allNodes.length), allNodes.length);
  }

  return {
    nodes: results,
    classified: results.length,
    skipped: allNodes.length - results.length,
    error: errors > 0 ? `${errors} nodes failed classification` : undefined,
  };
}

async function classifyBatch(
  nodes: GraphDataNode[],
  signal?: AbortSignal,
): Promise<ClassifiedNode[]> {
  const provider = getProvider();
  if (!provider) return [];

  const nodesPayload = nodes.map((n) => ({
    id: n.id,
    label: n.label || n.id,
    type: n.type || "unknown",
    path: n.properties?.path || "",
    language: n.properties?.language || "",
    loc: n.properties?.loc || 0,
  }));

  const userMessage = `Classify these ${nodes.length} code elements:\n\n${JSON.stringify(nodesPayload, null, 2)}`;

  let apiKey: string | null = null;
  try {
    apiKey = localStorage.getItem(STORAGE_KEY);
  } catch {
    return [];
  }
  if (!apiKey) return [];

  const responseText = await callLLM(provider, apiKey, userMessage, signal);
  return parseClassificationResponse(responseText, nodes);
}

async function callLLM(
  provider: ProviderName,
  apiKey: string,
  userMessage: string,
  signal?: AbortSignal,
): Promise<string> {
  if (provider === "anthropic") {
    const response = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
        "anthropic-dangerous-direct-browser-access": "true",
      },
      body: JSON.stringify({
        model: "claude-haiku-4-5-20251001",
        max_tokens: 4096,
        system: CLASSIFICATION_PROMPT,
        messages: [{ role: "user", content: userMessage }],
      }),
      signal,
    });

    if (!response.ok) {
      throw new Error(`Anthropic API error: ${response.status}`);
    }

    const data = await response.json();
    const textBlock = data.content?.find(
      (b: { type: string }) => b.type === "text",
    );
    return textBlock?.text || "[]";
  } else {
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "gpt-4o-mini",
        max_tokens: 4096,
        messages: [
          { role: "system", content: CLASSIFICATION_PROMPT },
          { role: "user", content: userMessage },
        ],
      }),
      signal,
    });

    if (!response.ok) {
      throw new Error(`OpenAI API error: ${response.status}`);
    }

    const data = await response.json();
    return data.choices?.[0]?.message?.content || "[]";
  }
}

function parseClassificationResponse(
  text: string,
  originalNodes: GraphDataNode[],
): ClassifiedNode[] {
  // Extract JSON array from response (may have markdown wrapping)
  let jsonStr = text.trim();
  const arrayMatch = jsonStr.match(/\[[\s\S]*\]/);
  if (arrayMatch) {
    jsonStr = arrayMatch[0];
  }

  try {
    const parsed = JSON.parse(jsonStr);
    if (!Array.isArray(parsed)) return [];

    const validIds = new Set(originalNodes.map((n) => n.id));

    return parsed
      .filter(
        (item: Record<string, unknown>) =>
          typeof item.id === "string" && validIds.has(item.id),
      )
      .map((item: Record<string, unknown>) => ({
        id: item.id as string,
        enhancedType: typeof item.enhancedType === "string" ? item.enhancedType : undefined,
        group: typeof item.group === "string" ? item.group : undefined,
        subtitle: typeof item.subtitle === "string" ? item.subtitle : undefined,
        description: typeof item.description === "string" ? item.description : undefined,
        shape: typeof item.shape === "string" ? item.shape : undefined,
      }));
  } catch {
    return [];
  }
}

/**
 * Merge classification results back into GraphData.
 * Returns a new GraphData with enriched node properties.
 */
export function mergeClassification(
  graphData: GraphData,
  classified: ClassifiedNode[],
): GraphData {
  if (classified.length === 0) return graphData;

  const classMap = new Map(classified.map((c) => [c.id, c]));

  const enrichedNodes = graphData.nodes.map((n) => {
    const c = classMap.get(n.id);
    if (!c) return n;

    return {
      ...n,
      type: c.enhancedType || n.type,
      group: c.group || n.group,
      properties: {
        ...n.properties,
        ...(c.subtitle ? { subtitle: c.subtitle } : {}),
        ...(c.description ? { description: c.description } : {}),
        ...(c.shape ? { shape: c.shape } : {}),
      },
    };
  });

  return {
    ...graphData,
    nodes: enrichedNodes,
  };
}
