import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Node, Edge } from "@/lib/api";

interface DetailPanelProps {
  node: Node;
  edges: Edge[];
  allNodes: Node[];
  onClose: () => void;
  onNavigate?: (nodeId: string) => void;
}

export function DetailPanel({
  node,
  edges,
  allNodes,
  onClose,
  onNavigate,
}: DetailPanelProps) {
  const incoming = edges
    .filter((e) => e.to === node.id)
    .map((e) => ({
      ...e,
      label: allNodes.find((n) => n.id === e.from)?.text || e.from,
    }));

  const outgoing = edges
    .filter((e) => e.from === node.id)
    .map((e) => ({
      ...e,
      label: allNodes.find((n) => n.id === e.to)?.text || e.to,
    }));

  return (
    <div className="glass absolute right-4 top-4 w-80 rounded-[var(--radius-lg)] p-4">
      {/* Header */}
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-[var(--color-text-primary)]">
            {node.id}
          </h3>
          <div className="mt-1 flex items-center gap-1.5">
            <Badge variant="secondary" className="text-[10px]">
              {node.layerName}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              {node.type}
            </Badge>
          </div>
        </div>
        <button
          onClick={onClose}
          className="shrink-0 rounded-[var(--radius-sm)] p-1 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Text / Description */}
      <p className="mb-3 text-xs leading-relaxed text-[var(--color-text-secondary)]">
        {node.text}
      </p>

      {/* Metadata */}
      <div className="space-y-2 border-t border-[var(--color-border-subtle)] pt-3">
        {node.severity && node.severity !== "info" && (
          <MetaRow label="Severity" value={node.severity} />
        )}
        {node.confidence != null && (
          <MetaRow
            label="Confidence"
            value={`${Math.round(node.confidence * 100)}%`}
          />
        )}
        {node.epistemicStatus && (
          <MetaRow label="Epistemic" value={node.epistemicStatus} />
        )}
        {node.technologies?.length > 0 && (
          <MetaRow label="Technologies" value={node.technologies.join(", ")} />
        )}
        {node.domains?.length > 0 && (
          <MetaRow label="Domains" value={node.domains.join(", ")} />
        )}
      </div>

      {/* Why / How To */}
      {(node.why || node.howTo) && (
        <div className="mt-3 space-y-2 border-t border-[var(--color-border-subtle)] pt-3">
          {node.why && (
            <div>
              <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
                Why
              </p>
              <p className="text-xs text-[var(--color-text-secondary)]">
                {node.why}
              </p>
            </div>
          )}
          {node.howTo && (
            <div>
              <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
                How To
              </p>
              <p className="text-xs text-[var(--color-text-secondary)]">
                {node.howTo}
              </p>
            </div>
          )}
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
                key={`out-${e.to}`}
                onClick={() => onNavigate?.(e.to)}
                className="flex w-full items-center gap-1.5 rounded-[var(--radius-sm)] px-1.5 py-0.5 text-left text-[11px] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
              >
                <span className="text-[var(--color-accent)]">&rarr;</span>
                <span className="truncate">{e.label}</span>
                <span className="ml-auto shrink-0 text-[10px] text-[var(--color-text-tertiary)]">
                  {e.type}
                </span>
              </button>
            ))}
            {incoming.slice(0, 8).map((e) => (
              <button
                key={`in-${e.from}`}
                onClick={() => onNavigate?.(e.from)}
                className="flex w-full items-center gap-1.5 rounded-[var(--radius-sm)] px-1.5 py-0.5 text-left text-[11px] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
              >
                <span className="text-[var(--color-secondary)]">&larr;</span>
                <span className="truncate">{e.label}</span>
                <span className="ml-auto shrink-0 text-[10px] text-[var(--color-text-tertiary)]">
                  {e.type}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="text-[var(--color-text-tertiary)]">{label}</span>
      <span className="text-[var(--color-text-secondary)]">{value}</span>
    </div>
  );
}
