import { useState, useCallback, useMemo } from "react";
import { ThreeCanvas } from "@/components/scene/three-canvas";
import { DetailPanel } from "@/components/scene/detail-panel";
import { SysmapDetailPanel } from "@/components/scene/sysmap-detail-panel";
import { StatsBar } from "@/components/scene/stats-bar";
import { SearchOverlay } from "@/components/search/search-overlay";
import { ChatPanel } from "@/components/agent/chat-panel";
import { KlibModal } from "@/components/klib/klib-modal";
import { MiniMap } from "@/components/scene/mini-map";
import { EarthquakeOverlay } from "@/components/scene/earthquake-overlay";
import { HeatmapControls } from "@/components/scene/heatmap-controls";
import { GhostOverlay } from "@/components/scene/ghost-overlay";
import { AnnotationPanel } from "@/components/scene/annotation-panel";
import { SandboxPanel } from "@/components/scene/sandbox-panel";
import { TimeTravelSlider } from "@/components/scene/time-travel-slider";
import { PluginPanel } from "@/components/scene/plugin-panel";
import { ShapePackSelector } from "@/components/scene/shape-pack-selector";
import { EmbedDialog } from "@/components/scene/embed-dialog";
import { XRButton } from "@/components/scene/xr-button";
import { HealthDashboard } from "@/components/scene/health-dashboard";
import { AITrailOverlay } from "@/components/scene/ai-trail-overlay";
import { SourcetrailView } from "@/components/scene/sourcetrail-view";
import { ShareDialog } from "@/components/scene/share-dialog";
import { useBrain } from "@/hooks/use-brain";
import { useMapFeatures } from "@/hooks/use-map-features";
import { useKeyboard } from "@/hooks/use-keyboard";
import {
  MessageCircle,
  Search as SearchIcon,
  BookOpen,
  Volume2,
  VolumeX,
  Code2,
  Heart,
  Route,
  GitBranch,
  Share2,
} from "lucide-react";
import { playSelectPing } from "@/lib/engine/sound";
import { getPulseColor } from "@/lib/engine/pulse";
import { findPath } from "@/lib/engine/ai-trails";
import { inferConfig } from "@/lib/inference";
import { buildSysmap } from "@/lib/inference/build-sysmap";
import type { SysmapData } from "@/lib/inference/build-sysmap";
import type { Node } from "@/lib/api";

export default function MapPage() {
  const { graph, graphData, loading, error, projectPath, classifying, classifyProgress } = useBrain();
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedSysmapNodeId, setSelectedSysmapNodeId] = useState<string | null>(null);
  const [submapId, setSubmapId] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [klibOpen, setKlibOpen] = useState(false);

  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];

  // Compute SYSMAP from graphData via inference engine
  const sysmapData: SysmapData | null = useMemo(() => {
    if (!graphData || graphData.nodes.length === 0) return null;
    const inferred = inferConfig(graphData);
    return buildSysmap(graphData, inferred);
  }, [graphData]);

  // Active view: main map or submap
  const activeSysmapData: SysmapData | null = useMemo(() => {
    if (!sysmapData) return null;
    if (submapId && sysmapData.SUBMAPS[submapId]) {
      const sub = sysmapData.SUBMAPS[submapId];
      return {
        ...sysmapData,
        N: sub.nodes,
        E: sub.edges,
        title: sub.title,
      };
    }
    return sysmapData;
  }, [sysmapData, submapId]);

  const isSysmapMode = activeSysmapData != null;

  const features = useMapFeatures(nodes, projectPath);

  const handleNodeSelect = useCallback(
    (nodeId: string | null) => {
      setSelectedSysmapNodeId(nodeId);
      const node = nodeId ? nodes.find((n) => n.id === nodeId) ?? null : null;
      setSelectedNode(node);
      features.setEarthquakeActive(false);
      features.setAnnotationOpen(false);
      if (nodeId && features.soundOn) playSelectPing();
    },
    [nodes, features.soundOn, features.setEarthquakeActive, features.setAnnotationOpen],
  );

  const handleSubmapEnter = useCallback(
    (nodeId: string) => {
      if (sysmapData?.SUBMAPS[nodeId]) {
        setSubmapId(nodeId);
        setSelectedSysmapNodeId(null);
        setSelectedNode(null);
      }
    },
    [sysmapData],
  );

  const handleSubmapBack = useCallback(() => {
    setSubmapId(null);
    setSelectedSysmapNodeId(null);
    setSelectedNode(null);
  }, []);

  const handleSearchSelect = useCallback((node: Node) => {
    setSelectedNode(node);
    setSelectedSysmapNodeId(node.id);
  }, []);

  const handleNodeNavigate = useCallback(
    (nodeId: string) => {
      setSelectedSysmapNodeId(nodeId);
      const node = nodes.find((n) => n.id === nodeId) || null;
      setSelectedNode(node);
    },
    [nodes],
  );

  const handleKlibNodeSelect = useCallback((node: Node) => {
    setSelectedNode(node);
    setKlibOpen(false);
  }, []);

  // AI Trail creation
  const handleCreateTrail = useCallback(
    (fromId: string, toId: string) => {
      const path = findPath(fromId, toId, nodes, edges);
      if (path) {
        features.setAiTrailPath(path);
        features.setAiTrailActive(true);
      }
    },
    [nodes, edges, features],
  );

  // Keyboard shortcuts
  const bindings = useMemo(
    () => [
      {
        key: "k",
        meta: true,
        handler: () => setSearchOpen(true),
      },
      {
        key: "Escape",
        handler: () => {
          if (features.annotationOpen) features.setAnnotationOpen(false);
          else if (features.earthquakeActive) features.setEarthquakeActive(false);
          else if (searchOpen) setSearchOpen(false);
          else if (klibOpen) setKlibOpen(false);
          else if (submapId) handleSubmapBack();
          else if (selectedNode) { setSelectedNode(null); setSelectedSysmapNodeId(null); }
        },
      },
      {
        key: "d",
        handler: () => {
          if (selectedNode) features.setEarthquakeActive((prev) => !prev);
        },
      },
      {
        key: "h",
        handler: () => features.setHeatmapActive((prev) => !prev),
      },
      {
        key: "g",
        handler: () => features.setGhostActive((prev) => !prev),
      },
      {
        key: "n",
        handler: () => {
          if (selectedNode) features.setAnnotationOpen((prev) => !prev);
        },
      },
      {
        key: "s",
        handler: () => features.setSandboxActive((prev) => !prev),
      },
      {
        key: "t",
        handler: () => features.setTimeTravelActive((prev) => !prev),
      },
      {
        key: "r",
        handler: () => features.setAiTrailActive((prev) => !prev),
      },
      {
        key: "x",
        handler: () => {
          if (selectedNode) features.setSourcetrailActive((prev) => !prev);
        },
      },
    ],
    [searchOpen, klibOpen, selectedNode, submapId, handleSubmapBack, features],
  );
  useKeyboard(bindings);

  // Stats for bottom bar
  const statsItems = useMemo(() => {
    if (activeSysmapData) {
      const items = activeSysmapData.stats.map((s) => ({
        label: s.label.toLowerCase(),
        value: s.value,
      }));
      if (submapId) {
        items.unshift({ label: "submap", value: 1 });
      }
      return items;
    }
    return [
      { label: "nodes", value: nodes.length },
      { label: "edges", value: edges.length },
    ];
  }, [activeSysmapData, submapId, nodes.length, edges.length]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-[var(--color-surface-0)]">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
          <span className="text-sm text-[var(--color-text-secondary)]">
            Loading graph...
          </span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center bg-[var(--color-surface-0)]">
        <div className="flex flex-col items-center gap-3 text-center">
          <span className="text-sm text-[var(--color-destructive)]">
            Failed to load graph: {error}
          </span>
          <p className="text-xs text-[var(--color-text-tertiary)]">
            The 3D scene will show when the Rust backend is running.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex h-full">
      {/* 3D Canvas */}
      <div className="relative flex-1">
        <ThreeCanvas
          nodes={nodes}
          edges={edges}
          sysmapData={activeSysmapData}
          selectedNodeId={selectedSysmapNodeId}
          onNodeSelect={handleNodeSelect}
        />

        {/* Earthquake overlay (top-left) */}
        <EarthquakeOverlay
          epicenterNode={selectedNode}
          nodes={nodes}
          edges={edges}
          active={features.earthquakeActive}
        />

        {/* Ghost overlay (top-left, below earthquake) */}
        {!features.earthquakeActive && (
          <GhostOverlay
            nodes={nodes}
            edges={edges}
            active={features.ghostActive}
          />
        )}

        {/* Heatmap controls (top-right) */}
        <HeatmapControls
          nodes={nodes}
          edges={edges}
          active={features.heatmapActive}
          metric={features.heatmapMetric}
          onMetricChange={features.setHeatmapMetric}
        />

        {/* Detail panel overlay */}
        {isSysmapMode && selectedSysmapNodeId && sysmapData ? (
          <SysmapDetailPanel
            nodeId={selectedSysmapNodeId}
            sysmapData={sysmapData}
            hasSubmap={!!sysmapData.SUBMAPS[selectedSysmapNodeId]}
            isInSubmap={!!submapId}
            onClose={() => { setSelectedSysmapNodeId(null); setSelectedNode(null); }}
            onNavigate={handleNodeNavigate}
            onDrillDown={handleSubmapEnter}
            onSubmapBack={handleSubmapBack}
          />
        ) : selectedNode ? (
          <DetailPanel
            node={selectedNode}
            edges={edges}
            allNodes={nodes}
            onClose={() => setSelectedNode(null)}
            onNavigate={handleNodeNavigate}
          />
        ) : null}

        {/* Annotation panel */}
        {selectedNode && (
          <AnnotationPanel
            nodeId={selectedNode.id}
            nodeText={selectedNode.text}
            open={features.annotationOpen}
            onClose={() => features.setAnnotationOpen(false)}
          />
        )}

        {/* Sandbox panel (top-left, toggle with S) */}
        <SandboxPanel
          nodes={nodes}
          edges={edges}
          active={features.sandboxActive}
          onToggle={() => features.setSandboxActive((prev) => !prev)}
        />

        {/* Time-Travel slider (bottom center, toggle with T) */}
        <TimeTravelSlider
          projectPath={projectPath}
          active={features.timeTravelActive}
          onCommitSelect={features.handleTimeTravelCommit}
        />

        {/* Plugin panel (right side) */}
        <PluginPanel
          active={features.pluginPanelOpen}
          onToggle={() => features.setPluginPanelOpen((prev) => !prev)}
        />

        {/* AI Trail overlay (top-left) */}
        <AITrailOverlay
          nodes={nodes}
          edges={edges}
          trailPath={features.aiTrailPath}
          isPlaying={features.aiTrailPlaying}
          progress={features.aiTrailProgress}
          onCreateTrail={handleCreateTrail}
          onPlay={() => features.setAiTrailPlaying(true)}
          onPause={() => features.setAiTrailPlaying(false)}
          onClear={() => {
            features.setAiTrailPath(null);
            features.setAiTrailPlaying(false);
            features.setAiTrailProgress(0);
          }}
          onNodeClick={handleNodeNavigate}
          active={features.aiTrailActive}
        />

        {/* Sourcetrail bidirectional view */}
        <SourcetrailView
          nodes={nodes}
          edges={edges}
          selectedNode={selectedNode}
          onNodeSelect={(node) => setSelectedNode(node)}
          onClose={() => features.setSourcetrailActive(false)}
          active={features.sourcetrailActive}
        />

        {/* Health dashboard (top-right, overlaid) */}
        {features.healthDashboardOpen && (
          <div className="absolute right-4 top-4 z-20">
            <HealthDashboard
              nodes={nodes}
              edges={edges}
              onHotspotClick={handleNodeNavigate}
            />
          </div>
        )}

        {/* Pulse indicators */}
        {features.pulseMap.size > 0 && (
          <div className="absolute right-4 top-4 z-10">
            <div className="glass rounded-[var(--radius-sm)] px-2.5 py-1.5">
              <p className="text-[10px] font-medium text-[var(--color-text-secondary)]">
                <span
                  className="mr-1.5 inline-block h-2 w-2 animate-pulse rounded-full"
                  style={{ backgroundColor: getPulseColor(1) }}
                />
                {features.pulseMap.size} pulsing
              </p>
            </div>
          </div>
        )}

        {/* LLM Classification progress */}
        {classifying && classifyProgress && (
          <div className="absolute left-1/2 top-4 z-20 -translate-x-1/2">
            <div className="glass flex items-center gap-2 rounded-[var(--radius-sm)] px-3 py-1.5">
              <div className="h-3 w-3 animate-spin rounded-full border border-[var(--color-accent)] border-t-transparent" />
              <span className="text-[11px] text-[var(--color-text-secondary)]">
                Classifying nodes... {classifyProgress.done}/{classifyProgress.total}
              </span>
            </div>
          </div>
        )}

        {/* Stats bar */}
        <StatsBar items={statsItems} />

        {/* Mini-map (bottom-left) */}
        <div className="pointer-events-none absolute bottom-12 left-4 z-10">
          <MiniMap
            nodes={nodes}
            edges={edges}
            selectedNodeId={selectedNode?.id}
          />
        </div>

        {/* Toolbar — bottom right */}
        <div className="absolute bottom-4 right-4 flex gap-2">
          <button
            onClick={() => setSearchOpen(true)}
            className="glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
            title="Search (Cmd+K)"
          >
            <SearchIcon className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Search</span>
            <kbd className="hidden rounded border border-[var(--color-border-subtle)] px-1 text-[9px] sm:inline">
              &Cmd;K
            </kbd>
          </button>
          <button
            onClick={() => setKlibOpen(true)}
            className="glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
            title="Knowledge Library"
          >
            <BookOpen className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Library</span>
          </button>
          <button
            onClick={features.toggleSound}
            className={`glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] transition-colors ${
              features.soundOn
                ? "text-[var(--color-accent)]"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
            title={features.soundOn ? "Sound On" : "Sound Off"}
          >
            {features.soundOn ? (
              <Volume2 className="h-3.5 w-3.5" />
            ) : (
              <VolumeX className="h-3.5 w-3.5" />
            )}
          </button>
          <ShapePackSelector
            enabledPacks={features.enabledShapePacks}
            onPacksChange={features.setEnabledShapePacks}
          />
          <button
            onClick={() => features.setHealthDashboardOpen((prev) => !prev)}
            className={`glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] transition-colors ${
              features.healthDashboardOpen
                ? "text-[var(--color-accent)]"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
            title="Code Health Score"
          >
            <Heart className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => features.setAiTrailActive((prev) => !prev)}
            className={`glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] transition-colors ${
              features.aiTrailActive
                ? "text-[var(--color-accent)]"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
            title="AI Trails (R)"
          >
            <Route className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => {
              if (selectedNode) features.setSourcetrailActive((prev) => !prev);
            }}
            className={`glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] transition-colors ${
              features.sourcetrailActive
                ? "text-[var(--color-accent)]"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
            title="Dependency Explorer (X)"
          >
            <GitBranch className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => features.setShareDialogOpen(true)}
            className="glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
            title="Share"
          >
            <Share2 className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => features.setEmbedOpen(true)}
            className="glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)]"
            title="Embed Widget"
          >
            <Code2 className="h-3.5 w-3.5" />
          </button>
          <XRButton />
          <button
            onClick={() => setAgentOpen(!agentOpen)}
            className={`glass flex items-center gap-1.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[11px] transition-colors ${
              agentOpen
                ? "text-[var(--color-accent)]"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
            }`}
            title="AI Agent"
          >
            <MessageCircle className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Agent</span>
          </button>
        </div>

        {/* Keyboard hints */}
        <div className="pointer-events-none absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 gap-3 text-[9px] text-[var(--color-text-tertiary)]">
          <span>
            <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
              D
            </kbd>{" "}
            Earthquake
          </span>
          <span>
            <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
              H
            </kbd>{" "}
            Heatmap
          </span>
          <span>
            <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
              G
            </kbd>{" "}
            Ghost
          </span>
          <span>
            <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
              N
            </kbd>{" "}
            Note
          </span>
          <span>
            <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
              S
            </kbd>{" "}
            Sandbox
          </span>
          <span>
            <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
              T
            </kbd>{" "}
            Time-Travel
          </span>
          <span>
            <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
              R
            </kbd>{" "}
            Trail
          </span>
          <span>
            <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
              X
            </kbd>{" "}
            Explorer
          </span>
          <span>
            <kbd className="rounded border border-[var(--color-border-subtle)] px-1">
              Esc
            </kbd>{" "}
            Dismiss
          </span>
        </div>
      </div>

      {/* Agent panel (right sidebar) */}
      {agentOpen && (
        <ChatPanel
          open={agentOpen}
          onClose={() => setAgentOpen(false)}
          nodes={nodes}
          edges={edges}
        />
      )}

      {/* Search overlay */}
      <SearchOverlay
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        nodes={nodes}
        sysmapData={sysmapData}
        onSelect={handleSearchSelect}
        onSysmapSelect={handleNodeNavigate}
      />

      {/* Knowledge Library modal */}
      <KlibModal
        open={klibOpen}
        onClose={() => setKlibOpen(false)}
        nodes={nodes}
        edges={edges}
        onSelectNode={handleKlibNodeSelect}
      />

      {/* Embed dialog */}
      <EmbedDialog
        open={features.embedOpen}
        onClose={() => features.setEmbedOpen(false)}
        nodes={nodes}
        edges={edges}
      />

      {/* Share dialog */}
      <ShareDialog
        open={features.shareDialogOpen}
        onClose={() => features.setShareDialogOpen(false)}
        nodes={nodes}
        edges={edges}
      />
    </div>
  );
}
