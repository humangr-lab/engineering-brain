/**
 * Plugin Registry — manages installed plugins and their lifecycle.
 * Pure engine module (no React dependency).
 */

import type {
  PluginManifest,
  PluginInstance,
  PluginToHostMessage,
  HostToPluginMessage,
  SerializedNode,
  SerializedEdge,
  OverlayNode,
  OverlayEdge,
  ThemeInfo,
} from "./types";
import type { Node, Edge } from "@/lib/api";

// ─── Serialization ───────────────────────────────────────────────────────────

function serializeNode(node: Node): SerializedNode {
  return {
    id: node.id,
    type: node.type,
    layer: node.layer,
    layerName: node.layerName,
    text: node.text,
    severity: node.severity,
    confidence: node.confidence,
    technologies: node.technologies,
    domains: node.domains,
  };
}

function serializeEdge(edge: Edge): SerializedEdge {
  return {
    from: edge.from,
    to: edge.to,
    type: edge.type,
    weight: edge.weight,
  };
}

// ─── Registry ────────────────────────────────────────────────────────────────

export type PluginEventCallback = (
  pluginId: string,
  event: "ready" | "overlay-changed" | "navigate" | "notification" | "error",
  data?: unknown,
) => void;

export class PluginRegistry {
  private plugins = new Map<string, PluginInstance>();
  private listeners = new Set<PluginEventCallback>();
  private messageHandler: ((event: MessageEvent) => void) | null = null;

  constructor() {
    this.messageHandler = this.handleMessage.bind(this);
    if (typeof window !== "undefined") {
      window.addEventListener("message", this.messageHandler);
    }
  }

  /** Register a listener for plugin events */
  on(cb: PluginEventCallback): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  private emit(
    pluginId: string,
    event: "ready" | "overlay-changed" | "navigate" | "notification" | "error",
    data?: unknown,
  ) {
    for (const cb of this.listeners) {
      try {
        cb(pluginId, event, data);
      } catch {
        // listener error — ignore
      }
    }
  }

  /** Install and start a plugin from its manifest */
  install(manifest: PluginManifest, baseUrl: string): PluginInstance {
    // Validate permissions
    const allowed = new Set(manifest.permissions);
    if (allowed.has("write:overlays") && !allowed.has("read:graph")) {
      // Overlay plugins implicitly need read access
      manifest.permissions.push("read:graph");
    }

    const instance: PluginInstance = {
      manifest,
      iframe: null,
      status: "loading",
      overlayNodes: [],
      overlayEdges: [],
    };

    this.plugins.set(manifest.id, instance);

    // Create sandboxed iframe
    if (typeof document !== "undefined") {
      const iframe = document.createElement("iframe");
      iframe.setAttribute("sandbox", "allow-scripts");
      iframe.style.display = "none";
      iframe.src = `${baseUrl}/${manifest.entryPoint}`;

      iframe.addEventListener("load", () => {
        this.sendToPlugin(manifest.id, {
          type: "init",
          manifest,
          theme: this.getCurrentTheme(),
        });
      });

      iframe.addEventListener("error", () => {
        instance.status = "error";
        instance.error = "Failed to load plugin iframe";
        this.emit(manifest.id, "error", instance.error);
      });

      document.body.appendChild(iframe);
      instance.iframe = iframe;
    }

    return instance;
  }

  /** Stop and uninstall a plugin */
  uninstall(pluginId: string): void {
    const instance = this.plugins.get(pluginId);
    if (!instance) return;

    if (instance.iframe?.parentNode) {
      instance.iframe.parentNode.removeChild(instance.iframe);
    }

    instance.status = "stopped";
    instance.iframe = null;
    instance.overlayNodes = [];
    instance.overlayEdges = [];
    this.plugins.delete(pluginId);
  }

  /** Get a plugin instance */
  get(pluginId: string): PluginInstance | undefined {
    return this.plugins.get(pluginId);
  }

  /** Get all installed plugins */
  getAll(): PluginInstance[] {
    return Array.from(this.plugins.values());
  }

  /** Get all overlay nodes across all plugins */
  getAllOverlayNodes(): OverlayNode[] {
    const result: OverlayNode[] = [];
    for (const instance of this.plugins.values()) {
      if (instance.status === "ready") {
        result.push(...instance.overlayNodes);
      }
    }
    return result;
  }

  /** Get all overlay edges across all plugins */
  getAllOverlayEdges(): OverlayEdge[] {
    const result: OverlayEdge[] = [];
    for (const instance of this.plugins.values()) {
      if (instance.status === "ready") {
        result.push(...instance.overlayEdges);
      }
    }
    return result;
  }

  /** Broadcast graph data to all plugins with read:graph permission */
  broadcastGraph(nodes: Node[], edges: Edge[]): void {
    const serializedNodes = nodes.map(serializeNode);
    const serializedEdges = edges.map(serializeEdge);

    for (const [id, instance] of this.plugins) {
      if (
        instance.status === "ready" &&
        instance.manifest.permissions.includes("read:graph")
      ) {
        this.sendToPlugin(id, {
          type: "graph:snapshot",
          nodes: serializedNodes,
          edges: serializedEdges,
        });
      }
    }
  }

  /** Broadcast selection change to plugins with read:selection permission */
  broadcastSelection(nodeId: string | null): void {
    for (const [id, instance] of this.plugins) {
      if (
        instance.status === "ready" &&
        instance.manifest.permissions.includes("read:selection")
      ) {
        this.sendToPlugin(id, { type: "selection:changed", nodeId });
      }
    }
  }

  /** Broadcast graph version update to subscribers */
  broadcastGraphUpdate(version: number): void {
    for (const [id, instance] of this.plugins) {
      if (
        instance.status === "ready" &&
        instance.manifest.permissions.includes("subscribe:events")
      ) {
        this.sendToPlugin(id, { type: "graph:updated", version });
      }
    }
  }

  /** Broadcast theme change */
  broadcastTheme(theme: ThemeInfo): void {
    for (const [id, instance] of this.plugins) {
      if (instance.status === "ready") {
        this.sendToPlugin(id, { type: "theme:changed", theme });
      }
    }
  }

  /** Send a message to a specific plugin */
  private sendToPlugin(pluginId: string, message: HostToPluginMessage): void {
    const instance = this.plugins.get(pluginId);
    if (!instance?.iframe?.contentWindow) return;
    instance.iframe.contentWindow.postMessage(message, "*");
  }

  /** Handle incoming messages from plugin iframes */
  private handleMessage(event: MessageEvent): void {
    const msg = event.data as PluginToHostMessage;
    if (!msg || typeof msg.type !== "string") return;

    // Find which plugin sent this message
    let senderId: string | null = null;
    for (const [id, instance] of this.plugins) {
      if (instance.iframe?.contentWindow === event.source) {
        senderId = id;
        break;
      }
    }
    if (!senderId) return;

    const instance = this.plugins.get(senderId)!;

    switch (msg.type) {
      case "ready":
        instance.status = "ready";
        this.emit(senderId, "ready");
        break;

      case "request:graph":
        // Plugin is requesting graph data — will be fulfilled by the React layer
        this.emit(senderId, "ready", { request: "graph" });
        break;

      case "request:selection":
        this.emit(senderId, "ready", { request: "selection" });
        break;

      case "overlay:add-node":
        if (instance.manifest.permissions.includes("write:overlays")) {
          instance.overlayNodes.push(msg.node);
          this.emit(senderId, "overlay-changed");
        }
        break;

      case "overlay:add-edge":
        if (instance.manifest.permissions.includes("write:overlays")) {
          instance.overlayEdges.push(msg.edge);
          this.emit(senderId, "overlay-changed");
        }
        break;

      case "overlay:clear":
        if (instance.manifest.permissions.includes("write:overlays")) {
          instance.overlayNodes = [];
          instance.overlayEdges = [];
          this.emit(senderId, "overlay-changed");
        }
        break;

      case "navigate:node":
        this.emit(senderId, "navigate", msg.nodeId);
        break;

      case "notification":
        this.emit(senderId, "notification", {
          message: msg.message,
          level: msg.level,
        });
        break;
    }
  }

  private getCurrentTheme(): ThemeInfo {
    if (typeof document === "undefined") {
      return { mode: "dark", accent: "#10b981", surface: "#1a1a2e", text: "#e2e8f0", border: "#2d2d44" };
    }
    const style = getComputedStyle(document.documentElement);
    return {
      mode: document.documentElement.classList.contains("light") ? "light" : "dark",
      accent: style.getPropertyValue("--color-accent").trim() || "#10b981",
      surface: style.getPropertyValue("--color-surface-0").trim() || "#1a1a2e",
      text: style.getPropertyValue("--color-text-primary").trim() || "#e2e8f0",
      border: style.getPropertyValue("--color-border-subtle").trim() || "#2d2d44",
    };
  }

  /** Cleanup — call on app unmount */
  destroy(): void {
    if (this.messageHandler && typeof window !== "undefined") {
      window.removeEventListener("message", this.messageHandler);
    }
    for (const id of this.plugins.keys()) {
      this.uninstall(id);
    }
  }
}

/** Singleton registry */
let _registry: PluginRegistry | null = null;

export function getPluginRegistry(): PluginRegistry {
  if (!_registry) {
    _registry = new PluginRegistry();
  }
  return _registry;
}
