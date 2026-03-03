/**
 * Heatmap Controls — metric selector and legend.
 * Appears when H key is pressed.
 */

import { useMemo } from "react";
import {
  computeHeatmap,
  getAvailableMetrics,
  type HeatmapMetric,
  type HeatmapResult,
} from "@/lib/engine/heatmap";
import type { Node, Edge } from "@/lib/api";

interface HeatmapControlsProps {
  nodes: Node[];
  edges: Edge[];
  active: boolean;
  metric: HeatmapMetric;
  onMetricChange: (metric: HeatmapMetric) => void;
  onResult?: (result: HeatmapResult | null) => void;
}

const METRIC_LABELS: Record<HeatmapMetric, string> = {
  degree: "Degree Centrality",
  complexity: "Complexity",
  loc: "Lines of Code",
  layer: "Layer Depth",
  confidence: "Confidence",
};

export function HeatmapControls({
  nodes,
  edges,
  active,
  metric,
  onMetricChange,
  onResult,
}: HeatmapControlsProps) {
  const availableMetrics = useMemo(
    () => getAvailableMetrics(nodes),
    [nodes],
  );

  // Compute heatmap when active
  const result = useMemo(() => {
    if (!active) {
      onResult?.(null);
      return null;
    }
    const r = computeHeatmap(nodes, edges, metric);
    onResult?.(r);
    return r;
  }, [active, nodes, edges, metric, onResult]);

  if (!active) return null;

  return (
    <div className="absolute right-4 top-4 z-20 w-[180px]">
      <div className="glass rounded-[var(--radius-md)] p-3">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
          Heatmap
        </p>

        {/* Metric selector */}
        <div className="space-y-1">
          {availableMetrics.map((m) => (
            <button
              key={m}
              onClick={() => onMetricChange(m)}
              className={`flex w-full items-center gap-2 rounded-[var(--radius-sm)] px-2 py-1.5 text-left text-[11px] transition-colors ${
                m === metric
                  ? "bg-[var(--color-accent-muted)] text-[var(--color-accent)]"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-1)]"
              }`}
            >
              {METRIC_LABELS[m]}
            </button>
          ))}
        </div>

        {/* Gradient legend */}
        {result && (
          <div className="mt-3 border-t border-[var(--color-border-subtle)] pt-2">
            <div className="flex items-center justify-between text-[9px] tabular-nums text-[var(--color-text-tertiary)]">
              <span>{result.range.min.toFixed(1)}</span>
              <span>{result.range.max.toFixed(1)}</span>
            </div>
            <div
              className="mt-1 h-2 rounded-full"
              style={{
                background:
                  "linear-gradient(to right, #1e3a5f, #1e6091, #3b9c6b, #d4a017, #e06c2e, #d93025)",
              }}
            />
          </div>
        )}

        <p className="mt-2 text-[9px] text-[var(--color-text-tertiary)]">
          Press H to toggle
        </p>
      </div>
    </div>
  );
}
