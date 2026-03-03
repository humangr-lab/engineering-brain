/**
 * Live Code Pulse — track recently changed files and highlight corresponding nodes.
 * Pure engine module (no React dependency).
 *
 * Polls git status at intervals and produces a set of "pulsing" node IDs
 * with glow intensity that fades over time.
 */

import type { Node } from "@/lib/api";

export interface PulseState {
  /** Node ID → pulse intensity (0-1, fades over time) */
  pulses: Map<string, number>;
  /** Files that changed recently */
  changedFiles: string[];
  /** Timestamp of last update */
  lastUpdate: number;
}

/** Create initial empty pulse state */
export function createPulseState(): PulseState {
  return {
    pulses: new Map(),
    changedFiles: [],
    lastUpdate: Date.now(),
  };
}

/**
 * Update pulse state with new changed files.
 * Maps file paths to node IDs and creates/updates pulse intensities.
 */
export function updatePulses(
  state: PulseState,
  changedFiles: string[],
  nodes: Node[],
): PulseState {
  const now = Date.now();
  const elapsed = (now - state.lastUpdate) / 1000; // seconds

  // Fade existing pulses
  const pulses = new Map<string, number>();
  for (const [id, intensity] of state.pulses) {
    const faded = intensity * Math.exp(-elapsed * 0.2); // 5s half-life
    if (faded > 0.05) {
      pulses.set(id, faded);
    }
  }

  // Map new changed files to node IDs
  for (const file of changedFiles) {
    const matchingNodes = findNodesForFile(file, nodes);
    for (const nodeId of matchingNodes) {
      pulses.set(nodeId, 1.0); // full intensity for new changes
    }
  }

  return {
    pulses,
    changedFiles,
    lastUpdate: now,
  };
}

/**
 * Decay all pulses by elapsed time (call on each animation frame).
 * Returns updated map. Does NOT make API calls.
 */
export function decayPulses(
  pulses: Map<string, number>,
  deltaSeconds: number,
): Map<string, number> {
  const result = new Map<string, number>();
  for (const [id, intensity] of pulses) {
    const faded = intensity * Math.exp(-deltaSeconds * 0.2);
    if (faded > 0.05) {
      result.set(id, faded);
    }
  }
  return result;
}

/**
 * Find node IDs that correspond to a file path.
 * Matches by suffix — e.g. "src/auth.py" matches node "python:src.auth".
 */
function findNodesForFile(filePath: string, nodes: Node[]): string[] {
  const normalized = filePath
    .replace(/\\/g, "/")
    .replace(/^\.\//, "");

  const matches: string[] = [];

  for (const node of nodes) {
    // Check direct ID match (adapters use file path in ID)
    if (node.id.includes(normalized.replace(/\//g, "."))) {
      matches.push(node.id);
      continue;
    }
    // Check with original slash separators (e.g., "src/auth.py")
    if (node.id.includes(normalized)) {
      matches.push(node.id);
      continue;
    }

    // Check metadata file_path if present
    const nodePath = node.metadata?.file_path;
    if (typeof nodePath === "string" && nodePath === normalized) {
      matches.push(node.id);
    }
  }

  return matches;
}

/** Get pulse color — green for recent, fading to transparent */
export function getPulseColor(intensity: number): string {
  const alpha = Math.round(intensity * 255)
    .toString(16)
    .padStart(2, "0");
  return `#10b981${alpha}`; // emerald with alpha
}
