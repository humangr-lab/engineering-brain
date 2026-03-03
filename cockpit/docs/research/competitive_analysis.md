# Competitive Analysis: Ontology Map Toolkit

> Last updated: 2026-02-27
> Methodology: Primary sources (official docs, GitHub repos, academic papers, npm registries). No speculation -- only verifiable claims.

---

## Table of Contents

1. [Competitor Deep-Dives](#competitor-deep-dives)
   - [1. ExplorViz](#1-explorviz-closest-semantic-zoom-3d)
   - [2. Backstage](#2-backstage-closest-developer-portal-ecosystem)
   - [3. cosmos.gl / Cosmograph](#3-cosmosgl--cosmograph-closest-large-scale-graph-performance)
2. [Feature Comparison Matrix](#feature-comparison-matrix)
3. [Differentiation Summary](#differentiation-summary)
4. [References](#references)

---

## Competitor Deep-Dives

### 1. ExplorViz (closest: semantic zoom 3D)

**What it is:** An open-source research tool for live trace visualization of software landscapes using the 3D city metaphor. Developed at Kiel University (Germany) since 2012 under Prof. Wilhelm Hasselbring's group. The project has produced 30+ peer-reviewed publications across IEEE VISSOFT, ECIS, IST, and Software Impacts.

**Website:** https://explorviz.dev | **GitHub:** https://github.com/ExplorViz | **License:** Apache 2.0

#### Architecture

| Component | Technology |
|---|---|
| Frontend | TypeScript (current), historically Ember.js + GWT; Three.js for 3D rendering; WebXR for VR/AR |
| Backend | Java microservices (11 services: adapter-service, span-service, persistence-service, landscape-service, user-service, code-service, code-agent, broadcast-service, settings-service, trace-generator, ai-chat-service) |
| Message Bus | Apache Kafka (spans split into structural + dynamic data across topics) |
| Database | Neo4j (persistence-service, current), MongoDB (legacy architecture for settings/history), Cassandra (legacy span storage) |
| Instrumentation | OpenTelemetry (primary), Kieker-to-OTel bridge for legacy Java systems |
| Deployment | Docker containers (11+ containers), Docker Compose orchestration |

The architecture has evolved significantly. The legacy monolith (pre-2020) used Kafka + Cassandra + MongoDB. The current architecture (2024+) migrated persistence to Neo4j and adopted OpenTelemetry as the primary instrumentation standard, replacing the proprietary Kieker format for new deployments.

#### Semantic Zoom Implementation

ExplorViz's semantic zoom is its flagship academic contribution, detailed in Hansen et al. (2025):

- **Approach:** Discrete Level-of-Detail (LoD). The graphical representation changes based on the virtual camera's Euclidean distance from visual objects.
- **9 distance-dependent visual changes:**
  1. Class height varies based on instance creation metrics
  2. Method meshes stack on classes (height = lines of code)
  3. Method meshes hide at distance
  4. Class label sizes adjust
  5. Labels shorten to prevent overlaps
  6. Communication line thickness changes
  7. Communication curvature adapts for visibility
  8. Communication and directional indicators hide based on request counts
  9. Packages close automatically, hiding inner classes and aggregating communication
- **Clustering for performance:** Uses k-Means or Mean Shift clustering to group objects. Distance calculations target cluster centroids instead of individual objects, reducing computational overhead for large landscapes.
- **Configuration:** Users configure cluster quantity and distance thresholds through the web interface.

The zoom levels map roughly to three conceptual tiers: landscape (systems, nodes, applications), application (packages, sub-packages), and class (classes, methods, communication). However, the implementation is continuous-discrete rather than strict 3-level; the 9 visual properties change independently at different distance thresholds.

**User study (n=16):** 15 of 16 participants preferred the semantic zoom version. Task completion time differences were statistically inconclusive due to high standard deviation (Hansen et al., 2025).

#### What ExplorViz Does Well

- **Academic rigor:** 30+ publications with controlled experiments. Fittkau et al. (2015) demonstrated a statistically significant 14% increase in task correctness with hierarchical landscape visualization vs. flat visualization.
- **Semantic zoom SOTA in academia:** The 9-property distance-dependent system with cluster centroid optimization is the most thoroughly studied semantic zoom implementation for software cities.
- **Real-time trace visualization:** Live OpenTelemetry span ingestion with dynamic city updates.
- **VR/AR support:** WebXR integration for immersive collaborative exploration (Krause-Glau et al., 2023).
- **Multi-device output:** Recent work on rendering across multiple visual output devices simultaneously (Hansen et al., 2024, IEEE VISSOFT).

#### Weaknesses

| Weakness | Detail |
|---|---|
| Heavy infrastructure | Requires Docker Compose with 11+ containers, Kafka, Neo4j. Cannot run without backend services. |
| Java-centric instrumentation | OpenTelemetry support is recent; historically tied to Kieker (Java-only). Non-Java ecosystems require manual OTel setup. |
| No static export | Visualization requires the full running backend. Cannot generate a standalone HTML/JS artifact. |
| No on-rails inference | Requires manual OpenTelemetry instrumentation or Kieker agents. Zero-config analysis does not exist. |
| Academic UX | Interface designed for research experiments, not production developer workflows. No breadcrumb navigation, no search with filters, no deep linking. |
| No code editing | Visualization is read-only. Cannot navigate from a 3D class representation to editable source code. |
| No AI agent | The ai-chat-service repository exists (0 stars, recent) but is not documented as a core feature. |
| No templates | Each visualization is derived from live traces. No template library for common architectures. |
| Limited adoption | Frontend repo: 6 GitHub stars. Primarily used within Kiel University research group. |

---

### 2. Backstage (closest: developer portal ecosystem)

**What it is:** An open-source framework for building internal developer portals, originally created at Spotify and donated to CNCF (Incubation level). It provides a software catalog, documentation system, and software templates unified through a plugin architecture.

**Website:** https://backstage.io | **GitHub:** https://github.com/backstage/backstage | **License:** Apache 2.0

#### Architecture

| Component | Technology |
|---|---|
| Frontend | React, TypeScript (94% of codebase), Material UI components |
| Backend | Node.js with the new Backend System (dependency injection, stable since Sep 2024) |
| Database | PostgreSQL (production), SQLite (development/testing), per-plugin logical database isolation via Knex |
| Cache | memory (dev), memcache, Redis, Valkey, or Infinispan (production) |
| Plugin system | Three types: standalone (browser-only), service backend (org APIs), third-party backend (SaaS proxy) |
| Build | Custom CLI build system with bundle optimization and plugin deduplication |

#### Key Metrics (as of Feb 2026)

| Metric | Value |
|---|---|
| GitHub stars | 32,700+ |
| Contributors | 1,851 |
| Commits | 71,276 |
| Latest release | v1.48.3 (2026-02-26) |
| Market share (IDP frameworks) | 89% (reported) |
| Organizations using | 3,400+ |
| Developers served | 2,000,000+ outside Spotify |
| Plugin ecosystem | Hundreds (CI/CD, monitoring, Kubernetes, incident management, cost controls) |

#### Entity Model (catalog-info.yaml)

Backstage uses a Kubernetes-inspired YAML descriptor format:

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: my-service
  description: My backend service
  tags: [python, grpc]
  annotations:
    github.com/project-slug: org/my-service
spec:
  type: service
  lifecycle: production
  owner: team-backend
  system: payments
  dependsOn:
    - resource:default/my-database
  providesApis:
    - my-api
```

Default entity kinds: Component, API, Resource, System, Domain, Group, User, Location. Extensible with custom kinds via plugins.

#### What Backstage Does Well

- **Massive ecosystem:** 1,851 contributors, hundreds of plugins, backed by Spotify with full-time engineering team. The network effect is unmatched in the developer portal space.
- **YAML declarative catalog:** `catalog-info.yaml` colocated with source code. Familiar Kubernetes-style manifests. Automatic discovery via repository scanning.
- **Plugin architecture:** Well-designed three-tier plugin system (standalone, service backend, third-party). The new Backend System (1.0, Sep 2024) provides clean dependency injection.
- **Software Templates:** Scaffolding system for creating new services with organizational best practices baked in.
- **TechDocs:** "Docs like code" -- Markdown documentation rendered and searchable within the portal.
- **CNCF backing:** Incubation-level project with governance, security audits, and long-term sustainability.
- **RAG AI plugin:** Recent addition enabling LLM-powered queries over the software catalog.

#### Weaknesses

| Weakness | Detail |
|---|---|
| Zero visualization | Entirely text and table-based. No graph view, no 3D, no spatial representation of systems. The catalog is a list, not a map. |
| No semantic zoom | No concept of LOD or progressive disclosure of architectural detail. |
| No code navigation | Cannot drill from catalog entry to source code lines. Links out to external code hosts. |
| Heavy infrastructure | Requires Node.js runtime, PostgreSQL for production, cache layer, container orchestration. Not embeddable. |
| Large bundle | Frontend bundles all plugins into one app bundle. With many plugins installed, bundle sizes grow significantly. Deduplication tooling (`yarn dedupe`) is recommended but manual. |
| Steep setup | Not a packaged service. Must use `@backstage/create-app`, configure database, authentication, and plugins. Operational overhead is substantial. |
| No static export | Requires running backend. Cannot produce standalone artifacts. |
| No on-rails inference | Catalog entries must be manually authored as YAML files or discovered via limited auto-ingestion plugins. |
| Maintenance burden | Plugin API changes require updates across all installed plugins. The legacy-to-new backend migration (completed Dec 2024) was a multi-year effort. |

#### Why We Are Different Despite Overlapping "Developer Tool" Space

Backstage answers "what services do we have and who owns them?" -- it is a **catalog** (registry + metadata). The Ontology Map Toolkit answers "how does this system look spatially, and how do its parts relate in 3D space?" -- it is a **map** (visual + navigable). These are complementary, not competing. Backstage could be an import source for the Ontology Map Toolkit (parse `catalog-info.yaml` into ontology nodes), but Backstage itself provides zero spatial understanding. A developer looking at a Backstage catalog with 500 services sees a paginated table; with the Ontology Map Toolkit, they see a navigable 3D landscape with semantic zoom.

---

### 3. cosmos.gl / Cosmograph (closest: large-scale graph performance)

**What it is:** A GPU-accelerated force-directed graph layout and rendering engine. cosmos.gl is the core open-source library (MIT license, OpenJS Foundation incubating project since May 2025). Cosmograph is the higher-level commercial product built on top of it, adding DuckDB analytics, SQL queries, clustering, and a cloud sharing service.

**Website:** https://cosmograph.app | **GitHub:** https://github.com/cosmosgl/graph | **License:** MIT (cosmos.gl core)

#### Architecture

| Component | Technology |
|---|---|
| Rendering | WebGL2 with custom GLSL fragment and vertex shaders (10.6% of codebase is GLSL) |
| Computation | All force calculations on GPU via shaders. CPU is freed entirely. Uses `EXT_float_blend` extension for Many-Body force. |
| Data format | Float32Array for positions (`[x1, y1, x2, y2, ...]`) and links. WebGL-native format, zero serialization overhead. |
| Language | TypeScript (78.3%), GLSL (10.6%), MDX (10.4%) |
| Build | Vite |
| Analytics (Cosmograph) | DuckDB (in-memory WASM), Mosaic cross-filtering, SQLRooms |

#### Performance

cosmos.gl's core value proposition is raw rendering speed through GPU-only computation:

| Benchmark | Source |
|---|---|
| 133K nodes, 321K edges | Demonstrated in Nightingale article (Rokotyan) |
| 475K nodes, 1M edges | Patient distribution dataset visualization |
| "Over one million nodes and links" | Official claim (OpenJS Foundation announcement, cosmograph.app docs) |
| Real-time force simulation | All computation in GPU shaders; CPU freed for other tasks |

**Creators:** Nikita Rokotyan (creator) and Olya Stukova (co-maintainer).

**v2.0 changes (2025):** New data structures with `setPointPositions(Float32Array)` and `setLinks(Float32Array)` replacing `setData()`. New clustering force via `setPointClusters()`. Point dragging. Improved data handling pipeline.

#### What cosmos.gl Does Well

- **Unmatched WebGL graph performance:** The only browser-based graph engine that handles 1M+ nodes with real-time force simulation. All other force-directed libraries (d3-force, sigma.js, vis.js) hit CPU bottlenecks at 10-50K nodes.
- **Pure GPU computation:** Fragment and vertex shaders handle both layout and rendering. No CPU-GPU data transfer bottleneck during simulation.
- **Clean, minimal API:** `setPointPositions`, `setLinks`, `render()`. Low surface area, easy to integrate.
- **OpenJS Foundation:** Institutional backing for long-term maintenance and governance.
- **Use cases:** Production deployments in biotech (protein similarity networks), financial fraud detection, and AI embedding visualization.

#### Weaknesses

| Weakness | Detail |
|---|---|
| 2D only | No 3D rendering. Flat plane with x,y coordinates only. |
| No semantic zoom | No LOD system. All nodes render at the same detail level regardless of zoom. At high zoom-out with 100K+ nodes, individual labels are illegible. |
| Circles only | Nodes are rendered as points/circles. No custom shapes, no icons, no rectangles for packages/modules. |
| No drill-down | Clicking a node returns an index (not an object). No concept of hierarchy, nesting, or fractal navigation. |
| No labels at scale | Label rendering is not part of the core engine. At 100K+ nodes, label placement is an unsolved problem in their stack. |
| Library, not framework | Provides a rendering engine, not an application framework. No templates, no import adapters, no configuration system. |
| No static export | Requires JavaScript runtime. Cannot produce a standalone image or self-contained HTML. |
| No code view | Graph nodes are abstract data points. No concept of mapping to source code files, functions, or classes. |
| No AI integration | Pure rendering library with no inference, analysis, or agent capabilities. |
| iOS compatibility | `EXT_float_blend` was dropped in iOS 15.4, breaking the Many-Body force simulation. Reportedly fixed in later iOS versions but remains a fragility. |

---

## Feature Comparison Matrix

Legend: checkmark = implemented, *italic* = planned/designed but not yet implemented.

| # | Feature | ExplorViz | Backstage | cosmos.gl | Ontology Map Toolkit |
|---|---|---|---|---|---|
| 1 | **3D rendering** | Yes (Three.js city metaphor) | No | No (2D WebGL only) | Yes (Three.js + InstancedMesh) |
| 2 | **Semantic zoom levels** | 9 distance-dependent properties (discrete LoD) | No | No | *Designed* (fractal drill-down F-06) |
| 3 | **Code drill-down** | No (read-only class view) | No (links to external code host) | No | *Designed* (F-06 L3-L4) |
| 4 | **On-rails inference** | No (requires OTel instrumentation) | No (manual YAML authoring) | No (manual data loading) | *Designed* (inference engine spec) |
| 5 | **Static export** | No (requires running backend) | No (requires running backend) | No (requires JS runtime) | *Designed* (INV-OT-002) |
| 6 | **Zero build step** | No (Docker Compose + 11 containers) | No (create-app + Node + PostgreSQL) | Partial (npm install + code) | Yes (CLI or npx) |
| 7 | **Plugin system** | Limited (Ember addons, legacy) | Yes (hundreds of plugins, 3-tier) | No | *Designed* (shape packs, import adapters) |
| 8 | **YAML catalog** | No | Yes (catalog-info.yaml, K8s-style) | No | Yes (cockpit_schema.yaml) |
| 9 | **10K+ nodes at 60fps** | Unverified (no published benchmarks) | N/A (no visualization) | Yes (100K+ nodes demonstrated) | *Target* (INV-OT-009, InstancedMesh + LOD) |
| 10 | **InstancedMesh rendering** | No (individual Three.js meshes) | N/A | N/A (WebGL points, not meshes) | *Designed* (performance benchmarks spec) |
| 11 | **Template library** | No | Yes (Software Templates for scaffolding) | No | *Designed* (8 architecture templates) |
| 12 | **Import adapters** | OpenTelemetry traces only | YAML + limited auto-discovery | Float32Array raw data | *Designed* (OpenAPI, GraphQL, etc.) |
| 13 | **AI agent integration** | Experimental (ai-chat-service, undocumented) | RAG AI plugin (recent) | No | *Designed* (F-15 BYOK agent) |
| 14 | **Time-travel / history** | Yes (trace replay, temporal navigation) | No (snapshots only) | No | *Designed* (F-09 sprint replay) |
| 15 | **Annotations** | No | Yes (entity annotations in YAML) | No | *Designed* (in-visualization annotations) |
| 16 | **Terminal mode** | No | No | No | *Designed* (F-18) |
| 17 | **Federation / multi-system** | Partial (landscape view shows multiple apps) | Yes (multi-org catalog, API) | No | *Designed* (F-19 federation) |
| 18 | **BYOK (Bring Your Own Key)** | No | No (managed AI only) | N/A | *Designed* (F-15 browser-direct) |
| 19 | **Accessibility (WCAG)** | Limited (VR focus, not WCAG-audited) | Partial (React + MUI a11y) | No (canvas-based, no DOM) | *Planned* (accessibility audit P0-P3) |
| 20 | **Bundle size (initial load)** | N/A (server-rendered) | Large (React + all plugins bundled) | ~100KB (core rendering engine) | <250KB target |
| 21 | **VSCode theme reuse** | No | No | No | *Designed* (F-21) |
| 22 | **Edge styling system** | Communication lines (thickness, curvature) | N/A | Lines with width/color | Yes (typed edges, colored) |
| 23 | **Breadcrumb navigation** | No | No | No | *Designed* (F-06) |
| 24 | **Deep linking** | No | Yes (URL-based entity routing) | No | *Designed* (F-32) |
| 25 | **Search with filters** | No | Yes (modular search, multi-source) | No | Yes (Cmd+K search) |
| 26 | **Sprint replay** | No | No | No | *Designed* (F-09) |
| 27 | **Custom shape packs** | No (fixed city metaphor: buildings + districts) | N/A | No (circles only) | Yes (26 shapes implemented) |
| 28 | **Embed mode** | No | No (full app only) | Yes (library embed) | *Designed* (F-22 embed) |
| 29 | **VR/AR support** | Yes (WebXR, flagship feature) | No | No | No (not planned for v1) |
| 30 | **Live runtime traces** | Yes (core feature, OTel ingestion) | No | No | No (static analysis only in v1) |
| 31 | **Collaborative editing** | Yes (multi-user VR sessions) | No (single-user portal) | No | *Planned* (v2) |

---

## Differentiation Summary

### What Each Competitor Does BETTER Than Us

**ExplorViz beats us on:**

- **Semantic zoom academic rigor.** 30+ publications with controlled experiments. Our semantic zoom is engineering-driven, not experimentally validated. Hansen et al. (2025) provides quantitative user study data we lack.
- **Live runtime trace visualization.** ExplorViz ingests OpenTelemetry spans in real-time and updates the 3D city dynamically. Our v1 is static-analysis-only; we cannot show runtime behavior.
- **VR/AR immersion.** WebXR support with multi-user collaborative VR sessions is a genuine differentiator for spatial comprehension research. We have no VR roadmap.
- **Clustering algorithm for LOD.** Their k-Means/Mean-Shift cluster centroid distance calculation is a proven optimization for large landscapes. Our LOD approach uses frustum culling and InstancedMesh but lacks published clustering benchmarks.

**Backstage beats us on:**

- **Ecosystem scale.** 32,700 stars, 1,851 contributors, 3,400+ organizations, CNCF governance. We are a new project with zero community. The plugin marketplace and network effects are a decade ahead.
- **Software catalog completeness.** The YAML entity model with kinds (Component, API, Resource, System, Domain, Group, User) is a mature, well-documented standard. Our ontology schema is newer and less battle-tested.
- **Software Templates.** Backstage's scaffolding system for creating new services with org best practices is a productivity feature we do not replicate.
- **TechDocs.** Integrated "docs like code" rendering is a proven feature with wide adoption that we do not offer.
- **Enterprise adoption.** Spotify, Netflix, HP, Expedia, and thousands of others in production. We have zero production deployments.

**cosmos.gl beats us on:**

- **Raw rendering performance.** 1M+ nodes with GPU-only force simulation is a benchmark we cannot match with Three.js InstancedMesh. WebGL2 shader-based computation avoids CPU-GPU transfer entirely.
- **Force-directed layout speed.** Their GPU-based force simulation converges in seconds for 100K+ nodes. Our layout engine is CPU-bound and will not match this for force-directed use cases.
- **Minimal footprint.** The core cosmos.gl engine is approximately 100KB. Our <250KB target includes substantially more functionality but is still larger for the pure rendering case.

### What We Do That NOBODY Else Does

1. **On-rails inference (zero-config).** Point at a codebase, get a 3D ontology map. No instrumentation, no YAML authoring, no manual data loading. ExplorViz requires OTel agents. Backstage requires catalog-info.yaml files. cosmos.gl requires Float32Array data. We require nothing.

2. **Semantic zoom to code.** Fractal drill-down from system landscape to package to module to function to line of code, all within the same 3D viewport. ExplorViz zooms to class level but cannot show code. Backstage has no visualization. cosmos.gl has no hierarchy.

3. **Static export.** Generate a self-contained HTML file that anyone can open in a browser without servers, databases, or runtimes. No competitor offers this. ExplorViz needs 11 Docker containers. Backstage needs Node + PostgreSQL. cosmos.gl needs a JavaScript application.

4. **Terminal mode.** Navigate the ontology map from a terminal. No competitor has a CLI-based visualization mode.

5. **Sprint replay.** Visualize how the codebase evolved across sprints or git history as a time-lapse through the 3D map. ExplorViz replays runtime traces (different concept). No other tool replays structural evolution.

6. **VSCode ecosystem reuse.** Themes, keybindings, and editor conventions from VSCode applied to the 3D visualization. No competitor leverages the VSCode ecosystem.

7. **BYOK AI agent.** Bring your own API key for any LLM provider. The agent understands the ontology and can answer questions about the system in context. Backstage has a managed RAG plugin (recent, limited). ExplorViz has an experimental undocumented chat service. cosmos.gl has nothing.

8. **Import adapter ecosystem with zero-build-step.** Parse OpenAPI, GraphQL, Terraform, Kubernetes manifests, Backstage catalog-info.yaml, and more into the ontology, all from a CLI with no build step. cosmos.gl is data-format-agnostic (manual). Backstage ingests only its own YAML format. ExplorViz only ingests OTel traces.

9. **<250KB initial load.** A complete 3D interactive visualization framework that loads faster than most marketing pages. ExplorViz is server-rendered (no bundle concept). Backstage bundles grow with each plugin. cosmos.gl core is ~100KB but provides only raw rendering, not a framework.

### The Unique Combination

No single feature above is entirely unprecedented in isolation. The genuine novelty is the **combination**: a sub-250KB framework that performs zero-config static analysis, renders a 3D ontology with semantic zoom down to code lines, exports to a self-contained HTML file, accepts input from 10+ adapter formats, integrates a BYOK AI agent, and runs in both browser and terminal -- without requiring any backend infrastructure.

Each competitor owns one piece of this space:
- ExplorViz owns **academic semantic zoom in 3D software cities**
- Backstage owns **developer portal ecosystem and catalog**
- cosmos.gl owns **GPU-accelerated large-scale graph rendering**

None of them combine spatial visualization + code navigation + zero-config inference + static export + AI agent + lightweight bundle. That intersection is unoccupied.

---

## References

### ExplorViz Papers

- Hansen, M., Bamberg, J., Baumann, N., Hasselbring, W. (2025). "Semantic Zoom and Mini-Maps for Software Cities." arXiv:2510.00003. https://arxiv.org/abs/2510.00003
- Hasselbring, W., Krause, A., Zirkelbach, C. (2020). "ExplorViz: Research on software visualization, comprehension and collaboration." Software Impacts, 6, 100034. https://doi.org/10.1016/j.simpa.2020.100034
- Fittkau, F., Krause, A., Hasselbring, W. (2017). "Software landscape and application visualization for system comprehension with ExplorViz." Information and Software Technology, 87, 259-277. https://doi.org/10.1016/j.infsof.2016.09.007
- Fittkau, F., Krause, A., Hasselbring, W. (2015). "Hierarchical Software Landscape Visualization for System Comprehension: A Controlled Experiment." IEEE VISSOFT. https://doi.org/10.1109/VISSOFT.2015.7332413
- Fittkau, F., Roth, S., Hasselbring, W. (2015). "ExplorViz: Visual Runtime Behavior Analysis of Enterprise Application Landscapes." ECIS 2015.
- Fittkau, F., Waller, J., Wulf, C., Hasselbring, W. (2013). "Live Trace Visualization for Comprehending Large Software Landscapes: The ExplorViz Approach." IEEE VISSOFT. https://doi.org/10.1109/VISSOFT.2013.6650536
- Krause-Glau, A., Hansen, M., Hasselbring, W. (2023). "Collaborative Program Comprehension in Extended Reality." Software Engineering.
- Hansen, M., Bielfeldt, H., Bernstetter, A., Kwasnitschka, T., Hasselbring, W. (2024). "A Software Visualization Approach for Multiple Visual Output Devices." IEEE VISSOFT. https://doi.org/10.1109/VISSOFT60929.2024.00015

### ExplorViz Sources

- Official site: https://explorviz.dev
- GitHub organization: https://github.com/ExplorViz (20 repositories)
- Frontend repo: https://github.com/ExplorViz/frontend (TypeScript, 6 stars)
- Persistence service: https://github.com/ExplorViz/persistence-service (Java, Neo4j)

### Backstage Sources

- Official site: https://backstage.io
- GitHub: https://github.com/backstage/backstage (32,700+ stars, Apache 2.0)
- Architecture overview: https://backstage.io/docs/overview/architecture-overview/
- Entity descriptor format: https://backstage.io/docs/features/software-catalog/descriptor-format/
- Plugin marketplace: https://backstage.io/plugins/
- Spotify for Backstage: https://backstage.spotify.com
- Roadie guide (2026): https://roadie.io/backstage-spotify/

### cosmos.gl / Cosmograph Sources

- Cosmograph docs: https://cosmograph.app/docs-general/
- cosmos.gl GitHub: https://github.com/cosmosgl/graph (MIT license)
- OpenJS Foundation announcement: https://openjsf.org/blog/introducing-cosmos-gl (May 2025)
- Nightingale article: https://nightingaledvs.com/how-to-visualize-a-graph-with-a-million-nodes/
- npm package: https://www.npmjs.com/package/@cosmograph/cosmos
- DeepWiki analysis: https://deepwiki.com/cosmograph-org/cosmos
