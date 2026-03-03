import { X, ChevronRight, ArrowLeft } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { SysmapData } from "@/lib/inference/build-sysmap";

interface SysmapDetailPanelProps {
  nodeId: string;
  sysmapData: SysmapData;
  hasSubmap: boolean;
  isInSubmap: boolean;
  onClose: () => void;
  onNavigate?: (nodeId: string) => void;
  onDrillDown?: (nodeId: string) => void;
  onSubmapBack?: () => void;
}

export function SysmapDetailPanel({
  nodeId,
  sysmapData,
  hasSubmap,
  isInSubmap,
  onClose,
  onNavigate,
  onDrillDown,
  onSubmapBack,
}: SysmapDetailPanelProps) {
  const dt = sysmapData.DT[nodeId];
  const sysmapNode = sysmapData.N.find((n) => n.id === nodeId);

  // Find connections from edge list
  const incoming = sysmapData.E
    .filter((e) => e.t === nodeId)
    .map((e) => {
      const fromNode = sysmapData.N.find((n) => n.id === e.f);
      return {
        id: e.f,
        label: fromNode?.label || e.f,
        color: e.c,
      };
    });

  const outgoing = sysmapData.E
    .filter((e) => e.f === nodeId)
    .map((e) => {
      const toNode = sysmapData.N.find((n) => n.id === e.t);
      return {
        id: e.t,
        label: toNode?.label || e.t,
        color: e.c,
      };
    });

  if (!dt) {
    return (
      <div className="glass absolute right-4 top-4 w-80 rounded-[var(--radius-lg)] p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-[var(--color-text-secondary)]">
            No details for {nodeId}
          </span>
          <button
            onClick={onClose}
            className="rounded-[var(--radius-sm)] p-1 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-2)]"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="glass absolute right-4 top-4 w-80 rounded-[var(--radius-lg)] p-4">
      {/* Back button when in submap */}
      {isInSubmap && (
        <button
          onClick={onSubmapBack}
          className="mb-2 flex items-center gap-1 text-[11px] text-[var(--color-accent)] transition-colors hover:text-[var(--color-text-primary)]"
        >
          <ArrowLeft className="h-3 w-3" />
          Back to main map
        </button>
      )}

      {/* Header */}
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-[var(--color-text-primary)]">
            {dt.t}
          </h3>
          <div className="mt-1 flex items-center gap-1.5">
            <Badge variant="secondary" className="text-[10px]">
              {dt.tp}
            </Badge>
            {sysmapNode?.g && (
              <Badge variant="outline" className="text-[10px]">
                {sysmapNode.g}
              </Badge>
            )}
            {sysmapNode?.sh && sysmapNode.sh !== "sphere" && (
              <Badge variant="outline" className="text-[10px]">
                {sysmapNode.sh}
              </Badge>
            )}
          </div>
        </div>
        <button
          onClick={onClose}
          className="shrink-0 rounded-[var(--radius-sm)] p-1 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Description */}
      <p className="mb-3 text-xs leading-relaxed text-[var(--color-text-secondary)]">
        {dt.d}
      </p>

      {/* Drill-down button */}
      {hasSubmap && !isInSubmap && (
        <button
          onClick={() => onDrillDown?.(nodeId)}
          className="mb-3 flex w-full items-center justify-between rounded-[var(--radius-sm)] bg-[var(--color-accent)]/10 px-3 py-2 text-[11px] font-medium text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)]/20"
        >
          <span>Explore submap ({sysmapData.SUBMAPS[nodeId]?.nodes.length} nodes)</span>
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      )}

      {/* Metrics */}
      {Object.keys(dt.m).length > 0 && (
        <div className="space-y-2 border-t border-[var(--color-border-subtle)] pt-3">
          {Object.entries(dt.m).map(([key, value]) => (
            <div
              key={key}
              className="flex items-center justify-between text-[11px]"
            >
              <span className="text-[var(--color-text-tertiary)]">{key}</span>
              <span className="max-w-[180px] truncate text-[var(--color-text-secondary)]">
                {value}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Connections */}
      {(incoming.length > 0 || outgoing.length > 0) && (
        <div className="mt-3 border-t border-[var(--color-border-subtle)] pt-3">
          <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
            Connections ({incoming.length} in, {outgoing.length} out)
          </p>
          <div className="max-h-32 space-y-1 overflow-y-auto">
            {outgoing.slice(0, 8).map((e) => (
              <button
                key={`out-${e.id}`}
                onClick={() => onNavigate?.(e.id)}
                className="flex w-full items-center gap-1.5 rounded-[var(--radius-sm)] px-1.5 py-0.5 text-left text-[11px] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
              >
                <span className="text-[var(--color-accent)]">&rarr;</span>
                <span className="truncate">{e.label}</span>
              </button>
            ))}
            {incoming.slice(0, 8).map((e) => (
              <button
                key={`in-${e.id}`}
                onClick={() => onNavigate?.(e.id)}
                className="flex w-full items-center gap-1.5 rounded-[var(--radius-sm)] px-1.5 py-0.5 text-left text-[11px] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
              >
                <span className="text-[var(--color-secondary)]">&larr;</span>
                <span className="truncate">{e.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Inference confidence */}
      {sysmapData.inferredConfig && (
        <div className="mt-3 border-t border-[var(--color-border-subtle)] pt-3">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-[var(--color-text-tertiary)]">Template</span>
            <span className="text-[var(--color-text-secondary)]">
              {sysmapData.inferredConfig.template}
            </span>
          </div>
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-[var(--color-text-tertiary)]">Confidence</span>
            <span className="text-[var(--color-text-secondary)]">
              {Math.round(sysmapData.inferredConfig.confidence.total * 100)}%
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
