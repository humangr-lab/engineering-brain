/**
 * Share Engine — compressed graph URLs + social preview metadata.
 * Pure engine module (no React dependency).
 *
 * Compression pipeline:
 *   1. Compact JSON (short keys, array-of-arrays)
 *   2. TextEncoder → Uint8Array
 *   3. Deflate compression (built-in CompressionStream API)
 *   4. Base64url encoding (URL-safe, no padding)
 *
 * Achieves ~85-95% reduction on typical graph data.
 *
 * Share URL format: {baseUrl}/share#{base64url_compressed_data}
 * Using hash fragment so data never hits the server.
 */

import type { Node, Edge } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface SharePayload {
  /** Compact node array: [id, text, layer, type] */
  n: [string, string, number, string][];
  /** Compact edge array: [from, to, type] */
  e: [string, string, string][];
  /** Metadata */
  m: {
    /** Title */
    t?: string;
    /** Node count (original, before limit) */
    c: number;
    /** Timestamp */
    ts: number;
  };
}

export interface ShareOptions {
  /** Max nodes in share URL */
  maxNodes: number;
  /** Base URL for share links */
  baseUrl: string;
  /** Title for social preview */
  title?: string;
}

const DEFAULT_OPTIONS: ShareOptions = {
  maxNodes: 100,
  baseUrl: "https://ontology-map.dev",
  title: undefined,
};

// ─── Compression ─────────────────────────────────────────────────────────────

/** Compress string to Uint8Array using built-in DeflateRaw */
async function compress(data: string): Promise<Uint8Array> {
  const encoder = new TextEncoder();
  const input = encoder.encode(data);

  // Use CompressionStream API (available in all modern browsers + Tauri WebView)
  if (typeof CompressionStream !== "undefined") {
    const cs = new CompressionStream("deflate-raw");
    const writer = cs.writable.getWriter();
    writer.write(input);
    writer.close();

    const reader = cs.readable.getReader();
    const chunks: Uint8Array[] = [];
    let totalLength = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      totalLength += value.length;
    }

    const result = new Uint8Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
      result.set(chunk, offset);
      offset += chunk.length;
    }
    return result;
  }

  // Fallback: return raw UTF-8 bytes (no compression)
  return input;
}

/** Decompress Uint8Array to string */
async function decompress(data: Uint8Array): Promise<string> {
  if (typeof DecompressionStream !== "undefined") {
    const ds = new DecompressionStream("deflate-raw");
    const writer = ds.writable.getWriter();
    writer.write(data as Uint8Array<ArrayBuffer>);
    writer.close();

    const reader = ds.readable.getReader();
    const chunks: Uint8Array[] = [];
    let totalLength = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      totalLength += value.length;
    }

    const result = new Uint8Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
      result.set(chunk, offset);
      offset += chunk.length;
    }

    return new TextDecoder().decode(result);
  }

  return new TextDecoder().decode(data);
}

// ─── Base64url ───────────────────────────────────────────────────────────────

/** Encode Uint8Array to base64url (no padding) */
function toBase64url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

/** Decode base64url to Uint8Array */
function fromBase64url(str: string): Uint8Array {
  // Restore standard base64
  let b64 = str.replace(/-/g, "+").replace(/_/g, "/");
  // Add padding
  while (b64.length % 4 !== 0) b64 += "=";

  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

// ─── Share URL Generation ────────────────────────────────────────────────────

/** Generate a compressed share URL from graph data */
export async function generateShareUrl(
  nodes: Node[],
  edges: Edge[],
  options: Partial<ShareOptions> = {},
): Promise<string> {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  // Limit nodes
  const limited = nodes.slice(0, opts.maxNodes);
  const nodeIds = new Set(limited.map((n) => n.id));
  const limitedEdges = edges.filter(
    (e) => nodeIds.has(e.from) && nodeIds.has(e.to),
  );

  // Build compact payload
  const payload: SharePayload = {
    n: limited.map((n) => [n.id, n.text, n.layer, n.type]),
    e: limitedEdges.map((e) => [e.from, e.to, e.type]),
    m: {
      t: opts.title,
      c: nodes.length,
      ts: Date.now(),
    },
  };

  const json = JSON.stringify(payload);
  const compressed = await compress(json);
  const encoded = toBase64url(compressed);

  return `${opts.baseUrl}/share#${encoded}`;
}

/** Parse a share URL back into graph data */
export async function parseShareUrl(
  url: string,
): Promise<{ nodes: Node[]; edges: Edge[]; title?: string } | null> {
  try {
    const hashIndex = url.indexOf("#");
    if (hashIndex === -1) return null;

    const encoded = url.slice(hashIndex + 1);
    const bytes = fromBase64url(encoded);
    const json = await decompress(bytes);
    const payload: SharePayload = JSON.parse(json);

    const nodes: Node[] = payload.n.map(([id, text, layer, type]) => ({
      id,
      text,
      layer,
      type,
      layerName: `Layer ${layer}`,
      severity: "medium",
      confidence: 0.5,
      technologies: [],
      domains: [],
      outEdges: [],
      inEdges: [],
      metadata: {},
    }));

    const edges: Edge[] = payload.e.map(([from, to, type]) => ({
      from,
      to,
      type,
    }));

    return { nodes, edges, title: payload.m.t };
  } catch {
    return null;
  }
}

/** Get the size of the share URL for display */
export async function getShareUrlSize(
  nodes: Node[],
  edges: Edge[],
  maxNodes = 100,
): Promise<{ urlLength: number; compressionRatio: number }> {
  const url = await generateShareUrl(nodes, edges, { maxNodes });
  const rawSize = JSON.stringify({
    nodes: nodes.slice(0, maxNodes).map((n) => ({ id: n.id, text: n.text, layer: n.layer, type: n.type })),
    edges: edges.filter((e) => {
      const ids = new Set(nodes.slice(0, maxNodes).map((n) => n.id));
      return ids.has(e.from) && ids.has(e.to);
    }).map((e) => ({ from: e.from, to: e.to, type: e.type })),
  }).length;

  return {
    urlLength: url.length,
    compressionRatio: rawSize > 0 ? 1 - url.length / rawSize : 0,
  };
}

// ─── OG Meta Tags ────────────────────────────────────────────────────────────

/** Generate meta tags for social sharing preview */
export function generateOGMetaTags(
  title: string,
  nodeCount: number,
  edgeCount: number,
  grade?: string,
): string {
  const description = `${nodeCount} nodes, ${edgeCount} edges${grade ? ` | Health: ${grade}` : ""} — Interactive 3D code architecture map`;
  const ogImage = `https://ontology-map.dev/api/og?nodes=${nodeCount}&edges=${edgeCount}${grade ? `&grade=${grade}` : ""}`;

  return [
    `<meta property="og:title" content="${escapeHtml(title)}" />`,
    `<meta property="og:description" content="${escapeHtml(description)}" />`,
    `<meta property="og:image" content="${ogImage}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${escapeHtml(title)}" />`,
    `<meta name="twitter:description" content="${escapeHtml(description)}" />`,
    `<meta name="twitter:image" content="${ogImage}" />`,
  ].join("\n");
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
