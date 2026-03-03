/**
 * Earthquake Overlay — shows BFS blast radius + counter.
 * Renders as a floating overlay on the 3D scene.
 */

import { useEffect, useState, useMemo } from "react";
import {
  computeEarthquake,
  DEPTH_COLORS,
  type EarthquakeResult,
} from "@/lib/engine/earthquake";
import { playEarthquakeRumble } from "@/lib/engine/sound";
import type { Node, Edge } from "@/lib/api";

interface EarthquakeOverlayProps {
  epicenterNode: Node | null;
  nodes: Node[];
  edges: Edge[];
  active: boolean;
  onResult?: (result: EarthquakeResult | null) => void;
}

export function EarthquakeOverlay({
  epicenterNode,
  nodes,
  edges,
  active,
  onResult,
}: EarthquakeOverlayProps) {
  const [result, setResult] = useState<EarthquakeResult | null>(null);
  const [animating, setAnimating] = useState(false);
  const [currentDepth, setCurrentDepth] = useState(0);

  // Compute earthquake when activated
  useEffect(() => {
    if (!active || !epicenterNode) {
      setResult(null);
      setAnimating(false);
      setCurrentDepth(0);
      onResult?.(null);
      return;
    }

    const eq = computeEarthquake(epicenterNode.id, nodes, edges);
    setResult(eq);
    onResult?.(eq);

    // Play rumble
    playEarthquakeRumble(Math.min(1, eq.affectedPercent / 50));

    // Animate layer reveal
    setAnimating(true);
    setCurrentDepth(0);

    let depth = 0;
    const interval = setInterval(() => {
      depth++;
      if (depth >= eq.layers.length) {
        clearInterval(interval);
        setAnimating(false);
      } else {
        setCurrentDepth(depth);
      }
    }, 150); // 150ms per depth layer

    return () => clearInterval(interval);
  }, [active, epicenterNode, nodes, edges, onResult]);

  // Layer breakdown display
  const layerBreakdown = useMemo(() => {
    if (!result) return [];
    return result.layers
      .slice(0, Math.min(currentDepth + 1, result.layers.length))
      .map((layer, i) => ({
        depth: i,
        count: layer.length,
        color: DEPTH_COLORS[Math.min(i, DEPTH_COLORS.length - 1)],
        label: i === 0 ? "Epicenter" : `Depth ${i}`,
      }));
  }, [result, currentDepth]);

  if (!active || !result || !epicenterNode) return null;

  return (
    <div className="absolute left-4 top-4 z-20 max-w-[240px]">
      {/* Counter */}
      <div className="glass rounded-[var(--radius-md)] p-3">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold tabular-nums text-[var(--color-text-primary)]">
            {result.affectedCount}
          </span>
          <span className="text-xs text-[var(--color-text-secondary)]">
            nodes affected
          </span>
        </div>
        <div className="mt-1 flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[#ef4444] via-[#eab308] to-[#a3a3a3] transition-all duration-500"
              style={{ width: `${Math.min(100, result.affectedPercent)}%` }}
            />
          </div>
          <span className="text-[11px] tabular-nums text-[var(--color-text-tertiary)]">
            {result.affectedPercent.toFixed(1)}%
          </span>
        </div>

        {/* Layer breakdown */}
        <div className="mt-3 space-y-1.5">
          {layerBreakdown.map((layer) => (
            <div
              key={layer.depth}
              className="flex items-center gap-2 text-[11px]"
              style={{ opacity: animating && layer.depth === currentDepth ? 0.7 : 1 }}
            >
              <div
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: layer.color }}
              />
              <span className="flex-1 text-[var(--color-text-secondary)]">
                {layer.label}
              </span>
              <span className="tabular-nums text-[var(--color-text-tertiary)]">
                {layer.count}
              </span>
            </div>
          ))}
        </div>

        {/* Epicenter name */}
        <div className="mt-2 border-t border-[var(--color-border-subtle)] pt-2">
          <p className="text-[11px] text-[var(--color-text-tertiary)]">
            Epicenter:{" "}
            <span className="font-medium text-[var(--color-text-secondary)]">
              {epicenterNode.text}
            </span>
          </p>
        </div>
      </div>

      {/* Legend */}
      <div className="mt-2 flex items-center justify-between rounded-[var(--radius-sm)] px-2 py-1 text-[9px] text-[var(--color-text-tertiary)]">
        <span>Press D to toggle</span>
        <span>ESC to dismiss</span>
      </div>
    </div>
  );
}
