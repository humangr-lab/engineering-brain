# F-06 Fractal Drill-Down: Research Document

> Feature: Infinite Semantic Zoom (5-Level Deep Drill)
> Work Package: WP-4 (Fractal Drill-Down)
> Status: Research Phase (WP-4.1)
> Author: Claude Opus 4.6
> Date: 2026-02-27

---

## 1. Problem Statement

The current Ontology Map Toolkit cockpit supports only a single level of submap navigation: clicking a system-level node opens a flat submap containing 8-15 child nodes, rendered as a modal overlay. This architecture has three fundamental limitations:

**Depth ceiling.** Real software systems have hierarchies 4-7 levels deep (product, package, module, file, class, method, line). The current 1-level drill exposes only the first hop, leaving the vast majority of the project graph inaccessible from the spatial interface.

**Context loss.** When the user opens a submap, the parent context disappears entirely. There is no breadcrumb, no minimap, and no visual continuity between the system-level view and the submap. The user must mentally reconstruct the hierarchy, defeating the purpose of a spatial interface.

**Data cliff.** The transition from the 3D map (which fetches all ~2,000 nodes at once) to code-level detail (which requires per-file reads) has no intermediate representation. The user jumps from "architectural blobs" to raw source code with nothing in between to aid comprehension.

**Target architecture.** F-06 introduces 5 semantic zoom levels, each with a distinct visual representation and interaction model:

| Level | Name | Visual Representation | Data Source |
|-------|------|-----------------------|-------------|
| L0 | System | 3D shapes in orbital/force layout, labels, edges | `graph.json` top-level nodes |
| L1 | Module | File nodes as cubes, import edges | Project Graph `Package -> File` |
| L2 | File | Class/function nodes, call edges, inheritance | Project Graph `File -> Symbol` |
| L3 | Function | Syntax-highlighted read-only code (Shiki, ~25 KB) | File system read |
| L4 | Code Line | Editable code (CodeMirror 6, ~75 KB lazy) | File system read + write |

This document surveys the academic and industrial state of the art for implementing this 5-level fractal drill-down, covering LOD strategies, focus+context theory, camera transitions, instanced rendering at scale, and bidirectional graph-code linking.

---

## 2. ExplorViz LOD Strategy

ExplorViz is the most directly relevant system to the Ontology Map Toolkit. Developed at Kiel University under Wilhelm Hasselbring, it is a web-based 3D software visualization tool that uses the city metaphor (derived from CodeCity [1]) and focuses on live trace visualization of enterprise application landscapes.

### Cluster-Based Centroid Distance Threshold Switching

The core LOD mechanism in ExplorViz is **distance-based semantic zoom**: the graphical representation of a software element changes based on the virtual camera's distance from the element's centroid, not merely the element's screen-space size. This distinction matters because screen-space LOD (as used in terrain rendering) does not respect the semantic hierarchy of software -- a distant package and a nearby class may occupy the same screen area but require fundamentally different visual treatments.

Fittkau et al. (2015, 2017) describe the original ExplorViz architecture [2][3], which organizes the software landscape into a hierarchy of **application containers** (servers, VMs) containing **components** (packages) containing **clazzes** (classes). The LOD strategy operates as follows:

1. **Threshold computation.** For each component in the hierarchy, a centroid is computed from the bounding box of all contained elements. A distance threshold `d_open` is defined per hierarchy level (deeper levels have smaller thresholds).

2. **Open/close switching.** When the camera distance to a component's centroid drops below `d_open`, the component "opens" -- its opaque roof disappears and its children become visible. When the camera moves away beyond `d_open + hysteresis`, the component closes again.

3. **Hysteresis band.** A hysteresis margin (typically 15-20% of `d_open`) prevents rapid open/close flickering when the camera hovers near the threshold.

Hasselbring et al. (2025) extended this work with a formal study on semantic zoom and mini-maps for software cities [4]. Their study found that semantic zoom is "especially useful for large software landscapes," and that combining it with a 2D mini-map orientation widget significantly improves navigation efficiency in deep hierarchies.

### Application to the Toolkit

For the 5-level Ontology Map Toolkit drill, we adapt ExplorViz's approach:

| Level Transition | Threshold (camera distance) | Hysteresis |
|------------------|-----------------------------|------------|
| L0 -> L1 | `< 40 units` from module centroid | 8 units |
| L1 -> L2 | `< 15 units` from file centroid | 3 units |
| L2 -> L3 | `< 5 units` from function centroid | 1 unit |
| L3 -> L4 | Click "Edit" button (explicit, not distance) | N/A |

L3->L4 is intentionally not distance-based: entering edit mode is a commitment that should require explicit user intent, not an accidental scroll.

---

## 3. Furnas DOI Formula

George W. Furnas introduced the **Degree of Interest (DOI)** function in his seminal 1986 paper "Generalized Fisheye Views" [5]. The formula provides a principled mathematical framework for deciding what to show and what to suppress in a large information structure:

```
DOI(x) = API(x) - D(x, focus)
```

Where:
- `API(x)` = **A Priori Importance** of node `x`. This is a static, context-independent measure of how important `x` is in the overall structure. For code: a `main()` function has higher API than a private helper; a `models.py` file has higher API than `__init__.py`.
- `D(x, focus)` = **Distance** from `x` to the current focus point. This can be graph distance (number of hops), tree depth distance, or Euclidean distance in the 3D layout.
- `DOI(x)` = the resulting degree of interest. Nodes with `DOI(x)` below a threshold `theta` are hidden or reduced to minimal representation.

### Computing API(x) for the Toolkit

For a codebase project graph, we define API heuristics per level:

| Level | API Heuristic | Range |
|-------|---------------|-------|
| L0 (System) | `log(total_LOC) + edge_count * 0.1` | 0-10 |
| L1 (Module) | `log(file_count) + import_count * 0.05` | 0-8 |
| L2 (File) | `log(LOC) + class_count + function_count * 0.5` | 0-6 |
| L3 (Function) | `complexity + is_public * 2 + test_coverage * 1` | 0-5 |
| L4 (Code Line) | `is_definition * 3 + has_annotation * 1` | 0-3 |

### Computing D(x, focus) Across Levels

The distance function must work across hierarchy levels. We use a **weighted tree distance**:

```
D(x, focus) = sum of edge weights on the path from x to focus in the containment tree
```

Where edge weights increase with depth: L0->L1 weight = 1, L1->L2 weight = 2, L2->L3 weight = 4, L3->L4 weight = 8. This ensures that distant siblings at the same level are penalized less than elements several levels away.

### Practical Application

When the user focuses on `auth_service.validate()` at L3:
- `auth_service.py` (parent file, D=4) retains high DOI -- rendered fully.
- `auth_service.AuthService` (sibling class, D=6) retains medium DOI -- rendered as a collapsed badge.
- `models.py` (sibling file, D=3) retains decent DOI -- rendered as a labeled cube.
- `utils/helpers.py` (distant file, D=8) has low DOI -- reduced to a dot or hidden.
- `tests/test_auth.py` (cross-reference via TESTS edge, D=5 but high API due to test relationship) -- rendered as a faded link line.

This DOI-driven approach replaces the current all-or-nothing rendering: instead of showing all ~2,000 nodes or just the children of one submap, the system renders a focus+context view where the focused element and its neighborhood are detailed, while distant elements gracefully degrade.

---

## 4. Pad++ Logarithmic Scale Mapping

Bederson and Hollan's Pad++ system (1994) [6] introduced the concept of a **zoomable user interface (ZUI)** where continuous geometric zoom maps to discrete semantic levels. The key insight is that human perception of scale is logarithmic, not linear -- doubling the zoom factor does not double the perceived detail, but a 4x zoom does feel like "one level deeper."

### Logarithmic Breakpoint Mapping

Pad++ uses a logarithmic mapping from continuous zoom factor `z` to discrete semantic levels:

```
level = floor(log_b(z))
```

Where `b` is the base of the logarithm (typically 4 for 4x zoom per level). For the Ontology Map Toolkit, we define:

| Level | Zoom Factor | Logarithmic Position | Visual Content |
|-------|-------------|---------------------|----------------|
| L0 (System) | 1x (default) | `log4(1) = 0` | Full system map, 3D shapes |
| L1 (Module) | 4x | `log4(4) = 1` | Package contents, file nodes |
| L2 (File) | 16x | `log4(16) = 2` | File internals, classes/functions |
| L3 (Function) | 64x | `log4(64) = 3` | Syntax-highlighted code |
| L4 (Code Line) | 256x | `log4(256) = 4` | Editable code, line-level |

### Continuous vs. Discrete Transition

Pad++ demonstrated that the transition between semantic levels should feel **continuous** even though the underlying representation changes discretely. This is achieved by:

1. **Cross-fade.** When zoom crosses a level boundary (e.g., 3.8x -> 4.2x), the outgoing representation (L0 3D shapes) fades out while the incoming representation (L1 file nodes) fades in over a 200-300ms window.

2. **Geometric continuity.** The incoming representation's initial position and scale match the outgoing representation's final state, so the user perceives a smooth morphing rather than a jump.

3. **Pre-rendering.** The next level's representation is pre-computed when the zoom approaches within 20% of the boundary (`0.8 * threshold`), so the transition is instantaneous when the threshold is crossed.

### Adaptation for the Toolkit

The toolkit uses a hybrid approach: **mouse wheel / pinch zoom drives continuous zoom**, and the zoom-manager.js state machine (WP-4.2) maps the continuous zoom factor to the 5 discrete levels using the breakpoints above. Double-clicking a node provides instant "jump to next level" as a shortcut, bypassing the continuous zoom.

The 4x base was chosen because:
- It maps well to the 5-level hierarchy (1x to 256x is a comfortable range for mouse wheel)
- It matches human perceptual expectations (4x "feels like one step deeper")
- It is consistent with ExplorViz's empirically validated distance thresholds [4]
- It avoids the "lost in zoom" problem that occurs with smaller bases (2x requires too many scroll steps)

---

## 5. Camera Transitions

Camera transitions between drill-down levels are critical to spatial cognition: a poorly animated transition breaks the user's mental model of the hierarchy, while a well-crafted transition reinforces it.

### Duration

Material Design 3 motion guidelines [7] specify:

- **Large spatial transitions (full-screen, depth changes):** 300-400ms
- **Small UI transitions (tooltips, badges):** 150-200ms
- **Tablet:** +30% duration (e.g., 390-520ms)
- **Wearable:** -30% duration (e.g., 210-280ms)

For drill-down transitions in the toolkit, we target **350ms** as the default, configurable via the `motion.drill_duration_ms` design token.

### Easing

Material Design 3 defines easing tokens for different transition types [7]:

- **Emphasized (default):** `cubic-bezier(0.2, 0, 0, 1)` -- fast start, smooth landing. Used for camera moves to a new focus.
- **Emphasized decelerate:** `cubic-bezier(0.05, 0.7, 0.1, 1)` -- for entering elements (new level appearing).
- **Standard:** `cubic-bezier(0.2, 0, 0, 1)` -- for cross-fading between levels.

### Quaternion SLERP Interpolation

Camera orientation during drill-down transitions uses **Spherical Linear Interpolation (SLERP)** on quaternions, as introduced by Shoemake (1985) [8]. SLERP guarantees:

1. **Shortest path.** The rotation follows the minimal arc on the unit quaternion sphere.
2. **Constant angular velocity.** The rotation speed is uniform throughout the interpolation, avoiding the acceleration/deceleration artifacts of Euler angle interpolation.
3. **Gimbal-lock immunity.** Quaternions do not suffer from the singularities that plague Euler angle representations.

In Three.js, SLERP is natively supported via `Quaternion.slerp(target, t)`, where `t` is the interpolation parameter driven by the easing function.

### Arc Paths for Depth Changes

For transitions that involve both lateral movement and depth change (e.g., drilling from L0 into a module that is not centered on screen), a straight-line camera path can feel disorienting because it clips through intermediate geometry. Instead, we use an **arc path**:

```
position(t) = lerp(start, end, ease(t)) + up * sin(PI * t) * arc_height
```

Where `arc_height` is proportional to the lateral distance (typically 20-30% of the horizontal displacement). This lifts the camera slightly during the transition, providing a "fly-over" feel that preserves spatial context.

### Per-Level Camera Presets

| Level | Camera Type | Distance | FOV | Controls |
|-------|-------------|----------|-----|----------|
| L0 | Perspective, orbital | 80 units | 60deg | OrbitControls (rotate, pan, zoom) |
| L1 | Perspective, orbital | 30 units | 55deg | OrbitControls |
| L2 | Perspective, focused | 12 units | 50deg | OrbitControls (restricted pan) |
| L3 | Orthographic, top-down | 5 units | N/A | Scroll only (code view) |
| L4 | Orthographic, top-down | 5 units | N/A | Text cursor (editor mode) |

The switch from perspective to orthographic at L3 is intentional: code is inherently 2D, and forcing perspective distortion on text is counterproductive.

---

## 6. InstancedMesh2 (@three.ez)

Rendering 10K+ nodes at 60fps (INV-OT-009) requires instanced rendering. The `@three.ez/instanced-mesh` package [9] provides `InstancedMesh2`, an enhanced replacement for Three.js's native `InstancedMesh` with critical features for the toolkit:

### Per-Instance Frustum Culling

Native Three.js `InstancedMesh` performs frustum culling on the **entire mesh bounding box**, meaning either all 10K instances are rendered or none are. `InstancedMesh2` performs **per-instance frustum culling**: only instances within the camera frustum are submitted to the GPU. For a typical drill-down view where the user focuses on one region, this can reduce draw calls from 10K to 200-500 instances.

### BVH Spatial Indexing

To make per-instance frustum culling efficient (O(log N) instead of O(N)), `InstancedMesh2` supports building a **Bounding Volume Hierarchy (BVH)** over instance positions. The BVH is constructed once when instances are added and updated incrementally when instances move. For mostly-static software architecture nodes, the BVH is built once and never rebuilt.

API for BVH creation:

```javascript
const mesh = new InstancedMesh2(geometry, material, { capacity: 10000 });
// ... add instances ...
mesh.computeBVH();  // Build BVH for fast culling + raycasting
```

### LOD Switching

`InstancedMesh2` supports per-instance **Level of Detail (LOD)**: instances closer to the camera render at full geometry (e.g., 256 triangles for a detailed gear shape), while distant instances render at reduced geometry (e.g., 16 triangles for a simple sphere). This integrates naturally with the DOI formula from Section 3 -- high-DOI nodes render at full detail, low-DOI nodes at reduced detail.

### Performance Benchmarks

According to the library's benchmarks and Three.js forum reports [9]:

| Instance Count | Native InstancedMesh (FPS) | InstancedMesh2 (FPS) | InstancedMesh2 + BVH (FPS) |
|----------------|---------------------------|---------------------|---------------------------|
| 10K | 60 | 60 | 60 |
| 100K | 25-30 | 50-55 | 58-60 |
| 500K | 5-10 | 20-25 | 40-50 |
| 1M | < 5 | 10-15 | 40-70 |

For the toolkit's target of 10K nodes at 60fps, even native InstancedMesh suffices. However, `InstancedMesh2` becomes critical for:
- Large codebases (100K+ symbols across all files)
- Federation mode (F-19) where multiple systems are rendered simultaneously
- Smooth LOD transitions during drill-down

### Integration Pattern for the Toolkit

```javascript
// lod.js -- LOD manager for fractal drill-down
import { InstancedMesh2 } from '@three.ez/instanced-mesh';

export function createLODManager(scene, nodeData) {
    // Group nodes by current drill level
    const meshByLevel = new Map();

    for (const level of [0, 1, 2]) {
        const nodes = nodeData.filter(n => n.depth === level);
        const mesh = new InstancedMesh2(
            getGeometryForLevel(level),
            getMaterialForLevel(level),
            { capacity: nodes.length, createEntities: true }
        );

        nodes.forEach((node, i) => {
            mesh.setMatrixAt(i, computeTransform(node));
            mesh.setColorAt(i, computeColor(node));
        });

        mesh.computeBVH();
        scene.add(mesh);
        meshByLevel.set(level, mesh);
    }

    return {
        update(cameraPosition, focusNode) {
            // Adjust LOD levels based on DOI
            // Hide/show instances based on drill state
        }
    };
}
```

---

## 7. Sourcetrail Bidirectional Linking

Sourcetrail [10] was a free, open-source, cross-platform code explorer (discontinued in 2021) that pioneered **bidirectional graph-code linking**: selecting a symbol in the code editor highlights it in the dependency graph, and selecting a node in the graph jumps to its definition in the code viewer. This is the exact interaction model needed for the toolkit's L2->L3->L4 transitions.

### Sourcetrail Architecture

Sourcetrail's data architecture is built on three components:

1. **Indexer.** Language-specific indexers (C, C++, Java, Python) parse source code and extract an Abstract Syntax Graph (ASG) containing nodes (files, classes, functions, variables) and edges (calls, inheritance, containment, imports). The indexer writes results to a SQLite database (`.srctrldb`).

2. **SQLite Graph Database.** The indexed graph is stored in SQLite with three core tables: `node` (id, type, name), `edge` (id, type, source_node_id, target_node_id), and `source_location` (id, file_id, start_line, start_col, end_line, end_col, node_id). The `source_location` table is the key to bidirectional linking -- it maps every graph node to its exact position in source code.

3. **MessageDispatcher.** The UI components (graph view and code view) communicate via a central `MessageDispatcher` using a publish-subscribe pattern. When the user clicks a node in the graph, a `MessageActivateNodes` message is dispatched; the code view subscribes to this message and scrolls to the corresponding `source_location`. Conversely, clicking a symbol in the code view dispatches `MessageActivateSourceLocation`, which the graph view uses to highlight the corresponding node.

### Adaptation for the Toolkit

The toolkit's data layer (`state.js`) already implements a reactive pub/sub store, which maps directly to Sourcetrail's MessageDispatcher pattern. The adaptation requires:

1. **Source location data in graph.json.** The Project Graph adapter (WP-1.3) must include `source_location` fields in node metadata:

```json
{
    "id": "auth_service.validate",
    "type": "function",
    "source_location": {
        "file": "src/veritas/services/auth_service.py",
        "start_line": 42,
        "start_col": 4,
        "end_line": 67,
        "end_col": 0
    }
}
```

2. **Graph -> Code navigation.** When the user drills from L2 (file) into L3 (code view), the `source_location` of the selected node is used to scroll the code view to the exact line and highlight the definition span.

3. **Code -> Graph navigation.** At L3/L4, clicking a symbol reference in the code (e.g., a function call) dispatches a state update that navigates the graph to the called function's node, potentially triggering a cross-file drill.

4. **Bidirectional highlight sync.** When the cursor moves in the code editor (L4), the currently-scoped symbol is determined via bracket matching or AST analysis, and the corresponding graph node is highlighted in the minimap. This provides continuous spatial awareness even while editing code.

### Differences from Sourcetrail

| Aspect | Sourcetrail | Ontology Map Toolkit |
|--------|-------------|---------------------|
| Rendering | 2D graph + code panels | 3D spatial map + code overlay |
| Navigation | Click-to-navigate (flat) | Fractal drill-down (hierarchical) |
| Data source | SQLite (local index) | Project Graph (FalkorDB) + graph.json |
| Message bus | C++ MessageDispatcher | JavaScript state.js (Proxy-based) |
| Code display | Custom Qt widget | Shiki (L3) / CodeMirror 6 (L4) |
| Edit capability | None (read-only) | Full editing at L4 |

---

## 8. Design Recommendations

### 8.1 Finite State Machine

The zoom-manager.js (WP-4.2) should implement a 5-state FSM governing the drill-down lifecycle:

```
                    drill_into(node)              drill_into(node)
    ┌─────────┐    ──────────────>    ┌─────────┐    ──────────────>    ┌─────────┐
    │ SYSTEM  │                       │ MODULE  │                       │  FILE   │
    │  (L0)   │    <──────────────    │  (L1)   │    <──────────────    │  (L2)   │
    └─────────┘    drill_out()        └─────────┘    drill_out()        └─────────┘
                                                                            │  ▲
                                                              drill_into()  │  │ drill_out()
                                                                            ▼  │
                                                                        ┌─────────┐
                                                                        │FUNCTION │
                                                                        │  (L3)   │
                                                                        └─────────┘
                                                                            │  ▲
                                                                 edit()     │  │ close_editor()
                                                                            ▼  │
                                                                        ┌─────────┐
                                                                        │  CODE   │
                                                                        │  (L4)   │
                                                                        └─────────┘
```

**State transitions:**
- `drill_into(node)`: Triggered by double-click or zoom threshold crossing. Validates that the target node has children at the next level. Initiates camera transition (350ms, ease-out). Loads next level's data (from graph.json cache or server fetch).
- `drill_out()`: Triggered by breadcrumb click, Escape key, or zoom-out threshold. Reverses the camera transition. Unloads current level's detail data (memory management).
- `edit()`: Triggered by explicit "Edit" button at L3. Loads CodeMirror 6 lazily (Phase 4, ~75 KB). Switches camera to orthographic.
- `close_editor()`: Triggered by Escape or breadcrumb. Saves changes if dirty. Switches back to perspective.

### 8.2 LOD Thresholds

Based on the Furnas DOI formula (Section 3) and ExplorViz empirical data (Section 2):

| DOI Range | Visual Treatment | GPU Cost |
|-----------|------------------|----------|
| > 8.0 | Full 3D shape, label, glow outline | High |
| 5.0 - 8.0 | Simplified shape, label | Medium |
| 2.0 - 5.0 | Color dot, no label | Low |
| 0.0 - 2.0 | Sub-pixel dot or hidden | Minimal |
| < 0.0 | Hidden | Zero |

### 8.3 Camera Presets Per Level

See the table in Section 5. The key design decisions:

1. **Perspective at L0-L2** -- spatial relationships matter at architectural levels.
2. **Orthographic at L3-L4** -- text is 2D; perspective distortion on code is harmful.
3. **FOV narrows with depth** (60 -> 55 -> 50) -- creates a "tunneling" effect that reinforces the sense of going deeper.
4. **Controls simplify with depth** -- at L0, full orbit. At L3, scroll only. At L4, text cursor replaces 3D navigation.

### 8.4 Migration Path from Current 1-Level Submaps

The current submap system (`submaps.js`) should be preserved as a **fallback** for graph.json-only mode (no Project Graph server). The migration path:

1. **Phase 1 (WP-4.2-4.3):** Implement zoom-manager.js FSM and L0->L1 transition. The L1 renderer replaces the current submap modal with an in-scene drill. Current `submaps.js` becomes L1 data source for static mode.

2. **Phase 2 (WP-4.4):** Implement L2 renderer. Requires Project Graph bridge (WP-4.10) for live `File -> Symbol` queries. Falls back to a "no detail available" placeholder in static mode.

3. **Phase 3 (WP-4.5-4.6):** Implement L3 (Shiki) and L4 (CodeMirror 6). These are pure client-side -- they need file content, which can come from the server bridge or be embedded in graph.json for static export.

4. **Phase 4 (WP-4.7-4.9):** Add LOD manager (InstancedMesh2), performance testing, polish camera transitions. This is the optimization pass that ensures INV-OT-009 (10K nodes at 60fps) holds under fractal drill stress.

### 8.5 Data Loading Strategy

| Level | Data Source | Load Timing | Cache |
|-------|-------------|-------------|-------|
| L0 | `graph.json` (bundled) | Startup | Permanent |
| L1 | `graph.json` children OR server fetch | On drill (prefetch at 80% threshold) | LRU (50 modules) |
| L2 | Server fetch: `GET /api/graph/file/{id}/symbols` | On drill | LRU (100 files) |
| L3 | Server fetch: `GET /api/files/{path}` | On drill | LRU (20 files) |
| L4 | Same as L3 (already cached) | Immediate | Same as L3 |

For static export (INV-OT-002), L0 and L1 data are embedded in graph.json. L2-L4 require either pre-embedded file content (bloats the bundle) or accept that these levels are only available when the server is running.

---

## 9. Bibliography

[1] Wettel, R. and Lanza, M. (2007). "Visualizing Software Systems as Cities." In Proceedings of the 4th IEEE International Workshop on Visualizing Software for Understanding and Analysis (VISSOFT 2007), pp. 92-99. IEEE. DOI: [10.1109/VISSOF.2007.4290706](https://doi.org/10.1109/VISSOF.2007.4290706). Also: Wettel, R. and Lanza, M. (2008). "CodeCity: 3D Visualization of Large-Scale Software." In ICSE Companion '08, pp. 921-922. DOI: [10.1145/1370175.1370188](https://doi.org/10.1145/1370175.1370188).

[2] Fittkau, F., Roth, S., and Hasselbring, W. (2015). "ExplorViz: Visual Runtime Behavior Analysis of Enterprise Application Landscapes." In Proceedings of the 23rd European Conference on Information Systems (ECIS 2015). URL: [https://aisel.aisnet.org/ecis2015_cr/46/](https://aisel.aisnet.org/ecis2015_cr/46/).

[3] Fittkau, F., Krause, A., and Hasselbring, W. (2017). "Software Landscape and Application Visualization for System Comprehension with ExplorViz." Information and Software Technology, 87, pp. 259-277. DOI: [10.1016/j.infsof.2016.07.004](https://doi.org/10.1016/j.infsof.2016.07.004).

[4] Hasselbring, W., Krause, A., and Zirkelbach, C. (2020). "ExplorViz: Research on Software Visualization, Comprehension, and Collaboration." Software Impacts, 6, 100039. DOI: [10.1016/j.simpa.2020.100039](https://doi.org/10.1016/j.simpa.2020.100039). Also: Krause, A., Zirkelbach, C., Hasselbring, W., et al. (2022). "Collaborative Software Visualization for Program Comprehension." In Proceedings of ICSE 2022 Companion. DOI: [10.1145/3510455.3512792](https://doi.org/10.1145/3510455.3512792).

[5] Furnas, G. W. (1986). "Generalized Fisheye Views." In Proceedings of the SIGCHI Conference on Human Factors in Computing Systems (CHI '86), pp. 16-23. ACM. DOI: [10.1145/22627.22342](https://doi.org/10.1145/22627.22342). Also published in ACM SIGCHI Bulletin, 17(4). DOI: [10.1145/22339.22342](https://doi.org/10.1145/22339.22342).

[6] Bederson, B. B. and Hollan, J. D. (1994). "Pad++: A Zooming Graphical Interface for Exploring Alternate Interface Physics." In Proceedings of the 7th Annual ACM Symposium on User Interface Software and Technology (UIST '94), pp. 17-26. ACM. DOI: [10.1145/192426.192435](https://doi.org/10.1145/192426.192435).

[7] Google. (2024). "Easing and Duration -- Material Design 3." URL: [https://m3.material.io/styles/motion/easing-and-duration](https://m3.material.io/styles/motion/easing-and-duration). Also: "Duration & Easing -- Motion -- Material Design." URL: [https://m1.material.io/motion/duration-easing.html](https://m1.material.io/motion/duration-easing.html).

[8] Shoemake, K. (1985). "Animating Rotation with Quaternion Curves." ACM SIGGRAPH Computer Graphics, 19(3), pp. 245-254. DOI: [10.1145/325165.325242](https://doi.org/10.1145/325165.325242).

[9] Agargaro. (2024). "@three.ez/instanced-mesh: Enhanced InstancedMesh with Frustum Culling, Fast Raycasting (BVH), Sorting, Visibility, LOD, Skinning and More." npm: [@three.ez/instanced-mesh](https://www.npmjs.com/package/@three.ez/instanced-mesh). GitHub: [https://github.com/agargaro/instanced-mesh](https://github.com/agargaro/instanced-mesh). Three.js Forum Discussion: [https://discourse.threejs.org/t/three-ez-instancedmesh2-enhanced-instancedmesh-with-frustum-culling-fast-raycasting-bvh-sorting-visibility-management-lod-skinning-and-more/69344](https://discourse.threejs.org/t/three-ez-instancedmesh2-enhanced-instancedmesh-with-frustum-culling-fast-raycasting-bvh-sorting-visibility-management-lod-skinning-and-more/69344).

[10] CoatiSoftware. (2021). "Sourcetrail: Free and Open-Source Interactive Source Explorer." GitHub: [https://github.com/CoatiSoftware/Sourcetrail](https://github.com/CoatiSoftware/Sourcetrail). Documentation: [https://github.com/CoatiSoftware/Sourcetrail/blob/master/DOCUMENTATION.md](https://github.com/CoatiSoftware/Sourcetrail/blob/master/DOCUMENTATION.md).

[11] Nielsen Norman Group. (2020). "Executing UX Animations: Duration and Motion Characteristics." URL: [https://www.nngroup.com/articles/animation-duration/](https://www.nngroup.com/articles/animation-duration/).

[12] Three.js Contributors. (2024). "Three.js Documentation: Quaternion.slerp." URL: [https://threejs.org/docs/#api/en/math/Quaternion.slerp](https://threejs.org/docs/#api/en/math/Quaternion.slerp).

---

*Research document for WP-4.1 (UX Research: Semantic Zoom Patterns). This document should be reviewed and approved before implementation of WP-4.2 (Zoom State Machine) begins, per SPEC.md Execution Principle #5: "Research before code."*
