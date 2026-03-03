/**
 * Plugin System — type definitions.
 *
 * Follows Figma's plugin model:
 * - Plugins run in sandboxed iframes
 * - Communication via postMessage
 * - Manifest declares permissions
 */

// ─── Manifest ────────────────────────────────────────────────────────────────

export interface PluginManifest {
  /** Unique plugin ID (reverse-domain: "com.example.my-plugin") */
  id: string;
  /** Display name */
  name: string;
  /** Version (semver) */
  version: string;
  /** Short description */
  description: string;
  /** Author name */
  author: string;
  /** Plugin entry point — relative path to HTML file */
  entryPoint: string;
  /** Icon URL (data: URI or relative path) */
  icon?: string;
  /** Permissions the plugin requests */
  permissions: PluginPermission[];
  /** Minimum host version required */
  minHostVersion?: string;
}

export type PluginPermission =
  | "read:graph"        // Read nodes + edges
  | "read:selection"    // Read current selection
  | "write:overlays"    // Add overlay nodes/edges (visual only)
  | "subscribe:events"  // Subscribe to graph change events
  | "ui:panel"          // Show a panel in the UI
  | "ui:toolbar";       // Add toolbar button

// ─── Message Protocol ────────────────────────────────────────────────────────

/** Messages FROM host TO plugin */
export type HostToPluginMessage =
  | { type: "init"; manifest: PluginManifest; theme: ThemeInfo }
  | { type: "graph:snapshot"; nodes: SerializedNode[]; edges: SerializedEdge[] }
  | { type: "selection:changed"; nodeId: string | null }
  | { type: "graph:updated"; version: number }
  | { type: "theme:changed"; theme: ThemeInfo };

/** Messages FROM plugin TO host */
export type PluginToHostMessage =
  | { type: "ready" }
  | { type: "request:graph" }
  | { type: "request:selection" }
  | { type: "overlay:add-node"; node: OverlayNode }
  | { type: "overlay:add-edge"; edge: OverlayEdge }
  | { type: "overlay:clear" }
  | { type: "ui:resize"; width: number; height: number }
  | { type: "navigate:node"; nodeId: string }
  | { type: "notification"; message: string; level: "info" | "warning" | "error" };

// ─── Serialized Types (JSON-safe for postMessage) ────────────────────────────

export interface SerializedNode {
  id: string;
  type: string;
  layer: number;
  layerName: string;
  text: string;
  severity: string;
  confidence: number;
  technologies: string[];
  domains: string[];
}

export interface SerializedEdge {
  from: string;
  to: string;
  type: string;
  weight?: number;
}

// ─── Overlay Types ───────────────────────────────────────────────────────────

export interface OverlayNode {
  id: string;
  label: string;
  color: string;
  /** Attach to existing node ID (positions near it) */
  attachTo?: string;
}

export interface OverlayEdge {
  from: string;
  to: string;
  color: string;
  dashed?: boolean;
}

// ─── Theme ───────────────────────────────────────────────────────────────────

export interface ThemeInfo {
  mode: "dark" | "light";
  accent: string;
  surface: string;
  text: string;
  border: string;
}

// ─── Runtime State ───────────────────────────────────────────────────────────

export interface PluginInstance {
  manifest: PluginManifest;
  iframe: HTMLIFrameElement | null;
  status: "loading" | "ready" | "error" | "stopped";
  overlayNodes: OverlayNode[];
  overlayEdges: OverlayEdge[];
  error?: string;
}
