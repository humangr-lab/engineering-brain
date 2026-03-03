/**
 * Share Dialog — generate compressed share URLs and embeddable code.
 *
 * Features:
 * - Compressed URL with deflate + base64url (fits in tweets/links)
 * - Copy to clipboard
 * - Embed code snippet (HTML + Web Component)
 * - Standalone HTML export
 * - Compression stats display
 */

import { useState, useCallback, useEffect } from "react";
import type { Node, Edge } from "@/lib/api";
import {
  generateShareUrl,
  getShareUrlSize,
} from "@/lib/engine/share";
import {
  generateStandaloneHtml,
} from "@/lib/engine/web-component";
import {
  X,
  Copy,
  Check,
  Link2,
  Code2,
  Download,
} from "lucide-react";

interface ShareDialogProps {
  open: boolean;
  onClose: () => void;
  nodes: Node[];
  edges: Edge[];
}

export function ShareDialog({ open, onClose, nodes, edges }: ShareDialogProps) {
  const [shareUrl, setShareUrl] = useState("");
  const [urlSize, setUrlSize] = useState<{ urlLength: number; compressionRatio: number } | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [tab, setTab] = useState<"link" | "embed" | "export">("link");
  const [maxNodes, setMaxNodes] = useState(100);

  // Generate URL when dialog opens
  useEffect(() => {
    if (!open || nodes.length === 0) return;

    (async () => {
      const url = await generateShareUrl(nodes, edges, { maxNodes });
      setShareUrl(url);
      const size = await getShareUrlSize(nodes, edges, maxNodes);
      setUrlSize(size);
    })();
  }, [open, nodes, edges, maxNodes]);

  const handleCopy = useCallback(async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(label);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      // Fallback
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(label);
      setTimeout(() => setCopied(null), 2000);
    }
  }, []);

  const handleExportHtml = useCallback(() => {
    const limited = nodes.slice(0, maxNodes);
    const nodeIds = new Set(limited.map((n) => n.id));
    const limitedEdges = edges.filter((e) => nodeIds.has(e.from) && nodeIds.has(e.to));

    const html = generateStandaloneHtml(
      limited.map((n) => ({ id: n.id, text: n.text, layer: n.layer, type: n.type })),
      limitedEdges.map((e) => ({ from: e.from, to: e.to, type: e.type })),
      "Ontology Map Export",
    );

    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ontology-map.html";
    a.click();
    URL.revokeObjectURL(url);
  }, [nodes, edges, maxNodes]);

  const embedCode = `<script src="https://ontology-map.dev/widget.js"><\/script>
<ontology-map
  data-url="${shareUrl}"
  width="600"
  height="400"
  labels="true"
  interactive="true"
></ontology-map>`;

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div
        className="w-full max-w-lg rounded-[var(--radius-lg)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-0)] shadow-2xl"
        role="dialog"
        aria-label="Share"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] px-4 py-3">
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
            Share Map
          </h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[var(--color-border-subtle)] px-4">
          {[
            { id: "link" as const, label: "Link", icon: Link2 },
            { id: "embed" as const, label: "Embed", icon: Code2 },
            { id: "export" as const, label: "Export", icon: Download },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-[11px] font-medium transition-colors ${
                tab === t.id
                  ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                  : "border-transparent text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]"
              }`}
            >
              <t.icon className="h-3 w-3" />
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-4">
          {/* Node limit slider */}
          <div className="mb-3 flex items-center gap-3">
            <label className="text-[10px] text-[var(--color-text-tertiary)]">
              Max nodes:
            </label>
            <input
              type="range"
              min={10}
              max={Math.min(nodes.length, 500)}
              value={maxNodes}
              onChange={(e) => setMaxNodes(Number(e.target.value))}
              className="flex-1"
            />
            <span className="text-[10px] font-medium text-[var(--color-text-secondary)]">
              {maxNodes}
            </span>
          </div>

          {tab === "link" && (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={shareUrl}
                  readOnly
                  className="flex-1 rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] px-3 py-2 text-[11px] text-[var(--color-text-primary)]"
                />
                <button
                  onClick={() => handleCopy(shareUrl, "url")}
                  className="flex items-center gap-1 rounded bg-[var(--color-accent)] px-3 py-2 text-[11px] font-medium text-white transition-opacity hover:opacity-90"
                >
                  {copied === "url" ? (
                    <Check className="h-3 w-3" />
                  ) : (
                    <Copy className="h-3 w-3" />
                  )}
                  {copied === "url" ? "Copied!" : "Copy"}
                </button>
              </div>
              {urlSize && (
                <div className="flex gap-4 text-[10px] text-[var(--color-text-tertiary)]">
                  <span>URL length: {urlSize.urlLength.toLocaleString()} chars</span>
                  <span>Compression: {Math.round(urlSize.compressionRatio * 100)}% smaller</span>
                  <span>{maxNodes} of {nodes.length} nodes</span>
                </div>
              )}
            </div>
          )}

          {tab === "embed" && (
            <div className="flex flex-col gap-3">
              <div className="overflow-x-auto rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-3">
                <pre className="text-[10px] text-[var(--color-text-secondary)]">
                  {embedCode}
                </pre>
              </div>
              <button
                onClick={() => handleCopy(embedCode, "embed")}
                className="flex items-center justify-center gap-1.5 rounded bg-[var(--color-accent)] px-3 py-2 text-[11px] font-medium text-white transition-opacity hover:opacity-90"
              >
                {copied === "embed" ? (
                  <Check className="h-3 w-3" />
                ) : (
                  <Copy className="h-3 w-3" />
                )}
                {copied === "embed" ? "Copied!" : "Copy Embed Code"}
              </button>
            </div>
          )}

          {tab === "export" && (
            <div className="flex flex-col gap-3">
              <p className="text-[11px] text-[var(--color-text-secondary)]">
                Download a self-contained HTML file with an interactive graph viewer.
                No dependencies required — works offline.
              </p>
              <button
                onClick={handleExportHtml}
                className="flex items-center justify-center gap-1.5 rounded bg-[var(--color-accent)] px-3 py-2 text-[11px] font-medium text-white transition-opacity hover:opacity-90"
              >
                <Download className="h-3 w-3" />
                Download ontology-map.html
              </button>
              <p className="text-[9px] text-[var(--color-text-tertiary)]">
                Includes {Math.min(maxNodes, nodes.length)} nodes and{" "}
                {edges.filter((e) => {
                  const ids = new Set(nodes.slice(0, maxNodes).map((n) => n.id));
                  return ids.has(e.from) && ids.has(e.to);
                }).length}{" "}
                edges
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
