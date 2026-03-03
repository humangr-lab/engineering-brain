/* ====== INFERENCE ENGINE -- Barrel Export ====== */

export { inferConfig } from "./engine";
export type { InferredConfig, InferOptions, ConfidenceBreakdown } from "./engine";

export { detectTemplate, extractFeatures } from "./template-detector";
export type {
  TemplateName,
  TemplateResult,
  Features,
  NormalizedEdge,
} from "./template-detector";

export { selectLayout } from "./layout-selector";
export type { LayoutName, LayoutResult } from "./layout-selector";

export { extractGroups, generatePalette } from "./color-palette";
export type { GroupColor, PaletteResult } from "./color-palette";

export { mapShapes } from "./shape-mapper";
export type { ShapeName, ShapeResult } from "./shape-mapper";

export { computeSizes } from "./sizer";
export type { SizeResult } from "./sizer";

export { buildSysmap } from "./build-sysmap";
export type {
  SysmapData,
  SysmapNode,
  SysmapEdge,
  DetailTab,
  SubmapData,
  StatItem,
  LegendItem,
} from "./build-sysmap";
