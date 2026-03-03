import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Node } from "@/lib/api";
import type { SysmapData } from "@/lib/inference/build-sysmap";

const FILTER_CHIPS = [
  { key: "all", label: "All" },
  { key: "principle", label: "Principles" },
  { key: "pattern", label: "Patterns" },
  { key: "rule", label: "Rules" },
  { key: "evidence", label: "Evidence" },
] as const;

type FilterKey = (typeof FILTER_CHIPS)[number]["key"];

const DEBOUNCE_MS = 150;
const MAX_RESULTS = 20;

/** Unified search result item — works for both brain Nodes and SYSMAP nodes. */
interface SearchItem {
  id: string;
  text: string;
  type: string;
  layerName: string;
  layer: number;
  source: "brain" | "sysmap";
  originalNode?: Node;
}

interface SearchOverlayProps {
  open: boolean;
  onClose: () => void;
  nodes: Node[];
  sysmapData?: SysmapData | null;
  onSelect: (node: Node) => void;
  onSysmapSelect?: (nodeId: string) => void;
}

export function SearchOverlay({
  open,
  onClose,
  nodes,
  sysmapData,
  onSelect,
  onSysmapSelect,
}: SearchOverlayProps) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Focus input when overlay opens
  useEffect(() => {
    if (open) {
      setQuery("");
      setFilter("all");
      setActiveIdx(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Build unified search items from both brain nodes and SYSMAP nodes
  const searchItems: SearchItem[] = useMemo(() => {
    // If SYSMAP data is available, use it as primary search source
    if (sysmapData && sysmapData.N.length > 0) {
      return sysmapData.N.map((n) => {
        const dt = sysmapData.DT[n.id];
        return {
          id: n.id,
          text: dt?.t || n.label,
          type: dt?.tp || n.g,
          layerName: n.g,
          layer: 0,
          source: "sysmap" as const,
        };
      });
    }
    // Fallback to brain nodes
    return nodes.map((n) => ({
      id: n.id,
      text: n.text || n.id,
      type: n.type,
      layerName: n.layerName || `Layer ${n.layer}`,
      layer: n.layer,
      source: "brain" as const,
      originalNode: n,
    }));
  }, [nodes, sysmapData]);

  // Search logic
  const results = useMemo(() => {
    const q = query.toLowerCase().trim();
    let filtered = searchItems;

    // Apply type filter
    if (filter !== "all") {
      filtered = filtered.filter((n) => {
        const layerName = (n.layerName || "").toLowerCase();
        return layerName.includes(filter);
      });
    }

    // Apply text search
    if (q) {
      filtered = filtered.filter((n) => {
        const haystack = `${n.id} ${n.text} ${n.layerName} ${n.type}`.toLowerCase();
        return haystack.includes(q);
      });
    }

    return filtered.slice(0, MAX_RESULTS);
  }, [searchItems, query, filter]);

  // Group results by layer
  const grouped = useMemo(() => {
    const groups = new Map<string, SearchItem[]>();
    for (const item of results) {
      const key = item.layerName;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(item);
    }
    return Array.from(groups.entries());
  }, [results]);

  // Flat list for keyboard nav
  const flatResults = useMemo(
    () => grouped.flatMap(([, items]) => items),
    [grouped],
  );

  const handleInput = useCallback(
    (value: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        setQuery(value);
        setActiveIdx(0);
      }, DEBOUNCE_MS);
    },
    [],
  );

  const selectResult = useCallback(
    (item: SearchItem) => {
      if (item.source === "sysmap") {
        onSysmapSelect?.(item.id);
      } else if (item.originalNode) {
        onSelect(item.originalNode);
      }
      onClose();
    },
    [onSelect, onSysmapSelect, onClose],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case "Escape":
          e.preventDefault();
          onClose();
          break;
        case "ArrowDown":
          e.preventDefault();
          setActiveIdx((i) => Math.min(i + 1, flatResults.length - 1));
          break;
        case "ArrowUp":
          e.preventDefault();
          setActiveIdx((i) => Math.max(i - 1, 0));
          break;
        case "Enter":
          e.preventDefault();
          if (flatResults[activeIdx]) {
            selectResult(flatResults[activeIdx]);
          }
          break;
        case "Tab": {
          e.preventDefault();
          const chips = FILTER_CHIPS.map((c) => c.key);
          const currentIdx = chips.indexOf(filter);
          const dir = e.shiftKey ? -1 : 1;
          const nextIdx = (currentIdx + dir + chips.length) % chips.length;
          setFilter(chips[nextIdx]);
          break;
        }
      }
    },
    [flatResults, activeIdx, filter, onClose, selectResult],
  );

  // Scroll active item into view
  useEffect(() => {
    const el = resultsRef.current?.querySelector("[data-active='true']");
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIdx]);

  if (!open) return null;

  let globalIdx = 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-[15vh] backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={handleKeyDown}
    >
      <div className="glass w-full max-w-[600px] rounded-[var(--radius-lg)] shadow-2xl">
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-[var(--color-border-subtle)] px-4 py-3">
          <Search className="h-4 w-4 shrink-0 text-[var(--color-text-tertiary)]" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search nodes, modules, files..."
            className="flex-1 bg-transparent text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none"
            onChange={(e) => handleInput(e.target.value)}
          />
          <kbd className="hidden rounded-[var(--radius-sm)] border border-[var(--color-border-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-tertiary)] sm:inline">
            ESC
          </kbd>
        </div>

        {/* Filter chips */}
        <div className="flex gap-1.5 border-b border-[var(--color-border-subtle)] px-4 py-2">
          {FILTER_CHIPS.map((chip) => (
            <button
              key={chip.key}
              onClick={() => setFilter(chip.key)}
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                filter === chip.key
                  ? "bg-[var(--color-accent)] text-white"
                  : "text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-secondary)]"
              }`}
            >
              {chip.label}
            </button>
          ))}
        </div>

        {/* Results */}
        <div
          ref={resultsRef}
          className="max-h-[50vh] overflow-y-auto p-2"
        >
          {flatResults.length === 0 && query.trim() ? (
            <div className="px-4 py-8 text-center text-sm text-[var(--color-text-tertiary)]">
              No results found
            </div>
          ) : flatResults.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-[var(--color-text-tertiary)]">
              Type to search nodes, modules, files...
            </div>
          ) : (
            grouped.map(([groupLabel, items]) => (
              <div key={groupLabel}>
                <div className="px-2 pb-1 pt-2 text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
                  {groupLabel}
                </div>
                {items.map((item) => {
                  const idx = globalIdx++;
                  const isActive = idx === activeIdx;
                  return (
                    <button
                      key={item.id}
                      data-active={isActive}
                      onClick={() => selectResult(item)}
                      className={`flex w-full items-center gap-3 rounded-[var(--radius-sm)] px-3 py-2 text-left transition-colors ${
                        isActive
                          ? "bg-[var(--color-accent)]/10 text-[var(--color-text-primary)]"
                          : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-2)]"
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm">
                            <Highlight text={item.text || item.id} query={query} />
                          </span>
                          <Badge
                            variant="outline"
                            className="shrink-0 text-[9px]"
                          >
                            {item.type}
                          </Badge>
                        </div>
                        {item.id !== item.text && (
                          <div className="mt-0.5 truncate text-[11px] text-[var(--color-text-tertiary)]">
                            <Highlight text={item.id} query={query} />
                          </div>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-[var(--color-border-subtle)] px-4 py-2">
          <span className="text-[11px] text-[var(--color-text-tertiary)]">
            {flatResults.length} result{flatResults.length !== 1 ? "s" : ""}
          </span>
          <div className="flex items-center gap-2 text-[10px] text-[var(--color-text-tertiary)]">
            <span>
              <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
                &uarr;&darr;
              </kbd>{" "}
              navigate
            </span>
            <span>
              <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
                &crarr;
              </kbd>{" "}
              select
            </span>
            <span>
              <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
                Tab
              </kbd>{" "}
              filter
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function Highlight({ text, query }: { text: string; query: string }) {
  if (!query.trim() || !text) return <>{text}</>;
  const q = query.trim().toLowerCase();
  const idx = text.toLowerCase().indexOf(q);
  if (idx === -1) return <>{text}</>;

  return (
    <>
      {text.slice(0, idx)}
      <mark className="rounded-sm bg-[var(--color-accent)]/20 text-inherit">
        {text.slice(idx, idx + q.length)}
      </mark>
      {text.slice(idx + q.length)}
    </>
  );
}
