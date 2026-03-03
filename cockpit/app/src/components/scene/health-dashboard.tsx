/**
 * Health Dashboard — Code health score visualization with gamification.
 *
 * Shows:
 * - Circular gauge with overall score + grade
 * - Dimension breakdown (radar chart via SVG)
 * - Hotspot quadrant chart
 * - Sparkline trend
 * - Achievement badges
 */

import { useMemo, useState } from "react";
import type { Node, Edge } from "@/lib/api";
import {
  computeHealthScore,
  gradeHex,
  getScoreHistory,
  appendScoreHistory,
  type HealthGrade,
  type HealthDimensions,
  type Hotspot,
  type Achievement,
} from "@/lib/engine/health-score";
import { TrendingUp, TrendingDown, Minus, Award, Flame } from "lucide-react";

interface HealthDashboardProps {
  nodes: Node[];
  edges: Edge[];
  projectId?: string;
  onHotspotClick?: (nodeId: string) => void;
}

export function HealthDashboard({
  nodes,
  edges,
  projectId = "default",
  onHotspotClick,
}: HealthDashboardProps) {
  const [showAchievements, setShowAchievements] = useState(false);

  const previousHistory = useMemo(
    () => getScoreHistory(projectId),
    [projectId],
  );
  const previousScore = previousHistory.length > 0
    ? previousHistory[previousHistory.length - 1].score
    : undefined;

  const health = useMemo(() => {
    const score = computeHealthScore(nodes, edges, previousScore);
    appendScoreHistory(projectId, score.overall);
    return score;
  }, [nodes, edges, projectId, previousScore]);

  const sparklineData = useMemo(
    () => getScoreHistory(projectId),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projectId, health.overall],
  );

  return (
    <div className="glass flex flex-col gap-3 rounded-[var(--radius-md)] p-4" style={{ width: 320 }}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
          Code Health
        </h3>
        <TrendBadge trend={health.trend} delta={health.delta} />
      </div>

      {/* Main gauge + grade */}
      <div className="flex items-center gap-4">
        <ScoreGauge score={health.overall} grade={health.grade} />
        <div className="flex flex-1 flex-col gap-1">
          <DimensionBars dimensions={health.dimensions} />
        </div>
      </div>

      {/* Sparkline */}
      {sparklineData.length > 1 && (
        <Sparkline data={sparklineData.map((d) => d.score)} grade={health.grade} />
      )}

      {/* Hotspots */}
      {health.hotspots.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]">
            <Flame className="h-3 w-3" /> Top Hotspots
          </p>
          {health.hotspots.slice(0, 5).map((h) => (
            <HotspotRow key={h.nodeId} hotspot={h} onClick={() => onHotspotClick?.(h.nodeId)} />
          ))}
        </div>
      )}

      {/* Achievements toggle */}
      <button
        onClick={() => setShowAchievements(!showAchievements)}
        className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-secondary)]"
      >
        <Award className="h-3 w-3" />
        {health.achievements.filter((a) => a.unlocked).length}/{health.achievements.length} achievements
      </button>

      {showAchievements && (
        <div className="flex flex-wrap gap-1.5">
          {health.achievements.map((a) => (
            <AchievementBadge key={a.id} achievement={a} />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Sub-Components ──────────────────────────────────────────────────────────

function ScoreGauge({ score, grade }: { score: number; grade: HealthGrade }) {
  const color = gradeHex(grade);
  const circumference = 2 * Math.PI * 36;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="relative flex-shrink-0" style={{ width: 80, height: 80 }}>
      <svg viewBox="0 0 80 80" className="h-full w-full">
        {/* Background ring */}
        <circle
          cx="40" cy="40" r="36"
          fill="none"
          stroke="var(--color-border-subtle)"
          strokeWidth="4"
        />
        {/* Score arc */}
        <circle
          cx="40" cy="40" r="36"
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 40 40)"
          style={{ transition: "stroke-dashoffset 0.8s ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-lg font-bold" style={{ color }}>{score}</span>
        <span className="text-[9px] font-semibold" style={{ color }}>{grade}</span>
      </div>
    </div>
  );
}

function DimensionBars({ dimensions }: { dimensions: HealthDimensions }) {
  const dims = [
    { key: "complexity", label: "Complexity", value: dimensions.complexity },
    { key: "churnRisk", label: "Churn", value: dimensions.churnRisk },
    { key: "duplication", label: "DRY", value: dimensions.duplication },
    { key: "coverage", label: "Tests", value: dimensions.coverage },
    { key: "structure", label: "Structure", value: dimensions.structure },
    { key: "ownership", label: "Ownership", value: dimensions.ownership },
  ];

  return (
    <div className="flex flex-col gap-1">
      {dims.map((d) => (
        <div key={d.key} className="flex items-center gap-1.5">
          <span className="w-14 text-right text-[9px] text-[var(--color-text-tertiary)]">
            {d.label}
          </span>
          <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
            <div
              className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
              style={{
                width: `${d.value}%`,
                backgroundColor: d.value >= 80 ? "#10b981" : d.value >= 60 ? "#f59e0b" : "#ef4444",
              }}
            />
          </div>
          <span className="w-6 text-right text-[9px] font-medium text-[var(--color-text-secondary)]">
            {d.value}
          </span>
        </div>
      ))}
    </div>
  );
}

function Sparkline({ data, grade }: { data: number[]; grade: HealthGrade }) {
  const color = gradeHex(grade);
  const width = 280;
  const height = 28;
  const padding = 2;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = Math.max(max - min, 1);

  const points = data.map((v, i) => {
    const x = padding + (i / Math.max(data.length - 1, 1)) * (width - padding * 2);
    const y = height - padding - ((v - min) / range) * (height - padding * 2);
    return `${x},${y}`;
  }).join(" ");

  // Fill area
  const firstX = padding;
  const lastX = padding + ((data.length - 1) / Math.max(data.length - 1, 1)) * (width - padding * 2);
  const fillPoints = `${firstX},${height} ${points} ${lastX},${height}`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height: 28 }}>
      <polygon points={fillPoints} fill={color} fillOpacity="0.08" />
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Current value dot */}
      {data.length > 0 && (
        <circle
          cx={lastX}
          cy={height - padding - ((data[data.length - 1] - min) / range) * (height - padding * 2)}
          r="2.5"
          fill={color}
        />
      )}
    </svg>
  );
}

function TrendBadge({ trend, delta }: { trend: string; delta: number }) {
  const Icon = trend === "improving" ? TrendingUp : trend === "declining" ? TrendingDown : Minus;
  const color = trend === "improving" ? "#10b981" : trend === "declining" ? "#ef4444" : "var(--color-text-tertiary)";

  return (
    <div className="flex items-center gap-1 text-[10px]" style={{ color }}>
      <Icon className="h-3 w-3" />
      {delta !== 0 && <span>{delta > 0 ? "+" : ""}{delta}</span>}
    </div>
  );
}

function HotspotRow({
  hotspot,
  onClick,
}: {
  hotspot: Hotspot;
  onClick: () => void;
}) {
  const quadrantColors = {
    refactor: "#ef4444",
    monitor: "#f59e0b",
    stable: "#10b981",
    dead: "#6b7280",
  };

  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 rounded px-1.5 py-0.5 text-left transition-colors hover:bg-[var(--color-surface-2)]"
    >
      <div
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: quadrantColors[hotspot.quadrant] }}
      />
      <span className="flex-1 truncate text-[10px] text-[var(--color-text-secondary)]">
        {hotspot.label}
      </span>
      <span className="text-[9px] text-[var(--color-text-tertiary)]">
        {Math.round(hotspot.score * 100)}
      </span>
    </button>
  );
}

function AchievementBadge({ achievement }: { achievement: Achievement }) {
  return (
    <div
      className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[9px] ${
        achievement.unlocked
          ? "bg-[var(--color-accent)]/10 text-[var(--color-accent)]"
          : "bg-[var(--color-surface-2)] text-[var(--color-text-tertiary)] opacity-50"
      }`}
      title={achievement.description}
    >
      <span>{achievement.icon}</span>
      <span>{achievement.title}</span>
      {!achievement.unlocked && (
        <span className="ml-0.5">({Math.round(achievement.progress * 100)}%)</span>
      )}
    </div>
  );
}
