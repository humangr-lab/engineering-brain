/**
 * Agent Tools — 6 tools for AI-driven map interaction.
 * Each tool has: name, description, input_schema, execute(args).
 * Pure data layer — no DOM or React dependencies.
 */

import type { Node, Edge } from "@/lib/api";

export interface ToolDefinition {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  execute: (args: Record<string, unknown>, ctx: ToolContext) => unknown;
}

export interface ToolContext {
  nodes: Node[];
  edges: Edge[];
  onNavigate?: (nodeId: string) => void;
  onHighlight?: (nodeIds: string[]) => void;
  onSelect?: (nodeId: string | null) => void;
}

// ── Tool: search_nodes ──

const TOOL_SEARCH_NODES: ToolDefinition = {
  name: "search_nodes",
  description:
    "Search for nodes in the knowledge graph by name, type, or description. Returns matching nodes with relevance.",
  input_schema: {
    type: "object",
    properties: {
      query: {
        type: "string",
        description: "Search query (name, keyword, or description)",
      },
      limit: {
        type: "integer",
        description: "Maximum results to return (default 10, max 50)",
      },
    },
    required: ["query"],
  },
  execute(args, ctx) {
    const query = ((args.query as string) || "").toLowerCase();
    const limit = Math.min((args.limit as number) || 10, 50);

    const scored = ctx.nodes
      .map((node) => {
        const haystack =
          `${node.id} ${node.text} ${node.layerName} ${node.type} ${(node.technologies || []).join(" ")} ${(node.domains || []).join(" ")}`.toLowerCase();
        if (!haystack.includes(query)) return null;

        const idMatch = node.id.toLowerCase().includes(query) ? 2 : 0;
        const textMatch = (node.text || "").toLowerCase().startsWith(query)
          ? 1.5
          : 0;
        return { node, score: 1 + idMatch + textMatch };
      })
      .filter(Boolean)
      .sort((a, b) => b!.score - a!.score)
      .slice(0, limit);

    return {
      results: scored.map((s) => ({
        id: s!.node.id,
        label: s!.node.text || s!.node.id,
        layer: s!.node.layerName,
        type: s!.node.type,
        score: s!.score,
      })),
      total: scored.length,
      query,
    };
  },
};

// ── Tool: navigate_to ──

const TOOL_NAVIGATE_TO: ToolDefinition = {
  name: "navigate_to",
  description:
    "Move the 3D camera to focus on a specific node. The map animates smoothly to the target.",
  input_schema: {
    type: "object",
    properties: {
      node_id: {
        type: "string",
        description: "ID of the node to navigate to",
      },
    },
    required: ["node_id"],
  },
  execute(args, ctx) {
    const nodeId = args.node_id as string;
    const node = ctx.nodes.find((n) => n.id === nodeId);

    if (!node) {
      return { success: false, error: `Node "${nodeId}" not found in graph.` };
    }

    ctx.onNavigate?.(nodeId);
    ctx.onSelect?.(nodeId);

    return {
      success: true,
      node_id: nodeId,
      label: node.text || nodeId,
    };
  },
};

// ── Tool: highlight_nodes ──

const TOOL_HIGHLIGHT_NODES: ToolDefinition = {
  name: "highlight_nodes",
  description:
    "Visually highlight a set of nodes on the map with a glow effect. Use to show dependencies, blast radius, related components.",
  input_schema: {
    type: "object",
    properties: {
      node_ids: {
        type: "array",
        items: { type: "string" },
        description: "IDs of nodes to highlight",
      },
      duration_ms: {
        type: "integer",
        description: "Duration of highlight in ms (default 5000). 0 for persistent.",
      },
    },
    required: ["node_ids"],
  },
  execute(args, ctx) {
    const nodeIds = (args.node_ids as string[]) || [];
    const existing = nodeIds.filter((id) =>
      ctx.nodes.some((n) => n.id === id),
    );

    ctx.onHighlight?.(existing);

    const notFound = nodeIds.length - existing.length;
    return {
      success: true,
      highlighted: existing,
      total_requested: nodeIds.length,
      note:
        notFound > 0
          ? `${notFound} node(s) not found in current view`
          : undefined,
    };
  },
};

// ── Tool: get_details ──

const TOOL_GET_DETAILS: ToolDefinition = {
  name: "get_details",
  description:
    "Get detailed information about a specific node: its type, metadata, connections, and available data.",
  input_schema: {
    type: "object",
    properties: {
      node_id: {
        type: "string",
        description: "ID of the node to inspect",
      },
    },
    required: ["node_id"],
  },
  execute(args, ctx) {
    const nodeId = args.node_id as string;
    const node = ctx.nodes.find((n) => n.id === nodeId);

    if (!node) {
      return { error: `Node "${nodeId}" not found.` };
    }

    const incoming = ctx.edges
      .filter((e) => e.to === nodeId)
      .map((e) => ({
        id: e.from,
        label: ctx.nodes.find((n) => n.id === e.from)?.text || e.from,
        type: e.type,
      }));

    const outgoing = ctx.edges
      .filter((e) => e.from === nodeId)
      .map((e) => ({
        id: e.to,
        label: ctx.nodes.find((n) => n.id === e.to)?.text || e.to,
        type: e.type,
      }));

    return {
      id: nodeId,
      label: node.text || nodeId,
      layer: node.layerName,
      type: node.type,
      severity: node.severity,
      confidence: node.confidence,
      technologies: node.technologies,
      domains: node.domains,
      why: node.why,
      howTo: node.howTo,
      connections: {
        incoming: incoming.slice(0, 20),
        outgoing: outgoing.slice(0, 20),
        total_incoming: incoming.length,
        total_outgoing: outgoing.length,
      },
    };
  },
};

// ── Tool: get_submap ──

const TOOL_GET_SUBMAP: ToolDefinition = {
  name: "get_submap",
  description:
    "Get the subgraph around a node: BFS expansion within a specified depth. Returns nodes and edges.",
  input_schema: {
    type: "object",
    properties: {
      node_id: {
        type: "string",
        description: "Center node ID",
      },
      depth: {
        type: "integer",
        description: "How many hops to expand (default 1, max 3)",
      },
    },
    required: ["node_id"],
  },
  execute(args, ctx) {
    const nodeId = args.node_id as string;
    const depth = Math.min((args.depth as number) || 1, 3);

    const visited = new Set([nodeId]);
    let frontier = new Set([nodeId]);
    const collectedEdges: { from: string; to: string; type: string }[] = [];

    for (let d = 0; d < depth; d++) {
      const nextFrontier = new Set<string>();
      for (const e of ctx.edges) {
        if (frontier.has(e.from) && !visited.has(e.to)) {
          nextFrontier.add(e.to);
          visited.add(e.to);
          collectedEdges.push({ from: e.from, to: e.to, type: e.type });
        }
        if (frontier.has(e.to) && !visited.has(e.from)) {
          nextFrontier.add(e.from);
          visited.add(e.from);
          collectedEdges.push({ from: e.from, to: e.to, type: e.type });
        }
        if (
          frontier.has(e.from) &&
          visited.has(e.to) &&
          !collectedEdges.some(
            (ce) => ce.from === e.from && ce.to === e.to,
          )
        ) {
          collectedEdges.push({ from: e.from, to: e.to, type: e.type });
        }
      }
      frontier = nextFrontier;
    }

    const subNodes = Array.from(visited).map((nId) => {
      const node = ctx.nodes.find((n) => n.id === nId);
      return {
        id: nId,
        label: node?.text || nId,
        layer: node?.layerName || "",
        is_center: nId === nodeId,
      };
    });

    return {
      center: nodeId,
      depth,
      nodes: subNodes,
      edges: collectedEdges,
      node_count: subNodes.length,
      edge_count: collectedEdges.length,
    };
  },
};

// ── Tool: get_metrics ──

const TOOL_GET_METRICS: ToolDefinition = {
  name: "get_metrics",
  description:
    "Get aggregated graph-level statistics: total nodes, edges, density, layer distribution, most connected nodes.",
  input_schema: {
    type: "object",
    properties: {},
    required: [],
  },
  execute(_args, ctx) {
    const n = ctx.nodes.length;
    const e = ctx.edges.length;

    const layers: Record<string, number> = {};
    for (const node of ctx.nodes) {
      const key = node.layerName || `L${node.layer}`;
      layers[key] = (layers[key] || 0) + 1;
    }

    const edgeTypes: Record<string, number> = {};
    for (const edge of ctx.edges) {
      edgeTypes[edge.type] = (edgeTypes[edge.type] || 0) + 1;
    }

    const degrees: Record<string, number> = {};
    for (const edge of ctx.edges) {
      degrees[edge.from] = (degrees[edge.from] || 0) + 1;
      degrees[edge.to] = (degrees[edge.to] || 0) + 1;
    }
    const degreeValues = Object.values(degrees);
    const avgDegree =
      degreeValues.length > 0
        ? +(
            degreeValues.reduce((a, b) => a + b, 0) / degreeValues.length
          ).toFixed(1)
        : 0;
    const maxDegree =
      degreeValues.length > 0 ? Math.max(...degreeValues) : 0;

    const maxEdges = (n * (n - 1)) / 2;
    const density = maxEdges > 0 ? +(e / maxEdges).toFixed(4) : 0;

    return {
      total_nodes: n,
      total_edges: e,
      density,
      avg_degree: avgDegree,
      max_degree: maxDegree,
      layers,
      edge_types: edgeTypes,
    };
  },
};

// ── Registry ──

export const TOOLS: ToolDefinition[] = [
  TOOL_SEARCH_NODES,
  TOOL_NAVIGATE_TO,
  TOOL_HIGHLIGHT_NODES,
  TOOL_GET_DETAILS,
  TOOL_GET_SUBMAP,
  TOOL_GET_METRICS,
];

export function getToolsForAnthropic() {
  return TOOLS.map((t) => ({
    name: t.name,
    description: t.description,
    input_schema: t.input_schema,
  }));
}

export function getToolsForOpenAI() {
  return TOOLS.map((t) => ({
    type: "function" as const,
    function: {
      name: t.name,
      description: t.description,
      parameters: t.input_schema,
    },
  }));
}

export function executeTool(
  toolName: string,
  args: Record<string, unknown>,
  ctx: ToolContext,
): unknown {
  const tool = TOOLS.find((t) => t.name === toolName);
  if (!tool) return { error: `Unknown tool: ${toolName}` };
  try {
    return tool.execute(args, ctx);
  } catch (e) {
    return {
      error: `Tool execution failed: ${e instanceof Error ? e.message : String(e)}`,
    };
  }
}
