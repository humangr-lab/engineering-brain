/**
 * Embed Dialog — configure and export an embeddable widget.
 */

import { useState, useCallback } from "react";
import { Code2, Copy, Download, X } from "lucide-react";
import { generateEmbed, generateEmbedTag } from "@/lib/engine/embed";
import type { Node, Edge } from "@/lib/api";

interface EmbedDialogProps {
  open: boolean;
  onClose: () => void;
  nodes: Node[];
  edges: Edge[];
}

export function EmbedDialog({ open, onClose, nodes, edges }: EmbedDialogProps) {
  const [maxNodes, setMaxNodes] = useState(100);
  const [autoRotate, setAutoRotate] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [copied, setCopied] = useState(false);

  const handleCopyTag = useCallback(() => {
    const tag = generateEmbedTag({
      width: "100%",
      height: "400px",
      maxNodes,
      autoRotate,
      showLabels,
    });
    navigator.clipboard.writeText(tag);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [maxNodes, autoRotate, showLabels]);

  const handleDownload = useCallback(() => {
    const html = generateEmbed(nodes, edges, {
      maxNodes,
      autoRotate,
      showLabels,
    });
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ontology-map-embed.html";
    a.click();
    URL.revokeObjectURL(url);
  }, [nodes, edges, maxNodes, autoRotate, showLabels]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="glass relative z-10 w-[360px] rounded-[var(--radius-md)] p-4">
        {/* Header */}
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Code2 className="h-4 w-4 text-[var(--color-accent)]" />
            <span className="text-[13px] font-medium text-[var(--color-text-primary)]">
              Embed Widget
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-[var(--radius-sm)] p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="mb-3 text-[11px] text-[var(--color-text-secondary)]">
          Export a self-contained 3D visualization as an embeddable HTML widget.
          Includes {Math.min(maxNodes, nodes.length)} of {nodes.length} nodes.
        </p>

        {/* Options */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-[11px] text-[var(--color-text-secondary)]">
              Max nodes
            </label>
            <input
              type="number"
              min={10}
              max={500}
              value={maxNodes}
              onChange={(e) => setMaxNodes(Number(e.target.value))}
              className="w-20 rounded-[var(--radius-sm)] bg-[var(--color-surface-1)] px-2 py-1 text-right text-[11px] text-[var(--color-text-primary)] outline-none"
            />
          </div>

          <label className="flex items-center justify-between">
            <span className="text-[11px] text-[var(--color-text-secondary)]">
              Auto-rotate
            </span>
            <input
              type="checkbox"
              checked={autoRotate}
              onChange={(e) => setAutoRotate(e.target.checked)}
              className="accent-[var(--color-accent)]"
            />
          </label>

          <label className="flex items-center justify-between">
            <span className="text-[11px] text-[var(--color-text-secondary)]">
              Show labels
            </span>
            <input
              type="checkbox"
              checked={showLabels}
              onChange={(e) => setShowLabels(e.target.checked)}
              className="accent-[var(--color-accent)]"
            />
          </label>
        </div>

        {/* Actions */}
        <div className="mt-4 flex gap-2">
          <button
            onClick={handleCopyTag}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border-subtle)] px-3 py-2 text-[11px] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-1)]"
          >
            <Copy className="h-3.5 w-3.5" />
            {copied ? "Copied!" : "Copy <iframe>"}
          </button>
          <button
            onClick={handleDownload}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3 py-2 text-[11px] text-white"
          >
            <Download className="h-3.5 w-3.5" />
            Download HTML
          </button>
        </div>
      </div>
    </div>
  );
}
