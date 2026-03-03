/**
 * Ghost Mode Overlay — shows translucent "ghost" nodes for missing items.
 * Toggle with G key.
 */

import { useMemo } from "react";
import { detectGhosts, getGhostSummary, type GhostNode } from "@/lib/engine/ghost";
import { AlertTriangle, FileQuestion, FileText } from "lucide-react";
import type { Node, Edge } from "@/lib/api";

interface GhostOverlayProps {
  nodes: Node[];
  edges: Edge[];
  active: boolean;
  onResult?: (ghosts: GhostNode[]) => void;
}

const GHOST_TYPE_ICONS = {
  missing_test: FileQuestion,
  todo: AlertTriangle,
  missing_doc: FileText,
} as const;

const GHOST_TYPE_COLORS = {
  missing_test: "text-[var(--color-secondary)]",
  todo: "text-[var(--color-warning)]",
  missing_doc: "text-[var(--color-text-tertiary)]",
} as const;

export function GhostOverlay({
  nodes,
  edges,
  active,
  onResult,
}: GhostOverlayProps) {
  const ghosts = useMemo(() => {
    if (!active) {
      onResult?.([]);
      return [];
    }
    const g = detectGhosts(nodes, edges);
    onResult?.(g);
    return g;
  }, [active, nodes, edges, onResult]);

  const summary = useMemo(() => getGhostSummary(ghosts), [ghosts]);

  if (!active || ghosts.length === 0) return null;

  return (
    <div className="absolute left-4 top-4 z-20 w-[220px]">
      <div className="glass rounded-[var(--radius-md)] p-3">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
          Ghost Mode
        </p>

        {/* Summary counts */}
        <div className="space-y-1.5">
          {summary.missingTests > 0 && (
            <div className="flex items-center gap-2 text-[11px]">
              <FileQuestion className="h-3.5 w-3.5 text-[var(--color-secondary)]" />
              <span className="flex-1 text-[var(--color-text-secondary)]">
                Missing tests
              </span>
              <span className="tabular-nums text-[var(--color-text-tertiary)]">
                {summary.missingTests}
              </span>
            </div>
          )}
          {summary.todos > 0 && (
            <div className="flex items-center gap-2 text-[11px]">
              <AlertTriangle className="h-3.5 w-3.5 text-[var(--color-warning)]" />
              <span className="flex-1 text-[var(--color-text-secondary)]">
                TODOs
              </span>
              <span className="tabular-nums text-[var(--color-text-tertiary)]">
                {summary.todos}
              </span>
            </div>
          )}
          {summary.missingDocs > 0 && (
            <div className="flex items-center gap-2 text-[11px]">
              <FileText className="h-3.5 w-3.5 text-[var(--color-text-tertiary)]" />
              <span className="flex-1 text-[var(--color-text-secondary)]">
                Missing docs
              </span>
              <span className="tabular-nums text-[var(--color-text-tertiary)]">
                {summary.missingDocs}
              </span>
            </div>
          )}
        </div>

        {/* Total */}
        <div className="mt-2 border-t border-[var(--color-border-subtle)] pt-2">
          <div className="flex items-baseline gap-2">
            <span className="text-lg font-bold tabular-nums text-[var(--color-text-primary)]">
              {summary.total}
            </span>
            <span className="text-[11px] text-[var(--color-text-tertiary)]">
              ghost nodes
            </span>
          </div>
        </div>

        {/* Ghost list (first 8) */}
        <div className="mt-2 max-h-[200px] space-y-1 overflow-y-auto">
          {ghosts.slice(0, 8).map((ghost) => {
            const Icon = GHOST_TYPE_ICONS[ghost.ghostType];
            const colorClass = GHOST_TYPE_COLORS[ghost.ghostType];
            return (
              <div
                key={ghost.id}
                className="flex items-center gap-2 rounded-[var(--radius-sm)] px-1.5 py-1 text-[10px] hover:bg-[var(--color-surface-1)]"
                style={{ opacity: 0.7 }}
              >
                <Icon className={`h-3 w-3 shrink-0 ${colorClass}`} />
                <span className="truncate text-[var(--color-text-secondary)]">
                  {ghost.reason}
                </span>
              </div>
            );
          })}
          {ghosts.length > 8 && (
            <p className="px-1.5 text-[9px] text-[var(--color-text-tertiary)]">
              +{ghosts.length - 8} more...
            </p>
          )}
        </div>

        <p className="mt-2 text-[9px] text-[var(--color-text-tertiary)]">
          Press G to toggle
        </p>
      </div>
    </div>
  );
}
