/**
 * Plugin SDK — lightweight API for plugin authors.
 *
 * Usage in plugin HTML:
 * ```html
 * <script type="module">
 *   import { OntologyMapPlugin } from './sdk.js';
 *
 *   const plugin = new OntologyMapPlugin();
 *
 *   plugin.on('graph', (nodes, edges) => {
 *     console.log(`Got ${nodes.length} nodes`);
 *   });
 *
 *   plugin.on('selection', (nodeId) => {
 *     console.log(`Selected: ${nodeId}`);
 *   });
 *
 *   plugin.requestGraph();
 * ```
 */

import type {
  HostToPluginMessage,
  PluginToHostMessage,
  SerializedNode,
  SerializedEdge,
  OverlayNode,
  OverlayEdge,
  ThemeInfo,
  PluginManifest,
} from "./types";

type GraphCallback = (nodes: SerializedNode[], edges: SerializedEdge[]) => void;
type SelectionCallback = (nodeId: string | null) => void;
type ThemeCallback = (theme: ThemeInfo) => void;
type UpdateCallback = (version: number) => void;

export class OntologyMapPlugin {
  private graphCallbacks: GraphCallback[] = [];
  private selectionCallbacks: SelectionCallback[] = [];
  private themeCallbacks: ThemeCallback[] = [];
  private updateCallbacks: UpdateCallback[] = [];
  private _manifest: PluginManifest | null = null;
  private _theme: ThemeInfo | null = null;

  constructor() {
    window.addEventListener("message", this.handleMessage.bind(this));
    this.send({ type: "ready" });
  }

  /** Current manifest (set after init) */
  get manifest(): PluginManifest | null {
    return this._manifest;
  }

  /** Current theme (set after init) */
  get theme(): ThemeInfo | null {
    return this._theme;
  }

  /** Subscribe to graph data */
  on(event: "graph", cb: GraphCallback): void;
  on(event: "selection", cb: SelectionCallback): void;
  on(event: "theme", cb: ThemeCallback): void;
  on(event: "update", cb: UpdateCallback): void;
  on(event: string, cb: GraphCallback | SelectionCallback | ThemeCallback | UpdateCallback): void {
    switch (event) {
      case "graph":
        this.graphCallbacks.push(cb as GraphCallback);
        break;
      case "selection":
        this.selectionCallbacks.push(cb as SelectionCallback);
        break;
      case "theme":
        this.themeCallbacks.push(cb as ThemeCallback);
        break;
      case "update":
        this.updateCallbacks.push(cb as UpdateCallback);
        break;
    }
  }

  /** Request the current graph data */
  requestGraph(): void {
    this.send({ type: "request:graph" });
  }

  /** Request the current selection */
  requestSelection(): void {
    this.send({ type: "request:selection" });
  }

  /** Add an overlay node */
  addOverlayNode(node: OverlayNode): void {
    this.send({ type: "overlay:add-node", node });
  }

  /** Add an overlay edge */
  addOverlayEdge(edge: OverlayEdge): void {
    this.send({ type: "overlay:add-edge", edge });
  }

  /** Clear all overlays from this plugin */
  clearOverlays(): void {
    this.send({ type: "overlay:clear" });
  }

  /** Navigate to a node */
  navigateToNode(nodeId: string): void {
    this.send({ type: "navigate:node", nodeId });
  }

  /** Show a notification in the host */
  notify(message: string, level: "info" | "warning" | "error" = "info"): void {
    this.send({ type: "notification", message, level });
  }

  /** Request iframe resize */
  resize(width: number, height: number): void {
    this.send({ type: "ui:resize", width, height });
  }

  private send(msg: PluginToHostMessage): void {
    window.parent.postMessage(msg, "*");
  }

  private handleMessage(event: MessageEvent): void {
    const msg = event.data as HostToPluginMessage;
    if (!msg || typeof msg.type !== "string") return;

    switch (msg.type) {
      case "init":
        this._manifest = msg.manifest;
        this._theme = msg.theme;
        break;
      case "graph:snapshot":
        for (const cb of this.graphCallbacks) cb(msg.nodes, msg.edges);
        break;
      case "selection:changed":
        for (const cb of this.selectionCallbacks) cb(msg.nodeId);
        break;
      case "graph:updated":
        for (const cb of this.updateCallbacks) cb(msg.version);
        break;
      case "theme:changed":
        this._theme = msg.theme;
        for (const cb of this.themeCallbacks) cb(msg.theme);
        break;
    }
  }
}
