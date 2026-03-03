import { useRef, useEffect, useCallback } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { OutlinePass } from "three/addons/postprocessing/OutlinePass.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { oklchToInt } from "@/lib/design/oklch";
import { ENGINE_CONFIG } from "@/lib/engine/config";
import { mkObj } from "@/lib/scene/shapes";
import { createMatFactory } from "@/lib/scene/materials";
import { applyLayout } from "@/lib/scene/layouts";
import type { SysmapData, SysmapEdge } from "@/lib/inference/build-sysmap";
import type { LayoutName } from "@/lib/inference/layout-selector"; // single source of truth
import type { Node, Edge } from "@/lib/api";

// ── Props ──

interface ThreeCanvasProps {
  // Legacy brain format (existing features)
  nodes?: Node[];
  edges?: Edge[];
  // New SYSMAP format (inference engine output)
  sysmapData?: SysmapData | null;
  // Common
  selectedNodeId?: string | null;
  onNodeSelect?: (nodeId: string | null) => void;
  onNodeHover?: (nodeId: string | null) => void;
  className?: string;
}

// ── Scene context ──

interface SceneContext {
  scene: THREE.Scene;
  camera: THREE.OrthographicCamera;
  renderer: THREE.WebGLRenderer;
  labelRenderer: CSS2DRenderer;
  controls: OrbitControls;
  composer: EffectComposer;
  outlinePass: OutlinePass;
  envMap: THREE.Texture;
  animFrameId: number;
  nodeGroups: Map<string, { group: THREE.Group; nodeId: string }>;
  edgeLines: THREE.Group;
  _cleanup: (() => void) | null;
  _raycastCache: THREE.Object3D[] | null;
}

/**
 * ThreeCanvas — React wrapper for the 3D system map.
 *
 * Supports two data paths:
 * - Legacy: `nodes` + `edges` (brain Node[] format, renders spheres)
 * - SYSMAP: `sysmapData` (inference engine output, renders 26 shapes)
 *
 * When sysmapData is provided, it takes priority over nodes/edges.
 */
export function ThreeCanvas({
  nodes = [],
  edges = [],
  sysmapData,
  selectedNodeId,
  onNodeSelect,
  onNodeHover,
  className,
}: ThreeCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const ctxRef = useRef<SceneContext | null>(null);

  const onNodeSelectRef = useRef(onNodeSelect);
  const onNodeHoverRef = useRef(onNodeHover);
  onNodeSelectRef.current = onNodeSelect;
  onNodeHoverRef.current = onNodeHover;

  // ── Build scene ────────────────────────────────────────────────────────
  const initScene = useCallback((container: HTMLDivElement) => {
    const W = container.clientWidth;
    const H = container.clientHeight || 1; // guard against zero-height producing Infinity frustum

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(oklchToInt(12, 0.01, 260));
    scene.fog = new THREE.FogExp2(oklchToInt(8, 0.015, 260), 0.008);

    // Lights
    const ambient = new THREE.AmbientLight(oklchToInt(95, 0.01, 260), 0.15);
    scene.add(ambient);
    const directional = new THREE.DirectionalLight(oklchToInt(98, 0.01, 50), 0.35);
    directional.position.set(8, 15, 10);
    scene.add(directional);
    const fill = new THREE.DirectionalLight(oklchToInt(85, 0.01, 250), 0.1);
    fill.position.set(-5, 8, -8);
    scene.add(fill);
    const rim = new THREE.DirectionalLight(oklchToInt(70, 0.05, 250), 0.08);
    rim.position.set(-8, 5, 15);
    scene.add(rim);

    // Camera
    const fd = ENGINE_CONFIG.ORTHO_FRUSTUM;
    const asp = W / H;
    const camera = new THREE.OrthographicCamera(-fd * asp, fd * asp, fd, -fd, 0.1, 200);
    camera.position.set(12, 18, 12);
    camera.lookAt(0, 0, 0);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    container.appendChild(renderer.domElement);

    // Environment map
    const pmremGen = new THREE.PMREMGenerator(renderer);
    const roomEnv = new RoomEnvironment();
    const envMap = pmremGen.fromScene(roomEnv, 0.04).texture;
    scene.environment = envMap;
    roomEnv.dispose();
    pmremGen.dispose();

    // CSS2D renderer (labels)
    const labelRenderer = new CSS2DRenderer();
    labelRenderer.setSize(W, H);
    labelRenderer.domElement.style.position = "absolute";
    labelRenderer.domElement.style.top = "0";
    labelRenderer.domElement.style.pointerEvents = "none";
    container.appendChild(labelRenderer.domElement);

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.maxPolarAngle = Math.PI / 2.2;
    controls.minPolarAngle = 0.2;

    // Post-processing
    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(Math.floor(W / 4), Math.floor(H / 4)),
      ENGINE_CONFIG.BLOOM_STRENGTH,
      ENGINE_CONFIG.BLOOM_RADIUS,
      ENGINE_CONFIG.BLOOM_THRESHOLD,
    );
    composer.addPass(bloomPass);
    const outlinePass = new OutlinePass(new THREE.Vector2(W, H), scene, camera);
    outlinePass.edgeStrength = 3;
    outlinePass.edgeGlow = 0.5;
    outlinePass.edgeThickness = 1.2;
    outlinePass.visibleEdgeColor.set(oklchToInt(72, 0.19, 165));
    outlinePass.enabled = false;
    composer.addPass(outlinePass);
    composer.addPass(new OutputPass());

    // Edge group
    const edgeLines = new THREE.Group();
    scene.add(edgeLines);

    const ctx: SceneContext = {
      scene,
      camera,
      renderer,
      labelRenderer,
      controls,
      composer,
      outlinePass,
      envMap,
      animFrameId: 0,
      nodeGroups: new Map(),
      edgeLines,
      _cleanup: null,
      _raycastCache: null,
    };

    // Resize
    const onResize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight || 1;
      const a = w / h;
      camera.left = -fd * a;
      camera.right = fd * a;
      camera.top = fd;
      camera.bottom = -fd;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      labelRenderer.setSize(w, h);
      composer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    // Raycasting
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    let lastMoveTime = 0;

    const updateMouse = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    };

    const findHit = (): string | null => {
      raycaster.setFromCamera(mouse, camera);
      // Use cached mesh list — rebuilt only when scene changes (clearScene sets to null)
      if (!ctx._raycastCache) {
        const objs: THREE.Object3D[] = [];
        for (const [, value] of ctx.nodeGroups) {
          value.group.traverse((child) => {
            if (child instanceof THREE.Mesh) objs.push(child);
          });
        }
        ctx._raycastCache = objs;
      }
      const intersects = raycaster.intersectObjects(ctx._raycastCache, false);
      if (intersects.length > 0) {
        // Walk up to find the node group
        let obj: THREE.Object3D | null = intersects[0].object;
        while (obj) {
          for (const [, value] of ctx.nodeGroups) {
            if (value.group === obj) return value.nodeId;
          }
          obj = obj.parent;
        }
      }
      return null;
    };

    const onClickHandler = (e: MouseEvent) => {
      updateMouse(e);
      const hitId = findHit();
      if (hitId) {
        const entry = ctx.nodeGroups.get(hitId);
        if (entry) {
          outlinePass.selectedObjects = [entry.group];
          outlinePass.enabled = true;
        }
        onNodeSelectRef.current?.(hitId);
      } else {
        outlinePass.selectedObjects = [];
        outlinePass.enabled = false;
        onNodeSelectRef.current?.(null);
      }
    };

    const onMoveHandler = (e: MouseEvent) => {
      const now = performance.now();
      if (now - lastMoveTime < 16) return;
      lastMoveTime = now;
      updateMouse(e);
      const hitId = findHit();
      renderer.domElement.style.cursor = hitId ? "pointer" : "default";
      onNodeHoverRef.current?.(hitId ?? null);
    };

    renderer.domElement.addEventListener("click", onClickHandler);
    renderer.domElement.addEventListener("mousemove", onMoveHandler);

    // Render loop
    const tick = () => {
      ctx.animFrameId = requestAnimationFrame(tick);
      controls.update();
      composer.render();
      labelRenderer.render(scene, camera);
    };
    ctx.animFrameId = requestAnimationFrame(tick);

    // Cleanup
    ctx._cleanup = () => {
      window.removeEventListener("resize", onResize);
      renderer.domElement.removeEventListener("click", onClickHandler);
      renderer.domElement.removeEventListener("mousemove", onMoveHandler);
      cancelAnimationFrame(ctx.animFrameId);
      renderer.dispose();
      composer.dispose();
      envMap.dispose();
      if (container.contains(renderer.domElement))
        container.removeChild(renderer.domElement);
      if (container.contains(labelRenderer.domElement))
        container.removeChild(labelRenderer.domElement);
    };

    return ctx;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Mount / Unmount ──
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const ctx = initScene(container);
    ctxRef.current = ctx;
    return () => {
      ctx._cleanup?.();
      ctxRef.current = null;
    };
  }, [initScene]);

  // ── Update scene from SYSMAP data or legacy data ──
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;

    // SYSMAP path (priority)
    if (sysmapData && sysmapData.N.length > 0) {
      clearScene(ctx);

      const { N, E, inferredConfig } = sysmapData;
      const layout = inferredConfig.layout as LayoutName;
      const palette = inferredConfig.palette;

      const positioned = applyLayout(layout, N, E);

      for (const pn of positioned) {
        const groupColor = palette.get(pn.g);
        const colorInt = groupColor ? groupColor.int : 0x556677;
        const matFactory = createMatFactory(colorInt, ctx.envMap);

        const shapeName = pn.sh || "sphere";
        const size = pn._inferredSize || 1.0;
        const group = mkObj(shapeName, size, matFactory);
        group.position.set(pn.px, pn.py, pn.pz);

        ctx.scene.add(group);
        ctx.nodeGroups.set(pn.id, { group, nodeId: pn.id });
      }

      buildEdges(ctx, E);
      return () => { if (ctxRef.current) clearScene(ctxRef.current); };
    }

    // Legacy path (brain Node[]/Edge[])
    if (!sysmapData && nodes.length > 0) {
      clearScene(ctx);

      const layerColors: Record<number, number> = {
        0: oklchToInt(72, 0.19, 165),
        1: oklchToInt(70, 0.15, 195),
        2: oklchToInt(65, 0.15, 270),
        3: oklchToInt(60, 0.15, 315),
        4: oklchToInt(75, 0.18, 85),
        5: oklchToInt(70, 0.12, 250),
        [-1]: oklchToInt(50, 0.02, 260),
      };

      const count = nodes.length;
      const radius = Math.max(8, Math.sqrt(count) * 1.2);

      nodes.forEach((node, i) => {
        const layerNum = node.layer;
        const color = layerColors[layerNum] ?? oklchToInt(50, 0.05, 260);
        const matFactory = createMatFactory(color, ctx.envMap);

        const phi = Math.acos(1 - (2 * (i + 0.5)) / count);
        const theta = Math.PI * (1 + Math.sqrt(5)) * i;
        const x = radius * Math.sin(phi) * Math.cos(theta);
        const y = (layerNum - 2) * 2;
        const z = radius * Math.sin(phi) * Math.sin(theta);

        const shapeName = nodeTypeToShape(node.type);
        const group = mkObj(shapeName, 0.8, matFactory);
        group.position.set(x, y, z);

        ctx.scene.add(group);
        ctx.nodeGroups.set(node.id, { group, nodeId: node.id });
      });

      const sysmapEdges: SysmapEdge[] = edges.map((e) => ({
        f: e.from,
        t: e.to,
        c: "white",
      }));
      buildEdges(ctx, sysmapEdges);
      return () => { if (ctxRef.current) clearScene(ctxRef.current); };
    }
  }, [sysmapData, nodes, edges]);

  // ── Selection sync ──
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;

    if (selectedNodeId) {
      const entry = ctx.nodeGroups.get(selectedNodeId);
      if (entry) {
        ctx.outlinePass.selectedObjects = [entry.group];
        ctx.outlinePass.enabled = true;
      }
    } else {
      ctx.outlinePass.selectedObjects = [];
      ctx.outlinePass.enabled = false;
    }
  }, [selectedNodeId]);

  return (
    <div
      ref={containerRef}
      className={cn("relative h-full w-full", className)}
      style={{ position: "relative" }}
    />
  );
}

// ── Helpers ──

function clearScene(ctx: SceneContext) {
  // Remove all node groups
  for (const [, value] of ctx.nodeGroups) {
    ctx.scene.remove(value.group);
    disposeGroup(value.group);
  }
  ctx.nodeGroups.clear();
  ctx._raycastCache = null; // invalidate cached mesh list

  // Remove all edge lines
  while (ctx.edgeLines.children.length > 0) {
    const child = ctx.edgeLines.children[0];
    ctx.edgeLines.remove(child);
    if (child instanceof THREE.Line) {
      child.geometry.dispose();
      if (Array.isArray(child.material)) {
        child.material.forEach((m) => m.dispose());
      } else {
        child.material.dispose();
      }
    }
  }
}

function disposeGroup(group: THREE.Group) {
  group.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      child.geometry.dispose();
      if (Array.isArray(child.material)) {
        child.material.forEach((m) => m.dispose());
      } else {
        child.material.dispose();
      }
    }
  });
}

function buildEdges(ctx: SceneContext, edges: SysmapEdge[]) {
  const edgeColorMap: Record<string, number> = {
    cyan: 0x5eead4,
    blue: 0x6b8fff,
    green: 0x34d399,
    purple: 0x9b7cff,
    white: oklchToInt(40, 0.02, 260),
  };

  // Pre-create one material per color to avoid per-edge allocation
  const materialCache = new Map<string, THREE.LineBasicMaterial>();
  for (const [name, colorInt] of Object.entries(edgeColorMap)) {
    materialCache.set(name, new THREE.LineBasicMaterial({
      color: colorInt,
      transparent: true,
      opacity: 0.2,
    }));
  }

  for (const edge of edges) {
    const fromEntry = ctx.nodeGroups.get(edge.f);
    const toEntry = ctx.nodeGroups.get(edge.t);
    if (!fromEntry || !toEntry) continue;

    const material = materialCache.get(edge.c) ?? materialCache.get("white")!;

    const points = [
      fromEntry.group.position.clone(),
      toEntry.group.position.clone(),
    ];
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const line = new THREE.Line(geometry, material);
    ctx.edgeLines.add(line);
  }
}

function nodeTypeToShape(nodeType: string): string {
  const t = nodeType.toLowerCase();
  if (t.includes("database") || t.includes("db")) return "database";
  if (t.includes("service")) return "gear";
  if (t.includes("api") || t.includes("gateway")) return "gate";
  if (t.includes("module") || t.includes("package")) return "vault";
  if (t.includes("class") || t.includes("model")) return "prism";
  if (t.includes("function")) return "sphere";
  if (t.includes("file")) return "terminal";
  if (t.includes("config")) return "dial";
  if (t.includes("test")) return "gauge";
  return "sphere";
}

function cn(...classes: (string | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}
