/**
 * Time-Travel Slider — navigate through git history commit by commit.
 * Shows a timeline of commits with file changes highlighted.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { getGitLog, type GitCommit } from "@/lib/api";
import { GitCommitHorizontal, Play, Pause, SkipBack, SkipForward } from "lucide-react";

interface TimeTravelSliderProps {
  projectPath: string | null;
  active: boolean;
  /** Called with the list of changed files at the selected commit */
  onCommitSelect?: (changedFiles: string[]) => void;
}

export function TimeTravelSlider({
  projectPath,
  active,
  onCommitSelect,
}: TimeTravelSliderProps) {
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  // Load git log when activated
  useEffect(() => {
    if (!active || !projectPath) {
      setCommits([]);
      setPlaying(false);
      return;
    }

    setLoading(true);
    setError(null);
    getGitLog(projectPath, 50)
      .then((log) => {
        setCommits(log.reverse()); // oldest first for slider
        setSelectedIdx(log.length - 1); // start at HEAD
        setLoading(false);
      })
      .catch((e) => {
        setError(typeof e === "string" ? e : "Failed to load git history");
        setLoading(false);
      });
  }, [active, projectPath]);

  // Notify parent of selected commit's changed files
  useEffect(() => {
    if (commits.length > 0 && selectedIdx >= 0 && selectedIdx < commits.length) {
      onCommitSelect?.(commits[selectedIdx].changedFiles);
    }
  }, [selectedIdx, commits, onCommitSelect]);

  // Playback
  useEffect(() => {
    if (playing && commits.length > 0) {
      intervalRef.current = setInterval(() => {
        setSelectedIdx((prev) => {
          if (prev >= commits.length - 1) {
            setPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, 800); // 800ms per commit
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing, commits.length]);

  const handleSliderChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setSelectedIdx(Number(e.target.value));
      setPlaying(false);
    },
    [],
  );

  if (!active) return null;

  const current = commits[selectedIdx];

  return (
    <div className="absolute bottom-16 left-1/2 z-20 w-[500px] max-w-[90vw] -translate-x-1/2">
      <div className="glass rounded-[var(--radius-md)] p-3">
        {loading ? (
          <div className="flex items-center gap-2 text-[11px] text-[var(--color-text-secondary)]">
            <div className="h-3 w-3 animate-spin rounded-full border border-[var(--color-accent)] border-t-transparent" />
            Loading git history...
          </div>
        ) : error ? (
          <p className="text-[11px] text-[var(--color-destructive)]">{error}</p>
        ) : commits.length === 0 ? (
          <p className="text-[11px] text-[var(--color-text-tertiary)]">
            No git history found
          </p>
        ) : (
          <>
            {/* Current commit info */}
            <div className="mb-2 flex items-center gap-2">
              <GitCommitHorizontal className="h-4 w-4 shrink-0 text-[var(--color-accent)]" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[11px] font-medium text-[var(--color-text-primary)]">
                  {current?.message}
                </p>
                <p className="text-[9px] text-[var(--color-text-tertiary)]">
                  {current?.shortHash} by {current?.author} &middot;{" "}
                  {current?.date.split("T")[0]} &middot;{" "}
                  {current?.changedFiles.length} files
                </p>
              </div>
            </div>

            {/* Slider */}
            <div className="flex items-center gap-2">
              <input
                type="range"
                min={0}
                max={commits.length - 1}
                value={selectedIdx}
                onChange={handleSliderChange}
                className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-[var(--color-surface-2)] accent-[var(--color-accent)]"
              />
            </div>

            {/* Controls */}
            <div className="mt-2 flex items-center justify-between">
              <div className="flex items-center gap-1">
                <button
                  onClick={() => {
                    setSelectedIdx(0);
                    setPlaying(false);
                  }}
                  className="rounded-[var(--radius-sm)] p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
                  title="First commit"
                >
                  <SkipBack className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => setPlaying(!playing)}
                  className="rounded-[var(--radius-sm)] p-1 text-[var(--color-accent)]"
                  title={playing ? "Pause" : "Play"}
                >
                  {playing ? (
                    <Pause className="h-4 w-4" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                </button>
                <button
                  onClick={() => {
                    setSelectedIdx(commits.length - 1);
                    setPlaying(false);
                  }}
                  className="rounded-[var(--radius-sm)] p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
                  title="Latest commit"
                >
                  <SkipForward className="h-3.5 w-3.5" />
                </button>
              </div>

              <span className="text-[9px] tabular-nums text-[var(--color-text-tertiary)]">
                {selectedIdx + 1} / {commits.length}
              </span>

              <span className="text-[9px] text-[var(--color-text-tertiary)]">
                Press T to toggle
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
