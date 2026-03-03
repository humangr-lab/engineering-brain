/* ====== LAYOUT SELECTOR -- Stage 2 of inference pipeline ======
   Maps detected template to a spatial layout algorithm.
   Includes size-based and topology-based overrides.            */

import type { GraphDataNode } from "@/lib/api";
import type { NormalizedEdge, TemplateName } from "./template-detector";

export type LayoutName =
  | "orbital"
  | "tree"
  | "pipeline"
  | "force"
  | "layered"
  | "grid";

export interface LayoutResult {
  layout: LayoutName;
  confidence: number;
}

const TEMPLATE_LAYOUT_MAP: Record<TemplateName, LayoutName> = {
  microservices: "orbital",
  monolith: "tree",
  pipeline: "pipeline",
  network: "force",
  hierarchy: "tree",
  layered: "layered",
  knowledge_graph: "force",
  blank: "force",
};

export function selectLayout(
  template: TemplateName,
  nodes: GraphDataNode[],
  edges: NormalizedEdge[],
): LayoutResult {
  const defaultLayout = TEMPLATE_LAYOUT_MAP[template] || "force";
  const nodeCount = nodes.length;

  // Rule 1: Very small graphs -> grid
  if (nodeCount < 10) {
    return { layout: "grid", confidence: 0.7 };
  }

  // Rule 2: Orbital does not scale beyond ~50 nodes
  if (defaultLayout === "orbital" && nodeCount > 50) {
    return { layout: "force", confidence: 0.7 };
  }

  // Rule 3: Tree-like structure
  if (isTreeLike(nodes, edges)) {
    return { layout: "tree", confidence: 0.8 };
  }

  // No override: template default
  return { layout: defaultLayout, confidence: 0.9 };
}

function isTreeLike(
  nodes: GraphDataNode[],
  edges: NormalizedEdge[],
): boolean {
  // Use Sets to avoid double-counting children from parent field + CONTAINS edges
  const childrenSets: Record<string, Set<string>> = {};

  for (const n of nodes) {
    if (n.parent) {
      if (!childrenSets[n.parent]) childrenSets[n.parent] = new Set();
      childrenSets[n.parent].add(n.id);
    }
  }

  for (const e of edges) {
    if (e.type === "CONTAINS") {
      if (!childrenSets[e.from]) childrenSets[e.from] = new Set();
      childrenSets[e.from].add(e.to);
    }
  }

  const parentIds = Object.keys(childrenSets);
  if (!parentIds.length) return false;

  const totalChildren = Object.values(childrenSets).reduce((s, set) => s + set.size, 0);
  const avgChildren = totalChildren / parentIds.length;
  return avgChildren <= 2.5;
}
