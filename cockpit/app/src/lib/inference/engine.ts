/* ====== INFERENCE ENGINE -- 5-stage pipeline orchestrator ======
   Deterministic: same input always produces identical output.
   Stages: template -> layout -> palette -> shapes -> sizes
   Total confidence = geometric mean of 5 stage confidences.     */

import type { GraphData, GraphDataEdge } from "@/lib/api";
import {
  detectTemplate,
  type Features,
  type NormalizedEdge,
  type TemplateName,
} from "./template-detector";
import { selectLayout, type LayoutName } from "./layout-selector";
import { extractGroups, generatePalette, type GroupColor } from "./color-palette";
import { mapShapes, type ShapeName } from "./shape-mapper";
import { computeSizes } from "./sizer";

// ── Types ──

export interface ConfidenceBreakdown {
  template: number;
  layout: number;
  palette: number;
  shapes: number;
  sizing: number;
  total: number;
}

export interface InferredConfig {
  template: TemplateName;
  layout: LayoutName;
  palette: Map<string, GroupColor>;
  shapes: Map<string, ShapeName>;
  sizes: Map<string, number>;
  confidence: ConfidenceBreakdown;
  features: Features | Record<string, never>;
  allScores: Record<string, number>;
}

export interface InferOptions {
  theme?: "dark" | "light";
  log?: boolean;
}

// ── Public API ──

export function inferConfig(
  graphData: GraphData,
  options: InferOptions = {},
): InferredConfig {
  const { theme = "dark", log = false } = options;
  const nodes = graphData.nodes || [];
  const edges = graphData.edges || [];

  if (!nodes.length) {
    return blankConfig();
  }

  // Normalize edges: support both { from, to } and { f, t } formats
  const normalizedEdges: NormalizedEdge[] = edges.map(
    (e: GraphDataEdge & { f?: string; t?: string }) => ({
      from: e.from || e.f || "",
      to: e.to || e.t || "",
      type: e.type || undefined,
      properties: e.properties || {},
    }),
  );

  // Stage 1: Template Detection
  const templateResult = detectTemplate(nodes, normalizedEdges);
  const conf1 = templateResult.confidence;

  if (log) {
    console.log(
      "[Inference] Stage 1 - Template:",
      templateResult.template,
      "(confidence:",
      conf1.toFixed(3),
      ")",
    );
    console.log("[Inference]   Scores:", templateResult.allScores);
  }

  // Stage 2: Layout Selection
  const layoutResult = selectLayout(
    templateResult.template,
    nodes,
    normalizedEdges,
  );
  const conf2 = layoutResult.confidence;

  if (log) {
    console.log(
      "[Inference] Stage 2 - Layout:",
      layoutResult.layout,
      "(confidence:",
      conf2.toFixed(3),
      ")",
    );
  }

  // Stage 3: Color Palette
  const groups = extractGroups(nodes);
  const paletteResult = generatePalette(groups, theme);
  const conf3 = paletteResult.confidence;

  if (log) {
    console.log(
      "[Inference] Stage 3 - Palette:",
      groups.length,
      "groups",
      "(confidence:",
      conf3.toFixed(3),
      ")",
    );
  }

  // Stage 4: Shape Mapping
  const shapeResult = mapShapes(nodes);
  const conf4 = shapeResult.confidence;

  if (log) {
    console.log(
      "[Inference] Stage 4 - Shapes mapped",
      "(confidence:",
      conf4.toFixed(3),
      ")",
    );
  }

  // Stage 5: Sizing
  const sizeResult = computeSizes(nodes, normalizedEdges);
  const conf5 = sizeResult.confidence;

  if (log) {
    console.log(
      "[Inference] Stage 5 - Sizes computed",
      "(confidence:",
      conf5.toFixed(3),
      ")",
    );
  }

  // Confidence aggregation (geometric mean)
  const total = Math.pow(conf1 * conf2 * conf3 * conf4 * conf5, 1 / 5);

  if (log) {
    console.log("[Inference] Total confidence:", total.toFixed(3));
  }

  // Low confidence fallback
  if (total < 0.3) {
    if (log)
      console.warn(
        "[Inference] Confidence below 0.30 -- falling back to blank",
      );

    const blankSizes = new Map<string, number>();
    const blankShapes = new Map<string, ShapeName>();
    for (const n of nodes) {
      blankSizes.set(n.id, 1.0);
      blankShapes.set(n.id, "sphere");
    }

    return {
      template: "blank",
      layout: "force",
      palette: paletteResult.palette,
      shapes: blankShapes,
      sizes: blankSizes,
      confidence: {
        template: conf1,
        layout: conf2,
        palette: conf3,
        shapes: conf4,
        sizing: conf5,
        total,
      },
      features: templateResult.features,
      allScores: templateResult.allScores,
    };
  }

  if (total < 0.5) {
    console.warn(
      `[Inference] Low inference confidence: ${total.toFixed(3)}`,
    );
  }

  return {
    template: templateResult.template,
    layout: layoutResult.layout,
    palette: paletteResult.palette,
    shapes: shapeResult.shapes,
    sizes: sizeResult.sizes,
    confidence: {
      template: conf1,
      layout: conf2,
      palette: conf3,
      shapes: conf4,
      sizing: conf5,
      total,
    },
    features: templateResult.features,
    allScores: templateResult.allScores,
  };
}

function blankConfig(): InferredConfig {
  return {
    template: "blank",
    layout: "force",
    palette: new Map(),
    shapes: new Map(),
    sizes: new Map(),
    confidence: {
      template: 0.5,
      layout: 0.5,
      palette: 0.5,
      shapes: 0.5,
      sizing: 0.5,
      total: 0.5,
    },
    features: {},
    allScores: { blank: 0.15 },
  };
}
