/**
 * Annotation Panel — create/edit/delete post-it notes on nodes.
 * Appears when pressing N on a selected node.
 */

import { useState, useCallback, useEffect } from "react";
import {
  createAnnotation,
  updateAnnotation,
  deleteAnnotation,
  getAnnotationsForNode,
  ANNOTATION_COLORS,
  type Annotation,
} from "@/lib/engine/annotations";
import { StickyNote, Trash2, Plus } from "lucide-react";

interface AnnotationPanelProps {
  nodeId: string;
  nodeText: string;
  open: boolean;
  onClose?: () => void;
}

export function AnnotationPanel({
  nodeId,
  nodeText,
  open,
}: AnnotationPanelProps) {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [newText, setNewText] = useState("");
  const [selectedColor, setSelectedColor] = useState<string>(ANNOTATION_COLORS[0]);
  const [editingId, setEditingId] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setAnnotations(getAnnotationsForNode(nodeId));
    }
  }, [open, nodeId]);

  const handleCreate = useCallback(() => {
    if (!newText.trim()) return;
    const ann = createAnnotation(nodeId, newText.trim(), selectedColor);
    setAnnotations((prev) => [...prev, ann]);
    setNewText("");
  }, [nodeId, newText, selectedColor]);

  const handleUpdate = useCallback((id: string, text: string) => {
    const updated = updateAnnotation(id, text);
    if (updated) {
      setAnnotations((prev) =>
        prev.map((a) => (a.id === id ? updated : a)),
      );
    }
    setEditingId(null);
  }, []);

  const handleDelete = useCallback((id: string) => {
    deleteAnnotation(id);
    setAnnotations((prev) => prev.filter((a) => a.id !== id));
  }, []);

  if (!open) return null;

  return (
    <div className="absolute bottom-16 right-4 z-30 w-[280px]">
      <div className="glass rounded-[var(--radius-md)] p-3">
        {/* Header */}
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <StickyNote className="h-4 w-4 text-[var(--color-warning)]" />
            <span className="text-[12px] font-medium text-[var(--color-text-primary)]">
              Notes
            </span>
          </div>
          <span className="text-[10px] text-[var(--color-text-tertiary)]">
            {nodeText}
          </span>
        </div>

        {/* Existing annotations */}
        <div className="max-h-[200px] space-y-2 overflow-y-auto">
          {annotations.map((ann) => (
            <div
              key={ann.id}
              className="group relative rounded-[var(--radius-sm)] p-2"
              style={{
                backgroundColor: ann.color + "15",
                borderLeft: `3px solid ${ann.color}`,
              }}
            >
              {editingId === ann.id ? (
                <textarea
                  autoFocus
                  defaultValue={ann.text}
                  className="w-full resize-none bg-transparent text-[11px] text-[var(--color-text-primary)] outline-none"
                  rows={2}
                  onBlur={(e) => handleUpdate(ann.id, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleUpdate(ann.id, e.currentTarget.value);
                    }
                  }}
                />
              ) : (
                <p
                  className="cursor-pointer text-[11px] text-[var(--color-text-secondary)]"
                  onClick={() => setEditingId(ann.id)}
                >
                  {ann.text}
                </p>
              )}
              <div className="mt-1 flex items-center justify-between">
                <span className="text-[9px] text-[var(--color-text-tertiary)]">
                  {new Date(ann.updatedAt).toLocaleDateString()}
                </span>
                <button
                  onClick={() => handleDelete(ann.id)}
                  className="opacity-0 transition-opacity group-hover:opacity-100"
                >
                  <Trash2 className="h-3 w-3 text-[var(--color-destructive)]" />
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* New annotation input */}
        <div className="mt-2 border-t border-[var(--color-border-subtle)] pt-2">
          <div className="flex gap-1.5">
            <textarea
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              placeholder="Add a note..."
              className="flex-1 resize-none rounded-[var(--radius-sm)] bg-[var(--color-surface-1)] px-2 py-1.5 text-[11px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] outline-none"
              rows={2}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleCreate();
                }
              }}
            />
            <button
              onClick={handleCreate}
              disabled={!newText.trim()}
              className="self-end rounded-[var(--radius-sm)] bg-[var(--color-accent)] p-1.5 text-white transition-opacity disabled:opacity-30"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Color picker */}
          <div className="mt-1.5 flex gap-1">
            {ANNOTATION_COLORS.map((color) => (
              <button
                key={color}
                onClick={() => setSelectedColor(color)}
                className={`h-4 w-4 rounded-full transition-all ${
                  color === selectedColor
                    ? "ring-2 ring-white ring-offset-1 ring-offset-[var(--color-surface-0)]"
                    : ""
                }`}
                style={{ backgroundColor: color }}
              />
            ))}
          </div>
        </div>

        <p className="mt-2 text-[9px] text-[var(--color-text-tertiary)]">
          Press N to toggle &middot; Enter to save
        </p>
      </div>
    </div>
  );
}
