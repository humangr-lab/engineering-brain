/**
 * Plugin Manager Panel — install, enable, disable plugins.
 * Shows installed plugins, their status, and overlay indicators.
 */

import { useState, useCallback, useEffect } from "react";
import {
  Puzzle,
  X,
  Play,
  Square,
  Trash2,
  AlertCircle,
  CheckCircle,
  Loader2,
} from "lucide-react";
import {
  getPluginRegistry,
  type PluginManifest,
  type PluginInstance,
} from "@/lib/plugins";

interface PluginPanelProps {
  active: boolean;
  onToggle: () => void;
}

/** Built-in demo plugin manifests for starter templates */
const STARTER_PLUGINS: PluginManifest[] = [
  {
    id: "com.ontology-map.complexity-heatmap",
    name: "Complexity Heatmap",
    version: "1.0.0",
    description: "Overlay showing cyclomatic complexity per module",
    author: "Ontology Map Team",
    entryPoint: "plugins/complexity-heatmap/index.html",
    permissions: ["read:graph", "write:overlays", "subscribe:events"],
  },
  {
    id: "com.ontology-map.dependency-lint",
    name: "Dependency Linter",
    version: "1.0.0",
    description: "Detect circular dependencies and unused imports",
    author: "Ontology Map Team",
    entryPoint: "plugins/dependency-lint/index.html",
    permissions: ["read:graph", "write:overlays", "ui:panel"],
  },
  {
    id: "com.ontology-map.api-surface",
    name: "API Surface Analyzer",
    version: "1.0.0",
    description: "Highlight public API surface and breaking change risk",
    author: "Ontology Map Team",
    entryPoint: "plugins/api-surface/index.html",
    permissions: ["read:graph", "read:selection", "write:overlays"],
  },
];

function StatusIcon({ status }: { status: PluginInstance["status"] }) {
  switch (status) {
    case "loading":
      return <Loader2 className="h-3 w-3 animate-spin text-[var(--color-accent)]" />;
    case "ready":
      return <CheckCircle className="h-3 w-3 text-[var(--color-success)]" />;
    case "error":
      return <AlertCircle className="h-3 w-3 text-[var(--color-destructive)]" />;
    case "stopped":
      return <Square className="h-3 w-3 text-[var(--color-text-tertiary)]" />;
  }
}

export function PluginPanel({ active, onToggle }: PluginPanelProps) {
  const [plugins, setPlugins] = useState<PluginInstance[]>([]);
  const registry = getPluginRegistry();

  // Sync plugin list
  const refreshPlugins = useCallback(() => {
    setPlugins([...registry.getAll()]);
  }, [registry]);

  useEffect(() => {
    refreshPlugins();
    const unsub = registry.on(() => refreshPlugins());
    return unsub;
  }, [registry, refreshPlugins]);

  const handleInstall = useCallback(
    (manifest: PluginManifest) => {
      if (registry.get(manifest.id)) return; // already installed
      registry.install(manifest, window.location.origin);
      refreshPlugins();
    },
    [registry, refreshPlugins],
  );

  const handleUninstall = useCallback(
    (pluginId: string) => {
      registry.uninstall(pluginId);
      refreshPlugins();
    },
    [registry, refreshPlugins],
  );

  if (!active) {
    return (
      <button
        onClick={onToggle}
        className="glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
        title="Plugins"
      >
        <Puzzle className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Plugins</span>
        {plugins.length > 0 && (
          <span className="rounded-full bg-[var(--color-accent)] px-1.5 text-[9px] text-white">
            {plugins.length}
          </span>
        )}
      </button>
    );
  }

  const installedIds = new Set(plugins.map((p) => p.manifest.id));
  const availableStarters = STARTER_PLUGINS.filter(
    (s) => !installedIds.has(s.id),
  );

  return (
    <div className="absolute right-4 top-12 z-20 w-[280px]">
      <div className="glass rounded-[var(--radius-md)] p-3">
        {/* Header */}
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Puzzle className="h-4 w-4 text-[var(--color-accent)]" />
            <span className="text-[12px] font-medium text-[var(--color-text-primary)]">
              Plugins
            </span>
          </div>
          <button
            onClick={onToggle}
            className="rounded-[var(--radius-sm)] p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Installed plugins */}
        {plugins.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
              Installed
            </p>
            {plugins.map((p) => (
              <div
                key={p.manifest.id}
                className="flex items-center gap-2 rounded-[var(--radius-sm)] bg-[var(--color-surface-1)] px-2 py-1.5"
              >
                <StatusIcon status={p.status} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[11px] font-medium text-[var(--color-text-primary)]">
                    {p.manifest.name}
                  </p>
                  <p className="truncate text-[9px] text-[var(--color-text-tertiary)]">
                    {p.manifest.description}
                  </p>
                </div>
                <button
                  onClick={() => handleUninstall(p.manifest.id)}
                  className="shrink-0 rounded-[var(--radius-sm)] p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-destructive)]"
                  title="Uninstall"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}

            {/* Overlay summary */}
            {(() => {
              const overlayNodes = registry.getAllOverlayNodes();
              const overlayEdges = registry.getAllOverlayEdges();
              if (overlayNodes.length === 0 && overlayEdges.length === 0) return null;
              return (
                <p className="text-[9px] text-[var(--color-text-tertiary)]">
                  Overlays: {overlayNodes.length} nodes, {overlayEdges.length} edges
                </p>
              );
            })()}
          </div>
        )}

        {/* Available starter plugins */}
        {availableStarters.length > 0 && (
          <div className="mt-3 space-y-1.5 border-t border-[var(--color-border-subtle)] pt-2">
            <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
              Available
            </p>
            {availableStarters.map((manifest) => (
              <div
                key={manifest.id}
                className="flex items-center gap-2 rounded-[var(--radius-sm)] px-2 py-1.5"
              >
                <Puzzle className="h-3 w-3 shrink-0 text-[var(--color-text-tertiary)]" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[11px] text-[var(--color-text-secondary)]">
                    {manifest.name}
                  </p>
                  <p className="truncate text-[9px] text-[var(--color-text-tertiary)]">
                    {manifest.description}
                  </p>
                </div>
                <button
                  onClick={() => handleInstall(manifest)}
                  className="shrink-0 rounded-[var(--radius-sm)] bg-[var(--color-accent)] p-1 text-white"
                  title="Install"
                >
                  <Play className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        {plugins.length === 0 && availableStarters.length === 0 && (
          <p className="text-[11px] text-[var(--color-text-tertiary)]">
            No plugins available
          </p>
        )}

        <p className="mt-2 text-[9px] text-[var(--color-text-tertiary)]">
          Plugins run in sandboxed iframes with limited permissions.
        </p>
      </div>
    </div>
  );
}
