/**
 * Annotation Layer — persistent post-it notes anchored to nodes.
 * Stored in localStorage (would use .ontology-map/annotations.json in production).
 * Pure engine module (no React dependency).
 */

export interface Annotation {
  id: string;
  nodeId: string;
  text: string;
  color: string;
  createdAt: string;
  updatedAt: string;
}

const STORAGE_KEY = "ontology-map:annotations";

const ANNOTATION_COLORS: string[] = [
  "#fbbf24", // yellow (default)
  "#34d399", // green
  "#60a5fa", // blue
  "#f472b6", // pink
  "#a78bfa", // purple
];

export { ANNOTATION_COLORS };

/** Load all annotations from storage */
export function loadAnnotations(): Annotation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/** Save all annotations to storage */
function saveAnnotations(annotations: Annotation[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(annotations));
}

/** Create a new annotation */
export function createAnnotation(
  nodeId: string,
  text: string,
  color = ANNOTATION_COLORS[0],
): Annotation {
  const now = new Date().toISOString();
  const annotation: Annotation = {
    id: `ann_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    nodeId,
    text,
    color,
    createdAt: now,
    updatedAt: now,
  };

  const all = loadAnnotations();
  all.push(annotation);
  saveAnnotations(all);
  return annotation;
}

/** Update an existing annotation */
export function updateAnnotation(id: string, text: string): Annotation | null {
  const all = loadAnnotations();
  const idx = all.findIndex((a) => a.id === id);
  if (idx === -1) return null;

  all[idx].text = text;
  all[idx].updatedAt = new Date().toISOString();
  saveAnnotations(all);
  return all[idx];
}

/** Delete an annotation */
export function deleteAnnotation(id: string): boolean {
  const all = loadAnnotations();
  const filtered = all.filter((a) => a.id !== id);
  if (filtered.length === all.length) return false;
  saveAnnotations(filtered);
  return true;
}

/** Get annotations for a specific node */
export function getAnnotationsForNode(nodeId: string): Annotation[] {
  return loadAnnotations().filter((a) => a.nodeId === nodeId);
}

/** Get count of annotated nodes */
export function getAnnotationStats(): {
  total: number;
  nodeCount: number;
} {
  const all = loadAnnotations();
  const nodeIds = new Set(all.map((a) => a.nodeId));
  return {
    total: all.length,
    nodeCount: nodeIds.size,
  };
}
