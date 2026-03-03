import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  GitBranch,
  FileCode,
  AlertTriangle,
  FolderOpen,
  Upload,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useBrain } from "@/hooks/use-brain";

interface StatCardProps {
  title: string;
  value: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  trend?: { value: string; positive: boolean };
}

function StatCard({
  title,
  value,
  description,
  icon: Icon,
  trend,
}: StatCardProps) {
  return (
    <Card className="gap-4 py-5">
      <CardHeader className="gap-1 pb-0">
        <div className="flex items-center justify-between">
          <CardDescription className="text-[13px]">{title}</CardDescription>
          <Icon className="h-4 w-4 text-[var(--color-text-tertiary)]" />
        </div>
        <div className="flex items-baseline gap-2">
          <CardTitle className="text-2xl font-bold tabular-nums">
            {value}
          </CardTitle>
          {trend && (
            <span
              className={`text-xs font-medium ${
                trend.positive
                  ? "text-[var(--color-success)]"
                  : "text-[var(--color-destructive)]"
              }`}
            >
              {trend.value}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <p className="text-[12px] text-[var(--color-text-tertiary)]">
          {description}
        </p>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { graph, stats, openProject } = useBrain();
  const navigate = useNavigate();
  const [dragging, setDragging] = useState(false);
  const [opening, setOpening] = useState(false);

  const nodeCount = stats?.nodeCount ?? graph?.nodes?.length ?? 0;
  const edgeCount = stats?.edgeCount ?? graph?.edges?.length ?? 0;

  const handleOpenFolder = useCallback(async () => {
    try {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const selected = await open({ directory: true, multiple: false });
      if (selected && typeof selected === "string") {
        setOpening(true);
        await openProject(selected);
        setOpening(false);
        navigate("/map");
      }
    } catch {
      // Not in Tauri environment — ignore
    }
  }, [openProject, navigate]);

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);

      // Tauri drag-drop provides paths via dataTransfer
      const items = e.dataTransfer.items;
      if (items.length > 0) {
        const item = items[0];
        if (item.kind === "file") {
          const file = item.getAsFile();
          if (file) {
            // In Tauri, file.path contains the full path
            const path = (file as File & { path?: string }).path;
            if (path) {
              setOpening(true);
              await openProject(path);
              setOpening(false);
              navigate("/map");
            }
          }
        }
      }
    },
    [openProject, navigate],
  );

  return (
    <div className="space-y-6 p-6">
      {/* Stats grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Nodes"
          value={nodeCount > 0 ? nodeCount.toLocaleString() : "--"}
          description="Across all knowledge layers"
          icon={Activity}
        />
        <StatCard
          title="Connections"
          value={edgeCount > 0 ? edgeCount.toLocaleString() : "--"}
          description="Edges in the knowledge graph"
          icon={GitBranch}
        />
        <StatCard
          title="Languages"
          value={
            stats?.technologies?.length
              ? String(stats.technologies.length)
              : "--"
          }
          description={
            stats?.technologies?.length
              ? stats.technologies.slice(0, 3).join(", ")
              : "Open a project to analyze"
          }
          icon={FileCode}
        />
        <StatCard
          title="Issues"
          value="0"
          description="No issues detected"
          icon={AlertTriangle}
        />
      </div>

      {/* Drop zone + Welcome */}
      <Card
        className={`border-dashed transition-colors ${
          dragging
            ? "border-[var(--color-accent)] bg-[var(--color-accent-muted)]"
            : "border-[var(--color-border-strong)]"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <CardHeader>
          <CardTitle className="text-xl">
            {opening ? "Analyzing project..." : "Welcome to Ontology Map"}
          </CardTitle>
          <CardDescription>
            Spatial Software Engineering — See your software. Understand it.
            Change it.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {opening ? (
            <div className="flex flex-col items-center gap-3 py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
              <span className="text-sm text-[var(--color-text-secondary)]">
                Detecting languages and extracting graph...
              </span>
            </div>
          ) : (
            <>
              {/* Drop zone area */}
              <div
                className="flex cursor-pointer flex-col items-center gap-3 rounded-[var(--radius-md)] border-2 border-dashed border-[var(--color-border-subtle)] py-8 transition-colors hover:border-[var(--color-accent)] hover:bg-[var(--color-surface-1)]"
                onClick={handleOpenFolder}
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-accent-muted)]">
                  {dragging ? (
                    <Upload className="h-6 w-6 text-[var(--color-accent)]" />
                  ) : (
                    <FolderOpen className="h-6 w-6 text-[var(--color-accent)]" />
                  )}
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium text-[var(--color-text-primary)]">
                    {dragging
                      ? "Drop folder here"
                      : "Drag a project folder here"}
                  </p>
                  <p className="mt-1 text-xs text-[var(--color-text-tertiary)]">
                    or click to open folder dialog
                  </p>
                </div>
                <p className="text-[11px] text-[var(--color-text-tertiary)]">
                  Supports: Python, JavaScript/TypeScript, Docker Compose
                </p>
              </div>

              {/* Steps */}
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-0)] p-4">
                  <h3 className="mb-1 text-sm font-medium text-[var(--color-text-primary)]">
                    1. Open a Project
                  </h3>
                  <p className="text-[13px] text-[var(--color-text-tertiary)]">
                    Drag a folder here or click to analyze your codebase
                    automatically.
                  </p>
                </div>
                <div className="rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-0)] p-4">
                  <h3 className="mb-1 text-sm font-medium text-[var(--color-text-primary)]">
                    2. Explore the Map
                  </h3>
                  <p className="text-[13px] text-[var(--color-text-tertiary)]">
                    Navigate your architecture in 3D. Orbit, zoom, and drill
                    into modules.
                  </p>
                </div>
                <div className="rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-0)] p-4">
                  <h3 className="mb-1 text-sm font-medium text-[var(--color-text-primary)]">
                    3. Ask the Agent
                  </h3>
                  <p className="text-[13px] text-[var(--color-text-tertiary)]">
                    Use AI to navigate, explain clusters, and find dependencies.
                  </p>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
