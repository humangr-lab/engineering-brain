/* ====== INFERENCE ENGINE -- 5-stage pipeline orchestrator ======
   Deterministic: same input always produces identical output.
   Stages: template -> layout -> palette -> shapes -> sizes
   Total confidence = geometric mean of 5 stage confidences.     */

import { detectTemplate } from './template-detector.js';
import { selectLayout } from './layout-selector.js';
import { extractGroups, generatePalette } from './color-palette.js';
import { mapShapes } from './shape-mapper.js';
import { computeSizes } from './sizer.js';

/**
 * Run the full inference pipeline on graph data.
 * @param {object} graphData - { nodes: [], edges: [], metadata?: {} }
 * @param {object} [options]
 * @param {string} [options.theme='dark'] - 'dark' or 'light'
 * @param {boolean} [options.log=false] - Log inference decisions to console
 * @returns {object} InferredConfig
 */
export function inferConfig(graphData, options = {}) {
  const { theme = 'dark', log = false } = options;
  const nodes = graphData.nodes || [];
  const edges = graphData.edges || [];

  if (!nodes.length) {
    return _blankConfig();
  }

  // Normalize edges: support both { from, to } and { f, t } formats
  const normalizedEdges = edges.map(e => ({
    from: e.from || e.f,
    to: e.to || e.t,
    type: e.type || undefined,
    properties: e.properties || {},
  }));

  // Stage 1: Template Detection
  const templateResult = detectTemplate(nodes, normalizedEdges);
  const conf1 = templateResult.confidence;

  if (log) {
    console.log('[Inference] Stage 1 - Template:', templateResult.template,
      '(confidence:', conf1.toFixed(3), ')');
    console.log('[Inference]   Scores:', templateResult.allScores);
  }

  // Stage 2: Layout Selection
  const layoutResult = selectLayout(templateResult.template, nodes, normalizedEdges);
  const conf2 = layoutResult.confidence;

  if (log) {
    console.log('[Inference] Stage 2 - Layout:', layoutResult.layout,
      '(confidence:', conf2.toFixed(3), ')');
  }

  // Stage 3: Color Palette
  const groups = extractGroups(nodes);
  const paletteResult = generatePalette(groups, theme);
  const conf3 = paletteResult.confidence;

  if (log) {
    console.log('[Inference] Stage 3 - Palette:', groups.length, 'groups',
      '(confidence:', conf3.toFixed(3), ')');
  }

  // Stage 4: Shape Mapping
  const shapeResult = mapShapes(nodes);
  const conf4 = shapeResult.confidence;

  if (log) {
    console.log('[Inference] Stage 4 - Shapes mapped',
      '(confidence:', conf4.toFixed(3), ')');
  }

  // Stage 5: Sizing
  const sizeResult = computeSizes(nodes, normalizedEdges);
  const conf5 = sizeResult.confidence;

  if (log) {
    console.log('[Inference] Stage 5 - Sizes computed',
      '(confidence:', conf5.toFixed(3), ')');
  }

  // Confidence aggregation (geometric mean)
  const total = Math.pow(conf1 * conf2 * conf3 * conf4 * conf5, 1 / 5);

  if (log) {
    console.log('[Inference] Total confidence:', total.toFixed(3));
  }

  // Low confidence fallback
  if (total < 0.30) {
    if (log) console.warn('[Inference] Confidence below 0.30 -- falling back to blank');

    const blankSizes = new Map();
    const blankShapes = new Map();
    for (const n of nodes) {
      blankSizes.set(n.id, 1.0);
      blankShapes.set(n.id, 'sphere');
    }

    return {
      template: 'blank',
      layout: 'force',
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

  // Warn on medium confidence
  if (total < 0.50) {
    console.warn(`[Inference] Low inference confidence: ${total.toFixed(3)}`);
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

function _blankConfig() {
  return {
    template: 'blank',
    layout: 'force',
    palette: new Map(),
    shapes: new Map(),
    sizes: new Map(),
    confidence: {
      template: 0.5, layout: 0.5, palette: 0.5,
      shapes: 0.5, sizing: 0.5, total: 0.5,
    },
    features: {},
    allScores: { blank: 0.15 },
  };
}
