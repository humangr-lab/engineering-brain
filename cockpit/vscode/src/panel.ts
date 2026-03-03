import * as vscode from "vscode";
import * as cp from "child_process";
import * as path from "path";

interface GraphData {
  nodes: Array<{
    id: string;
    label: string;
    node_type: string;
    file_path?: string;
    line_count?: number;
    layer?: string;
  }>;
  edges: Array<{
    from: string;
    to: string;
    edge_type: string;
  }>;
  adapters_used: string[];
}

export class OntologyMapPanel {
  public static currentPanel: OntologyMapPanel | undefined;
  private static readonly viewType = "ontologyMap";

  private readonly panel: vscode.WebviewPanel;
  private readonly extensionUri: vscode.Uri;
  private disposables: vscode.Disposable[] = [];
  private lastGraphData: GraphData | null = null;
  private refreshDebounce: NodeJS.Timeout | null = null;

  private constructor(
    panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
  ) {
    this.panel = panel;
    this.extensionUri = extensionUri;

    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

    // Handle messages from webview
    this.panel.webview.onDidReceiveMessage(
      (message) => this.handleMessage(message),
      null,
      this.disposables,
    );

    // Initial load
    this.refresh();
  }

  public static createOrShow(context: vscode.ExtensionContext) {
    const column = vscode.ViewColumn.Beside;

    if (OntologyMapPanel.currentPanel) {
      OntologyMapPanel.currentPanel.panel.reveal(column);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      OntologyMapPanel.viewType,
      "Ontology Map",
      column,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [context.extensionUri],
      },
    );

    OntologyMapPanel.currentPanel = new OntologyMapPanel(
      panel,
      context.extensionUri,
    );
  }

  public async refresh() {
    this.panel.webview.html = this.getLoadingHtml();

    try {
      const data = await this.runOntologyMap();
      this.lastGraphData = data;
      this.panel.webview.html = this.getWebviewHtml(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      this.panel.webview.html = this.getErrorHtml(message);
    }
  }

  public onFileSaved() {
    // Debounce refresh on file save (wait 2s after last save)
    if (this.refreshDebounce) {
      clearTimeout(this.refreshDebounce);
    }
    this.refreshDebounce = setTimeout(() => {
      if (this.lastGraphData) {
        // Send pulse event to webview instead of full refresh
        this.panel.webview.postMessage({ type: "pulse" });
      }
    }, 500);
  }

  private async runOntologyMap(): Promise<GraphData> {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
      throw new Error("No workspace folder open");
    }

    const config = vscode.workspace.getConfiguration("ontology-map");
    const binaryPath = config.get<string>("binaryPath", "ontology-map");
    const maxFiles = config.get<number>("maxFiles", 5000);

    return new Promise((resolve, reject) => {
      const args = ["--json", "--max-files", String(maxFiles), "--no-watch"];
      const cwd = workspaceFolder.uri.fsPath;

      const proc = cp.execFile(
        binaryPath,
        args,
        {
          cwd,
          maxBuffer: 50 * 1024 * 1024, // 50MB buffer for large graphs
          timeout: 30000,
        },
        (error, stdout, stderr) => {
          if (error) {
            if ((error as NodeJS.ErrnoException).code === "ENOENT") {
              reject(
                new Error(
                  `ontology-map binary not found at "${binaryPath}". ` +
                    "Install it with: cargo install ontology-map-tui\n" +
                    "Or set the path in Settings > Ontology Map > Binary Path",
                ),
              );
            } else if (error.killed || (error as { signal?: string }).signal === "SIGTERM") {
              reject(
                new Error(
                  "ontology-map timed out (30s). Your project may be too large.\n" +
                    "Try reducing maxFiles in Settings > Ontology Map > Max Files",
                ),
              );
            } else {
              reject(new Error(`ontology-map failed: ${stderr || error.message}`));
            }
            return;
          }

          try {
            const data = JSON.parse(stdout);
            resolve(data);
          } catch {
            reject(new Error("Failed to parse ontology-map output as JSON"));
          }
        },
      );

      // Kill if it takes too long
      setTimeout(() => proc.kill(), 30000);
    });
  }

  private handleMessage(message: { type: string; nodeId?: string; filePath?: string }) {
    switch (message.type) {
      case "nodeClick":
        if (message.filePath) {
          this.openFile(message.filePath);
        }
        break;
      case "requestRefresh":
        this.refresh();
        break;
    }
  }

  private async openFile(filePath: string) {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) return;

    const wsRoot = workspaceFolder.uri.fsPath;
    const fullPath = path.resolve(wsRoot, filePath);

    // SEC-001: Prevent path traversal — file must stay within workspace
    if (!fullPath.startsWith(wsRoot + path.sep) && fullPath !== wsRoot) {
      vscode.window.showWarningMessage(`Blocked path traversal attempt: ${filePath}`);
      return;
    }

    try {
      const doc = await vscode.workspace.openTextDocument(
        vscode.Uri.file(fullPath),
      );
      await vscode.window.showTextDocument(doc, vscode.ViewColumn.One);
    } catch {
      vscode.window.showWarningMessage(`Could not open file: ${filePath}`);
    }
  }

  private getLoadingHtml(): string {
    return `<!DOCTYPE html>
<html><head><style>
  body { background: #0f172a; color: #94a3b8; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; font-family: system-ui; }
  .spinner { width: 40px; height: 40px; border: 3px solid #1e293b; border-top-color: #64c8b4; border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .text { margin-top: 16px; font-size: 14px; }
</style></head><body>
  <div style="text-align:center"><div class="spinner"></div><div class="text">Analyzing project...</div></div>
</body></html>`;
  }

  private getErrorHtml(message: string): string {
    const escaped = message
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\n/g, "<br>");
    return `<!DOCTYPE html>
<html><head><style>
  body { background: #0f172a; color: #f87171; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; font-family: system-ui; padding: 20px; box-sizing: border-box; }
  .error { max-width: 500px; text-align: center; }
  h2 { color: #f87171; margin-bottom: 12px; }
  p { color: #94a3b8; line-height: 1.6; font-size: 13px; }
  button { background: #1e293b; color: #64c8b4; border: 1px solid #334155; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; margin-top: 12px; }
  button:hover { background: #334155; }
</style></head><body>
  <div class="error">
    <h2>Failed to analyze project</h2>
    <p>${escaped}</p>
    <button onclick="vscode.postMessage({type:'requestRefresh'})">Retry</button>
  </div>
  <script>const vscode = acquireVsCodeApi();</script>
</body></html>`;
  }

  private getWebviewHtml(data: GraphData): string {
    const nodesJson = JSON.stringify(data.nodes);
    const edgesJson = JSON.stringify(data.edges);
    const adapters = data.adapters_used.join(", ");

    return `<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0f172a; overflow: hidden; font-family: system-ui, -apple-system, sans-serif; }
  canvas { display: block; }
  #hud {
    position: fixed; top: 12px; left: 12px; color: #94a3b8; font-size: 12px;
    pointer-events: none; z-index: 10;
  }
  #hud .title { color: #64c8b4; font-size: 14px; font-weight: 600; margin-bottom: 4px; }
  #hud .stat { color: #64748b; }
  #hud .stat b { color: #e2e8f0; }
  #tooltip {
    position: fixed; display: none; background: #1e293b; border: 1px solid #334155;
    border-radius: 8px; padding: 10px 14px; color: #e2e8f0; font-size: 12px;
    pointer-events: none; z-index: 20; max-width: 300px; box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  }
  #tooltip .label { font-weight: 600; color: #f8fafc; margin-bottom: 4px; }
  #tooltip .type { color: #64c8b4; font-size: 11px; }
  #tooltip .file { color: #94a3b8; font-size: 11px; margin-top: 2px; }
  #tooltip .hint { color: #475569; font-size: 10px; margin-top: 6px; border-top: 1px solid #334155; padding-top: 4px; }
  #toolbar {
    position: fixed; bottom: 12px; left: 50%; transform: translateX(-50%);
    display: flex; gap: 6px; z-index: 10;
  }
  #toolbar button {
    background: #1e293b; color: #94a3b8; border: 1px solid #334155;
    padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px;
    transition: all 0.15s;
  }
  #toolbar button:hover { background: #334155; color: #e2e8f0; }
  #toolbar button.active { background: #164e63; color: #64c8b4; border-color: #64c8b4; }
</style>
</head><body>
<div id="hud">
  <div class="title">Ontology Map</div>
  <div class="stat"><b>${data.nodes.length}</b> nodes, <b>${data.edges.length}</b> edges</div>
  <div class="stat">${adapters}</div>
</div>
<div id="tooltip"></div>
<div id="toolbar">
  <button id="btn-labels" class="active" title="Toggle labels">Labels</button>
  <button id="btn-edges" class="active" title="Toggle edges">Edges</button>
  <button id="btn-fit" title="Fit to view">Fit</button>
  <button id="btn-refresh" title="Re-analyze project">Refresh</button>
</div>
<canvas id="canvas"></canvas>

<script>
const vscode = acquireVsCodeApi();
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const tooltip = document.getElementById('tooltip');

// Graph data
const rawNodes = ${nodesJson};
const rawEdges = ${edgesJson};

// Color palette (same as TUI)
const TYPE_COLORS = {
  'module':      '#64b4ff', 'namespace':   '#64b4ff',
  'class':       '#b482ff', 'function':    '#78dc8c',
  'method':      '#5ac878', 'export':      '#64c8c8',
  'component':   '#ffb464', 'hook':        '#ff8cc8',
  'struct':      '#dca0ff', 'enum':        '#c88cdc',
  'trait':       '#8cc8ff', 'interface':   '#8cc8ff',
  'type':        '#a0b4dc', 'constructor': '#96e696',
  'service':     '#ff8c64', 'network':     '#c8c864',
  'volume':      '#b4b4b4',
};
const DEFAULT_COLOR = '#a0a0a0';

function typeColor(t) { return TYPE_COLORS[t] || DEFAULT_COLOR; }

// Build node objects with positions
const nodes = rawNodes.map((n, i) => ({
  ...n,
  x: 0, y: 0, vx: 0, vy: 0,
  color: typeColor(n.node_type),
  radius: n.node_type === 'module' || n.node_type === 'namespace' ? 6 : 4,
}));

// Build edge index pairs
const nodeIndex = {};
nodes.forEach((n, i) => { nodeIndex[n.id] = i; });
const edges = rawEdges
  .filter(e => nodeIndex[e.from] !== undefined && nodeIndex[e.to] !== undefined)
  .map(e => ({ from: nodeIndex[e.from], to: nodeIndex[e.to], type: e.edge_type }));

// ─── Force simulation ───────────────────────────────────────
const N = nodes.length;

// Initialize positions in a circle
for (let i = 0; i < N; i++) {
  const angle = (2 * Math.PI * i) / N;
  const r = Math.sqrt(N) * 12;
  nodes[i].x = Math.cos(angle) * r;
  nodes[i].y = Math.sin(angle) * r;
}

// Run force simulation (limited iterations for responsiveness)
const iterations = Math.min(150, Math.max(50, 300 - N));
const k = Math.sqrt((N * 800) / Math.max(N, 1)); // optimal distance

for (let iter = 0; iter < iterations; iter++) {
  const temp = Math.max(0.1, 1.0 - iter / iterations) * k * 0.4;

  // Repulsive forces (use spatial hashing for large graphs)
  if (N < 2000) {
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const f = (k * k) / d;
        const fx = (dx / d) * f;
        const fy = (dy / d) * f;
        nodes[i].vx += fx; nodes[i].vy += fy;
        nodes[j].vx -= fx; nodes[j].vy -= fy;
      }
    }
  } else {
    // For very large graphs, use random sampling
    for (let i = 0; i < N; i++) {
      for (let s = 0; s < 20; s++) {
        const j = Math.floor(Math.random() * N);
        if (j === i) continue;
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const f = (k * k) / d * (N / 20);
        nodes[i].vx += (dx / d) * f;
        nodes[i].vy += (dy / d) * f;
      }
    }
  }

  // Attractive forces (edges)
  for (const e of edges) {
    const a = nodes[e.from], b = nodes[e.to];
    const dx = a.x - b.x, dy = a.y - b.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
    const f = (d * d) / k;
    const fx = (dx / d) * f, fy = (dy / d) * f;
    a.vx -= fx; a.vy -= fy;
    b.vx += fx; b.vy += fy;
  }

  // Apply with temperature clamping
  for (const n of nodes) {
    const d = Math.sqrt(n.vx * n.vx + n.vy * n.vy) || 0.01;
    const cap = Math.min(d, temp);
    n.x += (n.vx / d) * cap;
    n.y += (n.vy / d) * cap;
    n.vx = 0; n.vy = 0;
  }
}

// ─── Viewport ───────────────────────────────────────────────
let viewX = 0, viewY = 0, viewScale = 1;
let showLabels = true, showEdges = true;
let hoveredNode = null, selectedNode = null;
let isDragging = false, lastMouse = {x:0, y:0};

function fitView() {
  if (N === 0) return;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of nodes) {
    minX = Math.min(minX, n.x); minY = Math.min(minY, n.y);
    maxX = Math.max(maxX, n.x); maxY = Math.max(maxY, n.y);
  }
  const pad = 50;
  const w = maxX - minX + pad * 2;
  const h = maxY - minY + pad * 2;
  viewScale = Math.min(canvas.width / w, canvas.height / h) * 0.9;
  viewX = -(minX + maxX) / 2 * viewScale + canvas.width / 2;
  viewY = -(minY + maxY) / 2 * viewScale + canvas.height / 2;
}

// ─── Rendering ──────────────────────────────────────────────
function resize() {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = window.innerWidth * dpr;
  canvas.height = window.innerHeight * dpr;
  canvas.style.width = window.innerWidth + 'px';
  canvas.style.height = window.innerHeight + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function toScreen(x, y) {
  return { x: x * viewScale + viewX, y: y * viewScale + viewY };
}

function toWorld(sx, sy) {
  return { x: (sx - viewX) / viewScale, y: (sy - viewY) / viewScale };
}

function render() {
  ctx.fillStyle = '#0f172a';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Edges
  if (showEdges) {
    ctx.lineWidth = 0.5;
    ctx.globalAlpha = 0.25;
    for (const e of edges) {
      const a = toScreen(nodes[e.from].x, nodes[e.from].y);
      const b = toScreen(nodes[e.to].x, nodes[e.to].y);
      ctx.strokeStyle = e.type === 'contains' ? '#1e3a5f' : '#2a3a4f';
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  // Nodes
  const labelThreshold = 0.8;
  for (let i = 0; i < N; i++) {
    const n = nodes[i];
    const s = toScreen(n.x, n.y);
    const r = n.radius * Math.max(0.5, viewScale * 0.3);
    const isHovered = hoveredNode === i;
    const isSelected = selectedNode === i;

    // Glow for hovered/selected
    if (isHovered || isSelected) {
      ctx.shadowBlur = 12;
      ctx.shadowColor = n.color;
    }

    ctx.fillStyle = isSelected ? '#ffffff' : isHovered ? '#e2e8f0' : n.color;
    ctx.globalAlpha = isHovered || isSelected ? 1 : 0.8;
    ctx.beginPath();
    ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
    ctx.fill();

    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;

    // Labels
    if (showLabels && viewScale > labelThreshold) {
      const label = n.label.length > 20 ? n.label.slice(0, 17) + '...' : n.label;
      ctx.font = isHovered ? 'bold 11px system-ui' : '10px system-ui';
      ctx.fillStyle = isHovered ? '#f8fafc' : '#64748b';
      ctx.fillText(label, s.x + r + 3, s.y + 3);
    }
  }

  if (document.visibilityState !== 'hidden') {
    requestAnimationFrame(render);
  }
}

// Resume rendering when tab becomes visible
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') requestAnimationFrame(render);
});

// ─── Mouse interaction ──────────────────────────────────────
function findNode(mx, my) {
  const world = toWorld(mx, my);
  let closest = null, minDist = 15 / viewScale;
  for (let i = 0; i < N; i++) {
    const dx = nodes[i].x - world.x, dy = nodes[i].y - world.y;
    const d = Math.sqrt(dx * dx + dy * dy);
    if (d < minDist) { minDist = d; closest = i; }
  }
  return closest;
}

canvas.addEventListener('mousemove', (e) => {
  if (isDragging) {
    viewX += e.clientX - lastMouse.x;
    viewY += e.clientY - lastMouse.y;
    lastMouse = {x: e.clientX, y: e.clientY};
    tooltip.style.display = 'none';
    return;
  }

  const node = findNode(e.clientX, e.clientY);
  hoveredNode = node;
  canvas.style.cursor = node !== null ? 'pointer' : 'grab';

  if (node !== null) {
    const n = nodes[node];
    let html = '<div class="label">' + escapeHtml(n.label) + '</div>';
    html += '<div class="type">' + escapeHtml(n.node_type) + '</div>';
    if (n.file_path) html += '<div class="file">' + escapeHtml(n.file_path) + '</div>';
    if (n.line_count) html += '<div class="file">' + n.line_count + ' lines</div>';
    if (n.file_path) html += '<div class="hint">Click to open file</div>';
    tooltip.innerHTML = html;
    tooltip.style.display = 'block';
    tooltip.style.left = Math.min(e.clientX + 12, window.innerWidth - 320) + 'px';
    tooltip.style.top = Math.min(e.clientY + 12, window.innerHeight - 100) + 'px';
  } else {
    tooltip.style.display = 'none';
  }
});

canvas.addEventListener('mousedown', (e) => {
  const node = findNode(e.clientX, e.clientY);
  if (node !== null) {
    selectedNode = node;
    const n = nodes[node];
    if (n.file_path) {
      vscode.postMessage({ type: 'nodeClick', nodeId: n.id, filePath: n.file_path });
    }
  } else {
    isDragging = true;
    lastMouse = {x: e.clientX, y: e.clientY};
    canvas.style.cursor = 'grabbing';
  }
});

canvas.addEventListener('mouseup', () => {
  isDragging = false;
  canvas.style.cursor = hoveredNode !== null ? 'pointer' : 'grab';
});

canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  const mx = e.clientX, my = e.clientY;
  viewX = mx - (mx - viewX) * factor;
  viewY = my - (my - viewY) * factor;
  viewScale *= factor;
}, { passive: false });

// ─── Toolbar ────────────────────────────────────────────────
document.getElementById('btn-labels').addEventListener('click', function() {
  showLabels = !showLabels;
  this.classList.toggle('active');
});
document.getElementById('btn-edges').addEventListener('click', function() {
  showEdges = !showEdges;
  this.classList.toggle('active');
});
document.getElementById('btn-fit').addEventListener('click', fitView);
document.getElementById('btn-refresh').addEventListener('click', () => {
  vscode.postMessage({ type: 'requestRefresh' });
});

// ─── Messages from extension ────────────────────────────────
window.addEventListener('message', (e) => {
  if (e.data.type === 'pulse') {
    // Flash effect on save — brief white flash on all nodes
    for (const n of nodes) { n._pulse = Date.now(); }
    setTimeout(() => { for (const n of nodes) { delete n._pulse; } }, 500);
  }
});

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

// ─── Init ───────────────────────────────────────────────────
resize();
fitView();
render();
window.addEventListener('resize', () => { resize(); fitView(); });
</script>
</body></html>`;
  }

  private dispose() {
    OntologyMapPanel.currentPanel = undefined;
    this.panel.dispose();
    while (this.disposables.length) {
      const d = this.disposables.pop();
      if (d) d.dispose();
    }
  }
}
