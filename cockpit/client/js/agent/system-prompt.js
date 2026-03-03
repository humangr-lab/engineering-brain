/* ═══════════════ WP-6: SYSTEM PROMPT — Graph context compression + agent instructions ═══════════════
   Builds a system prompt that gives the agent awareness of the graph structure
   without dumping all nodes into context. Compresses graph data into a summary
   suitable for the LLM context window (~500-1000 tokens).
   ═══════════════════════════════════════════════════════════════════════════════════════════════════ */

import { state } from '../state.js';

/**
 * Compress graph data into a concise context string.
 * Returns node type distribution, edge type distribution,
 * top-10 most connected nodes, and aggregate stats.
 * @param {object} [graphData] - Optional explicit graph data. Falls back to state.
 * @returns {string} compressed context (typically 400-800 tokens)
 */
export function compressGraphContext(graphData) {
  const nodes = graphData?.nodes || state.sysNodes || [];
  const edges = graphData?.edges || state.sysEdges || [];
  const submaps = graphData?.submaps || state.submaps || {};
  const details = graphData?.details || state.sysDetails || {};

  if (!nodes.length) {
    return 'No graph data loaded.';
  }

  const lines = [];

  // --- Aggregate stats ---
  const submapNodeCount = Object.values(submaps).reduce(
    (sum, sm) => sum + (sm.nodes?.length || 0), 0
  );
  const totalNodes = nodes.length + submapNodeCount;
  lines.push(`Graph: ${totalNodes} nodes, ${edges.length} edges.`);

  // --- Node types / groups ---
  const groupCounts = {};
  for (const n of nodes) {
    const g = n.g || n.group || 'other';
    groupCounts[g] = (groupCounts[g] || 0) + 1;
  }
  const groupSummary = Object.entries(groupCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([g, c]) => `${g}(${c})`)
    .join(', ');
  lines.push(`Node groups: ${groupSummary}`);

  // --- Edge types ---
  const edgeTypeCounts = {};
  for (const e of edges) {
    const t = e.type || e.c || 'unknown';
    edgeTypeCounts[t] = (edgeTypeCounts[t] || 0) + 1;
  }
  const edgeSummary = Object.entries(edgeTypeCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([t, c]) => `${t}(${c})`)
    .join(', ');
  if (edgeSummary) {
    lines.push(`Edge types: ${edgeSummary}`);
  }

  // --- Top-10 most connected nodes ---
  const connectionCount = {};
  for (const e of edges) {
    const from = e.f || e.from;
    const to = e.t || e.to;
    if (from) connectionCount[from] = (connectionCount[from] || 0) + 1;
    if (to) connectionCount[to] = (connectionCount[to] || 0) + 1;
  }
  const topNodes = Object.entries(connectionCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  if (topNodes.length) {
    const topList = topNodes.map(([id, count]) => {
      const node = nodes.find(n => n.id === id);
      const label = node?.label || id;
      return `${label}(${count} edges)`;
    }).join(', ');
    lines.push(`Most connected: ${topList}`);
  }

  // --- Available submaps (drillable nodes) ---
  const submapIds = Object.keys(submaps);
  if (submapIds.length) {
    const smLabels = submapIds.slice(0, 15).map(id => {
      const node = nodes.find(n => n.id === id);
      return node?.label || id;
    }).join(', ');
    lines.push(`Drillable modules: ${smLabels}${submapIds.length > 15 ? ` (+${submapIds.length - 15} more)` : ''}`);
  }

  // --- Node list (all system-level nodes with labels) ---
  const nodeList = nodes
    .filter(n => !n.hidden)
    .map(n => {
      const label = n.label || n.id;
      const sub = n.sub ? ` -- ${n.sub}` : '';
      return `  ${n.id}: ${label}${sub}`;
    })
    .join('\n');
  if (nodeList) {
    lines.push(`\nSystem nodes:\n${nodeList}`);
  }

  return lines.join('\n');
}

/**
 * Build the full system prompt for the agent.
 * @param {object} [graphData] - Optional explicit graph data
 * @returns {string} system prompt ready for the messages array
 */
export function buildSystemPrompt(graphData) {
  const context = compressGraphContext(graphData);

  return `You are an AI assistant embedded in the Ontology Map Toolkit, a 3D interactive visualization of a software system or knowledge graph. You can navigate the map, highlight nodes, and show the user architectural relationships.

SYSTEM CONTEXT:
${context}

AVAILABLE TOOLS:
- search_nodes: Find nodes by name or description. Always use this before assuming a node exists.
- navigate_to: Move the 3D camera to focus on a specific node. The user will see the map animate smoothly to the target.
- highlight_nodes: Highlight a set of nodes on the map with a glow effect. Use to show dependencies, blast radius, related components.
- get_details: Get full details about a specific node (metadata, connections, metrics).
- get_submap: Get the connected subgraph around a node within N hops. Returns nodes and edges.
- get_metrics: Get aggregated graph-level statistics.

GUIDELINES:
1. When explaining relationships, SHOW them on the map using navigate_to and highlight_nodes together.
2. Always search_nodes first before assuming a node ID. Node IDs may differ from what the user mentions.
3. For blast radius or dependency questions, use get_submap then highlight the affected nodes.
4. Keep answers concise (2-4 short paragraphs). The map visualization carries most of the information.
5. If you cannot find relevant nodes, say so honestly rather than speculating.
6. When using highlight_nodes, choose meaningful colors: red for warnings/problems, green for healthy, blue for selected/focus, purple for related.
7. After using tools, briefly explain what you found and what the user should see on the map.`;
}
