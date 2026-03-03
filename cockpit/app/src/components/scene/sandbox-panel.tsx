/**
 * What-If Sandbox Panel — fork the graph, add/remove edges, diff, export RFC.
 */

import { useState, useCallback, useMemo } from "react";
import {
  createSandbox,
  sandboxAddEdge,
  sandboxRemoveEdge,
  computeSandboxDiff,
  exportSandboxAsRFC,
  type SandboxState,
} from "@/lib/engine/sandbox";
import {
  GitFork,
  Plus,
  Minus,
  FileDown,
  Undo2,
  X,
} from "lucide-react";
import type { Node, Edge } from "@/lib/api";

interface SandboxPanelProps {
  nodes: Node[];
  edges: Edge[];
  active: boolean;
  onToggle: () => void;
}

export function SandboxPanel({
  nodes,
  edges,
  active,
  onToggle,
}: SandboxPanelProps) {
  const [sandbox, setSandbox] = useState<SandboxState | null>(null);
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [edgeType, setEdgeType] = useState("DEPENDS_ON");
  const [rfcTitle, setRfcTitle] = useState("Proposed Refactoring");

  // Initialize sandbox when activated
  const handleActivate = useCallback(() => {
    if (!active) {
      setSandbox(createSandbox(nodes, edges));
    } else {
      setSandbox(null);
      setFromId("");
      setToId("");
    }
    onToggle();
  }, [active, nodes, edges, onToggle]);

  // Add edge
  const handleAddEdge = useCallback(() => {
    if (!sandbox || !fromId.trim() || !toId.trim()) return;
    setSandbox(sandboxAddEdge(sandbox, fromId.trim(), toId.trim(), edgeType));
    setFromId("");
    setToId("");
  }, [sandbox, fromId, toId, edgeType]);

  // Remove edge
  const handleRemoveEdge = useCallback(
    (from: string, to: string) => {
      if (!sandbox) return;
      setSandbox(sandboxRemoveEdge(sandbox, from, to));
    },
    [sandbox],
  );

  // Undo last modification
  const handleUndo = useCallback(() => {
    if (!sandbox || sandbox.modifications.length === 0) return;
    // Re-create from original, replaying all but last modification
    let s = createSandbox(nodes, edges);
    for (const mod of sandbox.modifications.slice(0, -1)) {
      if (mod.type === "add_edge") {
        s = sandboxAddEdge(s, mod.edge.from, mod.edge.to, mod.edge.type);
      } else if (mod.type === "remove_edge") {
        s = sandboxRemoveEdge(s, mod.from, mod.to);
      }
    }
    setSandbox(s);
  }, [sandbox, nodes, edges]);

  // Compute diff
  const diff = useMemo(() => {
    if (!sandbox) return null;
    return computeSandboxDiff({ nodes, edges }, sandbox);
  }, [sandbox, nodes, edges]);

  // Export RFC
  const handleExport = useCallback(() => {
    if (!sandbox) return;
    const md = exportSandboxAsRFC(rfcTitle, { nodes, edges }, sandbox);
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `rfc-${rfcTitle.toLowerCase().replace(/\s+/g, "-")}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [sandbox, rfcTitle, nodes, edges]);

  // Node ID suggestions (for autocomplete)
  const nodeIds = useMemo(
    () => nodes.map((n) => n.id).sort(),
    [nodes],
  );

  if (!active || !sandbox) {
    return (
      <button
        onClick={handleActivate}
        className="glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
        title="What-If Sandbox"
      >
        <GitFork className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Sandbox</span>
      </button>
    );
  }

  return (
    <div className="absolute left-4 top-4 z-20 w-[280px]">
      <div className="glass rounded-[var(--radius-md)] p-3">
        {/* Header */}
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitFork className="h-4 w-4 text-[var(--color-accent)]" />
            <span className="text-[12px] font-medium text-[var(--color-text-primary)]">
              What-If Sandbox
            </span>
          </div>
          <button
            onClick={handleActivate}
            className="rounded-[var(--radius-sm)] p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Add edge form */}
        <div className="space-y-1.5">
          <input
            value={fromId}
            onChange={(e) => setFromId(e.target.value)}
            placeholder="From node ID..."
            list="sandbox-nodes"
            className="w-full rounded-[var(--radius-sm)] bg-[var(--color-surface-1)] px-2 py-1 text-[11px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] outline-none"
          />
          <input
            value={toId}
            onChange={(e) => setToId(e.target.value)}
            placeholder="To node ID..."
            list="sandbox-nodes"
            className="w-full rounded-[var(--radius-sm)] bg-[var(--color-surface-1)] px-2 py-1 text-[11px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] outline-none"
          />
          <datalist id="sandbox-nodes">
            {nodeIds.slice(0, 100).map((id) => (
              <option key={id} value={id} />
            ))}
          </datalist>
          <div className="flex gap-1.5">
            <select
              value={edgeType}
              onChange={(e) => setEdgeType(e.target.value)}
              className="flex-1 rounded-[var(--radius-sm)] bg-[var(--color-surface-1)] px-2 py-1 text-[11px] text-[var(--color-text-primary)] outline-none"
            >
              <option value="DEPENDS_ON">DEPENDS_ON</option>
              <option value="IMPORTS">IMPORTS</option>
              <option value="CONTAINS">CONTAINS</option>
              <option value="RELATES_TO">RELATES_TO</option>
            </select>
            <button
              onClick={handleAddEdge}
              disabled={!fromId.trim() || !toId.trim()}
              className="rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-2 py-1 text-[11px] text-white transition-opacity disabled:opacity-30"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Diff summary */}
        {diff && (
          <div className="mt-3 border-t border-[var(--color-border-subtle)] pt-2">
            <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
              Changes
            </p>
            <div className="space-y-1 text-[11px]">
              {diff.addedEdges.length > 0 && (
                <div className="flex items-center gap-2 text-[var(--color-success)]">
                  <Plus className="h-3 w-3" />
                  <span>{diff.addedEdges.length} edge(s) added</span>
                </div>
              )}
              {diff.removedEdges.length > 0 && (
                <div className="flex items-center gap-2 text-[var(--color-destructive)]">
                  <Minus className="h-3 w-3" />
                  <span>{diff.removedEdges.length} edge(s) removed</span>
                </div>
              )}
              {diff.addedEdges.length === 0 &&
                diff.removedEdges.length === 0 && (
                  <span className="text-[var(--color-text-tertiary)]">
                    No changes yet
                  </span>
                )}
            </div>

            {/* Recent modifications (scrollable) */}
            {sandbox.modifications.length > 0 && (
              <div className="mt-2 max-h-[100px] space-y-0.5 overflow-y-auto">
                {sandbox.modifications.map((mod, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-1 text-[9px] text-[var(--color-text-tertiary)]"
                  >
                    {mod.type === "add_edge" && (
                      <>
                        <Plus className="h-2.5 w-2.5 text-[var(--color-success)]" />
                        <span className="truncate">
                          {mod.edge.from} → {mod.edge.to}
                        </span>
                        <button
                          onClick={() =>
                            handleRemoveEdge(mod.edge.from, mod.edge.to)
                          }
                          className="ml-auto shrink-0"
                        >
                          <X className="h-2.5 w-2.5 hover:text-[var(--color-destructive)]" />
                        </button>
                      </>
                    )}
                    {mod.type === "remove_edge" && (
                      <>
                        <Minus className="h-2.5 w-2.5 text-[var(--color-destructive)]" />
                        <span className="truncate">
                          {mod.from} → {mod.to}
                        </span>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* RFC title + Actions */}
        <div className="mt-3 space-y-1.5">
          <input
            value={rfcTitle}
            onChange={(e) => setRfcTitle(e.target.value)}
            placeholder="RFC title..."
            className="w-full rounded-[var(--radius-sm)] bg-[var(--color-surface-1)] px-2 py-1 text-[11px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] outline-none"
          />
          <div className="flex gap-1.5">
            <button
              onClick={handleUndo}
              disabled={sandbox.modifications.length === 0}
              className="flex items-center gap-1 rounded-[var(--radius-sm)] px-2 py-1 text-[10px] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-1)] disabled:opacity-30"
            >
              <Undo2 className="h-3 w-3" />
              Undo
            </button>
            <div className="flex-1" />
            <button
              onClick={handleExport}
              disabled={sandbox.modifications.length === 0}
              className="flex items-center gap-1 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-2 py-1 text-[10px] text-white transition-opacity disabled:opacity-30"
            >
              <FileDown className="h-3 w-3" />
              Export RFC
            </button>
          </div>
        </div>

        <p className="mt-1.5 text-[9px] text-[var(--color-text-tertiary)]">
          Fork of {nodes.length} nodes, {edges.length} edges
        </p>
      </div>
    </div>
  );
}
