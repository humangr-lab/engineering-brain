/**
 * Mini-map — radar overlay showing top-down view of the graph.
 * Renders to a 2D canvas in the bottom-right corner.
 */

import { useRef, useEffect, useCallback, useMemo } from "react";
import type { Node, Edge } from "@/lib/api";

interface MiniMapProps {
  nodes: Node[];
  edges: Edge[];
  selectedNodeId?: string;
  /** Viewport bounds from Three.js camera (normalized 0-1) */
  viewport?: { x: number; y: number; w: number; h: number };
  /** Called when user clicks on the minimap to teleport camera */
  onTeleport?: (x: number, y: number) => void;
  width?: number;
  height?: number;
}

export function MiniMap({
  nodes,
  edges,
  selectedNodeId,
  viewport,
  onTeleport,
  width = 200,
  height = 200,
}: MiniMapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Compute node positions using a simple hash-based layout
  // (In production this would read from Three.js scene positions)
  const positions = useMemo(() => {
    const pos = new Map<string, { x: number; y: number }>();
    const count = nodes.length;
    if (count === 0) return pos;

    // Simple deterministic 2D layout based on node properties
    for (let i = 0; i < count; i++) {
      const n = nodes[i];
      // Use layer for Y, and a hash for X spread
      const hash = simpleHash(n.id);
      const layerY = (n.layer + 1) / 6; // normalize layers 0-5 to 0-1
      const x = (hash % 1000) / 1000;
      const y = layerY * 0.6 + 0.2 + ((hash % 100) / 100) * 0.2;
      pos.set(n.id, { x, y });
    }

    return pos;
  }, [nodes]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Clear
    ctx.fillStyle = "rgba(10, 12, 18, 0.85)";
    ctx.fillRect(0, 0, width, height);

    // Border
    ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, width - 1, height - 1);

    const pad = 10;
    const w = width - pad * 2;
    const h = height - pad * 2;

    // Draw edges (very subtle)
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.lineWidth = 0.5;
    for (const e of edges) {
      const from = positions.get(e.from);
      const to = positions.get(e.to);
      if (!from || !to) continue;
      ctx.beginPath();
      ctx.moveTo(pad + from.x * w, pad + from.y * h);
      ctx.lineTo(pad + to.x * w, pad + to.y * h);
      ctx.stroke();
    }

    // Draw nodes
    for (const n of nodes) {
      const p = positions.get(n.id);
      if (!p) continue;

      const x = pad + p.x * w;
      const y = pad + p.y * h;
      const isSelected = n.id === selectedNodeId;
      const r = isSelected ? 3 : 1.5;

      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);

      if (isSelected) {
        ctx.fillStyle = "#10b981"; // accent
        ctx.fill();
        // Glow
        ctx.beginPath();
        ctx.arc(x, y, 6, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(16, 185, 129, 0.2)";
        ctx.fill();
      } else {
        // Color by layer
        const layerColors = [
          "rgba(239, 68, 68, 0.7)", // L0 infra
          "rgba(59, 130, 246, 0.7)", // L1 module
          "rgba(139, 92, 246, 0.6)", // L2 class/component
          "rgba(107, 114, 128, 0.5)", // L3 function
        ];
        ctx.fillStyle = layerColors[Math.min(n.layer, 3)] ?? "rgba(107, 114, 128, 0.5)";
        ctx.fill();
      }
    }

    // Draw viewport indicator
    if (viewport) {
      ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
      ctx.lineWidth = 1;
      ctx.strokeRect(
        pad + viewport.x * w,
        pad + viewport.y * h,
        viewport.w * w,
        viewport.h * h,
      );
    }
  }, [nodes, edges, positions, selectedNodeId, viewport, width, height]);

  useEffect(() => {
    // Render at low priority to not steal from main scene
    const id = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(id);
  }, [draw]);

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!onTeleport) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const pad = 10;
      const x = (e.clientX - rect.left - pad) / (width - pad * 2);
      const y = (e.clientY - rect.top - pad) / (height - pad * 2);
      onTeleport(Math.max(0, Math.min(1, x)), Math.max(0, Math.min(1, y)));
    },
    [onTeleport, width, height],
  );

  return (
    <canvas
      ref={canvasRef}
      onClick={handleClick}
      className="pointer-events-auto cursor-crosshair rounded-[var(--radius-md)]"
      style={{ width, height }}
      title="Mini-map — click to teleport"
    />
  );
}

/** Simple string hash for deterministic layout */
function simpleHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}
