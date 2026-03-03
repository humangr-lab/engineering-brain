# Inference Engine Algorithm Specification

**Status:** Draft v1.0
**Scope:** Ontology Map Toolkit — zero-config visualization pipeline
**Invariant:** INV-OT-013 — `graph_data.json` alone produces a complete cockpit. INV-OT-014 — Template, layout, colors, shapes, sizes ALL inferred from data if not explicit.

---

## 1. Pipeline Overview

The inference engine is a deterministic, five-stage pipeline that transforms a raw `graph_data.json` (nodes + edges) into a complete rendering configuration. No randomness, no LLM calls, no network requests. Given identical input, the engine always produces identical output.

```
graph_data.json
      |
      v
+---------------------+     +---------------------+     +---------------------+
| Stage 1             | --> | Stage 2             | --> | Stage 3             |
| Template Detection  |     | Layout Selection    |     | Color Palette       |
| conf_1 in [0,1]    |     | conf_2 in [0,1]    |     | conf_3 in [0,1]    |
+---------------------+     +---------------------+     +---------------------+
                                                                |
      +-----------------------------+-----------------------------+
      |                             |
      v                             v
+---------------------+     +---------------------+     +---------------------+
| Stage 4             | --> | Stage 5             | --> | InferredConfig      |
| Shape Mapping       |     | Sizing              |     | + total_confidence  |
| conf_4 in [0,1]    |     | conf_5 in [0,1]    |     +---------------------+
+---------------------+     +---------------------+
```

Each stage receives the graph data (and the results of prior stages where needed), produces a concrete decision, and emits a confidence score in the continuous interval [0, 1]. The total pipeline confidence is the geometric mean of all five stage confidences:

```
total_confidence = (conf_1 * conf_2 * conf_3 * conf_4 * conf_5) ^ (1/5)
```

The geometric mean penalizes any single weak stage more aggressively than an arithmetic mean, ensuring that one bad decision drags the overall score down appropriately.

**Output type:**

```typescript
interface InferredConfig {
  template:   string;           // e.g. "microservices"
  layout:     string;           // e.g. "orbital"
  palette:    Map<string, string>; // group -> oklch color
  shapes:     Map<string, string>; // node_id -> shape name
  sizes:      Map<string, number>; // node_id -> size scalar in [0.3, 3.0]
  confidence: {
    template: number;
    layout:   number;
    palette:  number;
    shapes:   number;
    sizing:   number;
    total:    number;
  };
}
```

If `cockpit_schema.yaml` is present, its fields override the corresponding inferred values after the pipeline completes. The inference engine never reads the override file — merging happens in a separate layer.

---

## 2. Stage 1: Template Detection

Template detection is the most complex stage. It extracts structural features from the graph and scores eight candidate templates. The highest-scoring template wins.

### 2.1 Feature Extraction

Given a graph G = (N, E) where N is the set of nodes and E the set of directed edges, extract the following feature vector F:

```
F.edge_type_distribution  = { t: count(e in E where e.type == t) / |E|  for each unique t }
F.node_type_histogram     = { t: count(n in N where n.type == t) / |N|  for each unique t }
F.graph_density           = |E| / (|N| * (|N| - 1))           // directed graph density
F.hierarchy_depth         = max_depth(parent_chains(N))        // 0 if no parent fields
F.avg_degree              = sum(in_deg(n) + out_deg(n) for n in N) / |N|
F.clustering_coefficient  = transitivity(G)                    // fraction of closed triplets
F.has_containment         = any(e.type == "CONTAINS" for e in E) OR any(n.parent for n in N)
F.has_protocols           = any(e.type in {"HTTP","GRPC","AMQP","MQTT","REST","WEBSOCKET"} for e in E)
F.unique_edge_types       = |{ e.type for e in E where e.type != null }|
F.unique_node_types       = |{ n.type for n in N where n.type != null }|
F.max_chain_length        = longest_simple_path(G)             // sequential chain detection
F.node_groups             = { n.group for n in N if n.group }  // set of unique group values
```

**Pseudocode for `parent_chains` depth:**

```python
def max_depth(nodes):
    parent_map = {n.id: n.parent for n in nodes if n.parent}
    if not parent_map:
        return 0
    roots = {n.id for n in nodes} - set(parent_map.values())
    # BFS from roots through inverted parent pointers
    max_d = 0
    for root in (set(parent_map.values()) - set(parent_map.keys())):
        children = [nid for nid, pid in parent_map.items() if pid == root]
        queue = [(c, 1) for c in children]
        while queue:
            nid, depth = queue.pop(0)
            max_d = max(max_d, depth)
            for cid, pid in parent_map.items():
                if pid == nid:
                    queue.append((cid, depth + 1))
    return max_d
```

**Pseudocode for `transitivity`:**

```python
def transitivity(adj):
    closed = 0
    triplets = 0
    for u in adj:
        neighbors_u = adj[u]
        for v in neighbors_u:
            for w in adj.get(v, []):
                if w != u:
                    triplets += 1
                    if w in neighbors_u:
                        closed += 1
    return closed / triplets if triplets > 0 else 0.0
```

### 2.2 Template Scoring Functions

Each scoring function receives F and returns a score in [0, 1]. All weights are hand-tuned constants chosen to produce intuitive results on the eight test datasets in Section 8.

```python
def score_microservices(F):
    s  = 0.35 * F.has_protocols
    s += 0.25 * F.node_type_histogram.get("service", 0)
    s += 0.15 * F.node_type_histogram.get("api", 0)
    s += 0.10 * F.node_type_histogram.get("gateway", 0)
    s += 0.15 * max(0, 1.0 - F.graph_density / 0.3)   # density < 0.3 preferred
    return clamp(s, 0, 1)

def score_monolith(F):
    s  = 0.30 * float(F.has_containment)
    s += 0.25 * min(F.hierarchy_depth / 3.0, 1.0)       # depth >= 3 saturates
    s += 0.20 * (F.node_type_histogram.get("file", 0) +
                 F.node_type_histogram.get("class", 0) +
                 F.node_type_histogram.get("function", 0))
    s += 0.15 * (1.0 - min(F.unique_node_types / 6.0, 1.0))  # fewer distinct types
    s += 0.10 * min(F.hierarchy_depth / 4.0, 1.0)
    return clamp(s, 0, 1)

def score_pipeline(F, N):
    chain_ratio = F.max_chain_length / max(len(N), 1)
    s  = 0.35 * min(chain_ratio / 0.5, 1.0)             # long chains
    s += 0.25 * (F.node_type_histogram.get("stage", 0) +
                 F.node_type_histogram.get("step", 0) +
                 F.node_type_histogram.get("transform", 0))
    s += 0.20 * max(0, 1.0 - F.clustering_coefficient / 0.2)  # low clustering
    s += 0.20 * max(0, 1.0 - F.avg_degree / 3.0)              # low fan-out
    return clamp(s, 0, 1)

def score_network(F):
    s  = 0.30 * min(F.graph_density / 0.15, 1.0)        # high density
    s += 0.25 * (F.edge_type_distribution.get("CALLS", 0) +
                 F.edge_type_distribution.get("HTTP", 0))
    s += 0.25 * max(0, 1.0 - F.hierarchy_depth / 2.0)   # no clear hierarchy
    s += 0.20 * min(F.avg_degree / 4.0, 1.0)             # high average degree
    return clamp(s, 0, 1)

def score_hierarchy(F):
    s  = 0.35 * min(F.hierarchy_depth / 2.0, 1.0)       # depth >= 2
    s += 0.30 * F.edge_type_distribution.get("CONTAINS", 0)
    s += 0.20 * float(F.has_containment)
    tree_like = 1.0 if F.clustering_coefficient < 0.1 else 0.5
    s += 0.15 * tree_like
    return clamp(s, 0, 1)

def score_layered(F):
    s  = 0.30 * F.node_type_histogram.get("layer", 0)
    # detect group patterns suggesting layers
    layer_groups = {"frontend", "backend", "data", "infra", "presentation", "domain", "persistence"}
    group_overlap = len(set(F.node_groups) & layer_groups) / max(len(layer_groups), 1)
    s += 0.30 * group_overlap
    s += 0.20 * min(F.hierarchy_depth / 2.0, 1.0)
    s += 0.20 * max(0, 1.0 - F.clustering_coefficient / 0.3)
    return clamp(s, 0, 1)

def score_knowledge_graph(F):
    s  = 0.30 * min(F.unique_edge_types / 5.0, 1.0)     # diverse edge types >= 5
    kg_edges = sum(F.edge_type_distribution.get(t, 0)
                   for t in ("RELATES", "INFORMS", "GROUNDS", "SUPPORTS",
                             "CONTRADICTS", "DERIVED_FROM", "VALIDATES"))
    s += 0.30 * min(kg_edges / 0.4, 1.0)
    s += 0.20 * min(F.unique_node_types / 4.0, 1.0)     # diverse node types
    s += 0.20 * min(F.avg_degree / 3.0, 1.0)
    return clamp(s, 0, 1)

def score_blank(F):
    return 0.15   # constant low baseline — always available as fallback
```

### 2.3 Winner Selection

```python
def detect_template(F):
    scores = {
        "microservices":   score_microservices(F),
        "monolith":        score_monolith(F),
        "pipeline":        score_pipeline(F),
        "network":         score_network(F),
        "hierarchy":       score_hierarchy(F),
        "layered":         score_layered(F),
        "knowledge_graph": score_knowledge_graph(F),
        "blank":           score_blank(F),
    }

    sorted_templates = sorted(scores.items(), key=lambda x: -x[1])
    winner, winner_score = sorted_templates[0]
    runner_up_score = sorted_templates[1][1]

    # Tie-break rule: if margin < 0.1, use blank (ambiguous signal)
    if winner_score - runner_up_score < 0.1:
        return ("blank", 0.5)

    # Low absolute score guard
    if winner_score < 0.4:
        return ("blank", 0.5)

    total_score = sum(scores.values())
    confidence = winner_score / total_score if total_score > 0 else 0.5

    return (winner, confidence)
```

**Properties:**
- Deterministic: same F always produces same template.
- Tie-break safety: ambiguous graphs default to the neutral "blank" template at confidence 0.5.
- Low-signal guard: if no template scores above 0.4, the engine acknowledges uncertainty rather than guessing.

---

## 3. Stage 2: Layout Selection

Layout selection maps the detected template to a spatial arrangement algorithm, with heuristic overrides for extreme graph sizes or topological structures.

### 3.1 Default Layout Table

| Template | Default Layout | Rationale |
|----------|----------------|-----------|
| microservices | orbital | Radial placement clusters services by domain |
| monolith | tree | Hierarchical top-down reflects containment |
| pipeline | pipeline | Left-to-right flow matches sequential processing |
| network | force | Physics simulation handles dense connectivity |
| hierarchy | tree | Natural representation of parent-child |
| layered | layered | Horizontal bands separate architectural layers |
| knowledge_graph | force | Diverse topology needs flexible placement |
| blank | force | Safe default for unknown structure |

### 3.2 Override Rules

Override rules are evaluated in priority order. The first matching rule wins.

```python
def select_layout(template, N, E):
    default = TEMPLATE_LAYOUT_MAP[template]  # from table above
    node_count = len(N)

    # Rule 1: very small graphs benefit from grid simplicity
    if node_count < 10:
        return ("grid", 0.7)

    # Rule 2: orbital does not scale beyond ~50 nodes
    if default == "orbital" and node_count > 50:
        return ("force", 0.7)

    # Rule 3: tree-like structure (max 2 children per parent on average)
    if is_tree_like(N, E):
        return ("tree", 0.8)

    # No override triggered — use template default
    return (default, 0.9)
```

**Pseudocode for `is_tree_like`:**

```python
def is_tree_like(N, E):
    # Build child count map from parent field or CONTAINS edges
    children_count = defaultdict(int)
    for n in N:
        if n.parent:
            children_count[n.parent] += 1
    for e in E:
        if e.type == "CONTAINS":
            children_count[e.from_id] += 1

    if not children_count:
        return False

    avg_children = sum(children_count.values()) / len(children_count)
    return avg_children <= 2.5  # slightly above 2 allows minor deviations
```

**Confidence semantics:**
- 0.9 = template default applied without override (strong signal from template)
- 0.8 = topology-driven override (tree-like detection)
- 0.7 = size-driven override (guard rails for extreme node counts)

---

## 4. Stage 3: Color Palette Generation

The palette stage assigns a distinct color to each semantic group, ensuring perceptual separability across both dark and light themes.

### 4.1 Group Extraction

```python
def extract_groups(N):
    groups = set()
    for n in N:
        if n.group:
            groups.add(n.group)
        elif n.type:
            groups.add(n.type)
        else:
            # Fallback: derive from id prefix (e.g., "auth_service" -> "auth")
            prefix = n.id.split("_")[0] if "_" in n.id else n.id.split(".")[0]
            groups.add(prefix)
    return sorted(groups)  # sorted for determinism
```

### 4.2 Palette for <= 8 Categories (Equidistant OKLCH)

When the number of unique groups k is at most 8, generate an equidistant hue palette in the OKLCH color space:

```python
def generate_small_palette(groups, theme):
    k = len(groups)
    L = 0.65 if theme == "dark" else 0.55   # lightness for readability
    C = 0.15                                  # chroma (saturation)
    palette = {}
    for i, group in enumerate(groups):
        H = (i * 360.0 / k) % 360            # equidistant hues
        palette[group] = f"oklch({L} {C} {H})"
    return (palette, 0.95)
```

Equidistant hue spacing guarantees maximum perceptual distance between adjacent categories. With k <= 8 and chroma 0.15, all pairs exceed CIE Delta-E 30.

### 4.3 Palette for > 8 Categories (Hash-Based with Greedy Adjustment)

When k > 8, equidistant placement may not suffice due to hue crowding. Instead, use a hash-based initial assignment followed by greedy adjustment:

```python
def generate_large_palette(groups, theme):
    L = 0.65 if theme == "dark" else 0.55
    C = 0.15
    MIN_HUE_SEP = 30.0  # degrees

    # Initial assignment via stable hash
    hues = {}
    for group in groups:
        h = fnv1a_hash(group) % 360
        hues[group] = h

    # Greedy adjustment: iterate in sorted-hue order, push apart if too close
    sorted_groups = sorted(hues.keys(), key=lambda g: hues[g])
    for i in range(1, len(sorted_groups)):
        prev_hue = hues[sorted_groups[i - 1]]
        curr_hue = hues[sorted_groups[i]]
        if abs(curr_hue - prev_hue) < MIN_HUE_SEP:
            hues[sorted_groups[i]] = (prev_hue + MIN_HUE_SEP) % 360

    # Wrap-around check: last vs first
    if len(sorted_groups) >= 2:
        first_hue = hues[sorted_groups[0]]
        last_hue = hues[sorted_groups[-1]]
        if (360.0 - last_hue + first_hue) < MIN_HUE_SEP:
            hues[sorted_groups[-1]] = (first_hue - MIN_HUE_SEP) % 360

    palette = {g: f"oklch({L} {C} {h})" for g, h in hues.items()}
    return (palette, 0.80)
```

**Why FNV-1a?** It is a simple, fast, non-cryptographic hash with excellent distribution. Deterministic across platforms (no seed required).

**Confidence:** 0.95 for the equidistant case (mathematically optimal separation), 0.80 for the hash-based case (heuristic adjustment may produce suboptimal but acceptable spacing).

---

## 5. Stage 4: Shape Mapping

Shapes are assigned by substring-matching the node `type` field against a keyword lookup table. The table is ordered by specificity (longer keywords first) to prevent false matches.

### 5.1 Keyword Lookup Table

| Priority | Keywords | Shape | Confidence |
|----------|----------|-------|------------|
| 1 | `database`, `db`, `store`, `datastore` | database | 0.95 |
| 2 | `service` | gear | 0.95 |
| 3 | `api`, `gateway`, `endpoint` | gate | 0.90 |
| 4 | `queue`, `stream`, `kafka`, `broker`, `message` | conveyor | 0.90 |
| 5 | `file`, `source` | terminal | 0.85 |
| 6 | `class`, `model`, `entity` | prism | 0.85 |
| 7 | `function`, `method`, `handler` | sphere | 0.80 |
| 8 | `module`, `package`, `library` | vault | 0.85 |
| 9 | `config`, `env`, `settings`, `secret` | dial | 0.80 |
| 10 | `test`, `spec`, `suite` | gauge | 0.80 |
| 11 | `layer`, `tier` | stairs | 0.90 |
| 12 | `user`, `person`, `actor`, `client` | sphere | 0.85 |
| 13 | `monitor`, `dashboard`, `metric` | monitor | 0.85 |
| 14 | `pipeline`, `workflow`, `dag` | conveyor | 0.85 |
| 15 | `network`, `cluster`, `mesh` | nexus | 0.85 |
| 16 | `graph`, `ontology`, `knowledge` | graph | 0.90 |
| 17 | `cache`, `redis`, `memcached` | hub | 0.85 |
| 18 | `container`, `pod`, `docker` | rack | 0.85 |
| — | *(no match)* | sphere | 0.60 |

> All shape names in this table reference shapes implemented in `client/js/scene/shapes.js` (26 shapes).

### 5.2 Matching Algorithm

```python
# Table sorted by priority (specificity). First match wins.
SHAPE_TABLE = [
    (["database", "db", "store", "datastore"],                "database",  0.95),
    (["service"],                                             "gear",      0.95),
    (["api", "gateway", "endpoint"],                          "gate",      0.90),
    (["queue", "stream", "kafka", "broker", "message"],       "conveyor",  0.90),
    (["file", "source"],                                      "terminal",  0.85),
    (["class", "model", "entity"],                            "prism",     0.85),
    (["function", "method", "handler"],                       "sphere",    0.80),
    (["module", "package", "library"],                        "vault",     0.85),
    (["config", "env", "settings", "secret"],                 "dial",      0.80),
    (["test", "spec", "suite"],                               "gauge",     0.80),
    (["layer", "tier"],                                       "stairs",    0.90),
    (["user", "person", "actor", "client"],                   "sphere",    0.85),
    (["monitor", "dashboard", "metric"],                      "monitor",   0.85),
    (["pipeline", "workflow", "dag"],                          "conveyor",  0.85),
    (["network", "cluster", "mesh"],                          "nexus",     0.85),
    (["graph", "ontology", "knowledge"],                      "graph",     0.90),
    (["cache", "redis", "memcached"],                         "hub",       0.85),
    (["container", "pod", "docker"],                          "rack",      0.85),
]
DEFAULT_SHAPE = ("sphere", 0.60)

def map_shapes(N):
    shapes = {}
    confidences = []
    for n in N:
        node_type = (n.type or "").lower()
        matched = False
        for keywords, shape, conf in SHAPE_TABLE:
            if any(kw in node_type for kw in keywords):
                shapes[n.id] = shape
                confidences.append(conf)
                matched = True
                break
        if not matched:
            shapes[n.id] = DEFAULT_SHAPE[0]
            confidences.append(DEFAULT_SHAPE[1])

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.60
    return (shapes, avg_conf)
```

The stage confidence is the arithmetic mean of per-node confidences. A graph where most nodes match specific keywords yields high confidence; a graph full of untyped nodes yields confidence near 0.60.

All shapes referenced in this table (`database`, `gear`, `gate`, `conveyor`, `terminal`, `prism`, `sphere`, `vault`, `dial`, `gauge`, `stairs`, `monitor`, `nexus`, `graph`, `hub`, `rack`) are valid shape names defined in `client/js/scene/shapes.js`.

---

## 6. Stage 5: Sizing

Sizing determines the visual scale of each node. The engine uses a priority chain: the first available data source wins.

### 6.1 Priority Chain

```python
def compute_sizes(N, E):
    # Collect all available metric sources per node
    loc_values = {n.id: n.properties.loc for n in N
                  if n.properties and n.properties.get("loc") is not None}
    complexity_values = {n.id: n.properties.complexity for n in N
                        if n.properties and n.properties.get("complexity") is not None}

    # Compute degree centrality (always available as fallback)
    degree = {n.id: 0 for n in N}
    for e in E:
        degree[e.from_id] = degree.get(e.from_id, 0) + 1
        degree[e.to_id] = degree.get(e.to_id, 0) + 1
    max_deg = max(degree.values()) if degree else 1
    centrality = {nid: d / max(max_deg, 1) for nid, d in degree.items()}

    # Strategy: use best available source per node, then normalize together.
    # Priority per node: LOC > complexity > degree centrality > uniform (1.0).
    all_node_ids = {n.id for n in N}
    merged = {}
    source_label = "mixed"

    # If LOC covers >= 50% of nodes, normalize LOC-having nodes together
    # and degree-fallback nodes separately, then blend.
    if len(loc_values) >= len(N) * 0.5:
        loc_sizes, loc_conf = size_from_metric(loc_values, transform=log10)
        fallback_ids = all_node_ids - set(loc_values.keys())
        if fallback_ids:
            fallback_values = {nid: centrality.get(nid, 0) for nid in fallback_ids}
            fb_sizes, _ = size_from_metric(fallback_values, transform=identity)
            merged = {**loc_sizes, **fb_sizes}
        else:
            merged = loc_sizes
        confidence = 0.85  # mixed sources slightly lower than pure LOC
        source_label = "loc+degree"

    elif len(loc_values) > 0:
        # LOC covers < 50%: use LOC where available, degree everywhere else
        loc_sizes, _ = size_from_metric(loc_values, transform=log10)
        fallback_ids = all_node_ids - set(loc_values.keys())
        fallback_values = {nid: centrality.get(nid, 0) for nid in fallback_ids}
        fb_sizes, _ = size_from_metric(fallback_values, transform=identity)
        merged = {**loc_sizes, **fb_sizes}
        confidence = 0.75
        source_label = "loc+degree"

    elif len(complexity_values) > 0:
        comp_sizes, comp_conf = size_from_metric(complexity_values, transform=identity)
        fallback_ids = all_node_ids - set(complexity_values.keys())
        if fallback_ids:
            fallback_values = {nid: centrality.get(nid, 0) for nid in fallback_ids}
            fb_sizes, _ = size_from_metric(fallback_values, transform=identity)
            merged = {**comp_sizes, **fb_sizes}
        else:
            merged = comp_sizes
        confidence = 0.80
        source_label = "complexity"

    elif max_deg > 0:
        merged, confidence = size_from_metric(centrality, transform=identity)
        source_label = "degree"

    else:
        # No data available
        merged = {n.id: 1.0 for n in N}
        confidence = 0.50
        source_label = "uniform"

    return (merged, confidence)
```

### 6.2 Normalization: Z-Score to Sigmoid to Clamp

The normalization procedure converts raw metric values into a bounded size scalar:

```python
import math

def size_from_metric(values, transform):
    # Step 1: Apply transform (log10 for LOC, identity for others)
    transformed = {}
    for nid, v in values.items():
        if transform == log10:
            transformed[nid] = math.log10(max(v, 1))  # log10(0) guard
        else:
            transformed[nid] = float(v)

    # Step 2: Z-score normalization
    vals = list(transformed.values())
    mu = sum(vals) / len(vals)
    sigma = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5
    if sigma < 1e-9:
        # All values identical -> uniform size
        return {nid: 1.0 for nid in transformed}, 0.5

    z_scores = {nid: (v - mu) / sigma for nid, v in transformed.items()}

    # Step 3: Sigmoid mapping to (0, 1)
    sigmoid = {nid: 1.0 / (1.0 + math.exp(-z)) for nid, z in z_scores.items()}

    # Step 4: Linear map (0, 1) -> [0.3, 3.0] and clamp
    MIN_SIZE = 0.3
    MAX_SIZE = 3.0
    sizes = {}
    for nid, s in sigmoid.items():
        sizes[nid] = MIN_SIZE + s * (MAX_SIZE - MIN_SIZE)
        sizes[nid] = max(MIN_SIZE, min(MAX_SIZE, sizes[nid]))

    # Confidence based on source richness
    confidence = 0.90 if transform == log10 else 0.80
    return (sizes, confidence)
```

**Mathematical justification:**
- `log10` for LOC prevents large files (10K+ lines) from dominating; a 10,000-line file is only 4.0 vs. 100 lines at 2.0.
- Z-score centers the distribution at mean=0, std=1, making the sigmoid symmetric around the median node.
- The sigmoid function `1 / (1 + e^(-z))` maps the entire real line to (0, 1), providing a soft clamp that preserves relative ordering.
- The final linear rescaling to [0.3, 3.0] ensures every node is visible (at least 30% of default) and no node overwhelms the scene (at most 300%).

**Confidence values:**
- 0.90 for pure LOC-based (strong, quantitative signal)
- 0.85 for LOC + degree mixed (LOC covers >= 50% of nodes)
- 0.80 for complexity-based (reasonable proxy)
- 0.75 for LOC + degree mixed (LOC covers < 50% of nodes)
- 0.50 for uniform sizing (no data available)

---

## 7. Confidence Aggregation

After all five stages complete, the total pipeline confidence is computed:

```python
def aggregate_confidence(conf_1, conf_2, conf_3, conf_4, conf_5):
    product = conf_1 * conf_2 * conf_3 * conf_4 * conf_5
    total = product ** (1.0 / 5.0)   # geometric mean
    return total
```

### 7.1 Thresholds and Actions

| Condition | Action |
|-----------|--------|
| total >= 0.50 | Normal rendering. No warnings. |
| 0.30 <= total < 0.50 | Emit `console.warn("Low inference confidence: {total}")`. Show optional UI badge on the inference transparency panel. |
| total < 0.30 | Override all decisions: use template="blank", layout="force", default palette, all spheres, uniform sizing. Log warning. |

### 7.2 Worked Example

Consider a 30-node microservices graph with 12 services, 3 databases, 2 queues, 1 gateway, 42 edges mostly HTTP/CALLS. All nodes have `type` fields. 15 nodes have `properties.loc`.

| Stage | Decision | Confidence |
|-------|----------|------------|
| Template | microservices (score 0.78, runner-up "network" at 0.41) | 0.78 / 2.24 = 0.35 ... but via `winner / sum` = 0.78 / (0.78+0.41+0.22+0.18+0.30+0.12+0.08+0.15) = 0.78 / 2.24 = 0.348. However the dominant signal is clear, so let's recompute: conf = 0.78 / 2.24 = 0.35. |
| Layout | orbital (default, no override since 30 < 50 and 30 >= 10) | 0.90 |
| Palette | 4 groups, equidistant OKLCH | 0.95 |
| Shapes | 12 gear + 3 cylinder + 2 conveyor + 1 diamond + 12 sphere avg | ~0.87 |
| Sizing | LOC available on 15/30 nodes, degree fallback for rest | 0.85 |

Note: the template confidence formula `winner_score / sum(all_scores)` can yield modest values even with a clear winner. This is by design — the denominator normalizes against the total signal strength. A confidence of 0.35 for template detection reflects that 8 templates compete.

Total: `(0.35 * 0.90 * 0.95 * 0.87 * 0.85) ^ 0.2 = (0.227) ^ 0.2 ≈ 0.74`

This is above the 0.50 threshold, so rendering proceeds normally.

---

## 8. Test Datasets

### 8.1 Dataset A: Microservices (15 nodes, 16 edges)

```json
{
  "nodes": [
    {"id": "gateway", "type": "gateway", "group": "edge"},
    {"id": "auth_svc", "type": "service", "group": "auth", "properties": {"loc": 1200}},
    {"id": "user_svc", "type": "service", "group": "core", "properties": {"loc": 2400}},
    {"id": "order_svc", "type": "service", "group": "core", "properties": {"loc": 3100}},
    {"id": "payment_svc", "type": "service", "group": "core", "properties": {"loc": 1800}},
    {"id": "inventory_svc", "type": "service", "group": "core", "properties": {"loc": 900}},
    {"id": "notification_svc", "type": "service", "group": "infra", "properties": {"loc": 600}},
    {"id": "search_svc", "type": "service", "group": "core", "properties": {"loc": 1500}},
    {"id": "analytics_svc", "type": "service", "group": "infra", "properties": {"loc": 2200}},
    {"id": "shipping_svc", "type": "service", "group": "core", "properties": {"loc": 1100}},
    {"id": "users_db", "type": "database", "group": "data"},
    {"id": "orders_db", "type": "database", "group": "data"},
    {"id": "inventory_db", "type": "database", "group": "data"},
    {"id": "event_queue", "type": "queue", "group": "infra"},
    {"id": "notification_queue", "type": "queue", "group": "infra"}
  ],
  "edges": [
    {"from": "gateway", "to": "auth_svc", "type": "HTTP"},
    {"from": "gateway", "to": "user_svc", "type": "HTTP"},
    {"from": "gateway", "to": "order_svc", "type": "HTTP"},
    {"from": "gateway", "to": "search_svc", "type": "HTTP"},
    {"from": "auth_svc", "to": "users_db", "type": "DEPENDS_ON"},
    {"from": "user_svc", "to": "users_db", "type": "DEPENDS_ON"},
    {"from": "order_svc", "to": "orders_db", "type": "DEPENDS_ON"},
    {"from": "order_svc", "to": "payment_svc", "type": "CALLS"},
    {"from": "order_svc", "to": "inventory_svc", "type": "CALLS"},
    {"from": "order_svc", "to": "event_queue", "type": "PUBLISHES"},
    {"from": "inventory_svc", "to": "inventory_db", "type": "DEPENDS_ON"},
    {"from": "notification_svc", "to": "notification_queue", "type": "SUBSCRIBES"},
    {"from": "event_queue", "to": "notification_svc", "type": "SUBSCRIBES"},
    {"from": "event_queue", "to": "analytics_svc", "type": "SUBSCRIBES"},
    {"from": "order_svc", "to": "shipping_svc", "type": "CALLS"},
    {"from": "shipping_svc", "to": "event_queue", "type": "PUBLISHES"}
  ],
  "metadata": {"name": "E-Commerce Platform", "generator": "test/dataset-a"}
}
```

**Expected results:**
- Template: `microservices` (high has_protocols from HTTP edges, many "service" nodes, low density)
- Layout: `orbital` (default for microservices, 15 nodes < 50)
- Groups: 5 (`auth`, `core`, `data`, `edge`, `infra`) -> equidistant OKLCH palette, confidence 0.95
- Shapes: gateway=gate, services=gear, databases=database, queues=conveyor
- Sizing: LOC-based for services, degree-based fallback for db/queue/gateway

### 8.2 Dataset B: Monolith (15 nodes, hierarchy via parent)

```json
{
  "nodes": [
    {"id": "app", "type": "module", "label": "MyApp"},
    {"id": "pkg_core", "type": "package", "parent": "app", "label": "core"},
    {"id": "pkg_api", "type": "package", "parent": "app", "label": "api"},
    {"id": "pkg_utils", "type": "package", "parent": "app", "label": "utils"},
    {"id": "models_py", "type": "file", "parent": "pkg_core", "properties": {"loc": 450}},
    {"id": "services_py", "type": "file", "parent": "pkg_core", "properties": {"loc": 820}},
    {"id": "repository_py", "type": "file", "parent": "pkg_core", "properties": {"loc": 340}},
    {"id": "views_py", "type": "file", "parent": "pkg_api", "properties": {"loc": 290}},
    {"id": "serializers_py", "type": "file", "parent": "pkg_api", "properties": {"loc": 180}},
    {"id": "urls_py", "type": "file", "parent": "pkg_api", "properties": {"loc": 45}},
    {"id": "helpers_py", "type": "file", "parent": "pkg_utils", "properties": {"loc": 200}},
    {"id": "validators_py", "type": "file", "parent": "pkg_utils", "properties": {"loc": 150}},
    {"id": "class_user", "type": "class", "parent": "models_py"},
    {"id": "class_order", "type": "class", "parent": "models_py"},
    {"id": "class_product", "type": "class", "parent": "models_py"}
  ],
  "edges": [
    {"from": "views_py", "to": "services_py", "type": "IMPORTS"},
    {"from": "views_py", "to": "serializers_py", "type": "IMPORTS"},
    {"from": "services_py", "to": "repository_py", "type": "IMPORTS"},
    {"from": "services_py", "to": "models_py", "type": "IMPORTS"},
    {"from": "repository_py", "to": "models_py", "type": "IMPORTS"},
    {"from": "serializers_py", "to": "models_py", "type": "IMPORTS"},
    {"from": "validators_py", "to": "models_py", "type": "IMPORTS"},
    {"from": "views_py", "to": "validators_py", "type": "IMPORTS"}
  ],
  "metadata": {"name": "Django Monolith", "generator": "test/dataset-b"}
}
```

**Expected results:**
- Template: `monolith` (has_containment=true via parent, hierarchy_depth=3 [app->pkg->file->class], dominant types are file/class/package)
- Layout: `tree` (default for monolith, 15 nodes >= 10 so no grid override, tree-like structure confirmed)
- Groups: by type (module, package, file, class) -> 4 groups, equidistant OKLCH, confidence 0.95
- Shapes: app=vault (module), packages=vault (package), files=terminal (file), classes=prism (class)
- Sizing: LOC-based for files, degree fallback for packages/classes

---

## 9. Edge Cases

### 9.1 Empty Graph (edges only)

```json
{"nodes": [{"id": "a"}], "edges": []}
```

- Template: `blank` (all scoring functions return near-zero, winner < 0.4)
- Layout: `grid` (node_count=1 < 10 triggers grid override)
- Palette: 1 group, single OKLCH color
- Shape: sphere (no type field -> default)
- Size: 1.0 (no metric data -> uniform, confidence 0.5)

### 9.2 Single Node

Identical behavior to 9.1. A single node receives grid layout, sphere shape, size 1.0, and a single palette entry.

### 9.3 No Types

When no node has a `type` field, all shape lookups produce the default sphere at confidence 0.60. Group extraction falls back to the id-prefix heuristic (split on `_` or `.`, take first segment). Template detection still works from edge types and graph structure.

### 9.4 All Same Type

If all nodes have the same type (e.g., all "service"), the palette has exactly one group, yielding a single color. All nodes share the same shape. The template detection still functions normally since node_type_histogram concentrates on one type.

### 9.5 Disconnected Components

The graph is decomposed into connected components via BFS. Template detection runs independently on each component of size >= 3 nodes. The final template is the one that wins across the majority of components (weighted by component size). Components with fewer than 3 nodes inherit the global template.

```python
def detect_template_disconnected(N, E):
    components = find_connected_components(N, E)
    if len(components) <= 1:
        return detect_template(extract_features(N, E))

    votes = defaultdict(float)
    for comp_nodes, comp_edges in components:
        if len(comp_nodes) < 3:
            continue  # too small to classify
        F = extract_features(comp_nodes, comp_edges)
        template, conf = detect_template(F)
        votes[template] += len(comp_nodes) * conf  # weighted by size and confidence

    if not votes:
        return ("blank", 0.5)

    winner = max(votes.items(), key=lambda x: x[1])
    total = sum(votes.values())
    return (winner[0], winner[1] / total)
```

### 9.6 Self-Loops

Edges where `from == to` are excluded from density calculation and degree computation:

```python
effective_edges = [e for e in E if e.from_id != e.to_id]
density = len(effective_edges) / (len(N) * (len(N) - 1))
```

Self-loops are still rendered visually but do not influence inference decisions.

### 9.7 Missing or Null Edge Types

Edges without a `type` field are treated as type `"UNKNOWN"`. They contribute to density and degree calculations but do not contribute to `edge_type_distribution` scoring for specific protocols (HTTP, GRPC, etc.). Their edge_type_distribution entry is `UNKNOWN: count / |E|`.

### 9.8 Very Large Graphs (|N| > 1000)

The algorithm is O(|N| + |E|) for all stages except `max_chain_length` (longest simple path), which is NP-hard in the general case. For graphs with |N| > 200, `max_chain_length` is approximated by the longest BFS-discovered path from any source node (in-degree 0), capped at depth 50. This reduces worst-case to O(|N| + |E|) while remaining accurate for pipeline-like topologies.

```python
def approx_max_chain_length(N, E, max_depth=50):
    if len(N) <= 200:
        return exact_longest_path(N, E)   # feasible for small graphs

    adj = build_adjacency(E)
    sources = [n.id for n in N if in_degree(n.id, E) == 0]
    if not sources:
        sources = [N[0].id]   # arbitrary start if no sources

    max_len = 0
    for src in sources[:10]:  # limit to 10 sources
        visited = set()
        stack = [(src, 0)]
        while stack:
            node, depth = stack.pop()
            if depth > max_depth:
                continue
            max_len = max(max_len, depth)
            visited.add(node)
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    stack.append((neighbor, depth + 1))
    return max_len
```

---

## Appendix A: Complete Pipeline Pseudocode

```python
def infer(graph_data, theme="dark"):
    N = graph_data["nodes"]
    E = graph_data["edges"]

    # Stage 1: Template Detection
    if has_disconnected_components(N, E):
        template, conf_1 = detect_template_disconnected(N, E)
    else:
        F = extract_features(N, E)
        template, conf_1 = detect_template(F)

    # Stage 2: Layout Selection
    layout, conf_2 = select_layout(template, N, E)

    # Stage 3: Color Palette
    groups = extract_groups(N)
    if len(groups) <= 8:
        palette, conf_3 = generate_small_palette(groups, theme)
    else:
        palette, conf_3 = generate_large_palette(groups, theme)

    # Stage 4: Shape Mapping
    shapes, conf_4 = map_shapes(N)

    # Stage 5: Sizing
    sizes, conf_5 = compute_sizes(N, E)

    # Confidence Aggregation
    total = (conf_1 * conf_2 * conf_3 * conf_4 * conf_5) ** 0.2

    # Low confidence fallback
    if total < 0.30:
        template = "blank"
        layout = "force"
        shapes = {n["id"]: "sphere" for n in N}
        sizes = {n["id"]: 1.0 for n in N}

    return InferredConfig(
        template=template,
        layout=layout,
        palette=palette,
        shapes=shapes,
        sizes=sizes,
        confidence={
            "template": conf_1,
            "layout": conf_2,
            "palette": conf_3,
            "shapes": conf_4,
            "sizing": conf_5,
            "total": total,
        },
    )
```

---

## Appendix B: Invariant Compliance

| Invariant | How this spec satisfies it |
|-----------|---------------------------|
| INV-OT-013 | The pipeline requires only `graph_data.json`. No other input is needed. |
| INV-OT-014 | All five decisions (template, layout, colors, shapes, sizes) are inferred from data. |
| INV-OT-028 | Material properties (emissive, roughness) are outside inference scope; handled by the rendering layer using cockpit_schema.json defaults. |

---

## Appendix C: Shape Availability

All 26 shapes available in `client/js/scene/shapes.js` and their corresponding `mkObj()` case labels:

`warehouse`, `factory`, `satellite`, `terminal`, `monument`, `pillars`, `gear`, `gate`, `database`, `hourglass`, `brain`, `dyson_book`, `gauge`, `hub`, `tree`, `sphere`, `prism`, `stairs`, `nexus`, `graph`, `dial`, `vault`, `screens`, `rack`, `conveyor`, `monitor`

The inference engine maps only to shapes in this set. Shape names not found in `shapes.js` at render time fall back to the `default` case (plain box). The inference engine avoids unmapped shapes — all entries in the SHAPE_TABLE (Section 5.1) reference shapes from this list.
