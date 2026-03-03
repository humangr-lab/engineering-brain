/* ═══════════════ SCHEMA — Type defs, layer colors, icons ═══════════════
   Pure data — no rendering dependencies.
   LAYERS, EDGE_TYPES, GROUP_COLORS are mutable: populated from inference
   or schema overrides, with current values as defaults.                  */

// ── Default LAYERS (Engineering Brain-specific, overridden by inference) ──

export let LAYERS = [
  { id: 0, name: 'L0 — Axioms',     shortName: 'L0', color: '#ff6b6b', desc: 'Foundational truths. Confidence 1.0. Never decay.' },
  { id: 1, name: 'L1 — Principles', shortName: 'L1', color: '#fbbf24', desc: 'Engineering principles grounded by axioms.' },
  { id: 2, name: 'L2 — Patterns',   shortName: 'L2', color: '#34d399', desc: 'Recurring solutions promoted from rules.' },
  { id: 3, name: 'L3 — Rules',      shortName: 'L3', color: '#6b8fff', desc: 'Specific, actionable constraints.' },
  { id: 4, name: 'L4 — Evidence',   shortName: 'L4', color: '#9b7cff', desc: 'Observations from code analysis and feedback.' },
  { id: 5, name: 'L5 — Context',    shortName: 'L5', color: '#5eead4', desc: 'Temporal, ephemeral knowledge.' },
];

export let LAYER_BY_ID = Object.fromEntries(LAYERS.map(l => [l.id, l]));

export const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

export const SEVERITY_COLORS = {
  CRITICAL: '#ef4444',
  HIGH:     '#f59e0b',
  MEDIUM:   '#6b8fff',
  LOW:      '#34d399',
  INFO:     '#9b7cff',
};

// ── Default EDGE_TYPES ──

export let EDGE_TYPES = {
  // Hierarchical
  GROUNDS:        { cat: 'Hierarchical', desc: 'Axiom \u2192 Principle', color: '#ff6b6b' },
  INFORMS:        { cat: 'Hierarchical', desc: 'Principle \u2192 Pattern', color: '#fbbf24' },
  INSTANTIATES:   { cat: 'Hierarchical', desc: 'Pattern \u2192 Rule', color: '#34d399' },
  EVIDENCED_BY:   { cat: 'Hierarchical', desc: 'Rule \u2192 Finding', color: '#6b8fff' },
  DEMONSTRATED_BY:{ cat: 'Hierarchical', desc: 'Rule \u2192 CodeExample', color: '#9b7cff' },
  // Cross-layer
  APPLIES_TO:     { cat: 'Cross-layer', desc: 'Rule/Pattern \u2192 Technology', color: '#5eead4' },
  IN_DOMAIN:      { cat: 'Cross-layer', desc: 'Rule/Pattern \u2192 Domain', color: '#5eead4' },
  USED_IN:        { cat: 'Cross-layer', desc: 'Pattern \u2192 Technology', color: '#5eead4' },
  CAUGHT_BY:      { cat: 'Cross-layer', desc: 'Finding \u2192 HumanLayer', color: '#5eead4' },
  VIOLATED:       { cat: 'Cross-layer', desc: 'Finding \u2192 Rule', color: '#ef4444' },
  IN_SPRINT:      { cat: 'Cross-layer', desc: 'Finding \u2192 Sprint', color: '#5eead4' },
  // Evolution
  SUPERSEDES:     { cat: 'Evolution', desc: 'Rule \u2192 Rule (newer)', color: '#f59e0b' },
  CONFLICTS_WITH: { cat: 'Evolution', desc: 'Rule \u2194 Rule (contradiction)', color: '#ef4444' },
  VARIANT_OF:     { cat: 'Evolution', desc: 'Pattern \u2192 Pattern (family)', color: '#9b7cff' },
  REINFORCES:     { cat: 'Evolution', desc: 'Evidence \u2192 Rule', color: '#34d399' },
  WEAKENS:        { cat: 'Evolution', desc: 'Evidence \u2192 Rule', color: '#ef4444' },
  // Causal
  CAUSED_BY:      { cat: 'Causal', desc: 'Finding \u2192 Finding', color: '#f59e0b' },
  PREVENTS:       { cat: 'Causal', desc: 'Rule \u2192 Pattern (anti)', color: '#34d399' },
  // Context
  REQUIRES:       { cat: 'Context', desc: 'Task \u2192 Technology', color: '#5eead4' },
  PRODUCES:       { cat: 'Context', desc: 'Task \u2192 FileType', color: '#5eead4' },
  SUBDOMAIN_OF:   { cat: 'Context', desc: 'Domain \u2192 Domain', color: '#6b8fff' },
  // Source
  CITES:          { cat: 'Source', desc: 'Knowledge \u2192 Source', color: '#8b95aa' },
  SOURCED_FROM:   { cat: 'Source', desc: 'Rule \u2192 Source (creation)', color: '#8b95aa' },
  VALIDATED_BY:   { cat: 'Source', desc: 'Knowledge \u2192 ValidationRun', color: '#8b95aa' },
  // Reasoning (epistemic chains)
  RELATES_TO:     { cat: 'Reasoning', desc: 'General relationship', color: '#94a3b8' },
  STRENGTHENS:    { cat: 'Reasoning', desc: 'Evidence supports rule', color: '#34d399' },
  PREREQUISITE:   { cat: 'Reasoning', desc: 'Must hold before applying', color: '#fbbf24' },
  DEEPENS:        { cat: 'Reasoning', desc: 'Adds nuance or detail', color: '#6b8fff' },
  ALTERNATIVE:    { cat: 'Reasoning', desc: 'Different approach for same problem', color: '#9b7cff' },
  TRIGGERS:       { cat: 'Causal', desc: 'Activates when condition met', color: '#f59e0b' },
  COMPLEMENTS:    { cat: 'Reasoning', desc: 'Works well together', color: '#5eead4' },
  VALIDATES:      { cat: 'Source', desc: 'Test/evidence validates rule', color: '#34d399' },
};

export let EDGE_CATEGORIES = [...new Set(Object.values(EDGE_TYPES).map(e => e.cat))];

// ── Default GROUP_COLORS for 3D map ──

export let GROUP_COLORS = {
  source:   { hex: '#34d399', int: 0x34d399 },
  layer:    { hex: '#6b8fff', int: 0x6b8fff },
  module:   { hex: '#9b7cff', int: 0x9b7cff },
  consumer: { hex: '#5eead4', int: 0x5eead4 },
};

// Shape name list (26 shapes from shapes.js)
export const SHAPES = [
  'brain','gauge','tree','hub','sphere','monument','pillars','gear','gate',
  'database','hourglass','prism','stairs','nexus','graph','dial','vault',
  'warehouse','factory','satellite','terminal','screens','rack','conveyor',
  'monitor','dyson_book',
];

// ── Dynamic population from inference/schema ──

/**
 * Update GROUP_COLORS from an inferred palette Map.
 * @param {Map<string, {hex: string, int: number}>} palette
 */
export function setGroupColorsFromPalette(palette) {
  if (!palette || !palette.size) return;
  const updated = { ...GROUP_COLORS };
  for (const [group, color] of palette) {
    updated[group] = { hex: color.hex, int: color.int };
  }
  GROUP_COLORS = updated;
}

/**
 * Update LAYERS from schema data.
 * @param {Array} layers - Array of { id, name, shortName, color, desc }
 */
export function setLayers(layers) {
  if (!layers || !layers.length) return;
  LAYERS = layers;
  LAYER_BY_ID = Object.fromEntries(LAYERS.map(l => [l.id, l]));
}

/**
 * Update EDGE_TYPES from schema or graph edge types.
 * @param {object} edgeTypes - { TYPE_NAME: { cat, desc, color }, ... }
 */
export function setEdgeTypes(edgeTypes) {
  if (!edgeTypes) return;
  EDGE_TYPES = { ...EDGE_TYPES, ...edgeTypes };
  EDGE_CATEGORIES = [...new Set(Object.values(EDGE_TYPES).map(e => e.cat))];
}
