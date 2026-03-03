/* ═══ Drill-down constants — extracted to break circular dependency ═══ */

export const LEVELS = Object.freeze({
  SYSTEM:   0,
  MODULE:   1,
  FILE:     2,
  FUNCTION: 3,
  CODE:     4,
});

export const LEVEL_NAMES = ['System', 'Module', 'File', 'Function', 'Code'];
