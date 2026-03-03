/**
 * AI Trail Overlay — visual indicator for active AI-guided trails.
 *
 * Shows:
 * - Active trail info (path nodes, length)
 * - Camera flythrough progress bar
 * - Trail list (when multiple trails exist)
 * - Quick actions: play/pause flythrough, clear trails
 */

import { useState, useCallback, useMemo } from "react";
import type { Node, Edge } from "@/lib/api";
import {
  Play,
  Pause,
  Trash2,
  Sparkles,
  Route,
  Eye,
  ChevronRight,
} from "lucide-react";

interface AITrailOverlayProps {
  nodes: Node[];
  edges: Edge[];
  /** Currently active trail path (node IDs) */
  trailPath: string[] | null;
  /** Is camera flythrough playing */
  isPlaying: boolean;
  /** Flythrough progress 0–1 */
  progress: number;
  /** Callbacks */
  onCreateTrail: (from: string, to: string) => void;
  onPlay: () => void;
  onPause: () => void;
  onClear: () => void;
  onNodeClick: (nodeId: string) => void;
  /** Whether overlay is visible */
  active: boolean;
}

export function AITrailOverlay({
  nodes,
  edges: _edges,
  trailPath,
  isPlaying,
  progress,
  onCreateTrail,
  onPlay,
  onPause,
  onClear,
  onNodeClick,
  active,
}: AITrailOverlayProps) {
  const [fromSearch, setFromSearch] = useState("");
  const [toSearch, setToSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  // Search results
  const fromResults = useMemo(
    () => searchNodes(nodes, fromSearch),
    [nodes, fromSearch],
  );
  const toResults = useMemo(
    () => searchNodes(nodes, toSearch),
    [nodes, toSearch],
  );

  const [selectedFrom, setSelectedFrom] = useState<string | null>(null);
  const [selectedTo, setSelectedTo] = useState<string | null>(null);

  const handleCreate = useCallback(() => {
    if (selectedFrom && selectedTo) {
      onCreateTrail(selectedFrom, selectedTo);
      setShowCreate(false);
      setFromSearch("");
      setToSearch("");
      setSelectedFrom(null);
      setSelectedTo(null);
    }
  }, [selectedFrom, selectedTo, onCreateTrail]);

  // Path node labels for display
  const pathLabels = useMemo(() => {
    if (!trailPath) return [];
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    return trailPath.map((id) => ({
      id,
      label: nodeMap.get(id)?.text ?? id,
    }));
  }, [trailPath, nodes]);

  if (!active) return null;

  return (
    <div className="absolute left-4 top-4 z-20 flex flex-col gap-2" style={{ maxWidth: 300 }}>
      {/* Trail info card */}
      <div className="glass rounded-[var(--radius-md)] p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Route className="h-3.5 w-3.5 text-[var(--color-accent)]" />
            <span className="text-[11px] font-semibold text-[var(--color-text-primary)]">
              AI Trail
            </span>
          </div>
          <div className="flex gap-1">
            <button
              onClick={() => setShowCreate(!showCreate)}
              className="rounded p-1 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-accent)]"
              title="Create new trail"
            >
              <Sparkles className="h-3 w-3" />
            </button>
            {trailPath && (
              <button
                onClick={onClear}
                className="rounded p-1 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-destructive)]"
                title="Clear trail"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>

        {/* Active trail */}
        {trailPath && pathLabels.length > 0 && (
          <div className="mt-2 flex flex-col gap-1.5">
            {/* Path breadcrumb */}
            <div className="flex flex-wrap items-center gap-0.5">
              {pathLabels.map((node, i) => (
                <span key={node.id} className="flex items-center">
                  <button
                    onClick={() => onNodeClick(node.id)}
                    className="rounded px-1 py-0.5 text-[9px] font-medium text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)]/10"
                  >
                    {node.label}
                  </button>
                  {i < pathLabels.length - 1 && (
                    <ChevronRight className="h-2.5 w-2.5 text-[var(--color-text-tertiary)]" />
                  )}
                </span>
              ))}
            </div>

            {/* Flythrough controls */}
            <div className="flex items-center gap-2">
              <button
                onClick={isPlaying ? onPause : onPlay}
                className="rounded p-1 text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-accent)]"
              >
                {isPlaying ? (
                  <Pause className="h-3 w-3" />
                ) : (
                  <Play className="h-3 w-3" />
                )}
              </button>
              {/* Progress bar */}
              <div className="relative h-1 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-[var(--color-accent)] transition-all duration-100"
                  style={{ width: `${progress * 100}%` }}
                />
              </div>
              <span className="text-[9px] text-[var(--color-text-tertiary)]">
                {pathLabels.length} nodes
              </span>
            </div>
          </div>
        )}

        {/* No trail message */}
        {!trailPath && !showCreate && (
          <p className="mt-2 text-[10px] text-[var(--color-text-tertiary)]">
            No active trail. Click{" "}
            <Sparkles className="inline h-2.5 w-2.5 text-[var(--color-accent)]" />{" "}
            to trace a path between two nodes.
          </p>
        )}
      </div>

      {/* Create trail form */}
      {showCreate && (
        <div className="glass rounded-[var(--radius-md)] p-3">
          <p className="mb-2 text-[10px] font-medium text-[var(--color-text-secondary)]">
            Trace path between nodes
          </p>

          {/* From field */}
          <div className="mb-2">
            <label className="mb-0.5 block text-[9px] text-[var(--color-text-tertiary)]">
              From
            </label>
            <input
              type="text"
              value={fromSearch}
              onChange={(e) => {
                setFromSearch(e.target.value);
                setSelectedFrom(null);
              }}
              placeholder="Search node..."
              className="w-full rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] px-2 py-1 text-[10px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
            />
            {fromSearch && !selectedFrom && fromResults.length > 0 && (
              <div className="mt-0.5 max-h-20 overflow-y-auto rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]">
                {fromResults.slice(0, 5).map((n) => (
                  <button
                    key={n.id}
                    onClick={() => {
                      setSelectedFrom(n.id);
                      setFromSearch(n.text);
                    }}
                    className="block w-full px-2 py-0.5 text-left text-[9px] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-2)]"
                  >
                    {n.text}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* To field */}
          <div className="mb-2">
            <label className="mb-0.5 block text-[9px] text-[var(--color-text-tertiary)]">
              To
            </label>
            <input
              type="text"
              value={toSearch}
              onChange={(e) => {
                setToSearch(e.target.value);
                setSelectedTo(null);
              }}
              placeholder="Search node..."
              className="w-full rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] px-2 py-1 text-[10px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
            />
            {toSearch && !selectedTo && toResults.length > 0 && (
              <div className="mt-0.5 max-h-20 overflow-y-auto rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]">
                {toResults.slice(0, 5).map((n) => (
                  <button
                    key={n.id}
                    onClick={() => {
                      setSelectedTo(n.id);
                      setToSearch(n.text);
                    }}
                    className="block w-full px-2 py-0.5 text-left text-[9px] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-2)]"
                  >
                    {n.text}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={handleCreate}
            disabled={!selectedFrom || !selectedTo}
            className="w-full rounded bg-[var(--color-accent)] px-2 py-1 text-[10px] font-medium text-white transition-opacity disabled:opacity-40"
          >
            <Eye className="mr-1 inline h-3 w-3" />
            Trace Path
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function searchNodes(nodes: Node[], query: string): Node[] {
  if (!query || query.length < 2) return [];
  const lower = query.toLowerCase();
  return nodes.filter(
    (n) =>
      n.text.toLowerCase().includes(lower) ||
      n.id.toLowerCase().includes(lower),
  );
}
