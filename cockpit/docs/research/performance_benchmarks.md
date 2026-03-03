# Performance Benchmarks Specification

**Status**: Draft
**Date**: 2026-02-27
**Invariant**: INV-OT-009 -- 10K+ nodes at 60fps in the browser. Instanced rendering mandatory.

---

## 1. Methodology

### 1.1 Hardware Baseline

All benchmarks target a "modern laptop" reference machine. Results must be reproducible on either configuration below:

| Component   | Apple Silicon Config         | Intel Config                    |
|-------------|------------------------------|---------------------------------|
| CPU         | Apple M2 / M3 (8-core)      | Intel i7-12700H (14-core)       |
| RAM         | 16 GB unified               | 16 GB DDR5                      |
| GPU         | Integrated (8-10 core)      | Intel Iris Xe / UHD 770         |
| Display     | 2560x1600 @ 2x              | 1920x1080 @ 1x                 |
| Browser     | Chrome 120+ / Safari 17+    | Chrome 120+ / Firefox 120+      |
| Pixel ratio | Capped at 1.5 (engine.js L92) | Capped at 1.5 (engine.js L92) |

The pixel ratio cap (`Math.min(devicePixelRatio, 1.5)`) in `engine.js` means actual render resolution on a Retina display is 3840x2400 * 0.75 = 2880x1800 effective pixels. This is the worst-case fill-rate scenario and all benchmarks must use this configuration.

### 1.2 Metrics

Six metrics are collected per benchmark run:

| Metric            | Unit   | Source                          | Description                                              |
|-------------------|--------|---------------------------------|----------------------------------------------------------|
| FPS p50           | fps    | `requestAnimationFrame` deltas  | Median frames per second over measurement window         |
| FPS p95           | fps    | `requestAnimationFrame` deltas  | 95th percentile (worst 5% of frames)                     |
| FPS min           | fps    | `requestAnimationFrame` deltas  | Single worst frame in the window                         |
| Heap memory       | MB     | `performance.memory.usedJSHeapSize` | JS heap consumption at end of measurement            |
| Draw calls        | count  | `renderer.info.render.calls`    | WebGL draw calls per frame                               |
| Triangle count    | count  | `renderer.info.render.triangles`| Triangles submitted per frame                            |
| GPU time          | ms     | `EXT_disjoint_timer_query_webgl2` | GPU-side rendering time (Chrome only, optional)        |

### 1.3 Measurement Window

1. Load the scene and start the render loop.
2. Wait 5 seconds for stabilization (force layout convergence, texture uploads, shader compilation, JIT warmup).
3. Capture metrics for 10 seconds (minimum 600 frames at 60fps target).
4. Compute aggregates and output JSON report.

### 1.4 Measurement Snippet

```javascript
function runBenchmark(renderer, durationMs = 10000, stabilizeMs = 5000) {
  return new Promise((resolve) => {
    const frameTimes = [];
    let lastTime = 0;
    let measuring = false;
    let startTime = 0;

    const warmupEnd = performance.now() + stabilizeMs;

    function tick(now) {
      if (!measuring && now >= warmupEnd) {
        measuring = true;
        startTime = now;
        lastTime = now;
        // Reset renderer counters
        renderer.info.reset();
      }

      if (measuring) {
        if (lastTime > 0) {
          frameTimes.push(now - lastTime);
        }
        lastTime = now;

        if (now - startTime >= durationMs) {
          const sorted = [...frameTimes].sort((a, b) => a - b);
          const toFps = (ms) => ms > 0 ? 1000 / ms : 0;

          resolve({
            frames: frameTimes.length,
            fps_p50: toFps(sorted[Math.floor(sorted.length * 0.50)]),
            fps_p95: toFps(sorted[Math.floor(sorted.length * 0.95)]),
            fps_min: toFps(sorted[sorted.length - 1]),
            memory_mb: performance.memory
              ? Math.round(performance.memory.usedJSHeapSize / 1048576)
              : null,
            draw_calls: renderer.info.render.calls,
            triangles: renderer.info.render.triangles,
          });
          return;
        }
      }

      requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
  });
}
```

---

## 2. Current Baseline (25-33 Nodes)

### 2.1 Rendering Architecture Analysis

The current renderer is built on Three.js r162 with the following pipeline:

```
EffectComposer
  -> RenderPass (scene, orthographic camera)
  -> UnrealBloomPass (quarter resolution)
  -> OutlinePass (hover/selection highlighting)
  -> OutputPass (tone mapping: ACESFilmic, exposure 1.1)
```

Supplementary renderers: `CSS2DRenderer` for HTML labels overlaid on the WebGL canvas.

The scene graph structure for each node is:

```
THREE.Group (node root)
  +-- Mesh (body/primary)         -- MeshStandardMaterial
  +-- Mesh (detail 1)             -- MeshStandardMaterial
  +-- Mesh (detail 2)             -- MeshStandardMaterial
  +-- ... (M_avg child meshes)
```

Each node is constructed by `mkObj(shape, size, matFactory)` in `shapes.js` (719 lines, 26 procedural shape types). The function builds a `THREE.Group` containing 3-15 child `THREE.Mesh` instances depending on shape complexity.

### 2.2 Mesh Count Per Shape (Audited)

Audit of `g.add()` calls per shape in `shapes.js`:

| Shape       | Child meshes | Notable geometry                                |
|-------------|-------------|--------------------------------------------------|
| warehouse   | 10          | 1 box + 4 drawers + 4 handles + 1 top           |
| factory     | 9           | base, tower, 2 cross, drill, pipe, ctrl, screen  |
| satellite   | 4           | pole, dish (partial sphere), feed, tip            |
| terminal    | 14          | spine, 2 pages, 10 log lines, pen                |
| monument    | 5           | 4 tier boxes + capstone cone                      |
| pillars     | 6           | base, 3 columns, entablature, pediment            |
| gear        | 4           | 2 torus rings + 2 axle cylinders                  |
| gate        | 8           | body, top, shackle, 2 legs, keyhole, keyslit, pad |
| database    | 3           | 3 stacked cylinders                               |
| hourglass   | 7           | 2 pillars, 2 caps, 2 bulbs, neck                  |
| brain       | 3           | crystal (lathe), core (icosahedron), mobius strip  |
| dyson_book  | 14          | pedestal, rim, spine, 2 pages, 8 text lines, core, inner |
| gauge       | 4           | ring, face, needle, hub                            |
| hub         | 13          | center + 6 arms + 6 tips                          |
| tree        | 7           | trunk, crown, 2 branches, 2 leaves, (implicit)    |
| sphere      | 3           | sphere + 2 torus rings                             |
| prism       | 5           | rough, polished, 3 sparks                          |
| stairs      | 6           | 5 steps + arrow                                    |
| nexus       | 12          | 3 plates + 6 nodes + 3 connectors                  |
| graph       | 11          | 5 nodes + 6 edge cylinders                         |
| dial        | 11          | base, knob, indicator, 8 ticks                     |
| vault       | 10          | body, door, ring, center, handle, 4 bolts, (lock)  |
| screens     | 9           | 3 frames + 3 screens + stand + base               |
| rack        | 11          | frame + 5 units + 5 LEDs                           |
| conveyor    | 8           | belt, 3 rollers, 3 items, arrow                    |
| monitor     | 9           | frame, screen, 4 lines, stand, base               |

**Weighted average**: 109 total `g.add()` calls / 26 shapes = **M_avg = 7.6 meshes/node** (with loop-expanded shapes like hub=13 and terminal=14 pulling the average up).

### 2.3 Baseline Estimates (33 Nodes)

With 33 sysmap nodes (from `sysmap.js`) and approximately 50 edges rendered as line segments or tube meshes:

| Metric         | Estimated value | Reasoning                                                |
|----------------|-----------------|----------------------------------------------------------|
| Draw calls     | ~300-350        | 33 nodes * 7.6 avg meshes + ~50 edge lines + labels + bloom passes |
| Triangles      | ~80K-120K       | Each mesh averages ~300-400 tris (low-poly procedural)   |
| FPS p50        | 60              | Trivially under GPU budget at this scale                 |
| FPS p95        | 60              | No frame drops expected                                  |
| Heap memory    | 50-80 MB        | Three.js baseline (~30MB) + geometry + materials + bloom buffers + PMREM env map |

The current 33-node scene is well within budget. Performance concerns only arise at scale.

---

## 3. Synthetic Datasets

### 3.1 Generator Specification

Synthetic datasets place N nodes in randomized orbital positions and connect them with M = 3N edges (Erdos-Renyi random graph with p = 6/N, yielding expected degree 6 per node -- typical for real codebases).

Node generation:

```javascript
function generateSyntheticGraph(N) {
  const nodes = [];
  const edges = [];
  const shapes = [
    'warehouse','factory','satellite','terminal','monument','pillars',
    'gear','gate','database','hourglass','brain','dyson_book','gauge',
    'hub','tree','sphere','prism','stairs','nexus','graph','dial',
    'vault','screens','rack','conveyor','monitor'
  ];
  const groups = ['module','layer','source','consumer','infra'];

  for (let i = 0; i < N; i++) {
    // Orbital distribution: radius 0-50, random angle, height -5 to 5
    const r = Math.sqrt(Math.random()) * 50;  // sqrt for uniform area distribution
    const theta = Math.random() * Math.PI * 2;
    nodes.push({
      id: `n${i}`,
      label: `Node ${i}`,
      type: groups[i % groups.length],
      group: groups[i % groups.length],
      properties: {
        x: r * Math.cos(theta),
        z: r * Math.sin(theta),
        y: (Math.random() - 0.5) * 10,
        loc: Math.floor(Math.random() * 500) + 10,
      }
    });
  }

  // Erdos-Renyi edges: M = 3N
  const M = 3 * N;
  const edgeSet = new Set();
  while (edges.length < M) {
    const a = Math.floor(Math.random() * N);
    const b = Math.floor(Math.random() * N);
    if (a === b) continue;
    const key = `${Math.min(a,b)}-${Math.max(a,b)}`;
    if (edgeSet.has(key)) continue;
    edgeSet.add(key);
    edges.push({
      from: `n${a}`,
      to: `n${b}`,
      type: ['IMPORTS','CALLS','DEPENDS_ON','CONTAINS'][Math.floor(Math.random()*4)]
    });
  }

  return {
    nodes,
    edges,
    metadata: {
      name: `Synthetic ${N}`,
      generated_at: new Date().toISOString(),
      generator: 'ontology-map-toolkit/benchmark',
      node_count: N,
      edge_count: edges.length,
    }
  };
}
```

### 3.2 Dataset Sizes

| Dataset   | Nodes (N) | Edges (M=3N) | Shape distribution          |
|-----------|-----------|-------------|------------------------------|
| XS        | 100       | 300         | ~4 per shape type            |
| S         | 500       | 1,500       | ~19 per shape type           |
| M         | 1,000     | 3,000       | ~38 per shape type           |
| L         | 5,000     | 15,000      | ~192 per shape type          |
| XL        | 10,000    | 30,000      | ~385 per shape type          |
| XXL       | 50,000    | 150,000     | ~1,923 per shape type        |

Output format: `graph_data.json` per the schema at `schemas/graph_data.json`.

---

## 4. InstancedMesh Optimization Analysis

### 4.1 Current Architecture: O(N * M_avg) Draw Calls

The current rendering pipeline issues one WebGL draw call per `THREE.Mesh`. For N nodes with M_avg = 7.6 child meshes each:

```
Draw calls = N * M_avg + E_edges + C_postprocessing
           = N * 7.6   + 3N      + ~10
           = 10.6N + 10
```

Where `E_edges` assumes one line/tube mesh per edge, and `C_postprocessing` accounts for bloom, outline, and output passes.

| N       | Draw calls (current) | GPU budget @ 60fps |
|---------|---------------------|--------------------|
| 33      | 360                 | Well within budget |
| 100     | 1,070               | Comfortable        |
| 500     | 5,310               | Marginal           |
| 1,000   | 10,610              | Over budget         |
| 5,000   | 53,010              | Unusable (~5fps)   |
| 10,000  | 106,010             | Unusable (~1fps)   |
| 50,000  | 530,010             | Will not render    |

A modern integrated GPU can sustain approximately 2,000-4,000 draw calls at 60fps depending on material complexity. The current architecture hits the draw call wall at approximately N=300-500 nodes.

### 4.2 Target Architecture: O(S) Draw Calls via InstancedMesh

With `THREE.InstancedMesh`, all instances of a given geometry+material combination share a single draw call. The per-instance transform is stored in an `InstancedBufferAttribute` (4x4 matrix).

**Ideal case**: If each shape were a single merged geometry, draw calls would reduce to:

```
Draw calls = S + E_batched + C_postprocessing
           = 26 + 1 + 10
           = 37  (constant, regardless of N)
```

Where S = 26 unique shape types and E_batched = 1 instanced line batch for all edges.

### 4.3 The Composite Shape Problem

The `mkObj()` function builds composite shapes from 3-15 child meshes using different materials (dark, mid, light, accent, screen). A single "warehouse" shape uses 10 meshes across 3 material types. This means naive InstancedMesh conversion is not possible -- each sub-mesh within a composite shape must be instanced separately.

The true instancing granularity is:

```
Draw calls = S * P_avg + E_batched + C_postprocessing
```

Where P_avg is the average number of unique (geometry, material) pairs per shape. Since shapes reuse material factories (5 material slots: dark, mid, light, accent, screen), the actual draw call count is bounded by:

```
Draw calls <= S * 5 + 1 + 10  =  141  (upper bound)
```

In practice, many shapes share the same geometry primitives (BoxGeometry, CylinderGeometry, SphereGeometry). With geometry deduplication by type+dimensions, the expected draw call count is approximately 80-100, regardless of N.

### 4.4 Optimization Strategies

**Strategy A: Simplified LOD shapes for distance**

Replace composite shapes with single merged `BufferGeometry` at distances beyond a threshold (e.g., camera distance > 30 units). The LOD shape is a pre-merged version of the composite, requiring exactly 1 draw call per shape type.

- Complexity: Medium
- Draw call reduction: Full (26 draw calls for distant nodes)
- Visual fidelity: Reduced at distance (acceptable due to screen-space size)

**Strategy B: Pre-baked geometry atlases**

At build time or initialization, merge all child geometries of each shape type into a single `BufferGeometry` with vertex colors encoding the material slot. A custom shader maps vertex color IDs to the 5 material parameters. One draw call per shape type.

- Complexity: High (requires custom shader)
- Draw call reduction: Full (26 draw calls total)
- Visual fidelity: Identical

**Strategy C: @three-ez/InstancedMesh2 with per-instance frustum culling + BVH**

Use the `InstancedMesh2` library which extends `THREE.InstancedMesh` with:
- Per-instance bounding box computation
- BVH spatial index for O(log N) frustum culling
- Dynamic instance count (add/remove without recreation)
- Per-instance color and custom attributes

This approach instances each sub-mesh position within the composite as a fixed offset from the instance transform, using `InstancedBufferAttribute` for the offsets.

- Complexity: Medium (library handles BVH)
- Draw call reduction: 80-100 total draw calls
- Visual fidelity: Identical
- Bonus: O(log N) frustum culling eliminates off-screen instances from GPU submission

**Recommended approach**: Strategy C for the initial implementation (preserves visual fidelity, reasonable complexity), with Strategy A as a future enhancement for the XXL tier.

### 4.5 Predicted Performance

| N       | Draw calls (current) | Draw calls (instanced) | FPS current | FPS instanced |
|---------|---------------------|----------------------|-------------|---------------|
| 33      | 360                 | ~100                 | 60          | 60            |
| 100     | 1,070               | ~100                 | 60          | 60            |
| 500     | 5,310               | ~100                 | 45-60       | 60            |
| 1,000   | 10,610              | ~100                 | 15-25       | 60            |
| 5,000   | 53,010              | ~100                 | 2-5         | 55-60         |
| 10,000  | 106,010             | ~100                 | <1          | 45-55         |
| 50,000  | 530,010             | ~100                 | N/A         | 15-25         |

At 10,000 nodes the instanced approach still faces vertex throughput limits: 10,000 nodes * 7.6 meshes * ~350 triangles = ~26.6M triangles/frame. Integrated GPUs typically sustain 20-40M triangles at 60fps depending on material complexity. With frustum culling (typically 30-50% of nodes visible), the effective triangle count drops to ~10-15M, which is within budget.

At 50,000 nodes, even with instancing, vertex count alone (~133M triangles before culling, ~50-70M after) exceeds integrated GPU capacity. Strategy A (LOD simplification) becomes mandatory at this tier, reducing per-node triangle count by 80% for distant nodes.

### 4.6 Memory Impact

InstancedMesh stores one 4x4 float32 matrix (64 bytes) per instance:

| N       | Instance matrices | Edge buffers  | Total overhead |
|---------|-------------------|---------------|----------------|
| 1,000   | ~0.5 MB           | ~0.3 MB       | ~1 MB          |
| 10,000  | ~4.9 MB           | ~2.9 MB       | ~8 MB          |
| 50,000  | ~24.4 MB          | ~14.4 MB      | ~40 MB         |

This is negligible compared to geometry and texture memory.

---

## 5. Web Worker Offloading

### 5.1 Current Bottleneck

The force-directed layout (`d3-force-3d`) runs on the main thread. At N=5,000+, each force simulation tick takes 5-15ms, consuming a significant portion of the 16.6ms frame budget. The remaining budget for rendering, garbage collection, and JS execution becomes dangerously thin.

### 5.2 Architecture: Force Simulation in Web Worker

```
Main Thread                          Worker Thread
-----------                          -------------
graph_data.json
    |
    v
postMessage(nodes, edges)  -------->  d3-force-3d simulation
    |                                     |
    | requestAnimationFrame               | tick() every 16ms
    |                                     |
    | <--------  transferable Float32     |
    |            (x, y, z per node)       |
    v                                     v
update InstancedMesh matrices        continue simulation
render frame
```

**Communication protocol**:

1. **Initialization**: Main thread sends `{ type: 'init', nodes: [...], edges: [...] }` to worker.
2. **Tick results**: Worker posts `{ type: 'tick', positions: Float32Array }` using `Transferable` (zero-copy). The array layout is `[x0, y0, z0, x1, y1, z1, ...]` with 3 floats per node.
3. **Convergence signal**: Worker posts `{ type: 'converged', alpha: number }` when simulation alpha < 0.001.
4. **Interaction**: Main thread sends `{ type: 'pin', nodeIndex: number, x, y, z }` for drag interactions.
5. **Teardown**: Main thread sends `{ type: 'stop' }` to terminate the simulation.

Transfer size per tick: `N * 3 * 4` bytes. At N=10,000, this is 120KB per frame -- well within the budget for `Transferable` objects (zero-copy, effectively free).

### 5.3 Expected Performance Gain

| N       | Main thread (current) | With Worker    | FPS gain |
|---------|-----------------------|----------------|----------|
| 100     | <1ms                  | 0ms            | ~0%      |
| 1,000   | 2-4ms                 | <0.1ms         | ~15%     |
| 5,000   | 5-15ms                | <0.1ms         | ~30-50%  |
| 10,000  | 15-40ms               | <0.1ms         | ~60-80%  |

The gain is measured as recovered frame budget. At 10K nodes without a worker, force ticks alone consume the entire frame budget (16.6ms), leaving zero time for rendering. With the worker, the main thread only pays the cost of reading the `Float32Array` and updating instance matrices (~0.5ms for 10K nodes).

### 5.4 Alternative: requestIdleCallback

For simpler codebases (N < 2,000) where a full Web Worker is overkill, force simulation ticks can be batched into `requestIdleCallback`:

```javascript
function scheduleForceUpdate(simulation, updateCallback) {
  function idle(deadline) {
    while (deadline.timeRemaining() > 2 && simulation.alpha() > 0.001) {
      simulation.tick();
    }
    updateCallback(simulation.nodes());
    if (simulation.alpha() > 0.001) {
      requestIdleCallback(idle);
    }
  }
  requestIdleCallback(idle);
}
```

This yields frames to rendering priority but converges more slowly. Not recommended for N > 2,000 where per-tick cost exceeds the idle deadline.

---

## 6. Performance Targets

Derived from SPEC invariants and engineering constraints:

| Target                          | Value            | Source                    | Notes                                           |
|---------------------------------|------------------|---------------------------|-------------------------------------------------|
| 10K nodes @ 60fps              | Mandatory        | INV-OT-009                | Instanced rendering required                    |
| Initial bundle size             | < 250 KB gzip   | SPEC performance section   | Three.js tree-shaken + app code                 |
| First meaningful paint          | < 2 seconds      | SPEC performance section   | Scene visible with at least 1 node rendered     |
| Layout convergence (1K nodes)   | < 3 seconds      | Engineering target         | Force simulation alpha < 0.001                  |
| Layout convergence (10K nodes)  | < 8 seconds      | Engineering target         | With Web Worker, non-blocking                   |
| Memory ceiling (10K nodes)      | < 300 MB         | Engineering target         | Geometry + textures + instance buffers           |
| Memory ceiling (50K nodes)      | < 500 MB         | Engineering target         | With LOD, frustum culling active                |
| Draw calls (any N)              | < 200            | Engineering target         | Post-instancing, constant                       |
| Post-processing overhead        | < 4 ms/frame     | Engineering target         | Bloom at quarter resolution, outline optional   |

### 6.1 Budget Breakdown Per Frame (16.6ms at 60fps)

| Phase                  | Budget    | Notes                                         |
|------------------------|-----------|-----------------------------------------------|
| JS logic + callbacks   | 2.0 ms    | OrbitControls, animation, state updates       |
| Instance matrix update | 0.5 ms    | Copy positions from Worker Float32Array       |
| WebGL draw calls       | 6.0 ms    | ~100 instanced draw calls                     |
| Post-processing        | 4.0 ms    | Bloom (quarter-res) + outline + output        |
| CSS2D labels           | 1.5 ms    | DOM update for visible labels (capped at 200) |
| GC / idle              | 2.6 ms    | Safety margin                                 |
| **Total**              | **16.6 ms** |                                             |

---

## 7. Benchmark Harness Specification

### 7.1 `benchmark.html`

A standalone HTML page that loads the full rendering pipeline, generates a synthetic dataset, runs the measurement window, and outputs a JSON report.

**URL parameters**:

| Parameter  | Default | Description                                      |
|------------|---------|--------------------------------------------------|
| `nodes`    | 1000    | Number of synthetic nodes to generate             |
| `edges`    | 3x      | Edge multiplier (default 3x nodes)                |
| `duration` | 10000   | Measurement duration in ms                        |
| `stabilize`| 5000    | Stabilization wait in ms                          |
| `instanced`| false   | Use InstancedMesh path (once implemented)         |
| `worker`   | false   | Use Web Worker for force simulation               |
| `lod`      | false   | Enable LOD distance simplification                |

**Behavior**:

1. Parse URL params.
2. Initialize engine (renderer, camera, post-processing) via `initEngine()`.
3. Generate synthetic `graph_data.json` using the generator from Section 3.
4. Create scene objects (current or instanced path, depending on `?instanced=` flag).
5. Start force layout (main thread or worker, depending on `?worker=` flag).
6. Wait `stabilize` ms.
7. Run `runBenchmark(renderer, duration)` from Section 1.4.
8. Display results on-screen and log JSON to console.
9. If running under Puppeteer/Playwright, expose results via `window.__BENCHMARK_RESULT__`.

**Output JSON schema**:

```json
{
  "timestamp": "2026-02-27T12:00:00.000Z",
  "config": {
    "nodes": 1000,
    "edges": 3000,
    "instanced": false,
    "worker": false,
    "lod": false,
    "pixel_ratio": 1.5,
    "resolution": [2880, 1800],
    "user_agent": "..."
  },
  "results": {
    "frames": 612,
    "fps_p50": 60.2,
    "fps_p95": 58.7,
    "fps_min": 42.1,
    "memory_mb": 187,
    "draw_calls": 10610,
    "triangles": 3542000,
    "gpu_time_ms": null
  }
}
```

### 7.2 CLI Runner

A Node.js script that launches Puppeteer, iterates over dataset sizes, and collects results into a CSV/JSON report.

```
node scripts/benchmark.js --sizes 100,500,1000,5000,10000
                          [--instanced]
                          [--worker]
                          [--lod]
                          [--output results.json]
                          [--headless]
```

**Implementation outline**:

```javascript
// scripts/benchmark.js
import puppeteer from 'puppeteer';

const SIZES = (process.argv.find(a => a.startsWith('--sizes=')) || '--sizes=1000')
  .split('=')[1].split(',').map(Number);

const flags = {
  instanced: process.argv.includes('--instanced'),
  worker:    process.argv.includes('--worker'),
  lod:       process.argv.includes('--lod'),
  headless:  !process.argv.includes('--no-headless'),
};

async function run() {
  const browser = await puppeteer.launch({
    headless: flags.headless,
    args: ['--enable-webgl', '--use-gl=angle'],
  });

  const results = [];

  for (const n of SIZES) {
    console.log(`Benchmarking N=${n}...`);
    const page = await browser.newPage();

    const params = new URLSearchParams({
      nodes: n,
      instanced: flags.instanced,
      worker: flags.worker,
      lod: flags.lod,
    });

    await page.goto(`http://localhost:8420/benchmark.html?${params}`, {
      waitUntil: 'networkidle0',
    });

    // Wait for benchmark to complete (stabilize + measure + buffer)
    const timeout = 5000 + 10000 + 5000; // 20s
    const result = await page.waitForFunction(
      () => window.__BENCHMARK_RESULT__,
      { timeout }
    );

    const data = await result.jsonValue();
    results.push(data);
    console.log(`  FPS p50=${data.results.fps_p50.toFixed(1)}, ` +
                `draw_calls=${data.results.draw_calls}, ` +
                `memory=${data.results.memory_mb}MB`);

    await page.close();
  }

  await browser.close();

  // Output
  const output = process.argv.find(a => a.startsWith('--output='));
  if (output) {
    const fs = await import('fs');
    fs.writeFileSync(output.split('=')[1], JSON.stringify(results, null, 2));
  }

  // Summary table
  console.log('\n=== BENCHMARK SUMMARY ===');
  console.log('Nodes  | FPS p50 | FPS p95 | FPS min | Memory  | Draw calls | Triangles');
  console.log('-------|---------|---------|---------|---------|------------|----------');
  for (const r of results) {
    const c = r.config, s = r.results;
    console.log(
      `${String(c.nodes).padStart(6)} | ` +
      `${s.fps_p50.toFixed(1).padStart(7)} | ` +
      `${s.fps_p95.toFixed(1).padStart(7)} | ` +
      `${s.fps_min.toFixed(1).padStart(7)} | ` +
      `${String(s.memory_mb).padStart(5)}MB | ` +
      `${String(s.draw_calls).padStart(10)} | ` +
      `${String(s.triangles).padStart(9)}`
    );
  }
}

run().catch(console.error);
```

**Expected output** (projected, pre-optimization):

```
=== BENCHMARK SUMMARY ===
Nodes  | FPS p50 | FPS p95 | FPS min | Memory  | Draw calls | Triangles
-------|---------|---------|---------|---------|------------|----------
   100 |    60.0 |    59.5 |    55.2 |    62MB |       1070 |    266000
   500 |    52.3 |    44.8 |    38.1 |    95MB |       5310 |   1330000
  1000 |    28.6 |    21.2 |    15.4 |   142MB |      10610 |   2660000
  5000 |     4.2 |     2.8 |     1.9 |   385MB |      53010 |  13300000
 10000 |     1.1 |     0.6 |     0.4 |   720MB |     106010 |  26600000
```

**Expected output** (projected, post-InstancedMesh + Worker):

```
=== BENCHMARK SUMMARY ===
Nodes  | FPS p50 | FPS p95 | FPS min | Memory  | Draw calls | Triangles
-------|---------|---------|---------|---------|------------|----------
   100 |    60.0 |    60.0 |    58.9 |    58MB |         98 |    266000
   500 |    60.0 |    59.8 |    57.2 |    72MB |        100 |   1330000
  1000 |    60.0 |    59.2 |    55.8 |    95MB |        100 |   2660000
  5000 |    58.4 |    54.1 |    48.3 |   195MB |        100 |  13300000
 10000 |    52.8 |    46.5 |    40.2 |   290MB |        100 |  26600000
 50000 |    18.5 |    12.3 |     8.1 |   480MB |        100 | 133000000
```

Note: 10K nodes at 52.8 fps (p50) does not meet the 60fps target. To close the gap, frustum culling must be active (reducing effective triangles by 40-60%), and LOD simplification must reduce distant-node triangles by 80%. With both optimizations:

```
10K + instancing + worker + frustum culling + LOD:
  Effective triangles: ~26.6M * 0.5 (culled) * 0.4 (LOD blend) = ~5.3M
  FPS p50: 60 (target met)
```

### 7.3 CI Integration

The benchmark harness should run as a non-blocking CI job on every PR that touches `client/js/scene/` files. The job compares results against the baseline stored in `benchmarks/baseline.json` and fails if any target from Section 6 regresses by more than 10%.

```yaml
# .github/workflows/benchmark.yml (sketch)
benchmark:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: npm ci
    - run: npx playwright install chromium
    - run: node scripts/benchmark.js --sizes 100,1000,10000 --headless --output results.json
    - run: node scripts/benchmark-compare.js baseline.json results.json --threshold 0.10
```

---

## Appendix A: Formulas Reference

| Formula | Description |
|---------|-------------|
| `DC_current = N * M_avg + 3N + 10` | Draw calls, current architecture (M_avg = 7.6) |
| `DC_instanced = S * P_avg + 1 + 10` | Draw calls, instanced (S=26, P_avg~3.5) |
| `T_current = N * M_avg * T_avg` | Triangle count (T_avg ~ 350 per sub-mesh) |
| `M_edges = 3N` | Edge count (Erdos-Renyi, degree 6) |
| `Worker_transfer = N * 3 * 4 bytes` | Per-frame transfer size (Float32, xyz) |
| `Instance_memory = N * M_avg * 64 bytes` | InstancedMesh matrix storage |
| `Frustum_factor = 0.4 - 0.6` | Fraction of nodes visible (typical orbit view) |
| `LOD_factor = 0.2` | Triangle reduction factor for distant LOD shapes |

## Appendix B: Shape Complexity Tiers

For LOD and instancing priority, shapes are classified into complexity tiers:

| Tier   | Shapes                                            | Meshes | Priority |
|--------|---------------------------------------------------|--------|----------|
| Simple | database, sphere, gauge, brain, gear              | 3-4    | Low      |
| Medium | satellite, monument, pillars, prism, stairs, tree | 4-7    | Medium   |
| Complex| warehouse, factory, terminal, hub, vault, dial, nexus, graph, rack, screens, conveyor, monitor, dyson_book, gate, hourglass | 8-14 | High |

Complex shapes benefit most from LOD simplification at distance, as replacing a 14-mesh composite with a single merged geometry saves 13 draw calls per instance (in the non-instanced path) or reduces vertex count by ~75% (in the instanced path).
