/**
 * Sourcetrail-style Bidirectional Navigation Panel.
 *
 * Three-column layout:
 *   [Incoming deps] ← [Selected Node] → [Outgoing deps]
 *
 * Features:
 * - Click on any dependency to navigate (it becomes the center)
 * - Breadcrumb trail of navigation history
 * - Animated transitions between nodes
 * - Edge type grouping (IMPORTS, CONTAINS, CALLS, etc.)
 * - Code preview snippet (if file_path available)
 */

import { useState, useCallback, useMemo, useRef } from "react";
import type { Node, Edge } from "@/lib/api";
import {
  ArrowLeftCircle,
  ArrowRightCircle,
  ChevronRight,
  Home,
  Layers,
  GitBranch,
  FileCode,
  X,
} from "lucide-react";

interface SourcetrailViewProps {
  nodes: Node[];
  edges: Edge[];
  selectedNode: Node | null;
  onNodeSelect: (node: Node) => void;
  onClose: () => void;
  active: boolean;
}

interface NavEntry {
  nodeId: string;
  label: string;
}

export function SourcetrailView({
  nodes,
  edges,
  selectedNode,
  onNodeSelect,
  onClose,
  active,
}: SourcetrailViewProps) {
  const [history, setHistory] = useState<NavEntry[]>([]);
  const [animDir, setAnimDir] = useState<"left" | "right" | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // Node lookup map
  const nodeMap = useMemo(
    () => new Map(nodes.map((n) => [n.id, n])),
    [nodes],
  );

  // Incoming edges (edges pointing TO selected node)
  const incoming = useMemo(() => {
    if (!selectedNode) return [];
    return edges
      .filter((e) => e.to === selectedNode.id)
      .map((e) => ({
        edge: e,
        node: nodeMap.get(e.from),
      }))
      .filter((entry): entry is { edge: Edge; node: Node } => entry.node !== undefined);
  }, [selectedNode, edges, nodeMap]);

  // Outgoing edges (edges pointing FROM selected node)
  const outgoing = useMemo(() => {
    if (!selectedNode) return [];
    return edges
      .filter((e) => e.from === selectedNode.id)
      .map((e) => ({
        edge: e,
        node: nodeMap.get(e.to),
      }))
      .filter((entry): entry is { edge: Edge; node: Node } => entry.node !== undefined);
  }, [selectedNode, edges, nodeMap]);

  // Group by edge type
  const incomingGrouped = useMemo(() => groupByType(incoming), [incoming]);
  const outgoingGrouped = useMemo(() => groupByType(outgoing), [outgoing]);

  // Navigate to a node
  const navigateTo = useCallback(
    (node: Node, direction: "left" | "right") => {
      if (selectedNode) {
        setHistory((prev) => [
          ...prev,
          { nodeId: selectedNode.id, label: selectedNode.text },
        ]);
      }
      setAnimDir(direction);
      onNodeSelect(node);
      // Reset animation after transition
      setTimeout(() => setAnimDir(null), 300);
    },
    [selectedNode, onNodeSelect],
  );

  // Go back in history
  const goBack = useCallback(() => {
    if (history.length === 0) return;
    const prev = history[history.length - 1];
    const node = nodeMap.get(prev.nodeId);
    if (node) {
      setHistory((h) => h.slice(0, -1));
      setAnimDir("left");
      onNodeSelect(node);
      setTimeout(() => setAnimDir(null), 300);
    }
  }, [history, nodeMap, onNodeSelect]);

  if (!active || !selectedNode) return null;

  return (
    <div className="absolute inset-x-4 bottom-14 top-4 z-20 flex flex-col overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-0)]/95 backdrop-blur-md">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] px-4 py-2">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-[var(--color-accent)]" />
          <span className="text-xs font-semibold text-[var(--color-text-primary)]">
            Dependency Explorer
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Breadcrumb */}
          <div className="flex items-center gap-0.5 overflow-x-auto">
            {history.length > 0 && (
              <button
                onClick={goBack}
                className="rounded p-0.5 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]"
                title="Go back"
              >
                <Home className="h-3 w-3" />
              </button>
            )}
            {history.slice(-3).map((entry, i) => (
              <span key={`${entry.nodeId}-${i}`} className="flex items-center">
                <ChevronRight className="h-2.5 w-2.5 text-[var(--color-text-tertiary)]" />
                <button
                  onClick={() => {
                    const node = nodeMap.get(entry.nodeId);
                    if (node) navigateTo(node, "left");
                  }}
                  className="max-w-20 truncate rounded px-1 text-[9px] text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)]"
                >
                  {entry.label}
                </button>
              </span>
            ))}
            <ChevronRight className="h-2.5 w-2.5 text-[var(--color-text-tertiary)]" />
            <span className="text-[9px] font-medium text-[var(--color-accent)]">
              {selectedNode.text}
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Three-column layout */}
      <div
        ref={contentRef}
        className={`flex flex-1 overflow-hidden ${
          animDir === "left" ? "animate-slide-left" : animDir === "right" ? "animate-slide-right" : ""
        }`}
      >
        {/* Incoming (left column) */}
        <div className="flex w-1/3 flex-col border-r border-[var(--color-border-subtle)]">
          <div className="flex items-center gap-1.5 border-b border-[var(--color-border-subtle)] px-3 py-1.5">
            <ArrowLeftCircle className="h-3 w-3 text-[var(--color-secondary)]" />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
              References ({incoming.length})
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {Object.entries(incomingGrouped).map(([type, entries]) => (
              <EdgeGroup
                key={type}
                type={type}
                entries={entries}
                direction="incoming"
                onNodeClick={(node) => navigateTo(node, "left")}
              />
            ))}
            {incoming.length === 0 && (
              <EmptyState text="No incoming dependencies" />
            )}
          </div>
        </div>

        {/* Center (selected node detail) */}
        <div className="flex w-1/3 flex-col">
          <div className="flex items-center gap-1.5 border-b border-[var(--color-border-subtle)] px-3 py-1.5">
            <Layers className="h-3 w-3 text-[var(--color-accent)]" />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
              Selected
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            <NodeDetail node={selectedNode} edges={edges} />
          </div>
        </div>

        {/* Outgoing (right column) */}
        <div className="flex w-1/3 flex-col border-l border-[var(--color-border-subtle)]">
          <div className="flex items-center gap-1.5 border-b border-[var(--color-border-subtle)] px-3 py-1.5">
            <ArrowRightCircle className="h-3 w-3 text-[var(--color-warning)]" />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
              Dependencies ({outgoing.length})
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {Object.entries(outgoingGrouped).map(([type, entries]) => (
              <EdgeGroup
                key={type}
                type={type}
                entries={entries}
                direction="outgoing"
                onNodeClick={(node) => navigateTo(node, "right")}
              />
            ))}
            {outgoing.length === 0 && (
              <EmptyState text="No outgoing dependencies" />
            )}
          </div>
        </div>
      </div>

      {/* Footer stats */}
      <div className="flex items-center justify-between border-t border-[var(--color-border-subtle)] px-4 py-1">
        <span className="text-[9px] text-[var(--color-text-tertiary)]">
          Layer {selectedNode.layer} ({selectedNode.layerName}) | {selectedNode.type}
        </span>
        <span className="text-[9px] text-[var(--color-text-tertiary)]">
          {incoming.length} in | {outgoing.length} out | Confidence: {Math.round((selectedNode.confidence ?? 0) * 100)}%
        </span>
      </div>
    </div>
  );
}

// ─── Sub-Components ──────────────────────────────────────────────────────────

function EdgeGroup({
  type,
  entries,
  direction: _direction,
  onNodeClick,
}: {
  type: string;
  entries: { edge: Edge; node: Node }[];
  direction: "incoming" | "outgoing";
  onNodeClick: (node: Node) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="mb-2">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex w-full items-center gap-1 rounded px-1 py-0.5 text-[9px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-2)]"
      >
        <ChevronRight
          className={`h-2.5 w-2.5 transition-transform ${collapsed ? "" : "rotate-90"}`}
        />
        {type} ({entries.length})
      </button>
      {!collapsed && (
        <div className="ml-3 flex flex-col gap-0.5">
          {entries.map((entry) => (
            <button
              key={entry.node.id}
              onClick={() => onNodeClick(entry.node)}
              className="flex items-center gap-1.5 rounded px-1.5 py-0.5 text-left transition-colors hover:bg-[var(--color-surface-2)]"
            >
              <NodeTypeIcon type={entry.node.type} />
              <span className="flex-1 truncate text-[10px] text-[var(--color-text-secondary)]">
                {entry.node.text}
              </span>
              <span className="text-[8px] text-[var(--color-text-tertiary)]">
                L{entry.node.layer}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function NodeDetail({ node, edges }: { node: Node; edges: Edge[] }) {
  const totalEdges = edges.filter(
    (e) => e.from === node.id || e.to === node.id,
  ).length;

  return (
    <div className="flex flex-col gap-3">
      {/* Title */}
      <div>
        <div className="flex items-center gap-1.5">
          <NodeTypeIcon type={node.type} />
          <h4 className="text-sm font-semibold text-[var(--color-text-primary)]">
            {node.text}
          </h4>
        </div>
        <p className="mt-0.5 text-[10px] text-[var(--color-text-tertiary)]">
          {node.id}
        </p>
      </div>

      {/* Metadata grid */}
      <div className="grid grid-cols-2 gap-2">
        <MetaItem label="Type" value={node.type} />
        <MetaItem label="Layer" value={`${node.layer} (${node.layerName})`} />
        <MetaItem label="Severity" value={node.severity} />
        <MetaItem label="Confidence" value={`${Math.round((node.confidence ?? 0) * 100)}%`} />
        <MetaItem label="Total Edges" value={String(totalEdges)} />
        {node.epistemicStatus && (
          <MetaItem label="Epistemic" value={node.epistemicStatus} />
        )}
      </div>

      {/* Tags */}
      {(node.technologies.length > 0 || node.domains.length > 0) && (
        <div className="flex flex-wrap gap-1">
          {node.technologies.map((t) => (
            <span
              key={t}
              className="rounded-full bg-[var(--color-accent)]/10 px-1.5 py-0.5 text-[8px] text-[var(--color-accent)]"
            >
              {t}
            </span>
          ))}
          {node.domains.map((d) => (
            <span
              key={d}
              className="rounded-full bg-[var(--color-secondary)]/10 px-1.5 py-0.5 text-[8px] text-[var(--color-secondary)]"
            >
              {d}
            </span>
          ))}
        </div>
      )}

      {/* Why / HowTo / WhenToUse */}
      {node.why && (
        <div>
          <p className="text-[9px] font-semibold text-[var(--color-text-secondary)]">Why</p>
          <p className="text-[10px] text-[var(--color-text-tertiary)]">{node.why}</p>
        </div>
      )}
      {node.howTo && (
        <div>
          <p className="text-[9px] font-semibold text-[var(--color-text-secondary)]">How To</p>
          <p className="text-[10px] text-[var(--color-text-tertiary)]">{node.howTo}</p>
        </div>
      )}
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[8px] uppercase text-[var(--color-text-tertiary)]">{label}</p>
      <p className="text-[10px] font-medium text-[var(--color-text-secondary)]">{value}</p>
    </div>
  );
}

function NodeTypeIcon({ type }: { type: string }) {
  switch (type) {
    case "module":
    case "component":
      return <FileCode className="h-3 w-3 flex-shrink-0 text-[var(--color-accent)]" />;
    case "function":
    case "hook":
      return <GitBranch className="h-3 w-3 flex-shrink-0 text-[var(--color-secondary)]" />;
    case "class":
      return <Layers className="h-3 w-3 flex-shrink-0 text-[var(--color-warning)]" />;
    default:
      return <div className="h-3 w-3 flex-shrink-0 rounded-full bg-[var(--color-text-tertiary)]" style={{ width: 12, height: 12 }} />;
  }
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center py-8">
      <p className="text-[10px] text-[var(--color-text-tertiary)]">{text}</p>
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function groupByType(
  entries: { edge: Edge; node: Node }[],
): Record<string, { edge: Edge; node: Node }[]> {
  const groups: Record<string, { edge: Edge; node: Node }[]> = {};
  for (const entry of entries) {
    const type = entry.edge.type || "RELATED";
    if (!groups[type]) groups[type] = [];
    groups[type].push(entry);
  }
  return groups;
}
