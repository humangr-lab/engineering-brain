/* ═══════════════ WP-6: AGENT TOOLS — 6 tools for AI map interaction ═══════════════
   Each tool: { name, description, input_schema, execute(args) }
   Tools return JSON results + optionally trigger map actions.
   Consumed by stream.js for tool call execution.
   ════════════════════════════════════════════════════════════════════════════════ */

import { state } from '../state.js';
import { searchNodes } from '../search.js';
import { animateCamera } from '../scene/layout.js';
import { scene } from '../scene/engine.js';

/* ── Map action queue ── */
let _actionQueue = [];
let _actionTimer = null;
let _cancelled = false;

/**
 * Cancel all queued map actions (e.g., when user interacts with map).
 */
export function cancelQueuedActions() {
  _cancelled = true;
  if (_actionTimer) {
    clearTimeout(_actionTimer);
    _actionTimer = null;
  }
  _actionQueue = [];
}

/**
 * Queue a map action with a 200ms delay. User interaction cancels queued actions.
 */
function _queueAction(fn) {
  _cancelled = false;
  _actionQueue.push(fn);
  if (!_actionTimer) {
    _actionTimer = setTimeout(_processQueue, 200);
  }
}

function _processQueue() {
  _actionTimer = null;
  while (_actionQueue.length > 0 && !_cancelled) {
    const fn = _actionQueue.shift();
    try { fn(); } catch (e) { console.warn('[WP-6] Tool action error:', e); }
  }
  _actionQueue = [];
}

/* ── Highlight management ── */
let _highlightTimers = [];
let _highlightedMeshes = [];

function _clearHighlights() {
  for (const timer of _highlightTimers) clearTimeout(timer);
  _highlightTimers = [];
  for (const { mesh, originalEmissive } of _highlightedMeshes) {
    if (mesh?.material) {
      mesh.material.emissiveIntensity = originalEmissive;
    }
  }
  _highlightedMeshes = [];
  state.agentHighlightedNodes = [];
}

function _findNodeMesh(nodeId) {
  // Search through the scene graph for a mesh with matching userData.id
  let found = null;
  scene.traverse((obj) => {
    if (found) return;
    if (obj.userData?.id === nodeId) {
      found = obj;
    }
  });

  // If no direct match, look for groups that contain the node
  if (!found) {
    scene.traverse((obj) => {
      if (found) return;
      if (obj.isGroup) {
        obj.traverse((child) => {
          if (found) return;
          if (child.userData?.id === nodeId) {
            found = obj; // Return the parent group
          }
        });
      }
    });
  }

  return found;
}

function _findNodePosition(nodeId) {
  const node = (state.sysNodes || []).find(n => n.id === nodeId);
  if (node && node.x != null && node.z != null) {
    return { x: node.x, y: node.y || 1, z: node.z };
  }

  // Check submaps
  if (state.submaps) {
    for (const sm of Object.values(state.submaps)) {
      if (sm.nodes) {
        const subNode = sm.nodes.find(n => n.id === nodeId);
        if (subNode && subNode.x != null && subNode.z != null) {
          return { x: subNode.x, y: subNode.y || 1, z: subNode.z };
        }
      }
    }
  }

  return null;
}

/* ── Tool Definitions ── */

const TOOL_SEARCH_NODES = {
  name: 'search_nodes',
  description: 'Search for nodes in the system graph by name, type, or description. Returns matching nodes with relevance scores.',
  input_schema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'Search query (name, keyword, or natural language description)' },
      limit: { type: 'integer', description: 'Maximum results to return (default 10, max 50)' },
    },
    required: ['query'],
  },
  execute(args) {
    const query = args.query || '';
    const limit = Math.min(args.limit || 10, 50);
    const results = searchNodes(query, 'all');
    const trimmed = results.slice(0, limit).map(r => ({
      id: r.id,
      label: r.label,
      sub: r.sub || '',
      type: r.nodeType || r.type || '',
      group: r.group || '',
      score: r._score || 0,
    }));
    return {
      results: trimmed,
      total: results.length,
      query,
    };
  },
};

const TOOL_NAVIGATE_TO = {
  name: 'navigate_to',
  description: 'Move the 3D camera to focus on a specific node. The map animates smoothly to the target.',
  input_schema: {
    type: 'object',
    properties: {
      node_id: { type: 'string', description: 'ID of the node to navigate to' },
    },
    required: ['node_id'],
  },
  execute(args) {
    const nodeId = args.node_id;
    const pos = _findNodePosition(nodeId);

    if (!pos) {
      return { success: false, error: `Node "${nodeId}" not found in graph.` };
    }

    // Queue the camera animation
    _queueAction(() => {
      const targetPos = {
        x: pos.x + 8,
        y: pos.y + 10,
        z: pos.z + 8,
      };
      const targetLookAt = {
        x: pos.x,
        y: pos.y,
        z: pos.z,
      };
      animateCamera(targetPos, targetLookAt, 1200);

      // Select the node
      state.selectedNode = nodeId;
    });

    const node = (state.sysNodes || []).find(n => n.id === nodeId);
    return {
      success: true,
      node_id: nodeId,
      label: node?.label || nodeId,
      position: pos,
    };
  },
};

const TOOL_HIGHLIGHT_NODES = {
  name: 'highlight_nodes',
  description: 'Visually highlight a set of nodes on the map with a glow effect. Use to show dependencies, blast radius, related components.',
  input_schema: {
    type: 'object',
    properties: {
      node_ids: { type: 'array', items: { type: 'string' }, description: 'IDs of nodes to highlight' },
      color: { type: 'string', description: 'Highlight color as CSS color string (default: red for warnings, blue for focus)' },
      duration_ms: { type: 'integer', description: 'Duration of highlight in ms (default: 5000). 0 for persistent.' },
    },
    required: ['node_ids'],
  },
  execute(args) {
    const nodeIds = args.node_ids || [];
    const durationMs = args.duration_ms ?? 5000;

    // Pre-check which nodes exist (synchronous) so return value is accurate
    const existingNodeIds = nodeIds.filter(nid => !!_findNodeMesh(nid));

    _queueAction(() => {
      _clearHighlights();

      for (const nodeId of existingNodeIds) {
        const mesh = _findNodeMesh(nodeId);
        if (!mesh) continue;

        // Find the actual renderable mesh inside the group
        const renderables = [];
        if (mesh.isGroup || mesh.children?.length) {
          mesh.traverse((child) => {
            if (child.isMesh && child.material && !child.material.transparent) {
              renderables.push(child);
            }
          });
        } else if (mesh.isMesh) {
          renderables.push(mesh);
        }

        for (const rm of renderables) {
          const originalEmissive = rm.material.emissiveIntensity || 0;
          rm.material.emissiveIntensity = 0.4;
          if (rm.material.emissive) {
            rm.material.emissive.set(0xff6b6b); // Default red glow
          }
          _highlightedMeshes.push({ mesh: rm, originalEmissive });
        }
      }

      state.agentHighlightedNodes = [...existingNodeIds];

      // Auto-clear after duration
      if (durationMs > 0) {
        const timer = setTimeout(() => _clearHighlights(), durationMs);
        _highlightTimers.push(timer);
      }
    });

    const notFound = nodeIds.length - existingNodeIds.length;
    return {
      success: true,
      highlighted: existingNodeIds,
      total_requested: nodeIds.length,
      note: notFound > 0
        ? `${notFound} node(s) not found in current view`
        : undefined,
    };
  },
};

const TOOL_GET_DETAILS = {
  name: 'get_details',
  description: 'Get detailed information about a specific node: its type, metadata, connections, and available data.',
  input_schema: {
    type: 'object',
    properties: {
      node_id: { type: 'string', description: 'ID of the node to inspect' },
    },
    required: ['node_id'],
  },
  execute(args) {
    const nodeId = args.node_id;
    const node = (state.sysNodes || []).find(n => n.id === nodeId);
    const details = state.sysDetails?.[nodeId];
    const nodeDetail = state.nodeDetails?.[nodeId];
    const edges = state.sysEdges || [];

    if (!node && !details && !nodeDetail) {
      return { error: `Node "${nodeId}" not found.` };
    }

    // Collect connections
    const incoming = [];
    const outgoing = [];
    for (const e of edges) {
      const from = e.f || e.from;
      const to = e.t || e.to;
      const edgeType = e.type || e.c || 'unknown';
      if (from === nodeId) {
        const targetNode = (state.sysNodes || []).find(n => n.id === to);
        outgoing.push({ id: to, label: targetNode?.label || to, type: edgeType });
      }
      if (to === nodeId) {
        const sourceNode = (state.sysNodes || []).find(n => n.id === from);
        incoming.push({ id: from, label: sourceNode?.label || from, type: edgeType });
      }
    }

    // Check for submap
    const hasSubmap = !!(state.submaps && state.submaps[nodeId]);
    const submapInfo = hasSubmap ? {
      child_count: state.submaps[nodeId].nodes?.length || 0,
      title: state.submaps[nodeId].title || nodeId,
    } : null;

    return {
      id: nodeId,
      label: node?.label || nodeDetail?.t || nodeId,
      subtitle: node?.sub || '',
      group: node?.g || node?.group || '',
      description: details?.d || nodeDetail?.d || '',
      has_submap: hasSubmap,
      submap: submapInfo,
      connections: {
        incoming: incoming.slice(0, 20),
        outgoing: outgoing.slice(0, 20),
        total_incoming: incoming.length,
        total_outgoing: outgoing.length,
      },
      metrics: nodeDetail?.kv || null,
    };
  },
};

const TOOL_GET_SUBMAP = {
  name: 'get_submap',
  description: 'Get the subgraph around a node: its children, parents, and connected nodes within a specified depth. Returns nodes and edges.',
  input_schema: {
    type: 'object',
    properties: {
      node_id: { type: 'string', description: 'Center node ID' },
      depth: { type: 'integer', description: 'How many hops to expand (default 1, max 3)' },
    },
    required: ['node_id'],
  },
  execute(args) {
    const nodeId = args.node_id;
    const depth = Math.min(args.depth || 1, 3);
    const allEdges = state.sysEdges || [];
    const allNodes = state.sysNodes || [];

    // BFS expansion from center node
    const visited = new Set([nodeId]);
    let frontier = new Set([nodeId]);
    const collectedEdges = [];

    for (let d = 0; d < depth; d++) {
      const nextFrontier = new Set();
      for (const e of allEdges) {
        const from = e.f || e.from;
        const to = e.t || e.to;
        if (frontier.has(from) && !visited.has(to)) {
          nextFrontier.add(to);
          visited.add(to);
          collectedEdges.push({ from, to, type: e.type || e.c || 'unknown' });
        }
        if (frontier.has(to) && !visited.has(from)) {
          nextFrontier.add(from);
          visited.add(from);
          collectedEdges.push({ from, to, type: e.type || e.c || 'unknown' });
        }
        // Also collect edges between already-visited nodes
        if (frontier.has(from) && visited.has(to)) {
          const key = `${from}->${to}`;
          if (!collectedEdges.some(ce => `${ce.from}->${ce.to}` === key)) {
            collectedEdges.push({ from, to, type: e.type || e.c || 'unknown' });
          }
        }
      }
      frontier = nextFrontier;
    }

    // Collect node details
    const subNodes = [];
    for (const nId of visited) {
      const node = allNodes.find(n => n.id === nId);
      subNodes.push({
        id: nId,
        label: node?.label || nId,
        group: node?.g || node?.group || '',
        is_center: nId === nodeId,
      });
    }

    // Also check for submap children
    const submap = state.submaps?.[nodeId];
    const children = [];
    if (submap?.nodes) {
      for (const child of submap.nodes) {
        children.push({
          id: child.id,
          label: child.label || child.id,
          sub: child.sub || '',
        });
      }
    }

    return {
      center: nodeId,
      depth,
      nodes: subNodes,
      edges: collectedEdges,
      children: children.length > 0 ? children : undefined,
      node_count: subNodes.length,
      edge_count: collectedEdges.length,
    };
  },
};

const TOOL_GET_METRICS = {
  name: 'get_metrics',
  description: 'Get aggregated graph-level statistics: total nodes, edges, density, node groups, edge types, most connected nodes.',
  input_schema: {
    type: 'object',
    properties: {},
    required: [],
  },
  execute() {
    const nodes = state.sysNodes || [];
    const edges = state.sysEdges || [];
    const submaps = state.submaps || {};
    const visibleNodes = nodes.filter(n => !n.hidden);

    // Group distribution
    const groups = {};
    for (const n of visibleNodes) {
      const g = n.g || n.group || 'other';
      groups[g] = (groups[g] || 0) + 1;
    }

    // Edge type distribution
    const edgeTypes = {};
    for (const e of edges) {
      const t = e.type || e.c || 'unknown';
      edgeTypes[t] = (edgeTypes[t] || 0) + 1;
    }

    // Connection degree stats
    const degrees = {};
    for (const e of edges) {
      const from = e.f || e.from;
      const to = e.t || e.to;
      degrees[from] = (degrees[from] || 0) + 1;
      degrees[to] = (degrees[to] || 0) + 1;
    }
    const degreeValues = Object.values(degrees);
    const avgDegree = degreeValues.length > 0
      ? (degreeValues.reduce((a, b) => a + b, 0) / degreeValues.length).toFixed(1)
      : '0';
    const maxDegree = degreeValues.length > 0 ? Math.max(...degreeValues) : 0;

    // Submap count
    const submapCount = Object.keys(submaps).length;
    const totalSubmapNodes = Object.values(submaps).reduce(
      (sum, sm) => sum + (sm.nodes?.length || 0), 0
    );

    // Density
    const n = visibleNodes.length;
    const maxEdges = n * (n - 1) / 2;
    const density = maxEdges > 0 ? (edges.length / maxEdges).toFixed(4) : '0';

    return {
      total_nodes: visibleNodes.length,
      total_edges: edges.length,
      density: parseFloat(density),
      avg_degree: parseFloat(avgDegree),
      max_degree: maxDegree,
      groups,
      edge_types: edgeTypes,
      drillable_modules: submapCount,
      submap_total_nodes: totalSubmapNodes,
    };
  },
};

/* ── Exports ── */

/**
 * All tool definitions. Used to build the tools array for the LLM API call.
 */
export const TOOLS = [
  TOOL_SEARCH_NODES,
  TOOL_NAVIGATE_TO,
  TOOL_HIGHLIGHT_NODES,
  TOOL_GET_DETAILS,
  TOOL_GET_SUBMAP,
  TOOL_GET_METRICS,
];

/**
 * Get tool definitions formatted for the Anthropic API.
 * @returns {Array} tool definitions in Anthropic format
 */
export function getToolsForAnthropic() {
  return TOOLS.map(t => ({
    name: t.name,
    description: t.description,
    input_schema: t.input_schema,
  }));
}

/**
 * Get tool definitions formatted for the OpenAI API.
 * @returns {Array} tool definitions in OpenAI format
 */
export function getToolsForOpenAI() {
  return TOOLS.map(t => ({
    type: 'function',
    function: {
      name: t.name,
      description: t.description,
      parameters: t.input_schema,
    },
  }));
}

/**
 * Execute a tool by name with the given arguments.
 * @param {string} toolName - Name of the tool to execute
 * @param {object} args - Tool arguments
 * @returns {object} Tool result
 */
export function executeTool(toolName, args) {
  const tool = TOOLS.find(t => t.name === toolName);
  if (!tool) {
    return { error: `Unknown tool: ${toolName}` };
  }
  try {
    return tool.execute(args);
  } catch (e) {
    console.error(`[WP-6] Tool "${toolName}" execution error:`, e);
    return { error: `Tool execution failed: ${e.message}` };
  }
}

/**
 * Wire user interaction cancel (mouse/keyboard on canvas cancels queued actions).
 */
export function wireActionCancellation() {
  const sc = document.getElementById('sc');
  if (!sc) return;

  const cancelEvents = ['mousedown', 'wheel', 'touchstart'];
  for (const evt of cancelEvents) {
    sc.addEventListener(evt, () => cancelQueuedActions(), { passive: true });
  }
}
