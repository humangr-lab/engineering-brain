# F-15 Conversation Mode: Research Document

> Feature: AI Conversation Mode (Chat Panel with Map Navigation)
> Work Package: WP-6 (Conversation Mode)
> Status: Research Phase (WP-6.1)
> Author: Claude Opus 4.6
> Date: 2026-02-27

---

## 1. Problem Statement

The Ontology Map Toolkit currently has **zero AI integration**. The 3D map is a passive visualization: the user must manually navigate, manually search (Cmd+K), manually drill into submaps, and manually correlate what they see with their understanding of the system. There is no way to ask the system a question and have it answer by navigating to relevant nodes, highlighting dependencies, or explaining architectural relationships.

This creates three concrete problems:

**Navigation burden.** In a 10K-node system, finding the right node requires either (a) knowing the exact name to search for, or (b) manually drilling through 3-4 hierarchy levels. For unfamiliar codebases -- the primary use case -- neither is efficient. A developer exploring a new codebase spends 58% of their time navigating and only 42% reading code (Ko et al., 2006) [1].

**Explanation gap.** The map shows structure (nodes, edges, hierarchy) but not meaning. The user sees that `auth_service.py` depends on `models.py` via an edge, but the map cannot explain *why* -- what data flows through that edge, what happens if it breaks, or how it relates to a specific feature. This explanation requires cross-referencing graph structure with code content, which is exactly what LLMs excel at.

**Analysis paralysis.** For common developer questions -- "What is the blast radius if I change this model?", "Where is the entry point for authentication?", "Which modules have the highest coupling?" -- the user must manually trace edges, count connections, and build a mental model. An AI agent with access to the project graph can answer these questions in seconds and show the answer spatially on the map.

**Target architecture.** F-15 introduces a conversational AI agent that:
- Accepts natural language questions about the system
- Queries the project graph (FalkorDB) and engineering knowledge base
- Responds with text AND map actions (navigate, highlight, zoom, annotate)
- Streams responses in real-time with concurrent map animations
- Requires zero backend for Phase 1 (BYOK browser-direct pattern)
- Works with any LLM provider (Anthropic Claude, OpenAI GPT, local models)

This document surveys the state of the art in context compression, code retrieval, agent-UI protocols, browser-direct LLM patterns, and hierarchical summarization to inform the implementation of WP-6.

---

## 2. Cursor 4-Stage Context Compression

Cursor, the AI-native code editor, has developed one of the most sophisticated context management systems in production [2][3]. Understanding their architecture is critical because the Ontology Map Toolkit faces the same fundamental problem: a project graph can contain 10K-100K nodes with rich metadata, but the LLM context window is limited to 8K-200K tokens.

### The 4-Stage Compression Pipeline

Cursor's context management follows a progressive compression strategy that reduces the information available to the LLM at each stage:

**Stage 1: Full Codebase Index (~10M tokens).** The entire codebase is indexed using embeddings (code-specific embedding models). Every file, class, function, docstring, and comment is vectorized. This index is never sent to the LLM directly -- it serves as the searchable corpus.

**Stage 2: Retrieval (~500K tokens).** When the user asks a question, Cursor retrieves the top-K most relevant code chunks using hybrid search (semantic embedding similarity + BM25 keyword matching). Recent work from Cursor's "Dynamic Context Discovery" blog post (January 2026) [3] describes a shift from pre-loading context to making it easier for the agent to pull context on demand via tool calls -- which is "far more token-efficient as only the necessary data is pulled into the context window."

**Stage 3: Re-ranking and Filtering (~50K tokens).** Retrieved chunks are re-ranked using a cross-encoder model that considers the query-chunk relevance score, file recency (recently edited files rank higher), structural proximity (files in the same package rank higher), and dependency distance (files imported by the current file rank higher). Chunks below a relevance threshold are dropped.

**Stage 4: Final Context Window (~8K-32K tokens).** The surviving chunks are formatted into the LLM prompt with structured markers (file paths, line numbers, language tags). When the context window fills up during extended agent sessions, Cursor triggers a summarization step that compresses the conversation history. The agent can recover lost details by searching through the history file -- a lossy-but-recoverable compression approach.

### Application to Project Graph Summarization

For the Ontology Map Toolkit agent, we adapt the 4-stage pipeline to graph data:

| Stage | Cursor (Code) | Toolkit (Graph) |
|-------|---------------|-----------------|
| Stage 1: Full Index | All files vectorized | All nodes + edges + metadata indexed in Qdrant |
| Stage 2: Retrieval | Top-K code chunks | Top-K nodes by query relevance (semantic search on node names + descriptions) |
| Stage 3: Re-ranking | Cross-encoder | Graph-aware re-ranking: nodes connected to focus get boost; nodes at current drill level get boost |
| Stage 4: Final Context | Formatted code snippets | Structured graph context: node summaries, edge lists, metric highlights |

The key insight from Cursor is **not to pre-load context but to give the agent tools to pull it**. For the toolkit agent, this means providing `search_nodes`, `get_details`, and `get_submap` tools rather than dumping the entire graph into the system prompt.

---

## 3. RepoHYPER Search-Expand-Refine

RepoHYPER (Phan et al., 2024) [4] introduces a 3-phase retrieval pattern specifically designed for repository-level code understanding. The framework constructs a **Repo-level Semantic Graph (RSG)** that captures both syntactic relationships (imports, calls, inheritance) and semantic similarity between code elements.

### The 3-Phase Retrieval Pattern

**Phase 1: Search.** Given a natural language query, the system identifies a seed set of relevant nodes using embedding similarity. The RSG embeds every code element (file, class, function) as a vector and retrieves the top-K nearest neighbors to the query embedding. This phase is fast (milliseconds) and provides the initial entry points into the graph.

**Phase 2: Expand.** From the seed nodes, the system expands outward along graph edges to retrieve the connected subgraph. Expansion follows both syntactic edges (imports, function calls, inheritance chains) and semantic edges (similarity above threshold). The expansion depth is bounded (typically 2-3 hops) to prevent the subgraph from growing unboundedly. This phase leverages the graph structure to find contextually relevant code that might not match the query textually but is structurally connected to matching code.

**Phase 3: Refine.** The expanded subgraph is too large for the LLM context window, so a refinement step ranks all retrieved nodes by a composite score combining: query relevance (embedding similarity), structural centrality (PageRank within the subgraph), and usage frequency (how often referenced by other nodes). The top-scoring nodes and their edges form the final context provided to the LLM.

### Application to Cockpit Navigation

The Search-Expand-Refine pattern maps directly to toolkit agent tools:

| Phase | RepoHYPER | Toolkit Agent Tool |
|-------|-----------|-------------------|
| Search | Embedding similarity on RSG | `search_nodes(query)` -- returns top-K matching nodes with scores |
| Expand | Graph traversal (2-3 hops) | `get_submap(node_id, depth=2)` -- returns connected subgraph |
| Refine | Rank by centrality + relevance | Agent-side ranking in LLM (prompt instructs: "Select the 5 most relevant nodes from this subgraph and explain why") |

The agent's workflow for answering "What happens when I delete models.py?" would be:

1. **Search:** `search_nodes("models.py")` -> finds the `models.py` node.
2. **Expand:** `get_submap("models_py", depth=2)` -> retrieves all files that import models.py, all files that those files depend on, and all test files covering models.py symbols.
3. **Refine:** The LLM analyzes the subgraph and identifies the blast radius: 12 direct dependents, 3 cascading dependents, 8 test files affected.
4. **Navigate:** `highlight_nodes(["auth_service.py", "api_routes.py", ...])` + `navigate_to("models_py")` -- the map zooms to models.py and highlights all affected files in red.

---

## 4. LocAgent 3-Tool System

LocAgent (Gersteinlab, 2025) [5] is a graph-guided LLM agent framework for code localization, published at ACL 2025. It achieves 92.7% file-level localization accuracy on SWE-Bench-Lite by providing the LLM with exactly three tools that operate on a directed heterogeneous graph parsed from the codebase.

### The Three Tools

**Tool 1: `SearchEntity(query)`** -- searches for entities (files, classes, functions) by name or description. Returns a ranked list of matching entities with their types and locations. This is the LLM's entry point into the graph.

**Tool 2: `TraverseGraph(entity_id, edge_type, direction)`** -- traverses the graph from a given entity along a specific edge type (imports, calls, inherits, contains) in a given direction (incoming, outgoing). Returns the connected entities. This enables multi-hop reasoning: the LLM can follow an import chain across multiple files.

**Tool 3: `RetrieveEntity(entity_id)`** -- retrieves the full details of an entity: its source code, docstring, metadata, and all connected edges. This is the deep-dive tool used after the LLM has narrowed down to specific entities.

### Mapping to Cockpit Tools

For the toolkit agent, we extend LocAgent's 3-tool pattern to 6 tools that include map navigation actions:

| LocAgent Tool | Cockpit Tool | Description | Map Effect |
|---------------|-------------|-------------|------------|
| `SearchEntity` | `search_nodes(query, filters?)` | Find nodes by name, type, or description | Highlights matching nodes with pulse animation |
| `TraverseGraph` | `get_submap(node_id, depth?, edge_types?)` | Get connected subgraph | Shows subgraph edges with directional particles |
| `RetrieveEntity` | `get_details(node_id)` | Get full node metadata, code, metrics | Opens detail panel for node |
| (new) | `navigate_to(node_id, level?)` | Move camera to node, optionally drill to level | Camera transitions with 350ms ease-out |
| (new) | `highlight_nodes(node_ids[], color?, duration?)` | Highlight a set of nodes | Nodes glow with specified color for duration |
| (new) | `get_metrics(node_ids[], metric_type)` | Get metrics (LOC, complexity, coverage, coupling) | Optional: overlay metric heatmap |

The key insight from LocAgent is that **three well-designed tools are sufficient for complex graph reasoning**. The LLM does not need access to raw graph queries (Cypher, SPARQL) -- it needs high-level tools that abstract the graph operations. Adding raw query access would increase hallucination risk and require the LLM to know the graph schema, violating the simplicity principle.

---

## 5. AG-UI Protocol

AG-UI (Agent-User Interaction Protocol) [6] is an open, lightweight, event-based protocol standardizing how AI agents communicate with frontend applications. Developed by CopilotKit and adopted by Google, LangChain, AWS, Microsoft, PydanticAI, and others, AG-UI defines a vocabulary of SSE event types that the agent backend streams to the UI.

### Event Types

AG-UI defines events organized into five categories [6][7]:

**Lifecycle Events:**
- `RunStarted { runId }` -- agent begins processing.
- `RunFinished { runId }` -- agent completes.
- `StepStarted { stepId, name }` -- agent begins a subtask.
- `StepFinished { stepId }` -- agent completes a subtask.

**Text Streaming Events:**
- `TextMessageStart { messageId }` -- begin a new text message.
- `TextMessageContent { messageId, delta }` -- incremental text chunk (for streaming rendering).
- `TextMessageEnd { messageId }` -- text message complete.

**Tool Execution Events:**
- `ToolCallStart { toolCallId, toolName }` -- agent invokes a tool.
- `ToolCallArgs { toolCallId, delta }` -- incremental tool arguments.
- `ToolCallEnd { toolCallId }` -- tool call complete.

**State Events:**
- `StateSnapshot { state }` -- full agent state snapshot.
- `StateDelta { delta }` -- incremental state update (JSON patch).

**Custom Events:**
- `Custom { name, value }` -- extensible catch-all for domain-specific events.

### Application to the Toolkit

For the Ontology Map Toolkit, we extend AG-UI with custom events for map control:

```javascript
// Custom AG-UI events for map navigation
const TOOLKIT_EVENTS = {
    // Navigation
    NAVIGATE_TO:     { name: 'map.navigate',   value: { nodeId, level, animate: true } },
    HIGHLIGHT_NODES: { name: 'map.highlight',  value: { nodeIds, color, durationMs } },
    CLEAR_HIGHLIGHT: { name: 'map.highlight.clear', value: {} },

    // Drill
    DRILL_INTO:      { name: 'map.drill',      value: { nodeId, targetLevel } },
    DRILL_OUT:       { name: 'map.drill.out',  value: {} },

    // Camera
    FIT_TO_NODES:    { name: 'map.fitToNodes', value: { nodeIds, padding } },
    RESET_VIEW:      { name: 'map.reset',      value: {} },
};
```

### Synchronized Streaming

The power of AG-UI is that text streaming and tool calls are interleaved on the same SSE stream. This enables the following UX:

1. Agent sends `TextMessageContent: "The auth module has 3 dependencies..."`
2. Agent sends `ToolCallStart: { toolName: "highlight_nodes" }` + `ToolCallArgs: { nodeIds: ["db", "cache", "api"] }`
3. Map highlights the 3 nodes while the text is still streaming.
4. Agent sends `TextMessageContent: "...let me show you the blast radius"` + `ToolCallStart: { toolName: "navigate_to", nodeId: "auth" }`
5. Camera animates to the auth module while the text continues.

This concurrent text+map animation creates the "agent is thinking and showing" experience that distinguishes a spatial AI assistant from a traditional chatbot.

### Protocol Selection

For Phase 1 (browser-direct, no backend), AG-UI events are generated client-side from the LLM's tool-calling API responses. The chat.js module parses streaming tool calls and emits AG-UI events to state.js. For Phase 2 (server-proxied), the backend emits AG-UI events natively over SSE, and the client simply subscribes.

---

## 6. BYOK Browser-Direct

**Bring Your Own Key (BYOK)** is the pattern where the user provides their own LLM API key, and the application makes API calls directly from the browser without a backend proxy. This is critical for the Ontology Map Toolkit because INV-OT-002 requires offline-first static export: the cockpit must function without a server.

### Anthropic CORS Support

Since August 2024, Anthropic's API supports CORS requests from browser JavaScript via the `anthropic-dangerous-direct-browser-access: true` header [8]. This enables direct API calls from the toolkit's static HTML/JS bundle:

```javascript
// provider.js -- BYOK Anthropic provider
const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'x-api-key': userApiKey,  // User's own key
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
    },
    body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 4096,
        stream: true,
        tools: TOOLKIT_TOOLS,  // 6 tool definitions
        messages: conversationHistory,
    }),
});
```

The Anthropic JavaScript SDK also supports browser usage via `dangerouslyAllowBrowser: true`:

```javascript
import Anthropic from '@anthropic-ai/sdk';

const client = new Anthropic({
    apiKey: userApiKey,
    dangerouslyAllowBrowser: true,
});

const stream = await client.messages.stream({
    model: 'claude-sonnet-4-20250514',
    tools: TOOLKIT_TOOLS,
    messages: conversationHistory,
});
```

### OpenAI Browser Support

OpenAI's API also supports CORS for browser-direct calls. The `openai` npm package supports browser usage with `dangerouslyAllowBrowser: true` [9]:

```javascript
import OpenAI from 'openai';

const client = new OpenAI({
    apiKey: userApiKey,
    dangerouslyAllowBrowser: true,
});

const stream = await client.chat.completions.create({
    model: 'gpt-4o',
    tools: TOOLKIT_TOOLS_OPENAI_FORMAT,
    messages: conversationHistory,
    stream: true,
});
```

### Security Considerations

The BYOK pattern has an important security property: the user's API key is never sent to any server controlled by the toolkit. It stays in the browser's memory and is sent directly to the LLM provider's API. However:

1. **Key exposure risk.** If the cockpit is hosted on a public URL, browser DevTools could expose the key. Mitigation: the key is stored in `sessionStorage` (cleared on tab close), never in `localStorage`.

2. **Cost transparency.** Each agent interaction costs the user tokens. The UI must show estimated cost per query and cumulative session cost. A configurable rate limit (e.g., max 100 queries/session) prevents runaway costs.

3. **No key, no agent.** Per INV-OT-008, without a configured API key, the agent panel is hidden and the cockpit functions at 100% capability minus AI features. The agent is a pure enhancement, never a requirement.

### Phase 1 vs Phase 2 Architecture

| Aspect | Phase 1: Browser-Direct | Phase 2: Server-Proxied |
|--------|------------------------|------------------------|
| Backend required | No | Yes (FastAPI) |
| API key location | Browser sessionStorage | Server .env |
| Provider support | Anthropic, OpenAI | Any (including local Ollama) |
| Graph queries | Client-side (graph.json) | Server-side (FalkorDB) |
| Streaming | SSE from LLM API | SSE from backend AG-UI |
| Static export | Works | Does not work |
| Enterprise ready | No (key in browser) | Yes (server-managed keys) |

Phase 1 ships with the core toolkit (WP-6.2-6.5). Phase 2 is implemented when the server layer exists (WP-6.6-6.7).

---

## 7. HCGS Hierarchical Summarization

Code-Craft (2025) [10] introduces **Hierarchical Code Graph Summarization (HCGS)**, a system that generates multi-level summaries of codebases by traversing the code graph bottom-up and summarizing at each hierarchical level. Their evaluation demonstrates **up to 82% relative improvement in top-1 precision** for code retrieval on large codebases compared to flat embedding approaches.

### The Tree-of-Summaries Approach

HCGS operates on the code graph (analogous to the toolkit's project graph) and generates summaries at each level of the hierarchy:

1. **Leaf Summaries (Functions/Methods).** Each function is summarized by an LLM: its purpose, parameters, return value, and key logic. These summaries are typically 2-4 sentences.

2. **File Summaries.** For each file, the leaf summaries of all contained functions are aggregated and an LLM generates a file-level summary that captures the file's overall purpose, its public API, and its role in the module.

3. **Module Summaries.** File summaries are aggregated per module/package, and an LLM generates a module-level summary describing the module's responsibility, key abstractions, and external interfaces.

4. **System Summary.** Module summaries are aggregated into a system-level overview describing the overall architecture, key design patterns, and module interactions.

### Application to Agent Context Building

For the toolkit agent, HCGS solves the **context bootstrapping problem**: when the user first opens the agent and asks "What does this system do?", the agent needs a system-level summary without reading every file. The tree-of-summaries approach provides this by pre-computing summaries at each level of the project graph hierarchy.

**Pre-computation strategy:**

| Level | Summary Source | When Computed | Storage |
|-------|---------------|---------------|---------|
| L0 (System) | Aggregate of L1 summaries | At index time | `graph.json` metadata |
| L1 (Module) | Aggregate of L2 summaries | At index time | `graph.json` node metadata |
| L2 (File) | LLM summary of file content | At index time or on-demand | Server cache or `graph.json` |
| L3 (Function) | LLM summary of function body | On-demand (lazy) | Server cache |

**Agent context assembly:**

When the agent receives a query, it assembles context using the appropriate summary level:

- **Broad questions** ("What does this system do?"): Use L0 system summary (~200 tokens).
- **Module questions** ("How does authentication work?"): Use L1 module summary for auth (~150 tokens) + L2 file summaries for auth files (~100 tokens each).
- **Specific questions** ("What does validate() do?"): Use L3 function summary (~80 tokens) + L2 file context (~100 tokens) + L1 module context (~150 tokens).

This hierarchical approach keeps the agent's context window under 4K tokens for most queries while providing sufficient depth for accurate answers. For complex cross-module queries, the agent uses the Search-Expand-Refine pattern (Section 3) to selectively pull additional context.

### Evaluation Results

Code-Craft's evaluation on 5 codebases totaling 7,531 functions showed [10]:

| Metric | Flat Embeddings | HCGS | Improvement |
|--------|----------------|------|-------------|
| Top-1 Precision | 0.31 | 0.56 | +82% |
| Top-3 Precision | 0.52 | 0.79 | +52% |
| Pass@3 (small repos) | 0.67 | 1.00 | +49% |

The improvement is most pronounced for cross-module queries (questions that require understanding relationships between distant parts of the codebase), which is exactly the type of question a developer exploring an unfamiliar system would ask.

### Integration with Language Server Protocol

A notable technical detail of HCGS is its use of the **Language Server Protocol (LSP)** for language-agnostic code analysis. Rather than building custom parsers for each language, HCGS connects to a running LSP server (e.g., pyright for Python, typescript-language-server for TypeScript) to extract symbol information, references, and documentation.

For the toolkit, this is relevant to WP-6.6 (Project Graph integration): the server-side agent tools can leverage LSP for real-time symbol resolution, go-to-definition, and hover documentation -- enriching the agent's answers with IDE-quality information.

---

## 8. Architecture Recommendation

### 8.1 Phase 1: BYOK Browser-Direct (No Backend)

Phase 1 is the MVP that ships with the core toolkit. It requires zero backend, works in static export mode, and uses the user's own LLM API key.

**Components:**

```
┌──────────────────────────────────────────────────────────────────┐
│                     BROWSER (Static HTML/JS)                      │
│                                                                    │
│  ┌──────────┐    ┌───────────┐    ┌────────────┐                 │
│  │ chat.js  │───>│commands.js│───>│  state.js   │──> 3D Map      │
│  │ Chat UI  │    │ AG-UI     │    │ (pub/sub)   │   Animation    │
│  │          │    │ events    │    │             │                 │
│  └────┬─────┘    └───────────┘    └────────────┘                 │
│       │                                                           │
│       │  stream                                                   │
│       ▼                                                           │
│  ┌──────────┐                                                    │
│  │provider.js│──> Anthropic API (CORS)                           │
│  │ BYOK     │──> OpenAI API (CORS)                               │
│  │          │    Direct browser fetch with user's API key         │
│  └──────────┘                                                    │
│       │                                                           │
│       │  tool calls                                               │
│       ▼                                                           │
│  ┌──────────────────────────────┐                                │
│  │ Client-side Tool Execution   │                                │
│  │                              │                                │
│  │ search_nodes  → graph.json   │                                │
│  │ get_details   → graph.json   │                                │
│  │ get_submap    → graph.json   │                                │
│  │ navigate_to   → state.js     │                                │
│  │ highlight_nodes → state.js   │                                │
│  │ get_metrics   → graph.json   │                                │
│  └──────────────────────────────┘                                │
└──────────────────────────────────────────────────────────────────┘
```

**Limitations of Phase 1:**
- Graph data limited to what is in `graph.json` (no live FalkorDB queries).
- No file content access (L3/L4 code questions require server).
- No HCGS pre-computed summaries (system summary must be embedded in graph.json metadata).
- API key visible in browser memory (acceptable for personal/internal use).

### 8.2 Phase 2: Server-Proxied (Enterprise)

Phase 2 adds a server backend that manages API keys, runs FalkorDB queries, and provides file content access.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        BROWSER                                          │
│  ┌──────────┐    ┌───────────┐    ┌────────────┐                      │
│  │ chat.js  │───>│commands.js│───>│  state.js   │──> 3D Map           │
│  │          │    │ AG-UI SSE │    │             │                      │
│  └────┬─────┘    └───────────┘    └────────────┘                      │
│       │ SSE subscribe                                                  │
│       ▼                                                                │
│  ┌──────────┐                                                         │
│  │ api.js   │──> EventSource('/api/agent/stream')                     │
│  └──────────┘                                                         │
└────────────────────────────────────────────────────────────────────────┘
        │
        │  SSE (AG-UI events)
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        SERVER (FastAPI)                                  │
│  ┌──────────────────────────────────────┐                              │
│  │ routes/agent.py                       │                              │
│  │                                       │                              │
│  │ POST /api/agent/message               │                              │
│  │ GET  /api/agent/stream (SSE)          │                              │
│  └────┬──────────────────────────────────┘                              │
│       │                                                                │
│       ▼                                                                │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────┐          │
│  │ LLM Provider │  │ Project Graph  │  │ File System      │          │
│  │ (server key) │  │ (FalkorDB)     │  │ (source code)    │          │
│  └──────────────┘  └────────────────┘  └──────────────────┘          │
└────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Tool Definitions

The 6 tools exposed to the LLM agent, defined in both Anthropic and OpenAI formats:

```javascript
const TOOLKIT_TOOLS = [
    {
        name: 'search_nodes',
        description: 'Search for nodes in the system graph by name, type, or description. Returns matching nodes with relevance scores.',
        input_schema: {
            type: 'object',
            properties: {
                query: { type: 'string', description: 'Search query (name, keyword, or natural language description)' },
                filters: {
                    type: 'object',
                    properties: {
                        type: { type: 'string', enum: ['package', 'file', 'class', 'function', 'enum', 'constant'] },
                        level: { type: 'integer', minimum: 0, maximum: 4 },
                    },
                },
                limit: { type: 'integer', default: 10, maximum: 50 },
            },
            required: ['query'],
        },
    },
    {
        name: 'navigate_to',
        description: 'Move the 3D camera to focus on a specific node. Optionally drill down to a specific hierarchy level. The map animates smoothly to the target.',
        input_schema: {
            type: 'object',
            properties: {
                node_id: { type: 'string', description: 'ID of the node to navigate to' },
                level: { type: 'integer', minimum: 0, maximum: 4, description: 'Target drill level (0=system, 1=module, 2=file, 3=function, 4=code)' },
            },
            required: ['node_id'],
        },
    },
    {
        name: 'highlight_nodes',
        description: 'Visually highlight a set of nodes on the map with a glow effect. Use to show dependencies, blast radius, related components, etc.',
        input_schema: {
            type: 'object',
            properties: {
                node_ids: { type: 'array', items: { type: 'string' }, description: 'IDs of nodes to highlight' },
                color: { type: 'string', default: '#ff6b6b', description: 'Highlight color (CSS color)' },
                duration_ms: { type: 'integer', default: 5000, description: 'How long to keep the highlight (ms). 0 = persistent until cleared.' },
            },
            required: ['node_ids'],
        },
    },
    {
        name: 'get_details',
        description: 'Get detailed information about a specific node: its type, metadata, metrics (LOC, complexity, coverage), connected nodes, and source location.',
        input_schema: {
            type: 'object',
            properties: {
                node_id: { type: 'string', description: 'ID of the node to inspect' },
            },
            required: ['node_id'],
        },
    },
    {
        name: 'get_submap',
        description: 'Get the subgraph around a node: its children, parents, and connected nodes within a specified depth. Returns nodes and edges.',
        input_schema: {
            type: 'object',
            properties: {
                node_id: { type: 'string', description: 'Center node ID' },
                depth: { type: 'integer', default: 2, maximum: 4, description: 'How many hops to expand' },
                edge_types: { type: 'array', items: { type: 'string' }, description: 'Filter by edge types (e.g., IMPORTS, DEPENDS_ON, CONTAINS)' },
            },
            required: ['node_id'],
        },
    },
    {
        name: 'get_metrics',
        description: 'Get aggregated metrics for a set of nodes: total LOC, average complexity, test coverage, coupling score, etc.',
        input_schema: {
            type: 'object',
            properties: {
                node_ids: { type: 'array', items: { type: 'string' }, description: 'Node IDs to aggregate metrics for' },
                metric_type: { type: 'string', enum: ['loc', 'complexity', 'coverage', 'coupling', 'all'], default: 'all' },
            },
            required: ['node_ids'],
        },
    },
];
```

### 8.4 SSE Streaming with Concurrent Map Animation

The core UX innovation is that map animations happen **concurrently** with text streaming, not sequentially. Implementation:

```javascript
// chat.js -- process streaming response
async function processStream(stream) {
    let currentText = '';

    for await (const event of stream) {
        switch (event.type) {
            case 'content_block_delta':
                // Text chunk -- append to chat bubble
                currentText += event.delta.text;
                updateChatBubble(currentText);
                break;

            case 'tool_use':
                // Tool call -- execute AND animate concurrently
                const toolResult = await executeToolLocally(event.name, event.input);

                // Emit AG-UI custom event for map animation
                if (event.name === 'navigate_to') {
                    state.emit('map.navigate', event.input);
                } else if (event.name === 'highlight_nodes') {
                    state.emit('map.highlight', event.input);
                }

                // Return tool result to continue the conversation
                break;
        }
    }
}
```

The key constraint: map animations (350ms) must not block text streaming. The `state.emit()` call is fire-and-forget -- the animation runs on the next `requestAnimationFrame` cycle while text continues to stream.

### 8.5 System Prompt Template

```
You are an AI assistant embedded in the Ontology Map Toolkit, a 3D interactive
visualization of a software system. You can navigate the map, highlight nodes,
and show the user architectural relationships.

SYSTEM CONTEXT:
{system_summary}  // From HCGS L0 summary or graph.json metadata

AVAILABLE TOOLS:
- search_nodes: Find nodes by name or description
- navigate_to: Move the camera to a node (the user will see the map animate)
- highlight_nodes: Highlight nodes on the map (the user will see them glow)
- get_details: Get full details about a node
- get_submap: Get connected nodes within N hops
- get_metrics: Get code metrics for nodes

GUIDELINES:
1. When explaining relationships, SHOW them on the map using navigate_to + highlight_nodes.
2. Always search before assuming a node exists. Node IDs may differ from what the user says.
3. For blast radius / dependency questions, use get_submap then highlight the affected nodes.
4. Keep answers concise (2-4 paragraphs). The map visualization carries most of the information.
5. If you cannot find relevant nodes, say so honestly rather than speculating.
```

---

## 9. Bibliography

[1] Ko, A. J., DeLine, R., and Venolia, G. (2006). "An Exploratory Study of How Developers Seek, Relate, and Collect Relevant Information During Software Maintenance Tasks." IEEE Transactions on Software Engineering, 32(12), pp. 971-987. DOI: [10.1109/TSE.2006.116](https://doi.org/10.1109/TSE.2006.116).

[2] Cursor Team. (2024). "More Problems." Cursor Blog. URL: [https://cursor.com/en/blog/problems-2024](https://cursor.com/en/blog/problems-2024).

[3] Cursor Team. (2026). "Dynamic Context Discovery." Cursor Blog. URL: [https://cursor.com/blog/dynamic-context-discovery](https://cursor.com/blog/dynamic-context-discovery).

[4] Phan, H. N., Phan, H. N., Nguyen, T. N., and Bui, N. D. Q. (2024). "RepoHyper: Search-Expand-Refine on Semantic Graphs for Repository-Level Code Completion." arXiv preprint arXiv:2403.06095. URL: [https://arxiv.org/abs/2403.06095](https://arxiv.org/abs/2403.06095). Published at FORGE 2025.

[5] Gersteinlab. (2025). "LocAgent: Graph-Guided LLM Agents for Code Localization." In Proceedings of ACL 2025. arXiv:2503.09089. URL: [https://arxiv.org/abs/2503.09089](https://arxiv.org/abs/2503.09089). ACL Anthology: [https://aclanthology.org/2025.acl-long.426/](https://aclanthology.org/2025.acl-long.426/).

[6] AG-UI Protocol. (2025). "AG-UI: The Agent-User Interaction Protocol." Documentation: [https://docs.ag-ui.com/](https://docs.ag-ui.com/). GitHub: [https://github.com/ag-ui-protocol/ag-ui](https://github.com/ag-ui-protocol/ag-ui).

[7] CopilotKit. (2025). "Master the 17 AG-UI Event Types for Building Agents the Right Way." Blog post. URL: [https://www.copilotkit.ai/blog/master-the-17-ag-ui-event-types-for-building-agents-the-right-way](https://www.copilotkit.ai/blog/master-the-17-ag-ui-event-types-for-building-agents-the-right-way).

[8] Willison, S. (2024). "Claude's API Now Supports CORS Requests, Enabling Client-Side Applications." Blog post. URL: [https://simonwillison.net/2024/Aug/23/anthropic-dangerous-direct-browser-access/](https://simonwillison.net/2024/Aug/23/anthropic-dangerous-direct-browser-access/).

[9] OpenAI. (2025). "openai-node: Official JavaScript / TypeScript Library for the OpenAI API." GitHub: [https://github.com/openai/openai-node](https://github.com/openai/openai-node). API Reference: [https://platform.openai.com/docs/api-reference](https://platform.openai.com/docs/api-reference).

[10] Code-Craft Authors. (2025). "Code-Craft: Hierarchical Graph-Based Code Summarization for Enhanced Context Retrieval." arXiv preprint arXiv:2504.08975. URL: [https://arxiv.org/abs/2504.08975](https://arxiv.org/abs/2504.08975).

[11] AG-UI Protocol. (2025). "Events -- Agent User Interaction Protocol." URL: [https://docs.ag-ui.com/concepts/events](https://docs.ag-ui.com/concepts/events).

[12] Anthropic. (2024). "API Release Notes." URL: [https://docs.anthropic.com/en/release-notes/api](https://docs.anthropic.com/en/release-notes/api).

---

*Research document for WP-6.1 (Research: Agent Architecture). This document should be reviewed and approved before implementation of WP-6.2 (Chat UI) begins, per SPEC.md Execution Principle #5: "Research before code."*
