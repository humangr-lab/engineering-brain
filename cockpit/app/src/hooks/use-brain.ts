import { useCallback, useEffect, useRef, useState } from "react";
import {
  getGraph,
  getStats,
  openProject as apiOpenProject,
  analyzeProject as apiAnalyzeProject,
  type GraphSnapshot,
  type GraphData,
  type Stats,
} from "@/lib/api";
import {
  classifyNodes,
  mergeClassification,
  isEnrichmentEnabled,
} from "@/lib/agent/classifier";

/**
 * Hook for loading and subscribing to the brain graph data.
 * Calls Rust backend via invoke() IPC.
 *
 * Provides two data paths:
 * - `graph` / `stats`: Brain format (for existing knowledge graph features)
 * - `graphData`: graph_data.json format (for inference engine / 3D system map)
 */
export function useBrain() {
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projectPath, setProjectPath] = useState<string | null>(null);
  const [classifying, setClassifying] = useState(false);
  const [classifyProgress, setClassifyProgress] = useState<{ done: number; total: number } | null>(null);
  const classifyAbortRef = useRef<AbortController | null>(null);

  const loadGraph = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [graphResult, statsResult] = await Promise.all([
        getGraph(),
        getStats(),
      ]);
      setGraph(graphResult);
      setStats(statsResult);
    } catch (err) {
      // In dev mode without Tauri, invoke() will fail — graceful fallback
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("not a function") || msg.includes("__TAURI")) {
        setError("Running in browser mode — Tauri backend not available");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const openProject = useCallback(async (path: string) => {
    try {
      setLoading(true);
      setError(null);

      // Run both: brain format (for existing features) + graph_data format (for inference)
      const [snapshot, analyzed] = await Promise.all([
        apiOpenProject(path),
        apiAnalyzeProject(path),
      ]);

      setGraph(snapshot);
      setStats(snapshot.stats);
      setGraphData(analyzed);
      setProjectPath(path);

      // Optionally run LLM classification (non-blocking)
      if (isEnrichmentEnabled() && analyzed.nodes.length > 0) {
        // Abort any in-flight classification from a previous openProject call
        classifyAbortRef.current?.abort();
        const controller = new AbortController();
        classifyAbortRef.current = controller;

        setClassifying(true);
        setClassifyProgress({ done: 0, total: analyzed.nodes.length });
        classifyNodes(analyzed, {
          onProgress: (done, total) => setClassifyProgress({ done, total }),
          signal: controller.signal,
        })
          .then((result) => {
            if (controller.signal.aborted) return;
            if (result.classified > 0) {
              const enriched = mergeClassification(analyzed, result.nodes);
              setGraphData(enriched);
            }
          })
          .catch((err) => {
            if (err instanceof Error && err.name === "AbortError") return;
            console.warn("Classification failed:", err);
          })
          .finally(() => {
            if (!controller.signal.aborted) {
              setClassifying(false);
              setClassifyProgress(null);
            }
          });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  // Listen for file watcher events from Rust backend
  const projectPathRef = useRef(projectPath);
  projectPathRef.current = projectPath;

  useEffect(() => {
    let unlisten: (() => void) | null = null;

    async function setupListener() {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        unlisten = await listen("brain_version_changed", () => {
          // Auto-reload brain graph
          loadGraph();
          // Also re-analyze project if we have a path
          if (projectPathRef.current) {
            apiAnalyzeProject(projectPathRef.current)
              .then(setGraphData)
              .catch(() => {});
          }
        });
      } catch {
        // Not in Tauri context — ignore
      }
    }

    setupListener();
    return () => { unlisten?.(); };
  }, [loadGraph]);

  return {
    graph,
    graphData,
    stats,
    loading,
    error,
    projectPath,
    classifying,
    classifyProgress,
    reload: loadGraph,
    openProject,
  };
}
