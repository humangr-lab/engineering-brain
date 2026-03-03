/**
 * useMapFeatures — encapsulates all Wave 2-4 feature state for MapPage.
 * Extracted from map.tsx to reduce the number of useState calls in a single component.
 */

import { useState, useCallback, useEffect, useRef } from "react";
import {
  enableSound,
  disableSound,
  isSoundEnabled,
} from "@/lib/engine/sound";
import {
  createPulseState,
  updatePulses,
  decayPulses,
} from "@/lib/engine/pulse";
import { getChangedFiles } from "@/lib/api";
import type { HeatmapMetric } from "@/lib/engine/heatmap";
import type { Node } from "@/lib/api";

const PULSE_DECAY_INTERVAL_MS = 64; // ~15fps for decay, not 60fps

export function useMapFeatures(nodes: Node[], projectPath: string | null) {
  // Wave 2 state
  const [earthquakeActive, setEarthquakeActive] = useState(false);
  const [heatmapActive, setHeatmapActive] = useState(false);
  const [heatmapMetric, setHeatmapMetric] = useState<HeatmapMetric>("degree");
  const [soundOn, setSoundOn] = useState(false);

  // Wave 3 state
  const [ghostActive, setGhostActive] = useState(false);
  const [annotationOpen, setAnnotationOpen] = useState(false);
  const [sandboxActive, setSandboxActive] = useState(false);
  const [timeTravelActive, setTimeTravelActive] = useState(false);
  const [pulseMap, setPulseMap] = useState<Map<string, number>>(new Map());
  const pulseStateRef = useRef(createPulseState());

  // Wave 4 state
  const [pluginPanelOpen, setPluginPanelOpen] = useState(false);
  const [enabledShapePacks, setEnabledShapePacks] = useState(["default"]);
  const [embedOpen, setEmbedOpen] = useState(false);

  // Wave 5 (SOTA features) state
  const [healthDashboardOpen, setHealthDashboardOpen] = useState(false);
  const [aiTrailActive, setAiTrailActive] = useState(false);
  const [aiTrailPath, setAiTrailPath] = useState<string[] | null>(null);
  const [aiTrailPlaying, setAiTrailPlaying] = useState(false);
  const [aiTrailProgress, setAiTrailProgress] = useState(0);
  const [sourcetrailActive, setSourcetrailActive] = useState(false);
  const [shareDialogOpen, setShareDialogOpen] = useState(false);

  // Sound toggle
  const toggleSound = useCallback(() => {
    if (isSoundEnabled()) {
      disableSound();
      setSoundOn(false);
    } else {
      enableSound();
      setSoundOn(true);
    }
  }, []);

  // Live Code Pulse — poll changed files every 5s
  useEffect(() => {
    if (!projectPath || nodes.length === 0) return;

    const poll = async () => {
      try {
        const changed = await getChangedFiles(projectPath);
        const updated = updatePulses(pulseStateRef.current, changed, nodes);
        pulseStateRef.current = updated;
        setPulseMap(new Map(updated.pulses));
      } catch {
        // git not available or project not a repo — ignore
      }
    };

    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, [projectPath, nodes]);

  // Pulse decay — throttled to ~15fps (not every rAF)
  useEffect(() => {
    if (pulseMap.size === 0) return;

    let last = performance.now();
    let timer: ReturnType<typeof setTimeout>;

    const tick = () => {
      const now = performance.now();
      const dt = (now - last) / 1000;
      last = now;
      const decayed = decayPulses(pulseMap, dt);
      if (decayed.size > 0) {
        setPulseMap(decayed);
        timer = setTimeout(tick, PULSE_DECAY_INTERVAL_MS);
      } else {
        setPulseMap(new Map());
      }
    };

    timer = setTimeout(tick, PULSE_DECAY_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [pulseMap]);

  // Time-travel commit select — pulse changed files
  const handleTimeTravelCommit = useCallback(
    (changedFiles: string[]) => {
      const updated = updatePulses(pulseStateRef.current, changedFiles, nodes);
      pulseStateRef.current = updated;
      setPulseMap(new Map(updated.pulses));
    },
    [nodes],
  );

  return {
    // Wave 2
    earthquakeActive,
    setEarthquakeActive,
    heatmapActive,
    setHeatmapActive,
    heatmapMetric,
    setHeatmapMetric,
    soundOn,
    toggleSound,

    // Wave 3
    ghostActive,
    setGhostActive,
    annotationOpen,
    setAnnotationOpen,
    sandboxActive,
    setSandboxActive,
    timeTravelActive,
    setTimeTravelActive,
    pulseMap,
    handleTimeTravelCommit,

    // Wave 4
    pluginPanelOpen,
    setPluginPanelOpen,
    enabledShapePacks,
    setEnabledShapePacks,
    embedOpen,
    setEmbedOpen,

    // Wave 5 (SOTA)
    healthDashboardOpen,
    setHealthDashboardOpen,
    aiTrailActive,
    setAiTrailActive,
    aiTrailPath,
    setAiTrailPath,
    aiTrailPlaying,
    setAiTrailPlaying,
    aiTrailProgress,
    setAiTrailProgress,
    sourcetrailActive,
    setSourcetrailActive,
    shareDialogOpen,
    setShareDialogOpen,
  } as const;
}
