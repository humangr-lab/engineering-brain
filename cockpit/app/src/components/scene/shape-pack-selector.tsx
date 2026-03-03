/**
 * Shape Pack Selector — toggle icon packs in the toolbar.
 */

import { useState, useCallback } from "react";
import { Shapes, Check } from "lucide-react";
import { getAllShapePacks, type ShapePack } from "@/lib/engine/shape-packs";

interface ShapePackSelectorProps {
  enabledPacks: string[];
  onPacksChange: (packs: string[]) => void;
}

export function ShapePackSelector({
  enabledPacks,
  onPacksChange,
}: ShapePackSelectorProps) {
  const [open, setOpen] = useState(false);
  const packs = getAllShapePacks();

  const toggle = useCallback(
    (packId: string) => {
      if (enabledPacks.includes(packId)) {
        // Don't allow disabling the last pack
        if (enabledPacks.length <= 1) return;
        onPacksChange(enabledPacks.filter((p) => p !== packId));
      } else {
        onPacksChange([...enabledPacks, packId]);
      }
    },
    [enabledPacks, onPacksChange],
  );

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
        title="Shape Packs"
      >
        <Shapes className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Shapes</span>
      </button>

      {open && (
        <div className="absolute bottom-full right-0 z-30 mb-1 w-[200px]">
          <div className="glass rounded-[var(--radius-md)] p-2">
            <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
              Shape Packs
            </p>
            <div className="space-y-1">
              {packs.map((pack: ShapePack) => {
                const enabled = enabledPacks.includes(pack.id);
                return (
                  <button
                    key={pack.id}
                    onClick={() => toggle(pack.id)}
                    className={`flex w-full items-center gap-2 rounded-[var(--radius-sm)] px-2 py-1.5 text-left transition-colors ${
                      enabled
                        ? "bg-[var(--color-surface-1)] text-[var(--color-text-primary)]"
                        : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-1)]"
                    }`}
                  >
                    {enabled ? (
                      <Check className="h-3 w-3 text-[var(--color-accent)]" />
                    ) : (
                      <div className="h-3 w-3" />
                    )}
                    <div>
                      <p className="text-[11px]">{pack.name}</p>
                      <p className="text-[9px] text-[var(--color-text-tertiary)]">
                        {pack.shapes.length} shapes
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
