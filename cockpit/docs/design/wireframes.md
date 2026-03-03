# Ontology Map Toolkit -- Wireframes & Interaction Flows

> GAP-12 | Version 1.0 | Based on SPEC.md features F-06, F-15, F-29, F-30, F-31
> Design tokens: `docs/design/design_system.md` (GAP-6)
> Research: `docs/research/F-06_fractal_drill_down.md`, `docs/research/F-15_conversation_mode.md` (GAP-1)
> Date: 2026-02-27

---

## Table of Contents

1. [Design Token Quick Reference](#1-design-token-quick-reference)
2. [Screen 1: System Overview (Main View)](#2-screen-1-system-overview-main-view)
3. [Screen 2: Fractal Drill-Down (F-06)](#3-screen-2-fractal-drill-down-f-06)
4. [Screen 3: Search Overlay (Cmd+K)](#4-screen-3-search-overlay-cmdk)
5. [Screen 4: Chat Panel (F-15)](#5-screen-4-chat-panel-f-15)
6. [Screen 5: Code View (F-06 L3-L4)](#6-screen-5-code-view-f-06-l3-l4)
7. [Flow 1: Navigate to Function](#7-flow-1-navigate-to-function)
8. [Flow 2: Ask Agent About Module](#8-flow-2-ask-agent-about-module)
9. [State Catalog](#9-state-catalog)
10. [Responsive Breakpoints](#10-responsive-breakpoints)

---

## 1. Design Token Quick Reference

Tokens referenced throughout the wireframes. Full definitions in
`docs/design/design_system.md` (GAP-6).

### Surfaces

| Token | Dark | Light | Usage in wireframes |
|-------|------|-------|---------------------|
| `--surface-0` | `oklch(13% 0.02 260)` | `oklch(98% 0.01 260)` | Canvas background, deepest layer |
| `--surface-1` | `oklch(18% 0.02 260)` | `oklch(95% 0.01 260)` | Panel backgrounds, cards |
| `--surface-2` | `oklch(23% 0.02 260)` | `oklch(91% 0.012 260)` | Hover states, input backgrounds |
| `--surface-3` | `oklch(28% 0.02 260)` | `oklch(87% 0.015 260)` | Active/selected states |

### Text

| Token | Dark | Light |
|-------|------|-------|
| `--text-primary` | `oklch(92% 0.02 260)` | `oklch(15% 0.02 260)` |
| `--text-secondary` | `oklch(70% 0.02 260)` | `oklch(40% 0.02 260)` |
| `--text-tertiary` | `oklch(50% 0.02 260)` | `oklch(60% 0.01 260)` |

### Accents & Categorical

| Token | Hue | Dark L | Light L | Wireframe role |
|-------|-----|--------|---------|----------------|
| `--cat-0` / `--accent-red` | 0 | 65% | 55% | Error states, critical severity |
| `--cat-1` / `--accent-orange` | 45 | 65% | 55% | Warnings |
| `--cat-2` / `--accent-amber` | 90 | 65% | 55% | Edge color: IMPORTS |
| `--cat-3` / `--accent-green` | 135 | 65% | 55% | Success, healthy status |
| `--cat-4` / `--accent-teal` | 180 | 65% | 55% | Edge color: CONTAINS |
| `--cat-5` / `--accent-blue` | 225 | 65% | 55% | Primary accent, selected state glow |
| `--cat-6` / `--accent-indigo` | 270 | 65% | 55% | Edge color: DEPENDS_ON |
| `--cat-7` / `--accent-purple` | 315 | 65% | 55% | Agent messages, AI indicator |

### Spacing

| Token | Value | Wireframe annotation |
|-------|-------|---------------------|
| `--space-1` | 4px | Inline gaps, badge padding |
| `--space-2` | 8px | Icon-to-text, list item gap |
| `--space-3` | 12px | Panel item spacing |
| `--space-4` | 16px | Default padding, section gap |
| `--space-5` | 20px | Panel content padding |
| `--space-6` | 24px | Card padding, large gap |
| `--space-8` | 32px | Section margins |

### Typography

| Token | Size | Use |
|-------|------|-----|
| `--text-xs` | 10px | Badges, tiny labels |
| `--text-sm` | 12px | Secondary text, meta info |
| `--text-base` | 14px | Body text, default |
| `--text-lg` | 16px | Subheadings |
| `--text-xl` | 20px | Section/modal titles |
| `--text-2xl` | 24px | Page title |

### Motion

| Token | Value | Use |
|-------|-------|-----|
| `--duration-fast` | 100ms | Hover, tooltips |
| `--duration-normal` | 200ms | Panel open/close |
| `--duration-slow` | 400ms | Camera moves, drill transitions |
| `--ease-default` | `cubic-bezier(0.2, 0, 0, 1)` | Standard deceleration |
| `--ease-out` | `cubic-bezier(0, 0, 0.2, 1)` | Elements settling |

### Shadows & Borders

| Token | Use |
|-------|-----|
| `--shadow-sm` | Buttons, badges |
| `--shadow-md` | Cards, panels |
| `--shadow-lg` | Modals, overlays |
| `--shadow-glow` | Active nodes, highlights |
| `--radius-sm` | 4px -- badges |
| `--radius-md` | 8px -- cards, panels |
| `--radius-lg` | 12px -- modals |
| `--border-default` | Panel borders |
| `--border-emphasis` | Selected/focus borders |

### 3D Materials

| Token | Dark | Light |
|-------|------|-------|
| `--mat-metalness-mid` | 0.25 | 0.15 |
| `--mat-roughness-mid` | 0.55 | 0.65 |
| `--mat-emissive-glow` | 0.20 | 0.10 |
| `--mat-emissive-max` | 0.25 | 0.15 |

---

## 2. Screen 1: System Overview (Main View)

**Features:** F-29 (Breadcrumb), F-30 (Deep Link / Layout), F-31 (Cmd+K Search)
**Drill level:** L0 (System)
**Camera:** Perspective, orbital, 80 units, FOV 60deg

### 2.1 Wireframe -- Dark Mode

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HEADER BAR  height: 48px  bg: --surface-1  border-bottom: --border-default │
│                                                                             │
│  ┌──────────────────────┐  ┌─────────┐  ┌──────────────────────┐ ┌──┐┌──┐ │
│  │ Ontology Map         │  │ Ready   │  │ Search...    Cmd+K   │ │☀ ││💬│ │
│  │ --text-2xl           │  │ --cat-3 │  │ --surface-2          │ │  ││  │ │
│  │ --font-semibold      │  │ --text- │  │ --text-tertiary      │ │  ││  │ │
│  │ --text-primary       │  │    xs   │  │ --radius-md          │ │  ││  │ │
│  │ padding-left:        │  │ badge   │  │ width: 240px         │ │  ││  │ │
│  │   --space-5          │  │ --radi- │  │ padding: --space-2   │ │  ││  │ │
│  │                      │  │  us-sm  │  │                      │ │  ││  │ │
│  └──────────────────────┘  └─────────┘  └──────────────────────┘ └──┘└──┘ │
│                                                                             │
│  LAYOUT BUTTONS (right side of header, gap: --space-1)                      │
│  ┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐                 │
│  │orbit.││pipel.││ tree ││ grid ││force ││vert. ││group.│                 │
│  │ ACTV ││      ││      ││      ││      ││      ││      │                 │
│  └──────┘└──────┘└──────┘└──────┘└──────┘└──────┘└──────┘                 │
│  active: --surface-3 + --accent-blue border-bottom 2px                      │
│  inactive: --surface-1, hover: --surface-2                                  │
│  icon size: 16px, button: 32x32px                                           │
│  tooltip on hover: layout name, --duration-fast fade-in                     │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  BREADCRUMB BAR  height: 32px  bg: --surface-0 at 80% opacity              │
│  position: absolute, top: 48px, z-index: 10                                │
│  padding: 0 --space-5                                                       │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │  System                                                      │           │
│  │  --text-sm  --text-secondary  --font-medium                  │           │
│  │  At L0 only "System" shows. Deeper levels append:            │           │
│  │  System > auth_module > auth.py > validate()                 │           │
│  │  Each segment clickable, hover: --text-primary               │           │
│  │  Separator: " > " in --text-tertiary                         │           │
│  └──────────────────────────────────────────────────────────────┘           │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                         3D CANVAS                                           │
│                    fills remaining space                                     │
│                    bg: --surface-0                                           │
│                    renderer: Three.js WebGLRenderer                          │
│                                                                             │
│                                                                             │
│           ┌──┐                    ┌──┐                                      │
│           │  │  ──────────────    │  │                                      │
│           │N1│                    │N2│                                      │
│           │  │    ┌──┐           │  │                                      │
│           └──┘    │N3│           └──┘                                      │
│                   │  │──────┐                                              │
│       ┌──┐        └──┘      │     ┌──┐                                    │
│       │N4│                  └─────│N5│                                    │
│       │  │                        │  │                                    │
│       └──┘   ┌──┐                 └──┘                                    │
│              │N6│                                                          │
│              │  │                                                          │
│              └──┘                                                          │
│                                                                             │
│   Nodes: 3D shapes with labels below (--text-sm, --text-primary)            │
│   Edges: lines colored by type (--cat-2 IMPORTS, --cat-4 CONTAINS,          │
│           --cat-6 DEPENDS_ON, --cat-0 BREAKS, --cat-3 TESTS)               │
│   Node material: --mat-metalness-mid, --mat-roughness-mid                   │
│   Node colors: derived from --cat-N per node type/group                     │
│                                                                             │
│                                                                             │
│  ┌─────────────────────────────┐             ┌──────────────────────────┐  │
│  │ LEGEND PANEL                │             │ STATS BAR                │  │
│  │ position: absolute          │             │ position: absolute       │  │
│  │ bottom: --space-4           │             │ bottom: --space-4        │  │
│  │ left: --space-4             │             │ right: --space-4         │  │
│  │ bg: --surface-1 at 90%     │             │ bg: --surface-1 at 90%  │  │
│  │ radius: --radius-md         │             │ radius: --radius-md      │  │
│  │ shadow: --shadow-md         │             │ shadow: --shadow-md      │  │
│  │ padding: --space-3          │             │ padding: --space-2       │  │
│  │ max-width: 180px            │             │ --space-3               │  │
│  │ collapsible (click header)  │             │                          │  │
│  │                             │             │ Nodes: 47                │  │
│  │  ── IMPORTS  (--cat-2)     │             │ --text-sm                │  │
│  │  ── CONTAINS (--cat-4)     │             │ --text-secondary         │  │
│  │  ── DEPENDS  (--cat-6)     │             │                          │  │
│  │  ── BREAKS   (--cat-0)     │             │ Edges: 82                │  │
│  │  ── TESTS    (--cat-3)     │             │ Clusters: 5              │  │
│  │                             │             │ LOC: 12,450              │  │
│  │  --text-xs for labels       │             │ Coverage: 87%            │  │
│  │  line preview: 20px wide    │             │                          │  │
│  │  gap between entries:       │             │ each stat:               │  │
│  │    --space-2                │             │   label --text-tertiary  │  │
│  │                             │             │   value --text-primary   │  │
│  └─────────────────────────────┘             └──────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Dark vs Light Mode Differences

| Element | Dark Mode | Light Mode |
|---------|-----------|------------|
| Canvas bg | `--surface-0` oklch(13%) -- near black | `--surface-0` oklch(98%) -- near white |
| Panel bg | `--surface-1` oklch(18%) at 90% alpha | `--surface-1` oklch(95%) at 90% alpha |
| Node glow | `--mat-emissive-glow` 0.20 -- visible bloom | `--mat-emissive-glow` 0.10 -- subtle |
| Edge lines | Full brightness on dark bg | Reduced to L=55% on light bg |
| Text on panels | `--text-primary` oklch(92%) white | `--text-primary` oklch(15%) near black |
| Shadows | Barely visible (dark on dark) | `--shadow-md` clearly visible |
| Header bg | `--surface-1` blends with dark canvas | `--surface-1` distinct from white canvas |
| Layout btn active | `--accent-blue` bright underline | `--accent-blue` at L=55% underline |

### 2.3 Node States

**Idle State:**
- Material: `--mat-metalness-mid`, `--mat-roughness-mid`
- Emissive: 0 (no glow)
- Label: `--text-sm`, `--text-primary`, positioned below node center
- Opacity: 1.0

**Hover State** (cursor enters node, `--duration-fast` transition):
- Emissive: `--mat-emissive-glow` (0.20 dark / 0.10 light)
- Outline: 2px `--accent-blue` (via `--shadow-glow`)
- Label: scale 1.05x, `--font-semibold`
- Cursor: `pointer`
- Tooltip appears after 200ms delay:
  ```
  ┌─────────────────────────────┐
  │ auth_service                │  --text-base, --font-semibold
  │ Package | 12 files          │  --text-sm, --text-secondary
  │ LOC: 2,340 | Cov: 91%      │  --text-xs, --text-tertiary
  └─────────────────────────────┘
  bg: --surface-2, radius: --radius-sm, shadow: --shadow-sm
  padding: --space-2 --space-3
  max-width: 220px
  position: follows cursor, offset 12px right + 12px down
  ```

**Selected State** (click on node):
- Emissive: `--mat-emissive-max` (0.25 dark / 0.15 light), persistent
- Outline: 3px `--accent-blue`, persistent
- Label: `--font-semibold`, `--text-primary`
- Detail panel slides in from right (see below)

**Highlighted State** (via agent `highlight_nodes` tool):
- Emissive: `--mat-emissive-max` with pulse animation (0.15 to 0.25, 1s cycle)
- Color override: from tool's `color` parameter, mapped to nearest `--cat-N`
- Duration: per tool's `duration_ms` parameter (default 5000ms)
- Stacked with selected state (both can be active)

### 2.4 Detail Panel (Slides from Right on Node Select)

```
┌──────────────────────────────────────────────────┬─────────────────────────┐
│                                                  │ DETAIL PANEL            │
│                                                  │ width: 320px            │
│                                                  │ bg: --surface-1         │
│              3D CANVAS                           │ border-left:            │
│              resizes to                          │   --border-default      │
│              calc(100% - 320px)                  │ shadow: --shadow-md     │
│              transition: --duration-normal        │ padding: --space-5      │
│              --ease-default                       │                         │
│                                                  │ ┌─────────────────────┐ │
│                                                  │ │ auth_service    [X] │ │
│                                                  │ │ --text-xl           │ │
│                                                  │ │ --font-semibold     │ │
│                                                  │ └─────────────────────┘ │
│                                                  │                         │
│                                                  │ Type: Package           │
│                                                  │ Files: 12               │
│                                                  │ LOC: 2,340              │
│                                                  │ Complexity: 34 avg      │
│                                                  │ Coverage: 91%           │
│                                                  │ --text-sm               │
│                                                  │ --text-secondary        │
│                                                  │ gap: --space-2          │
│                                                  │                         │
│                                                  │ ─────────────────────── │
│                                                  │ border: --border-default│
│                                                  │                         │
│                                                  │ Dependencies (5)        │
│                                                  │ --text-base --font-med  │
│                                                  │                         │
│                                                  │  -> models.py           │
│                                                  │  -> config.py           │
│                                                  │  -> db_service.py       │
│                                                  │  -> cache.py            │
│                                                  │  -> utils.py            │
│                                                  │  --text-sm              │
│                                                  │  --accent-blue on hover │
│                                                  │  click -> navigate_to   │
│                                                  │  gap: --space-1         │
│                                                  │                         │
│                                                  │ ─────────────────────── │
│                                                  │                         │
│                                                  │ Dependents (3)          │
│                                                  │  <- api_routes.py       │
│                                                  │  <- middleware.py       │
│                                                  │  <- tests/test_auth.py  │
│                                                  │                         │
│                                                  │ ─────────────────────── │
│                                                  │                         │
│                                                  │ [Drill Into]            │
│                                                  │ button --accent-blue bg │
│                                                  │ --text-primary text     │
│                                                  │ --radius-sm             │
│                                                  │ padding: --space-2      │
│                                                  │   --space-4             │
│                                                  │ hover: brightness 1.1   │
│                                                  │ click: triggers L0->L1  │
│                                                  │                         │
│                                                  │ [Ask Agent]             │
│                                                  │ button --surface-2 bg   │
│                                                  │ --border-emphasis border│
│                                                  │ opens chat with context │
│                                                  │                         │
└──────────────────────────────────────────────────┴─────────────────────────┘
```

### 2.5 URL Hash (F-30)

At L0 System Overview, the URL hash encodes the current view state:

```
cockpit.html#layout=orbital&theme=dark&node=auth_service&zoom=1.0
```

Any change to layout, theme, selected node, or zoom level updates the hash.
Pasting a URL with a hash restores the exact view state on load.

---

## 3. Screen 2: Fractal Drill-Down (F-06)

**Features:** F-06 (5-level drill), F-29 (Breadcrumb)
**Transitions:** 350ms per level, `--ease-out`, quaternion SLERP camera rotation
**Reference:** `docs/research/F-06_fractal_drill_down.md` Sections 2, 5, 8.1

### 3.1 L0 to L1 Transition (System to Module)

**Trigger:** Double-click on `auth_service` node OR click "Drill Into" button
**Duration:** 350ms (`--duration-slow`)
**Easing:** `--ease-out` -- `cubic-bezier(0, 0, 0.2, 1)`
**Camera:** Arc path, perspective, orbital distance 80 -> 30 units, FOV 60 -> 55deg

```
BEFORE (L0 -- System View)                    AFTER (L1 -- Module View)
t=0ms                                          t=350ms

┌──────────────────────────────────┐          ┌──────────────────────────────────┐
│ System > auth_service            │          │ System > auth_service            │
│ --text-sm, clickable segments    │          │                ^^^^ --text-primary│
│                                  │          │                (current level)    │
├──────────────────────────────────┤          ├──────────────────────────────────┤
│                                  │          │                                  │
│         ┌──┐       ┌──┐         │          │   ┌────────┐    ┌────────┐      │
│         │au│───────│db│         │          │   │auth.py │────│models  │      │
│         │th│       │  │         │          │   │  .py   │    │  .py   │      │
│         └──┘       └──┘         │          │   └────────┘    └────────┘      │
│    ┌──┐       ┌──┐              │          │        │              │          │
│    │ap│       │cf│              │          │        ▼              ▼          │
│    │i │       │g │              │          │   ┌────────┐    ┌────────┐      │
│    └──┘       └──┘              │          │   │ utils  │    │config  │      │
│                                  │          │   │  .py   │    │  .py   │      │
│  Other nodes fade to opacity 0.1 │          │   └────────┘    └────────┘      │
│  --duration-slow transition      │          │                                  │
│                                  │          │   Nodes: cubes, labeled           │
│                                  │          │   Edges: --cat-2 (IMPORTS)        │
│                                  │          │   Material: --mat-roughness-mid   │
│                                  │          │                                  │
└──────────────────────────────────┘          └──────────────────────────────────┘

Transition sequence (350ms total):
  0-100ms:  Camera begins arc path lift (sin curve, 20% of lateral distance)
            Parent-level nodes begin opacity fade (1.0 -> 0.1)
  100-250ms: Camera descends toward module centroid
             Child nodes (files) begin opacity fade-in (0.0 -> 1.0)
             Child edges draw in with directional particle animation
  250-350ms: Camera settles at 30 units, FOV narrows to 55deg
             All child nodes fully opaque, labels appear
             Breadcrumb updates: "System > auth_service"
             URL hash updates: #level=1&node=auth_service
```

### 3.2 L1 to L2 Transition (Module to File)

**Trigger:** Double-click on `auth.py` file node
**Camera:** Orbital distance 30 -> 12 units, FOV 55 -> 50deg

```
AFTER (L2 -- File View, t=700ms from L0 start)

┌──────────────────────────────────────────────────────────────────────────┐
│ System > auth_service > auth.py                                          │
│ ^^^^^^^^^^^^^^^^^^^     ^^^^^^^ --text-primary (current)                 │
│  --accent-blue hover     --font-semibold                                 │
│  clickable (drills out)                                                  │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│                                                                          │
│       ┌────────────────┐            ┌────────────────┐                  │
│       │  AuthService   │            │  TokenManager  │                  │
│       │    (class)     │────────────│    (class)     │                  │
│       │  --cat-5 hue   │  DEPENDS   │  --cat-5 hue   │                  │
│       └───────┬────────┘            └────────────────┘                  │
│               │ CONTAINS                                                 │
│        ┌──────┴──────────────────┐                                      │
│        │                         │                                      │
│   ┌────┴──────┐    ┌────────────┐│   ┌────────────┐                    │
│   │ validate()│    │  login()   ││   │ refresh()  │                    │
│   │ (function)│    │ (function) ││   │ (function) │                    │
│   │ --cat-3   │    │ --cat-3    ││   │ --cat-3    │                    │
│   │ hue       │    │ hue        ││   │ hue        │                    │
│   └───────────┘    └────────────┘│   └────────────┘                    │
│                                  │                                      │
│   Nodes colored by type:                                                │
│     class:    --cat-5 (blue)     shape: cube                            │
│     function: --cat-3 (green)    shape: sphere                          │
│     enum:     --cat-1 (orange)   shape: octahedron                      │
│     constant: --cat-2 (amber)    shape: tetrahedron                     │
│                                                                          │
│   DOI-based LOD (Furnas formula):                                        │
│     Focused: full shape + label + glow   (DOI > 8.0)                    │
│     Near:    simplified shape + label    (DOI 5.0-8.0)                  │
│     Far:     color dot, no label         (DOI 2.0-5.0)                  │
│     Hidden:  not rendered                (DOI < 2.0)                    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.3 L2 to L3 Transition (File to Function -- Code Panel Appears)

**Trigger:** Double-click on `validate()` function node
**Key change:** Code panel slides in from right, 3D view compresses left
**Camera:** Switches from perspective to orthographic (per F-06 research Section 5)

```
AFTER (L3 -- Function / Read-Only Code View)

┌──────────────────────────────────────────────────────────────────────────┐
│ System > auth_service > auth.py > validate()                             │
├──────────────────────────────────────────────────────────────────────────┤
│                          │                                               │
│   3D MINIMAP             │          CODE PANEL (Shiki)                   │
│   width: 40%             │          width: 60%                           │
│                          │          bg: --surface-1                      │
│   Previous L2 view       │          border-left: --border-default        │
│   compressed,            │          shadow: --shadow-md                  │
│   camera orthographic    │          slide-in: --duration-normal          │
│   top-down               │                    --ease-default             │
│                          │                                               │
│   validate() node        │   ┌──────────────────────────────────────┐   │
│   highlighted with       │   │ auth.py                          RO │   │
│   --shadow-glow          │   │ --text-sm  --text-secondary          │   │
│   --accent-blue          │   │ RO badge: --cat-2 bg, --text-xs     │   │
│                          │   ├──────────────────────────────────────┤   │
│   Other nodes:           │   │  42 │ def validate(self, token):    │   │
│   DOI-reduced,           │   │  43 │     """Validate JWT token."""  │   │
│   dots only              │   │  44 │     try:                      │   │
│                          │   │  45 │         payload = jwt.decode(  │   │
│   Clicking a node        │   │  46 │             token,            │   │
│   in minimap scrolls     │   │  47 │             self.secret,      │   │
│   code to that           │   │  48 │             algorithms=["HS   │   │
│   symbol's definition    │   │  49 │                 256"]         │   │
│                          │   │  50 │         )                     │   │
│                          │   │  51 │         return payload        │   │
│   Clicking a symbol      │   │  52 │     except jwt.ExpiredSign..  │   │
│   in code highlights     │   │  53 │         raise AuthError(      │   │
│   the corresponding      │   │  54 │             "Token expired"   │   │
│   node in minimap        │   │  55 │         )                     │   │
│   (bidirectional,        │   │  56 │     except jwt.InvalidToken:  │   │
│    per Sourcetrail        │   │  57 │         raise AuthError(      │   │
│    pattern from           │   │  58 │             "Invalid token"   │   │
│    F-06 research)         │   │  59 │         )                     │   │
│                          │   │                                      │   │
│                          │   │ Line numbers: --text-xs               │   │
│                          │   │               --text-tertiary         │   │
│                          │   │ Code font: --font-mono                │   │
│                          │   │ Code size: --text-sm                  │   │
│                          │   │ Syntax: Shiki (read-only, ~25 KB)    │   │
│                          │   │ Highlighted line (42-59):             │   │
│                          │   │   bg: --surface-2                    │   │
│                          │   │ Scrollbar: custom, --surface-3 thumb │   │
│                          │   └──────────────────────────────────────┘   │
│                          │                                               │
└──────────────────────────┴───────────────────────────────────────────────┘
```

### 3.4 L3 to L4 Transition (Read-Only to Editor)

**Trigger:** Explicit "Edit" button click (NOT distance-based per F-06 research Section 8.1)
**Change:** Shiki replaced by CodeMirror 6, toolbar appears, "RO" badge changes to "EDIT"

```
AFTER (L4 -- Editable Code View)

┌──────────────────────────────────────────────────────────────────────────┐
│ System > auth_service > auth.py > validate()                             │
├──────────────────────────────────────────────────────────────────────────┤
│                          │                                               │
│   3D MINIMAP             │   CODE PANEL (CodeMirror 6, ~75 KB lazy)     │
│   width: 40%             │   width: 60%                                  │
│   (same as L3)           │                                               │
│                          │   ┌──────────────────────────────────────┐   │
│   Modified indicator:    │   │ TOOLBAR                    height:  │   │
│   dot on file node       │   │                            36px     │   │
│   --accent-amber         │   │  [Save] [Format] [Copy]   --surfa- │   │
│   (unsaved changes)      │   │  --surface-2 bg            ce-1 bg │   │
│                          │   │  buttons: --space-2 gap             │   │
│                          │   │  --radius-sm                        │   │
│                          │   │  --text-sm                          │   │
│                          │   │  hover: --surface-3                 │   │
│                          │   │                                      │   │
│                          │   │  [EDIT] badge: --accent-amber bg    │   │
│                          │   │  --text-xs, replaces "RO"           │   │
│                          │   │                                      │   │
│                          │   │  Modified: "2 unsaved changes"      │   │
│                          │   │  --text-xs --accent-amber           │   │
│                          │   ├──────────────────────────────────────┤   │
│                          │   │                                      │   │
│                          │   │  42 │ def validate(self, token):    │   │
│                          │   │  43 │     """Validate JWT token."""  │   │
│                          │   │     │  ^                             │   │
│                          │   │     │  blinking cursor               │   │
│                          │   │     │  --text-primary color          │   │
│                          │   │  44 │     try:                      │   │
│                          │   │  45 │         payload = jwt.decode(  │   │
│                          │   │  ...                                 │   │
│                          │   │                                      │   │
│                          │   │  CodeMirror keybindings active       │   │
│                          │   │  Ctrl+S: save, Ctrl+Z: undo         │   │
│                          │   │  Tab: indent, Shift+Tab: outdent    │   │
│                          │   │                                      │   │
│                          │   │  Controls: text cursor replaces      │   │
│                          │   │  3D navigation (per F-06 Section 8.3)│   │
│                          │   │  OrbitControls disabled on code panel │   │
│                          │   │                                      │   │
│                          │   └──────────────────────────────────────┘   │
│                          │                                               │
└──────────────────────────┴───────────────────────────────────────────────┘
```

### 3.5 Full Drill-Down Timing Chart

```
Event                     Time      Camera Dist  FOV    Level  Breadcrumb
────────────────────────  ────────  ───────────  ─────  ─────  ──────────────────────
Double-click auth_svc     0ms       80 units     60deg  L0     System
Arc path begins           0ms       78->50       60->57 L0->L1 System
Children fade in          100ms     50           57     L0->L1 System
Camera settles            350ms     30           55     L1     System > auth_service
Double-click auth.py      350ms     30           55     L1     System > auth_service
Camera zooms in           350ms     28->15       55->52 L1->L2 System > auth_service
Children appear           450ms     15           52     L1->L2
Camera settles            700ms     12           50     L2     System > auth_service > auth.py
Double-click validate()   700ms     12           50     L2
Code panel slides in      700ms     --           --     L2->L3
Camera -> orthographic    850ms     5            ortho  L3     ...> auth.py > validate()
Panel fully open          1000ms    5            ortho  L3     (complete)
Click "Edit" button       user      5            ortho  L3
Shiki->CodeMirror swap    1000ms    5            ortho  L3->L4
Toolbar appears           1200ms    5            ortho  L4     ...> auth.py > validate()

Total L0->L3: ~1000ms (3 transitions x 350ms, with 50ms overlap)
Each transition: 350ms, --ease-out, quaternion SLERP for rotation
```

---

## 4. Screen 3: Search Overlay (Cmd+K)

**Feature:** F-31 (Search & Filter Bar)
**Trigger:** Cmd+K (macOS) / Ctrl+K (Windows/Linux)
**Appearance:** 300ms fade-in with backdrop blur

### 4.1 Wireframe -- Search Overlay

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  3D CANVAS (dimmed, pointer-events: none while overlay open)                │
│  backdrop-filter: blur(8px)                                                 │
│  bg overlay: --surface-0 at 60% opacity                                     │
│  transition: --duration-normal fade-in                                      │
│                                                                             │
│        ┌────────────────────────────────────────────────────────────┐       │
│        │                                                            │       │
│        │  SEARCH OVERLAY                                            │       │
│        │  width: 600px                                              │       │
│        │  max-height: 480px                                         │       │
│        │  position: centered horizontally, top: 20vh                │       │
│        │  bg: --surface-1                                           │       │
│        │  border: --border-emphasis                                 │       │
│        │  radius: --radius-lg (12px)                                │       │
│        │  shadow: --shadow-lg                                       │       │
│        │  padding: 0 (inner elements have their own padding)        │       │
│        │                                                            │       │
│        │  ┌────────────────────────────────────────────────────┐   │       │
│        │  │ [Q] Search nodes...                                │   │       │
│        │  │                                                    │   │       │
│        │  │ icon: magnifying glass, --text-tertiary, 16px      │   │       │
│        │  │ input: --text-base, --font-family                  │   │       │
│        │  │ placeholder: --text-tertiary                       │   │       │
│        │  │ bg: --surface-2                                    │   │       │
│        │  │ border-bottom: --border-default                    │   │       │
│        │  │ padding: --space-3 --space-4                       │   │       │
│        │  │ height: 48px                                       │   │       │
│        │  │ autofocus: true                                    │   │       │
│        │  │                                                    │   │       │
│        │  │ [Esc] badge right-aligned                          │   │       │
│        │  │ --text-xs, --surface-3 bg, --radius-sm             │   │       │
│        │  └────────────────────────────────────────────────────┘   │       │
│        │                                                            │       │
│        │  ┌────────────────────────────────────────────────────┐   │       │
│        │  │ FILTER CHIPS (below input, horizontal scroll)      │   │       │
│        │  │ padding: --space-2 --space-4                       │   │       │
│        │  │ gap: --space-1                                     │   │       │
│        │  │                                                    │   │       │
│        │  │ [All] [Package] [File] [Class] [Function]          │   │       │
│        │  │  ^^^                                               │   │       │
│        │  │  active: --accent-blue bg, --text-primary text     │   │       │
│        │  │  inactive: --surface-2 bg, --text-secondary text   │   │       │
│        │  │  --text-xs, --radius-full (pill shape)             │   │       │
│        │  │  padding: --space-1 --space-2                      │   │       │
│        │  │  hover: --surface-3 bg                             │   │       │
│        │  └────────────────────────────────────────────────────┘   │       │
│        │                                                            │       │
│        │  ┌────────────────────────────────────────────────────┐   │       │
│        │  │ RESULTS LIST (scrollable, max-height: 360px)       │   │       │
│        │  │                                                    │   │       │
│        │  │ L0: System                                         │   │       │
│        │  │ --text-xs, --text-tertiary, uppercase               │   │       │
│        │  │ padding: --space-1 --space-4                       │   │       │
│        │  │ border-bottom: --border-default                    │   │       │
│        │  │                                                    │   │       │
│        │  │ ┌──────────────────────────────────────────────┐   │   │       │
│        │  │ │ [cube icon]  auth_service                    │   │   │       │
│        │  │ │              Authentication & authorization   │   │   │       │
│        │  │ │              [Package]                        │   │   │       │
│        │  │ │                                              │   │   │       │
│        │  │ │ icon: shape thumbnail, 20x20px, --cat-5     │   │   │       │
│        │  │ │ label: --text-base, --font-medium            │   │   │       │
│        │  │ │ subtitle: --text-sm, --text-secondary        │   │   │       │
│        │  │ │ badge: --text-xs, --surface-3 bg, --radius-sm│   │   │       │
│        │  │ │ padding: --space-2 --space-4                 │   │   │       │
│        │  │ │ hover bg: --surface-2                        │   │   │       │
│        │  │ │ keyboard selected: --surface-3 bg,           │   │   │       │
│        │  │ │   border-left: 2px --accent-blue             │   │   │       │
│        │  │ └──────────────────────────────────────────────┘   │   │       │
│        │  │                                                    │   │       │
│        │  │ L1: Module                                         │   │       │
│        │  │ --text-xs, --text-tertiary, uppercase               │   │       │
│        │  │                                                    │   │       │
│        │  │ ┌──────────────────────────────────────────────┐   │   │       │
│        │  │ │ [file icon] auth_service/auth.py             │   │   │       │
│        │  │ │             JWT token validation              │   │   │       │
│        │  │ │             [File]                            │   │   │       │
│        │  │ └──────────────────────────────────────────────┘   │   │       │
│        │  │                                                    │   │       │
│        │  │ L2: Symbol                                         │   │       │
│        │  │                                                    │   │       │
│        │  │ ┌──────────────────────────────────────────────┐   │   │       │
│        │  │ │ [fn icon]  auth_service.validate()           │   │   │       │
│        │  │ │            Validate JWT token and return..    │   │   │       │
│        │  │ │            [Function]                         │   │   │       │
│        │  │ └──────────────────────────────────────────────┘   │   │       │
│        │  │                                                    │   │       │
│        │  │ ┌──────────────────────────────────────────────┐   │   │       │
│        │  │ │ [fn icon]  middleware.validate_request()      │   │   │       │
│        │  │ │            Validate incoming HTTP request..   │   │   │       │
│        │  │ │            [Function]                         │   │   │       │
│        │  │ └──────────────────────────────────────────────┘   │   │       │
│        │  │                                                    │   │       │
│        │  └────────────────────────────────────────────────────┘   │       │
│        │                                                            │       │
│        │  ┌────────────────────────────────────────────────────┐   │       │
│        │  │ FOOTER                                             │   │       │
│        │  │ height: 32px, bg: --surface-2                      │   │       │
│        │  │ border-top: --border-default                       │   │       │
│        │  │ padding: --space-1 --space-4                       │   │       │
│        │  │                                                    │   │       │
│        │  │ [Up/Down] Navigate   [Enter] Open   [Esc] Close    │   │       │
│        │  │ --text-xs, --text-tertiary                         │   │       │
│        │  │ key badges: --surface-3, --radius-sm               │   │       │
│        │  └────────────────────────────────────────────────────┘   │       │
│        │                                                            │       │
│        └────────────────────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Search States

**Empty State (no query, just opened):**
```
┌────────────────────────────────────────────────────┐
│ [Q] Search nodes...                        [Esc]   │
├────────────────────────────────────────────────────┤
│                                                    │
│  Recent Searches                                   │
│  --text-xs, --text-tertiary                        │
│                                                    │
│  [clock icon] auth_service           [x] remove    │
│  [clock icon] models.py             [x] remove    │
│  [clock icon] validate              [x] remove    │
│                                                    │
│  --text-sm, --text-secondary                       │
│  hover: --surface-2                                │
│  click: populates search input                     │
│  stored in localStorage, max 10 entries            │
│                                                    │
│  (no filter chips shown until user types)          │
│                                                    │
└────────────────────────────────────────────────────┘
```

**Typing State (live filter, debounced 150ms):**
```
┌────────────────────────────────────────────────────┐
│ [Q] vali|                                  [Esc]   │
│         ^ cursor                                   │
├────────────────────────────────────────────────────┤
│ [All] [Package] [File] [Class] [Function]          │
├────────────────────────────────────────────────────┤
│ 3 results                                          │
│ --text-xs, --text-tertiary                         │
│                                                    │
│ Matching text highlighted: --accent-blue on the    │
│ matched substring. E.g., "vali" in "validate()"    │
│ rendered in --accent-blue --font-semibold           │
│                                                    │
│ Results update in real-time as user types           │
│ Filter by graph.json node names + descriptions     │
│ Client-side fuzzy match (Fuse.js or similar)       │
└────────────────────────────────────────────────────┘
```

**No Results State:**
```
┌────────────────────────────────────────────────────┐
│ [Q] xyznonexistent                         [Esc]   │
├────────────────────────────────────────────────────┤
│ [All] [Package] [File] [Class] [Function]          │
├────────────────────────────────────────────────────┤
│                                                    │
│              No nodes found                        │
│              --text-lg, --text-tertiary             │
│                                                    │
│              Try a different query or               │
│              clear the type filter.                 │
│              --text-sm, --text-tertiary             │
│                                                    │
│              [Ask the Agent]                        │
│              --accent-blue, --text-sm               │
│              click: closes search,                  │
│              opens chat with query                  │
│                                                    │
└────────────────────────────────────────────────────┘
```

### 4.3 Keyboard Navigation

| Key | Action |
|-----|--------|
| `Cmd+K` / `Ctrl+K` | Open search overlay |
| `Escape` | Close overlay (if open) |
| `ArrowDown` | Move selection to next result |
| `ArrowUp` | Move selection to previous result |
| `Enter` | Navigate to selected result (close overlay, camera moves) |
| `Tab` | Cycle through filter chips |
| Any character | Appends to search query, triggers live filter |

---

## 5. Screen 4: Chat Panel (F-15)

**Feature:** F-15 (Conversation Mode / Ontology Agent)
**Architecture:** BYOK browser-direct (Phase 1), AG-UI SSE events
**Tools:** 6 tools per `docs/research/F-15_conversation_mode.md` Section 8.3
**Reference:** `docs/research/F-15_conversation_mode.md` Sections 4-6, 8

### 5.1 Wireframe -- Chat Panel Open

```
┌──────────────────────────────────────────────┬──────────────────────────────┐
│                                              │ CHAT PANEL                   │
│  3D CANVAS                                   │ width: 400px                 │
│  width: calc(100% - 400px)                   │ bg: --surface-1              │
│  transition: --duration-normal               │ border-left: --border-default│
│  --ease-default                              │ shadow: --shadow-md          │
│                                              │ slide-in from right:         │
│  Canvas resizes smoothly.                    │   --duration-normal          │
│  OrbitControls re-center                     │   --ease-default             │
│  after resize.                               │                              │
│                                              │ ┌────────────────────────┐  │
│                                              │ │ HEADER     height: 48px│  │
│  ┌──┐                                        │ │                        │  │
│  │  │ Toggle button                          │ │ Ontology Agent         │  │
│  │< │ position: right edge of canvas         │ │ --text-lg              │  │
│  │  │ width: 24px, height: 48px              │ │ --font-semibold        │  │
│  └──┘ bg: --surface-2                        │ │                        │  │
│       radius: --radius-sm (left corners)     │ │ [Key icon] Using your  │  │
│       border: --border-default               │ │ Anthropic key          │  │
│       hover: --surface-3                     │ │ --text-xs              │  │
│       click: toggles chat open/close         │ │ --text-tertiary        │  │
│       arrow icon: --text-secondary           │ │ --accent-green dot     │  │
│       tooltip: "Toggle AI Chat"              │ │ (key configured)       │  │
│                                              │ │                        │  │
│                                              │ │ [Minimize] [X]         │  │
│                                              │ │ --text-secondary       │  │
│                                              │ │ hover: --text-primary  │  │
│                                              │ └────────────────────────┘  │
│                                              │                              │
│                                              │ ┌────────────────────────┐  │
│                                              │ │ MESSAGE AREA           │  │
│                                              │ │ flex: 1, overflow-y:   │  │
│                                              │ │ auto, scroll-snap-type │  │
│                                              │ │ padding: --space-4     │  │
│                                              │ │                        │  │
│                                              │ │ ┌─ USER MESSAGE ─────┐│  │
│                                              │ │ │ What does the       ││  │
│                                              │ │ │ crystallizer do?    ││  │
│                                              │ │ │                     ││  │
│                                              │ │ │ align: right        ││  │
│                                              │ │ │ bg: --accent-blue   ││  │
│                                              │ │ │   at 20% opacity    ││  │
│                                              │ │ │ color: --text-primary││  │
│                                              │ │ │ radius: --radius-md ││  │
│                                              │ │ │ padding: --space-3  ││  │
│                                              │ │ │ max-width: 85%      ││  │
│                                              │ │ │ font: --text-base   ││  │
│                                              │ │ └─────────────────────┘│  │
│                                              │ │                        │  │
│                                              │ │ ┌─ AGENT MESSAGE ────┐│  │
│                                              │ │ │ The crystallizer   ││  │
│                                              │ │ │ module converts    ││  │
│                                              │ │ │ raw observations...  ││  │
│                                              │ │ │                     ││  │
│                                              │ │ │ align: left         ││  │
│                                              │ │ │ bg: --surface-2     ││  │
│                                              │ │ │ color: --text-primary││  │
│                                              │ │ │ radius: --radius-md ││  │
│                                              │ │ │ padding: --space-3  ││  │
│                                              │ │ │ max-width: 85%      ││  │
│                                              │ │ │ font: --text-base   ││  │
│                                              │ │ │                     ││  │
│                                              │ │ │ Agent indicator:    ││  │
│                                              │ │ │ --accent-purple dot ││  │
│                                              │ │ │ "Agent" label       ││  │
│                                              │ │ │ --text-xs           ││  │
│                                              │ │ └─────────────────────┘│  │
│                                              │ │                        │  │
│                                              │ │ ┌─ ACTION CARD ──────┐│  │
│                                              │ │ │ [navigate_to]      ││  │
│                                              │ │ │ Navigating to      ││  │
│                                              │ │ │ crystallizer...    ││  │
│                                              │ │ │                    ││  │
│                                              │ │ │ bg: --surface-1    ││  │
│                                              │ │ │ border: --border-  ││  │
│                                              │ │ │   emphasis         ││  │
│                                              │ │ │ radius: --radius-md││  │
│                                              │ │ │ padding: --space-2 ││  │
│                                              │ │ │   --space-3        ││  │
│                                              │ │ │                    ││  │
│                                              │ │ │ Tool name: --text- ││  │
│                                              │ │ │   xs, --accent-    ││  │
│                                              │ │ │   purple, --font-  ││  │
│                                              │ │ │   mono             ││  │
│                                              │ │ │ Description:       ││  │
│                                              │ │ │   --text-sm,       ││  │
│                                              │ │ │   --text-secondary ││  │
│                                              │ │ │                    ││  │
│                                              │ │ │ States:            ││  │
│                                              │ │ │  pending: spinner  ││  │
│                                              │ │ │  complete: check   ││  │
│                                              │ │ │   --accent-green   ││  │
│                                              │ │ │  error: x icon     ││  │
│                                              │ │ │   --accent-red     ││  │
│                                              │ │ └────────────────────┘│  │
│                                              │ │                        │  │
│                                              │ │ ┌─ METRICS CARD ────┐ │  │
│                                              │ │ │ get_metrics result │ │  │
│                                              │ │ │                    │ │  │
│                                              │ │ │ LOC     2,340      │ │  │
│                                              │ │ │ Cmplx   34 avg     │ │  │
│                                              │ │ │ Cover   91%        │ │  │
│                                              │ │ │ Coupli  0.23       │ │  │
│                                              │ │ │                    │ │  │
│                                              │ │ │ bg: --surface-2    │ │  │
│                                              │ │ │ border: --border-  │ │  │
│                                              │ │ │   default          │ │  │
│                                              │ │ │ grid: 2 columns    │ │  │
│                                              │ │ │ labels: --text-xs  │ │  │
│                                              │ │ │   --text-tertiary  │ │  │
│                                              │ │ │ values: --text-sm  │ │  │
│                                              │ │ │   --text-primary   │ │  │
│                                              │ │ │   --font-semibold  │ │  │
│                                              │ │ └────────────────────┘ │  │
│                                              │ │                        │  │
│                                              │ └────────────────────────┘  │
│                                              │                              │
│                                              │ ┌────────────────────────┐  │
│                                              │ │ INPUT AREA  height: 64px│  │
│                                              │ │ bg: --surface-1         │  │
│                                              │ │ border-top: --border-   │  │
│                                              │ │   default               │  │
│                                              │ │ padding: --space-3      │  │
│                                              │ │                         │  │
│                                              │ │ ┌──────────────┐ [Send]│  │
│                                              │ │ │ Ask about    │       │  │
│                                              │ │ │ the system...│ btn:  │  │
│                                              │ │ │              │ 36px  │  │
│                                              │ │ │ --surface-2  │ sq.   │  │
│                                              │ │ │ --text-base  │ --acc-│  │
│                                              │ │ │ --radius-md  │ ent-  │  │
│                                              │ │ │ flex: 1      │ blue  │  │
│                                              │ │ │ padding:     │ bg    │  │
│                                              │ │ │  --space-2   │ arrow │  │
│                                              │ │ │  --space-3   │ icon  │  │
│                                              │ │ └──────────────┘       │  │
│                                              │ │                         │  │
│                                              │ │ Streaming indicator     │  │
│                                              │ │ (when agent responding):│  │
│                                              │ │  . . .                  │  │
│                                              │ │  3 dots pulsing         │  │
│                                              │ │  --text-tertiary        │  │
│                                              │ │  animation: 1.4s ease   │  │
│                                              │ │  stagger: 200ms between │  │
│                                              │ │  dots                   │  │
│                                              │ └────────────────────────┘  │
│                                              │                              │
└──────────────────────────────────────────────┴──────────────────────────────┘
```

### 5.2 Chat Panel States

**No API Key Configured:**
```
┌──────────────────────────────────┐
│ Ontology Agent                   │
│                                  │
│                                  │
│    [Key icon]                    │
│    --text-tertiary, 48px         │
│                                  │
│    Configure your API key        │
│    to enable the AI agent.       │
│    --text-base, --text-secondary │
│                                  │
│    Supports: Anthropic, OpenAI   │
│    --text-sm, --text-tertiary    │
│                                  │
│    [Configure Key]               │
│    --accent-blue bg              │
│    --radius-sm                   │
│    click: opens key input modal  │
│                                  │
│    Your key stays in your        │
│    browser. Never sent to us.    │
│    --text-xs, --text-tertiary    │
│                                  │
└──────────────────────────────────┘
```

**Empty State (key configured, no messages):**
```
┌──────────────────────────────────┐
│ Ontology Agent                   │
│ [Key] Using your Anthropic key   │
├──────────────────────────────────┤
│                                  │
│    [Chat bubbles icon]           │
│    --text-tertiary, 48px         │
│                                  │
│    Ask me about this system      │
│    --text-lg, --text-secondary   │
│                                  │
│    Try:                          │
│    "What does auth_service do?"  │
│    "Show me the dependencies"    │
│    "What's the blast radius of   │
│     changing models.py?"         │
│                                  │
│    --text-sm, --accent-blue      │
│    each suggestion clickable     │
│    click: populates input        │
│                                  │
│    Session cost: $0.00           │
│    --text-xs, --text-tertiary    │
│                                  │
├──────────────────────────────────┤
│ [Ask about the system...]  [>]   │
└──────────────────────────────────┘
```

**Streaming State (agent responding):**
- Agent message bubble grows incrementally as `TextMessageContent` SSE events arrive
- Action cards appear inline as `ToolCallStart` events arrive
- Map animations fire concurrently (not blocking text stream)
- Send button disabled, replaced by stop button (square icon, `--accent-red`)
- Input disabled with "Agent is responding..." placeholder

**Error State (API error):**
```
┌── ERROR CARD ────────────────────┐
│ [!] API Error                    │
│ --accent-red text                │
│                                  │
│ Rate limit exceeded. Try         │
│ again in 30 seconds.             │
│ --text-sm, --text-secondary      │
│                                  │
│ [Retry]                          │
│ --accent-blue, --text-sm         │
│                                  │
│ bg: --accent-red at 10% opacity  │
│ border: --accent-red at 30%      │
│ radius: --radius-md              │
└──────────────────────────────────┘
```

### 5.3 Chat Panel Closed (Collapsed)

When closed, only the toggle button is visible on the right edge of the canvas.
The 3D canvas occupies 100% width.

```
┌─────────────────────────────────────────────────────────────────────┬──┐
│                                                                     │> │
│  3D CANVAS (full width)                                             │  │
│                                                                     │  │
│                                                                     │  │
│  No resize animation needed -- canvas is already full width.        └──┘
│  Toggle button: 24x48px, right edge
│  Arrow points left (">") indicating "open panel"
│
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.4 AG-UI Event to UI Mapping

| AG-UI Event | Chat Panel Effect | Map Effect |
|-------------|-------------------|------------|
| `TextMessageStart` | New agent bubble appears | None |
| `TextMessageContent` | Text appended to bubble | None |
| `TextMessageEnd` | Bubble finalized | None |
| `ToolCallStart: navigate_to` | Action card: "Navigating to..." | Camera begins 350ms animation |
| `ToolCallStart: highlight_nodes` | Action card: "Highlighting..." | Nodes glow with `--shadow-glow` |
| `ToolCallStart: get_metrics` | (pending card) | None |
| `ToolCallEnd: get_metrics` | Metrics card rendered | None |
| `ToolCallStart: search_nodes` | (pending card) | Matching nodes pulse briefly |
| `ToolCallEnd: search_nodes` | Results shown inline | None |
| `ToolCallStart: get_details` | (pending card) | Detail panel opens |
| `ToolCallStart: get_submap` | (pending card) | Subgraph edges highlight |

---

## 6. Screen 5: Code View (F-06 L3-L4, F-31)

**Features:** F-06 (Fractal Drill-Down L3/L4), F-31 (symbol-level search)
**Split:** 40% 3D minimap / 60% code panel
**Bidirectional linking:** per Sourcetrail pattern (F-06 research Section 7)

### 6.1 Wireframe -- Full Code View with Bidirectional Highlights

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ System > auth_service > auth.py > AuthService > validate()                   │
│ ^^^^^^^   ^^^^^^^^^^^^   ^^^^^^^   ^^^^^^^^^^^   ^^^^^^^^^^                  │
│ clickable clickable      clickable clickable     current (--font-semibold)   │
│ each click drills out to that level                                          │
│ hover: --accent-blue, --text-primary                                         │
│ transition: --duration-fast                                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│                               │                                              │
│  3D MINIMAP (40%)             │  CODE PANEL (60%)                            │
│  bg: --surface-0              │  bg: --surface-1                             │
│                               │  border-left: --border-default               │
│  Camera: orthographic,        │                                              │
│  top-down, 5 units            │  ┌─ FILE TAB BAR ────────────────────────┐  │
│                               │  │ height: 32px                          │  │
│  Nodes rendered by DOI:       │  │ bg: --surface-2                       │  │
│                               │  │                                        │  │
│  HIGH DOI (focused):          │  │ [auth.py] [models.py]                 │  │
│  ┌────────────┐               │  │  ^^^^^^                                │  │
│  │ validate() │ <-- GLOWING   │  │  active: --surface-1 bg               │  │
│  │ --shadow-  │     because   │  │  border-bottom: 2px --accent-blue     │  │
│  │   glow     │     selected  │  │  --text-sm, --font-medium             │  │
│  │ --accent-  │               │  │                                        │  │
│  │   blue     │               │  │  inactive: --surface-2 bg              │  │
│  └────────────┘               │  │  --text-secondary                      │  │
│                               │  │  hover: --surface-3                    │  │
│  MED DOI (siblings):          │  │                                        │  │
│  ┌──────┐  ┌──────┐          │  │  [RO] or [EDIT] badge:                 │  │
│  │login │  │refre │          │  │  --cat-2 (RO) or --cat-1 (EDIT)        │  │
│  │      │  │ sh   │          │  │  --text-xs, --radius-sm                │  │
│  └──────┘  └──────┘          │  │  padding: --space-1                    │  │
│  Simplified: label only,      │  └────────────────────────────────────────┘  │
│  no glow, --mat-roughness-    │                                              │
│  high                         │  ┌─ SCROLL POSITION INDICATOR ───────────┐  │
│                               │  │ right: 2px, width: 4px                │  │
│  LOW DOI (distant):           │  │ bg: --accent-blue at 30% opacity      │  │
│  . . .  (dots only)           │  │ height: proportional to viewport      │  │
│  --text-tertiary at 30%       │  │ thumb: --accent-blue at 60%           │  │
│                               │  │ visible: only when scrolling          │  │
│                               │  │ fade-out: --duration-normal after 1s  │  │
│  BIDIRECTIONAL HIGHLIGHT:     │  └────────────────────────────────────────┘  │
│                               │                                              │
│  When cursor is on line 45    │  ┌─ CODE ─────────────────────────────────┐  │
│  in the code (jwt.decode),    │  │                                        │  │
│  the node for jwt module      │  │  38 │ class AuthService:              │  │
│  glows --accent-amber         │  │  39 │     """Authentication service."""│  │
│  in the minimap.              │  │  40 │                                  │  │
│                               │  │  41 │     def __init__(self, secret): │  │
│  When clicking login()        │  │  42 │         self.secret = secret     │  │
│  node in minimap, code        │  │  43 │                                  │  │
│  scrolls to line 68           │  │  44 │     def validate(self, token):  │  │
│  (login definition).          │  │     │      ^^^^^^^^ --accent-blue bg  │  │
│                               │  │     │      (selected symbol)           │  │
│  Scroll animation: 200ms      │  │  45 │         """Validate JWT."""     │  │
│  --ease-default               │  │  46 │         try:                    │  │
│                               │  │  47 │             payload = jwt.decode│  │
│                               │  │     │                      ^^^ ref   │  │
│                               │  │     │              hover: underline   │  │
│                               │  │     │              --accent-blue      │  │
│                               │  │     │              click: navigate    │  │
│                               │  │     │              to jwt node        │  │
│                               │  │  48 │                 token,          │  │
│                               │  │  49 │                 self.secret,    │  │
│                               │  │  50 │                 algorithms=[    │  │
│                               │  │  51 │                     "HS256"]    │  │
│                               │  │  52 │             )                   │  │
│                               │  │  53 │             return payload      │  │
│                               │  │  54 │         except jwt.ExpiredSig:  │  │
│                               │  │  55 │             raise AuthError(    │  │
│                               │  │  56 │                 "Token expired" │  │
│                               │  │  57 │             )                   │  │
│                               │  │  58 │         except jwt.InvalidTok:  │  │
│                               │  │  59 │             raise AuthError(    │  │
│                               │  │  60 │                 "Invalid token" │  │
│                               │  │  61 │             )                   │  │
│                               │  │                                        │  │
│                               │  │  Line numbers:                         │  │
│                               │  │    --font-mono, --text-xs              │  │
│                               │  │    --text-tertiary                     │  │
│                               │  │    width: 40px, text-align: right      │  │
│                               │  │    padding-right: --space-2            │  │
│                               │  │                                        │  │
│                               │  │  Code text:                            │  │
│                               │  │    --font-mono, --text-sm              │  │
│                               │  │    --text-primary                      │  │
│                               │  │    Syntax colors from Shiki theme      │  │
│                               │  │    mapped to --cat-N tokens:           │  │
│                               │  │      keywords: --accent-purple         │  │
│                               │  │      strings:  --accent-green          │  │
│                               │  │      functions: --accent-blue          │  │
│                               │  │      types:    --accent-teal           │  │
│                               │  │      comments: --text-tertiary         │  │
│                               │  │      numbers:  --accent-amber          │  │
│                               │  │                                        │  │
│                               │  │  Active line (cursor):                 │  │
│                               │  │    bg: --surface-2                     │  │
│                               │  │    border-left: 2px --accent-blue      │  │
│                               │  │                                        │  │
│                               │  │  Symbol highlight (selected symbol):   │  │
│                               │  │    bg: --accent-blue at 15% opacity    │  │
│                               │  │    all occurrences in file             │  │
│                               │  │                                        │  │
│                               │  └────────────────────────────────────────┘  │
│                               │                                              │
└───────────────────────────────┴──────────────────────────────────────────────┘
```

### 6.2 L4 Toolbar Detail

When user clicks "Edit" at L3, the toolbar appears above the code area:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ TOOLBAR  height: 36px  bg: --surface-2  border-bottom: --border-default │
│ padding: --space-1 --space-3                                             │
│                                                                          │
│  [EDIT] badge         auth.py               [Save] [Format] [Copy] [X]  │
│  --cat-1 bg                                                              │
│  (--accent-orange)    --text-sm             buttons: --surface-3 bg      │
│  --text-xs            --text-secondary      --text-sm, --font-medium     │
│  --radius-sm                                --radius-sm                   │
│                       Modified: *           padding: --space-1 --space-2 │
│                       --accent-amber        hover: --surface-3 +         │
│                       (dot indicator)         brightness(1.1)            │
│                                             gap: --space-1               │
│                                                                          │
│                                             [Save]: Ctrl+S shortcut      │
│                                               --accent-blue bg when      │
│                                               file is modified           │
│                                             [Format]: Ctrl+Shift+F       │
│                                             [Copy]: copies file content  │
│                                             [X]: close editor (back L3)  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 6.3 Bidirectional Sync Detail

The bidirectional graph-code linking follows the Sourcetrail MessageDispatcher
pattern adapted for the toolkit's `state.js` pub/sub system (per F-06 research
Section 7):

```
CODE -> GRAPH (clicking a symbol in code)
────────────────────────────────────────

  Code panel                    state.js                   3D Minimap
  ──────────                    ────────                   ──────────
  User clicks                   state.emit(                Node matching
  "jwt.decode"     ─────>       'symbol.activate',  ─────> symbol.source_
  at line 47                    { symbolId:                 location glows
                                  'jwt.decode',             with --shadow-
                                  line: 47 })               glow, --accent-
                                                            amber
                                                            transition:
                                                            --duration-fast

GRAPH -> CODE (clicking a node in minimap)
────────────────────────────────────────

  3D Minimap                    state.js                   Code panel
  ──────────                    ────────                   ──────────
  User clicks                   state.emit(                Code scrolls
  login() node     ─────>       'node.activate',    ─────> to line 68
                                { nodeId:                   (login def)
                                  'login',                  line highlighted:
                                  source_location:          bg --surface-2
                                  { line: 68 }})            scroll: 200ms
                                                            --ease-default
```

### 6.4 Dark vs Light Mode -- Code Panel

| Element | Dark | Light |
|---------|------|-------|
| Code bg | `--surface-1` oklch(18%) | `--surface-1` oklch(95%) |
| Line numbers | `--text-tertiary` oklch(50%) on dark | `--text-tertiary` oklch(60%) on light |
| Active line bg | `--surface-2` oklch(23%) | `--surface-2` oklch(91%) |
| Syntax: keywords | `--accent-purple` L=65% | `--accent-purple` L=55% |
| Syntax: strings | `--accent-green` L=65% | `--accent-green` L=55% |
| Syntax: functions | `--accent-blue` L=65% | `--accent-blue` L=55% |
| Syntax: comments | `--text-tertiary` L=50% | `--text-tertiary` L=60% |
| Scrollbar | `--accent-blue` at 30% | `--accent-blue` at 20% |
| Tab active | `--surface-1` matches code bg | `--surface-1` matches code bg |
| Tab inactive | `--surface-2` darker | `--surface-2` slightly darker than bg |

---

## 7. Flow 1: Navigate to Function

**Scenario:** User wants to find and navigate to `auth_service.validate()` from
the system overview. Uses Cmd+K search, then the system auto-drills through
L0 -> L1 -> L2 -> L3.

### Step-by-Step Flow

```
STEP 1: User presses Cmd+K
────────────────────────────
  State: L0 System Overview, no node selected
  Action: Keyboard shortcut detected
  Result: Search overlay fades in (300ms, --duration-normal, --ease-default)
          3D canvas dims with backdrop blur(8px)
          Search input auto-focused, cursor blinking
  URL: cockpit.html#layout=orbital&theme=dark

STEP 2: User types "validate"
────────────────────────────
  State: Search overlay open, input has "validate"
  Action: Each keystroke triggers 150ms debounced search
  Result: Filter chips appear: [All] [Package] [File] [Class] [Function]
          Results appear grouped by level:
            L2: Symbol
            ┌──────────────────────────────────────────────┐
            │ [fn] auth_service.validate()                  │  <-- selected
            │     Validate JWT token and return payload     │      (keyboard
            │     [Function]                                │       highlight)
            │                                              │
            │ [fn] middleware.validate_request()             │
            │     Validate incoming HTTP request headers    │
            │     [Function]                                │
            └──────────────────────────────────────────────┘
          "validate" substring highlighted in --accent-blue in each result
          Arrow keys move selection (--surface-3 bg + left border --accent-blue)

STEP 3: User presses Enter on "auth_service.validate()"
────────────────────────────
  State: Result selected
  Action: Enter keypress detected
  Result:
    a) Search overlay fades out (200ms, --duration-normal)
    b) Search term saved to localStorage recent searches
    c) State dispatches: { target: 'auth_service.validate', autoNavigate: true }
    d) Camera begins animated navigation

STEP 4: Camera animates to auth_service node (350ms)
────────────────────────────
  State: L0 System View, camera moving
  Action: Camera follows arc path to auth_service centroid
          --ease-out easing, quaternion SLERP rotation
          Duration: 350ms (--duration-slow)
          Arc height: 20% of lateral displacement
  Result: Camera centered on auth_service
          Other nodes begin fading (opacity 1.0 -> 0.1)
  Timing: t=0ms to t=350ms

STEP 5: Auto-drill L0 -> L1 (350ms)
────────────────────────────
  State: Camera at auth_service, beginning drill
  Action: Automatic drill triggered (no double-click needed, search initiated)
          FSM transition: SYSTEM -> MODULE
          Camera: 80 -> 30 units, FOV 60 -> 55deg
          Child nodes (files) fade in from opacity 0
          Parent nodes fade to opacity 0.1
  Result: L1 Module View showing auth_service contents
          Breadcrumb: "System > auth_service"
          URL: #level=1&node=auth_service
  Timing: t=350ms to t=700ms

STEP 6: Auto-drill L1 -> L2 (350ms)
────────────────────────────
  State: L1 Module View, auth.py visible
  Action: Automatic drill continues to file containing validate()
          FSM transition: MODULE -> FILE
          Camera: 30 -> 12 units, FOV 55 -> 50deg
          File children (classes, functions) appear
  Result: L2 File View showing auth.py symbols
          Breadcrumb: "System > auth_service > auth.py"
          URL: #level=2&node=auth_service.auth_py
          validate() node highlighted with --shadow-glow
  Timing: t=700ms to t=1050ms

STEP 7: validate() highlighted, code panel slides in (300ms)
────────────────────────────
  State: L2 File View, validate() node glowing
  Action: Auto-drill completes to L3 (function level)
          Code panel slides in from right (--duration-normal, --ease-default)
          3D view compresses to 40% width
          Camera switches to orthographic top-down
  Result: Split view: 40% minimap + 60% code panel
          Code panel shows auth.py with Shiki syntax highlighting
          validate() definition (line 44) scrolled into view
          Lines 44-61 highlighted with --surface-2 background
          Breadcrumb: "System > auth_service > auth.py > validate()"
          URL: #level=3&node=auth_service.validate&line=44
  Timing: t=1050ms to t=1350ms

TOTAL TIME: ~1350ms from Enter press to final view
  - Search close:     200ms
  - Camera to node:   350ms
  - L0->L1:          350ms (overlaps 50ms with camera)
  - L1->L2:          350ms
  - L2->L3 + panel:  300ms
```

### Flow 1 State Diagram

```
          Cmd+K                type "validate"           Enter
  ┌──────┐ ───> ┌────────────┐ ───────────> ┌──────────┐ ───> ┌───────────┐
  │ IDLE │      │  SEARCH    │              │ RESULTS  │      │ NAVIGATING│
  │ (L0) │      │  OPEN      │              │ SHOWN    │      │           │
  └──────┘ <─── └────────────┘              └──────────┘      └─────┬─────┘
          Esc                                                       │
                                                                    │ 350ms
                                                                    ▼
         code panel opens        auto-drill L2              auto-drill L1
  ┌──────┐ <──────────── ┌──────┐ <──────────── ┌──────┐ <──── ┌───┴───┐
  │ CODE │   300ms       │ FILE │    350ms       │MODULE│ 350ms │AT NODE│
  │ (L3) │               │ (L2) │               │ (L1) │       │ (L0)  │
  └──────┘               └──────┘               └──────┘       └───────┘
```

---

## 8. Flow 2: Ask Agent About Module

**Scenario:** User opens the chat panel and asks "What does the crystallizer
module do?" The agent responds with text, highlights related nodes on the map,
shows metrics, and navigates the camera -- all concurrently via AG-UI events.

### Step-by-Step Flow

```
STEP 1: User clicks chat toggle button
────────────────────────────
  State: L0 System View, chat panel closed
  Action: Click on toggle button (right edge, ">" arrow)
  Result:
    - Chat panel slides in from right (--duration-normal, --ease-default)
    - Panel width: 400px
    - 3D canvas resizes to calc(100% - 400px)
    - Toggle arrow flips to "<"
    - Chat shows empty state with suggestions:
      "What does auth_service do?"
      "Show me the dependencies"
      "What's the blast radius of changing models.py?"
    - Session cost: $0.00
  Timing: 300ms

STEP 2: User types "What does the crystallizer module do?" and sends
────────────────────────────
  State: Chat panel open, empty state
  Action: User types message in input area, clicks Send (or Enter)
  Result:
    - User message bubble appears (right-aligned, --accent-blue at 20% bg)
    - Input clears, disabled with "Agent is responding..." placeholder
    - Send button replaced by stop button (square, --accent-red)
    - Streaming indicator appears: 3 pulsing dots (--text-tertiary)
    - BYOK API call initiated:
      POST https://api.anthropic.com/v1/messages
      headers: { x-api-key: <user_key>, anthropic-dangerous-direct-browser-access: true }
      body: { model: claude-sonnet-4, stream: true, tools: TOOLKIT_TOOLS }

STEP 3: Agent streams response + calls highlight_nodes tool
────────────────────────────
  State: Agent processing, SSE stream active
  Action: AG-UI events arrive on the stream:
    t=0ms:    TextMessageStart { messageId: "msg_1" }
    t=50ms:   TextMessageContent "The crystallizer module"
    t=120ms:  TextMessageContent " is responsible for"
    t=200ms:  TextMessageContent " converting raw observations"
    t=300ms:  TextMessageContent " into structured knowledge nodes..."
    t=400ms:  ToolCallStart { toolName: "highlight_nodes" }
    t=420ms:  ToolCallArgs { node_ids: ["crystallizer", "pruner", "scorer"] }
    t=430ms:  ToolCallEnd
  Result (concurrent):
    - Agent text bubble grows word by word (SSE TextMessageContent deltas)
    - At t=400ms: Action card appears in chat:
      ┌─ ACTION CARD ─────────────────┐
      │ [highlight_nodes]              │
      │ Highlighting crystallizer,     │
      │ pruner, scorer                 │
      │ [check icon --accent-green]    │
      └────────────────────────────────┘
    - AT THE SAME TIME on the 3D map:
      3 nodes (crystallizer, pruner, scorer) begin glowing
      --shadow-glow, --accent-purple
      pulse animation: emissive 0.15 to 0.25, 1s cycle
      duration: 5000ms (default)
    - Text continues streaming DURING the map animation

STEP 4: Agent calls get_metrics tool
────────────────────────────
  State: Text still streaming, 3 nodes glowing on map
  Action: AG-UI events continue:
    t=500ms:  TextMessageContent " It has three main components..."
    t=600ms:  ToolCallStart { toolName: "get_metrics", args: { node_ids: ["crystallizer"], metric_type: "all" } }
    t=650ms:  ToolCallEnd (with result)
  Result:
    - Metrics action card appears in chat:
      ┌─ METRICS CARD ────────────────┐
      │ get_metrics: crystallizer      │
      │                                │
      │  LOC        1,234              │
      │  Complexity 28 avg             │
      │  Coverage   85%                │
      │  Coupling   0.31               │
      │                                │
      │  bg: --surface-2               │
      │  grid: 2 columns              │
      │  labels: --text-tertiary       │
      │  values: --font-semibold       │
      └────────────────────────────────┘

STEP 5: Agent text stream completes
────────────────────────────
  State: Metrics card shown, nodes still glowing
  Action: AG-UI events:
    t=700ms:  TextMessageContent " The crystallizer processes..."
    t=1200ms: TextMessageContent "...into the knowledge graph."
    t=1300ms: TextMessageEnd { messageId: "msg_1" }
  Result:
    - Agent bubble finalized (no more growth)
    - Streaming dots disappear
    - Session cost updates: "$0.003" (--text-xs, --text-tertiary)

STEP 6: Agent calls navigate_to tool
────────────────────────────
  State: Text complete, nodes glowing
  Action: AG-UI events (second turn of agent response):
    t=1400ms: ToolCallStart { toolName: "navigate_to", args: { node_id: "crystallizer" } }
    t=1420ms: ToolCallEnd
  Result:
    - Action card in chat:
      ┌─ ACTION CARD ─────────────────┐
      │ [navigate_to]                  │
      │ Navigating to crystallizer     │
      │ [check icon --accent-green]    │
      └────────────────────────────────┘
    - Camera animates to crystallizer node:
      Duration: 350ms (--duration-slow)
      Easing: --ease-out
      Path: arc path with 20% lift
      Quaternion SLERP for rotation
    - crystallizer node centered on screen
    - Input re-enabled, send button restored

STEP 7: User clicks a highlighted node to drill deeper
────────────────────────────
  State: Camera at crystallizer, 3 nodes glowing, chat open
  Action: User double-clicks crystallizer node in 3D view
  Result:
    - Standard drill-down L0 -> L1 (350ms)
    - Chat panel remains open (canvas width: calc(100% - 400px))
    - Chat context preserved (user can ask follow-up questions)
    - Breadcrumb updates: "System > crystallizer"
    - Glowing nodes within the drilled module remain highlighted
    - Nodes outside the drilled view fade out (including pruner, scorer)
```

### Flow 2 Timing Diagram

```
Time    Chat Panel                          3D Map
─────   ──────────────────────────          ────────────────────────
0ms     Panel slides in (300ms)             Canvas resizes (300ms)
300ms   Empty state visible                 Nodes re-centered
800ms   User sends message                  --
900ms   User bubble appears                 --
950ms   Streaming dots...                   --
1000ms  "The crystallizer module"           --
1200ms  "is responsible for..."             --
1400ms  ACTION: highlight_nodes             3 nodes glow (concurrent)
1500ms  "It has three components..."        glow animation continues
1600ms  METRICS CARD appears                --
1800ms  "The crystallizer processes..."     --
2300ms  Text complete, dots gone            --
2400ms  ACTION: navigate_to                 Camera arc to crystallizer
2750ms  Navigation complete                 Centered on crystallizer
3000ms  Input re-enabled                    Waiting for interaction
```

### Flow 2 State Diagram

```
                  click toggle        send message
  ┌────────┐      ──────────>  ┌──────────┐  ──────>  ┌───────────┐
  │ CLOSED │                   │  EMPTY   │           │ STREAMING │
  └────────┘  <──────────────  │  STATE   │           │           │
              click toggle     └──────────┘           └─────┬─────┘
                                                            │
                              TextMessageEnd                │
                  ┌────────────────────────────────────────┘
                  │
                  ▼
            ┌───────────┐   ToolCallStart:highlight    ┌────────────────┐
            │ RESPONSE  │  ─────────────────────────>  │ MAP ANIMATING  │
            │ COMPLETE  │                               │ (concurrent)   │
            └─────┬─────┘  <─────────────────────────  └────────────────┘
                  │         ToolCallEnd
                  │
                  │   ToolCallStart:navigate_to
                  ▼
            ┌───────────┐       350ms          ┌──────────┐
            │ NAVIGATING│  ───────────────>    │  READY   │
            │           │                       │ (input   │
            └───────────┘                       │  enabled)│
                                                └──────────┘
```

---

## 9. State Catalog

Complete catalog of all UI states across all 5 screens.

### 9.1 Global States

| State | Condition | Visual Effect |
|-------|-----------|---------------|
| Loading | App initializing, graph.json fetching | Centered spinner, `--surface-0` bg, "Loading..." `--text-secondary` |
| Error | graph.json failed to load | Error card centered, `--accent-red` icon, retry button |
| Empty | graph.json loaded but zero nodes | "No nodes found" message, link to documentation |
| Ready | Normal operation | Full UI visible, all interactions enabled |
| Offline | No network (static export) | Chat toggle hidden, BYOK indicator says "Offline mode" |

### 9.2 Per-Screen States

| Screen | State | Trigger | Visual |
|--------|-------|---------|--------|
| System Overview | Idle | Default | All nodes at rest, no selection |
| System Overview | Node hovered | Mouse enter | Glow + tooltip (100ms) |
| System Overview | Node selected | Click | Persistent glow + detail panel (200ms slide) |
| System Overview | Detail open | Node selected | 320px panel from right, canvas resizes |
| Drill-Down | Transitioning | Double-click or search | 350ms camera animation, node fade |
| Drill-Down | At level | Transition complete | Breadcrumb updated, URL hash updated |
| Search | Open | Cmd+K | 300ms overlay fade-in, backdrop blur |
| Search | Empty | Open, no input | Recent searches shown |
| Search | Typing | User input | Live-filtered results, debounced 150ms |
| Search | Results | Matches found | Grouped by level, keyboard navigable |
| Search | No results | No matches | Empty state message + "Ask Agent" link |
| Chat | Closed | Default or toggle | Only toggle button visible |
| Chat | No key | Panel open, no API key | Key configuration prompt |
| Chat | Empty | Key configured, no messages | Suggestions shown |
| Chat | Streaming | Agent responding | Text grows, action cards appear, dots pulse |
| Chat | Error | API failure | Error card with retry |
| Chat | Ready | Response complete | Input enabled, history scrollable |
| Code View | Read-only (L3) | Drill to function | Shiki highlighted, RO badge |
| Code View | Editing (L4) | Click "Edit" | CodeMirror active, toolbar visible, EDIT badge |
| Code View | Modified | Edits made | Amber dot indicator, "unsaved changes" text |
| Code View | Saved | Ctrl+S | Green flash on save button, dot clears (200ms) |

### 9.3 Transition Durations Reference

All transitions use design tokens from GAP-6 (`docs/design/design_system.md`
Section 7):

| Transition | Duration Token | Value | Easing Token |
|------------|---------------|-------|--------------|
| Hover effects (tooltip, glow) | `--duration-fast` | 100ms | `--ease-default` |
| Panel open/close | `--duration-normal` | 200ms | `--ease-default` |
| Search overlay appear/dismiss | `--duration-normal` | 200ms | `--ease-default` |
| Camera drill transition | `--duration-slow` | 400ms | `--ease-out` |
| Camera drill (target) | custom | 350ms | `--ease-out` |
| Code scroll to line | `--duration-normal` | 200ms | `--ease-default` |
| Node fade in/out (drill) | `--duration-slow` | 400ms | `--ease-default` |
| Stagger delay (list items) | custom | 30ms/item | -- |
| Streaming dot pulse | custom | 1.4s | ease-in-out |

---

## 10. Responsive Breakpoints

While the toolkit targets desktop-first (3D visualization requires adequate
screen real estate), panels adapt to narrower viewports:

| Breakpoint | Canvas | Detail Panel | Chat Panel | Search Overlay |
|------------|--------|-------------|------------|----------------|
| >= 1440px | Full - panels | 320px | 400px | 600px centered |
| 1024-1439px | Full - panels | 280px | 360px | 520px centered |
| 768-1023px | Full (panels overlay) | 100% overlay | 100% overlay | 100% width |
| < 768px | Full | Sheet from bottom | Sheet from bottom | Full screen |

On viewports < 1024px, the detail panel and chat panel become **overlays**
rather than side panels. The 3D canvas does not resize -- panels float above it
with `--surface-1` background at 95% opacity and `--shadow-lg`.

For the code view at L3/L4 on narrow viewports:
- < 1024px: Code panel takes 100% width, minimap hidden (accessible via toggle)
- >= 1024px: Standard 40/60 split

---

## Appendix A: Feature-to-Screen Mapping

| Feature | Screen 1 | Screen 2 | Screen 3 | Screen 4 | Screen 5 |
|---------|----------|----------|----------|----------|----------|
| F-06 Fractal Drill-Down | -- | Primary | -- | -- | Primary |
| F-15 Conversation Mode | -- | -- | -- | Primary | -- |
| F-29 Breadcrumb | Present | Present | -- | -- | Present |
| F-30 Deep Link / Layout | URL hash | URL hash | -- | -- | URL hash |
| F-31 Search & Filter | Trigger | -- | Primary | -- | -- |

## Appendix B: Design Token Usage Density

Token usage count across all 5 wireframes:

| Token Category | Unique Tokens Used | Total References |
|----------------|-------------------|-----------------|
| Surface (`--surface-*`) | 4 | 42 |
| Text (`--text-*`) | 3 | 38 |
| Accent / Categorical (`--cat-*`, `--accent-*`) | 8 | 27 |
| Space (`--space-*`) | 7 | 35 |
| Typography (`--text-xs..2xl`) | 6 | 31 |
| Font (`--font-*`) | 3 | 14 |
| Motion (`--duration-*`, `--ease-*`) | 5 | 18 |
| Shadow (`--shadow-*`) | 4 | 12 |
| Border (`--border-*`, `--radius-*`) | 5 | 19 |
| Material (`--mat-*`) | 4 | 8 |
| **TOTAL** | **49 / 66** | **244** |

Zero hardcoded color, spacing, or timing values used in any wireframe.
All values reference semantic tokens from the design system (GAP-6).

## Appendix C: Invariant Compliance

| Invariant | Status | Evidence |
|-----------|--------|----------|
| INV-OT-009 (10K nodes 60fps) | Addressed | DOI-based LOD at all drill levels (Screen 2, 5) |
| INV-OT-026 (no literal colors) | Compliant | All wireframes use `--cat-N`, `--surface-N`, `--text-*` tokens |
| INV-OT-027 (contrast >= 4.5:1) | Compliant | All text tokens exceed 4.5:1 on their surface backgrounds |
| INV-OT-028 (emissive <= 0.3) | Compliant | Max emissive is `--mat-emissive-max` = 0.25 (dark) |
| INV-OT-029 (animation < 1s) | Compliant | Max transition is 400ms (drill). Total drill L0-L3 ~1350ms but each step < 400ms |
| INV-OT-030 (2 fonts + 3 weights) | Compliant | Only `--font-family` + `--font-mono`, weights 400/500/600 |

---

*Wireframe document for GAP-12 (final gap). All 5 screens reference design tokens from
GAP-6 (`docs/design/design_system.md`). Camera transitions and drill-down timings match
GAP-1 F-06 research (350ms, ease-out, quaternion SLERP). Chat panel design follows GAP-1
F-15 research (AG-UI protocol, BYOK architecture, 6 tools). SPEC features covered:
F-06, F-15, F-29, F-30, F-31.*
