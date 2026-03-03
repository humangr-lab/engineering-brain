import { useState, useMemo, useCallback } from "react";
import {
  X,
  ChevronLeft,
  ChevronRight,
  List,
  LayoutGrid,
  Search,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Node, Edge } from "@/lib/api";

type GroupBy = "layer" | "severity" | "domain" | "technology";

interface KlibFilters {
  search: string;
  layers: number[];
  severities: string[];
  confidence: number;
  tags: string[];
}

interface KlibModalProps {
  open: boolean;
  onClose: () => void;
  nodes: Node[];
  edges: Edge[];
  onSelectNode: (node: Node) => void;
}

export function KlibModal({
  open,
  onClose,
  nodes,
  edges,
  onSelectNode,
}: KlibModalProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [groupBy, setGroupBy] = useState<GroupBy>("layer");
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [filters, setFilters] = useState<KlibFilters>({
    search: "",
    layers: [],
    severities: [],
    confidence: 0,
    tags: [],
  });

  // Apply filters
  const filteredNodes = useMemo(() => {
    let result = nodes;

    if (filters.layers.length > 0) {
      result = result.filter((n) => filters.layers.includes(n.layer));
    }
    if (filters.severities.length > 0) {
      result = result.filter((n) =>
        filters.severities.includes((n.severity || "").toUpperCase()),
      );
    }
    if (filters.confidence > 0) {
      result = result.filter((n) => (n.confidence || 0) >= filters.confidence);
    }
    if (filters.search) {
      const q = filters.search.toLowerCase();
      result = result.filter((n) => {
        const haystack =
          `${n.id} ${n.text} ${n.why || ""} ${n.howTo || ""} ${(n.technologies || []).join(" ")} ${(n.domains || []).join(" ")}`.toLowerCase();
        return haystack.includes(q);
      });
    }
    if (filters.tags.length > 0) {
      result = result.filter((n) => {
        const allTags = [...(n.technologies || []), ...(n.domains || [])];
        return filters.tags.some((t) => allTags.includes(t));
      });
    }

    return result;
  }, [nodes, filters]);

  // Group nodes
  const grouped = useMemo(() => {
    const groups = new Map<string, Node[]>();
    for (const node of filteredNodes) {
      let key: string;
      switch (groupBy) {
        case "layer":
          key = node.layerName || `Layer ${node.layer}`;
          break;
        case "severity":
          key = node.severity || "info";
          break;
        case "domain":
          key = (node.domains || [])[0] || "Unclassified";
          break;
        case "technology":
          key = (node.technologies || [])[0] || "General";
          break;
      }
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(node);
    }
    // Sort by key
    return Array.from(groups.entries()).sort(([a], [b]) =>
      a.localeCompare(b),
    );
  }, [filteredNodes, groupBy]);

  // Selected node detail
  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId) || null,
    [nodes, selectedNodeId],
  );

  // Unique layers, severities, technologies for filter chips
  const allLayers = useMemo(
    () =>
      [...new Set(nodes.map((n) => n.layer))].sort().map((l) => ({
        value: l,
        label:
          nodes.find((n) => n.layer === l)?.layerName || `Layer ${l}`,
      })),
    [nodes],
  );

  const selectNode = useCallback(
    (nodeId: string) => {
      setSelectedNodeId(nodeId);
      const newHistory = history.slice(0, historyIdx + 1);
      newHistory.push(nodeId);
      setHistory(newHistory);
      setHistoryIdx(newHistory.length - 1);
    },
    [history, historyIdx],
  );

  const navigateBack = useCallback(() => {
    if (historyIdx > 0) {
      const newIdx = historyIdx - 1;
      setHistoryIdx(newIdx);
      setSelectedNodeId(history[newIdx]);
    }
  }, [historyIdx, history]);

  const navigateForward = useCallback(() => {
    if (historyIdx < history.length - 1) {
      const newIdx = historyIdx + 1;
      setHistoryIdx(newIdx);
      setSelectedNodeId(history[newIdx]);
    }
  }, [historyIdx, history]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="glass flex h-[80vh] w-full max-w-5xl flex-col rounded-[var(--radius-lg)] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] px-6 py-4">
          <div className="flex items-center gap-4">
            <h2 className="text-base font-semibold text-[var(--color-text-primary)]">
              Knowledge Library
            </h2>
            <div className="flex gap-2">
              {allLayers.map((l) => (
                <button
                  key={l.value}
                  onClick={() =>
                    setFilters((f) => ({
                      ...f,
                      layers: f.layers.includes(l.value)
                        ? f.layers.filter((x) => x !== l.value)
                        : [...f.layers, l.value],
                    }))
                  }
                  className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                    filters.layers.includes(l.value)
                      ? "bg-[var(--color-accent)] text-white"
                      : "text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-2)]"
                  }`}
                >
                  {l.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Navigation */}
            <button
              onClick={navigateBack}
              disabled={historyIdx <= 0}
              className="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)] disabled:opacity-30"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={navigateForward}
              disabled={historyIdx >= history.length - 1}
              className="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)] disabled:opacity-30"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
            {/* View mode */}
            <button
              onClick={() => setViewMode("list")}
              className={`rounded-[var(--radius-sm)] p-1.5 transition-colors ${viewMode === "list" ? "bg-[var(--color-surface-2)] text-[var(--color-text-primary)]" : "text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-2)]"}`}
            >
              <List className="h-4 w-4" />
            </button>
            <button
              onClick={() => setViewMode("grid")}
              className={`rounded-[var(--radius-sm)] p-1.5 transition-colors ${viewMode === "grid" ? "bg-[var(--color-surface-2)] text-[var(--color-text-primary)]" : "text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-2)]"}`}
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
            <button
              onClick={onClose}
              className="rounded-[var(--radius-sm)] p-1.5 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Stats bar */}
        <div className="flex items-center gap-4 border-b border-[var(--color-border-subtle)] px-6 py-2">
          <span className="text-[11px] text-[var(--color-text-tertiary)]">
            {filteredNodes.length === nodes.length
              ? `${nodes.length.toLocaleString()} nodes`
              : `${filteredNodes.length.toLocaleString()} of ${nodes.length.toLocaleString()} nodes`}
          </span>
          <span className="text-[11px] text-[var(--color-text-tertiary)]">
            {edges.length.toLocaleString()} edges
          </span>

          <div className="ml-auto flex items-center gap-1.5">
            <span className="text-[11px] text-[var(--color-text-tertiary)]">
              Group by:
            </span>
            {(["layer", "severity", "domain", "technology"] as const).map(
              (g) => (
                <button
                  key={g}
                  onClick={() => setGroupBy(g)}
                  className={`rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors ${
                    groupBy === g
                      ? "bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
                      : "text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]"
                  }`}
                >
                  {g}
                </button>
              ),
            )}
          </div>
        </div>

        {/* Body */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left: search + list */}
          <div className="flex flex-1 flex-col overflow-hidden border-r border-[var(--color-border-subtle)]">
            {/* Search */}
            <div className="flex items-center gap-2 border-b border-[var(--color-border-subtle)] px-4 py-2">
              <Search className="h-3.5 w-3.5 text-[var(--color-text-tertiary)]" />
              <input
                type="text"
                placeholder="Filter nodes..."
                value={filters.search}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, search: e.target.value }))
                }
                className="flex-1 bg-transparent text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none"
              />
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto p-2">
              {grouped.map(([groupLabel, items]) => (
                <div key={groupLabel} className="mb-3">
                  <div className="px-2 pb-1 text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
                    {groupLabel} ({items.length})
                  </div>
                  {items.map((node) => (
                    <button
                      key={node.id}
                      onClick={() => selectNode(node.id)}
                      className={`flex w-full items-center gap-2 rounded-[var(--radius-sm)] px-3 py-1.5 text-left transition-colors ${
                        selectedNodeId === node.id
                          ? "bg-[var(--color-accent)]/10 text-[var(--color-text-primary)]"
                          : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-2)]"
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px]">
                          {node.text || node.id}
                        </p>
                        <p className="truncate text-[11px] text-[var(--color-text-tertiary)]">
                          {node.id}
                        </p>
                      </div>
                      {node.severity && node.severity !== "info" && (
                        <Badge
                          variant={
                            node.severity === "critical"
                              ? "destructive"
                              : "secondary"
                          }
                          className="shrink-0 text-[9px]"
                        >
                          {node.severity}
                        </Badge>
                      )}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>

          {/* Right: detail */}
          <div className="w-[360px] shrink-0 overflow-y-auto p-4">
            {selectedNode ? (
              <NodeDetail
                node={selectedNode}
                edges={edges}
                allNodes={nodes}
                onNavigate={(nodeId) => {
                  selectNode(nodeId);
                }}
                onOpenInMap={() => {
                  onSelectNode(selectedNode);
                  onClose();
                }}
              />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-tertiary)]">
                Select a node to see details
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function NodeDetail({
  node,
  edges,
  allNodes,
  onNavigate,
  onOpenInMap,
}: {
  node: Node;
  edges: Edge[];
  allNodes: Node[];
  onNavigate: (nodeId: string) => void;
  onOpenInMap: () => void;
}) {
  const incoming = edges.filter((e) => e.to === node.id);
  const outgoing = edges.filter((e) => e.from === node.id);

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
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

      <p className="text-xs leading-relaxed text-[var(--color-text-secondary)]">
        {node.text}
      </p>

      <button
        onClick={onOpenInMap}
        className="w-full rounded-[var(--radius-md)] border border-[var(--color-accent)]/30 px-3 py-1.5 text-[12px] font-medium text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent)]/10"
      >
        Open in Map
      </button>

      {/* Metadata */}
      <div className="space-y-1.5 border-t border-[var(--color-border-subtle)] pt-3">
        {node.confidence != null && (
          <div className="flex justify-between text-[11px]">
            <span className="text-[var(--color-text-tertiary)]">Confidence</span>
            <span className="text-[var(--color-text-secondary)]">
              {Math.round(node.confidence * 100)}%
            </span>
          </div>
        )}
        {node.severity && (
          <div className="flex justify-between text-[11px]">
            <span className="text-[var(--color-text-tertiary)]">Severity</span>
            <span className="text-[var(--color-text-secondary)]">
              {node.severity}
            </span>
          </div>
        )}
        {node.technologies?.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-1">
            {node.technologies.map((t) => (
              <Badge key={t} variant="outline" className="text-[9px]">
                {t}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Why / How */}
      {node.why && (
        <div className="border-t border-[var(--color-border-subtle)] pt-3">
          <p className="mb-0.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
            Why
          </p>
          <p className="text-xs text-[var(--color-text-secondary)]">
            {node.why}
          </p>
        </div>
      )}

      {/* Connections */}
      {(incoming.length > 0 || outgoing.length > 0) && (
        <div className="border-t border-[var(--color-border-subtle)] pt-3">
          <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
            Connections ({incoming.length + outgoing.length})
          </p>
          <div className="max-h-40 space-y-1 overflow-y-auto">
            {outgoing.slice(0, 10).map((e) => {
              const target = allNodes.find((n) => n.id === e.to);
              return (
                <button
                  key={`o-${e.to}`}
                  onClick={() => onNavigate(e.to)}
                  className="flex w-full items-center gap-1.5 rounded-[var(--radius-sm)] px-1.5 py-0.5 text-left text-[11px] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-2)]"
                >
                  <span className="text-[var(--color-accent)]">&rarr;</span>
                  <span className="truncate">
                    {target?.text || e.to}
                  </span>
                </button>
              );
            })}
            {incoming.slice(0, 10).map((e) => {
              const source = allNodes.find((n) => n.id === e.from);
              return (
                <button
                  key={`i-${e.from}`}
                  onClick={() => onNavigate(e.from)}
                  className="flex w-full items-center gap-1.5 rounded-[var(--radius-sm)] px-1.5 py-0.5 text-left text-[11px] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-2)]"
                >
                  <span className="text-[var(--color-secondary)]">&larr;</span>
                  <span className="truncate">
                    {source?.text || e.from}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
