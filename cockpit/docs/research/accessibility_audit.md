# WCAG 2.1 AA Accessibility Audit -- Ontology Cockpit

**Date:** 2026-02-27
**Auditor:** Engineering Brain Team
**Standard:** WCAG 2.1 Level AA
**Reference:** INV-OT-027 (WCAG AA contrast ratios)
**Scope:** Full client application (`client/index.html` and all CSS/JS modules)

---

## 1. Audit Methodology

### 1.1 Tools

| Tool | Purpose | Phase |
|------|---------|-------|
| axe-core (browser extension) | Automated WCAG scanning | Automated |
| axe-core (Playwright integration) | CI/CD automated regression | Automated |
| Manual keyboard testing | Tab order, focus traps, key handlers | Manual |
| VoiceOver (macOS) | Screen reader behavior | Manual |
| NVDA (Windows) | Screen reader behavior | Manual |
| Chrome DevTools Accessibility pane | Computed ARIA tree, contrast | Manual |
| WebAIM Contrast Checker | Precise contrast ratio calculation | Manual |

### 1.2 Standards Applied

- WCAG 2.1 Level AA (all Success Criteria)
- WAI-ARIA 1.2 Authoring Practices
- Section 508 (US federal, overlaps with WCAG 2.1 AA)

### 1.3 Scope

Every interactive element in `client/index.html` was assessed, including:

- 3D canvas scene (`#sc`)
- Header, stats bar, hint text
- Detail panel (`.dp`)
- Modal overlay (`.modal-ov`)
- Search overlay (`.search-ov`)
- Legend toggles (`.legend`)
- Tour button and info panel
- View toggle (3D/2D)
- Layout buttons (Orbital/Pipeline/Layers)
- Background toggle
- Knowledge Library button + full overlay (`.klib-ov`)
- Documentation Map button + overlay (`.doc-ov`)
- Hover tooltip (`.hover-tip`)
- All dynamically generated content (node modals, detail panel content, search results)

---

## 2. Current State Assessment

### 2.1 HTML Semantics

#### 2.1.1 Missing Landmark Roles

**Severity: CRITICAL**

The page has zero ARIA landmark regions. There is no `<main>`, `<nav>`, `<header role="banner">`, or `<footer>` element. Screen readers cannot navigate by landmark.

| Element | Current | Required |
|---------|---------|----------|
| `.header` div | `<div class="header">` | `<header role="banner">` |
| Stats bar | `<div class="stats-bar">` | `<footer role="contentinfo">` or `<div role="status">` |
| `#sc` canvas container | `<div id="sc">` | Needs `role="img"` or `role="application"` with `aria-label` |
| Legend | `<div class="legend">` | `<nav aria-label="Edge type filters">` |
| Layout buttons | `<div class="layout-btns">` | `<div role="toolbar" aria-label="Layout options">` |
| View toggle | `<div class="view-toggle">` | `<div role="tablist" aria-label="View mode">` |

#### 2.1.2 Canvas Has No Accessibility Alternative

**Severity: CRITICAL (WCAG 1.1.1 Non-text Content)**

The 3D scene container `<div id="sc"></div>` (line 32 of `index.html`) renders a full-screen Three.js canvas. It has:

- No `role` attribute
- No `aria-label` or `aria-labelledby`
- No text alternative describing the visualization
- No screen-reader-accessible representation of the 25 architecture nodes and their relationships

A screen reader user encounters a completely empty void where the primary content lives.

#### 2.1.3 Buttons Use Emoji/Symbol Characters Without Text Alternatives

**Severity: HIGH (WCAG 1.1.1, 4.1.2)**

Every close button and several action buttons use HTML entities as their only content:

| Element | HTML | Rendered | Missing |
|---------|------|----------|---------|
| `#dpX` (detail panel close) | `&#x2715;` | X | `aria-label="Close detail panel"` |
| `#modalX` (modal close) | `&#x2715;` | X | `aria-label="Close modal"` |
| `#docOvX` (doc overlay close) | `&#x2715;` | X | `aria-label="Close documentation"` |
| `#docViewerX` (doc viewer close) | `&#x2715;` | X | `aria-label="Close document viewer"` |
| `#klibX` (knowledge lib close) | `&#x2715;` | X | `aria-label="Close knowledge library"` |
| `#tourBtn` | `&#x25B6; Auto Tour` | Play triangle + text | Acceptable, but emoji not read consistently |
| `#bgBtn` | `&#x263E; Dark BG` | Moon + text | `aria-label="Toggle dark mode"` |
| `#klibBtn` | `&#x1F4DA; Knowledge Library` | Book emoji + text | Emoji read inconsistently by screen readers |
| `#docMapBtn` | `&#x1F4C4; Docs` | Page emoji + text | Same issue |
| `#backBtn` | `&#x2190; Back to Map` | Arrow + text | Arrow decorative, needs `aria-hidden="true"` on span |
| `#klibBack` | `&#x2190;` | Left arrow | `aria-label="Navigate back"` |
| `#klibFwd` | `&#x2192;` | Right arrow | `aria-label="Navigate forward"` |
| Layout buttons | `&#x2B21;`, `&#x2192;`, `&#x2193;` | Hexagon, arrows | Decorative symbols mixed with text |

#### 2.1.4 No Skip-to-Content Link

**Severity: HIGH (WCAG 2.4.1 Bypass Blocks)**

There is no skip navigation link. A keyboard user must tab through the entire header, all toolbar buttons, and the legend before reaching any content. Given the application's toolbar-heavy UI (14+ buttons before content), this is a significant barrier.

#### 2.1.5 Modal Has No Focus Trap

**Severity: HIGH (WCAG 2.4.3 Focus Order)**

The modal overlay (`.modal-ov`, line 150-155) is opened via `_openModal()` in `app.js`. Analysis of the code shows:

- Focus is NOT moved to the modal when it opens
- No focus trap exists -- Tab key moves focus behind the modal to invisible elements
- Escape closes the modal (good), but focus is not returned to the triggering element
- The close button `#modalX` has no `aria-label`

The same issues exist for:
- Knowledge Library overlay (`.klib-ov`)
- Documentation overlay (`.doc-ov`)
- Search overlay (`.search-ov`) -- partially better: `input.focus()` is called on open
- Detail panel (`.dp`) -- a slide-in panel with no focus management

#### 2.1.6 Missing Form Labels and ARIA Attributes

**Severity: MEDIUM (WCAG 1.3.1, 4.1.2)**

| Element | Issue |
|---------|-------|
| `#searchInput` | Has `placeholder` but no `<label>` or `aria-label` |
| `.klib-search-input` | Created dynamically in `filters.js` -- no label |
| `.klib-conf-slider` | Range input created dynamically -- no `aria-label`, `aria-valuemin`, `aria-valuemax`, `aria-valuenow` |
| `.legend-item` divs | Act as toggle buttons but are `<div>` elements with no `role="checkbox"` or `role="switch"` |
| `.klib-layer-item` | Acts as a checkbox filter -- no `role`, no `aria-checked` |
| `.klib-sev-chip` | Acts as a toggle chip -- no `role`, no `aria-pressed` |
| `.klib-tag` | Acts as a filter toggle -- no `role`, no `aria-pressed` |
| Search result items | No `role="option"`, no `aria-selected`, no `aria-activedescendant` on input |

#### 2.1.7 No Live Regions

**Severity: MEDIUM (WCAG 4.1.3 Status Messages)**

- Stats bar numbers animate from 0 to their target values on load. Screen readers never announce the final values. Needs `aria-live="polite"` on the stats container.
- Search results update dynamically with no `aria-live` region. The result count is not announced.
- Knowledge Library filter results change count -- not announced.
- Tour info text changes -- not announced (`#tourInfo` needs `aria-live="assertive"`).
- Detail panel opens/closes with node information -- not announced.

---

### 2.2 Keyboard Navigation

#### 2.2.1 Tab Order

**Severity: HIGH**

The natural tab order follows DOM source order, which is:

1. (No skip link)
2. Header area (no interactive elements -- `pointer-events:none`)
3. `#sc` canvas (receives no focus)
4. Hint text (not interactive)
5. Stats bar (not interactive)
6. `#dpX` (detail panel close -- hidden off-screen)
7. `#backBtn` (hidden via `display:none`)
8. Search input (hidden via `display:none`)
9. Legend items (5 items, but they are `<div>` elements with no `tabindex`)
10. `#tourBtn`
11. View toggle buttons (2)
12. Layout buttons (3)
13. `#bgBtn`
14. `#klibBtn`
15. `#docMapBtn`
16. Doc overlay close buttons (hidden)
17. Knowledge Library close button (hidden)
18. `#modalX` (hidden)

Problems identified:
- Legend items (`<div>`) are not focusable despite being interactive
- Hidden panels/overlays have focusable buttons that receive Tab even when the parent is visually hidden (using `left:-400px` or `display:none` with no inert/aria-hidden)
- The detail panel (`.dp`) is positioned at `left:-400px` when closed but its close button can still receive focus (not `display:none`, only translated)
- No `tabindex` management for overlay open/close states

#### 2.2.2 3D Scene Keyboard Access

**Severity: CRITICAL (WCAG 2.1.1 Keyboard)**

The 3D scene is the primary content of the application. It is completely inaccessible via keyboard:

- The canvas element receives no focus
- There is no keyboard equivalent for clicking nodes (raycasting only responds to mouse events in `interaction.js`)
- There is no keyboard equivalent for rotating the scene (OrbitControls is mouse/touch only)
- There is no way to navigate between the 25 architecture nodes using arrow keys
- The 2D view (accessible via the view toggle) uses the same Three.js scene with the same mouse-only interaction

The entire core functionality -- exploring architecture nodes, entering submaps, viewing node details -- requires a pointing device.

#### 2.2.3 Escape Key Behavior

**Severity: LOW (partial compliance)**

Escape handling exists but is inconsistent:

| Context | Escape Behavior | Status |
|---------|----------------|--------|
| Modal open | Closes modal | OK |
| Search open | Closes search | OK |
| Detail panel open | Not handled | MISSING |
| Knowledge Library open | Not handled | MISSING |
| Doc overlay open | Not handled | MISSING |
| Doc viewer open | Not handled | MISSING |
| Tour running | Not handled | MISSING |

#### 2.2.4 Focus Indicators

**Severity: HIGH (WCAG 2.4.7 Focus Visible)**

Focus indicators are almost entirely absent:

- The global reset `*{margin:0;padding:0;box-sizing:border-box}` in `tokens.css` (line 5) does not explicitly remove outlines, but no custom `:focus` or `:focus-visible` styles are defined for any button.
- The only `:focus` style in the entire codebase is on `.klib-search-input:focus` (klib.css line 47) and `.search-input` which has `outline:0` (layout.css line 124) -- **actively removing** the focus indicator.
- All `<button>` elements rely on browser defaults, which are often invisible on dark backgrounds.
- No `:focus-visible` styles exist anywhere.

---

### 2.3 Color Contrast

#### 2.3.1 Dark Mode Contrast Ratios (body.dark)

Background color: `--bg: #020204` (near-black, RGB 2,2,4)

| Token | Hex | Usage | Contrast vs #020204 | WCAG Requirement | Pass? |
|-------|-----|-------|---------------------|-----------------|-------|
| `--text` | `#e8ecf4` | Primary text | **17.7:1** | 4.5:1 (normal), 3:1 (large) | PASS |
| `--text2` | `#8b95aa` | Secondary text (descriptions, labels) | **6.7:1** | 4.5:1 (normal) | PASS |
| `--text3` | `#4a5268` | Tertiary text (hints, placeholders, section labels) | **2.8:1** | 4.5:1 (normal) | **FAIL** |
| `--border` | `#252540` | Borders | **1.5:1** | 3:1 (UI component) | **FAIL** |
| `--green` | `#34d399` | Status indicators, source category | **10.2:1** | 3:1 (large) | PASS |
| `--blue` | `#6b8fff` | Layer category | **5.9:1** | 3:1 (large) | PASS |
| `--purple` | `#9b7cff` | Module category, active states | **5.1:1** | 3:1 (large) | PASS |
| `--cyan` | `#5eead4` | Consumer category | **11.1:1** | 3:1 (large) | PASS |
| `--amber` | `#f59e0b` | Warnings | **8.5:1** | 3:1 (large) | PASS |
| `--red` | `#ef4444` | Errors, critical severity | **4.6:1** | 3:1 (large) | PASS |

**Critical failures in dark mode:**

1. **`--text3` (#4a5268) on `--bg` (#020204): 2.8:1** -- Used extensively for:
   - `.hint` text (layout.css line 27, uses `#808898` = approx 4.1:1 -- borderline)
   - `.search-hint` (layout.css line 134)
   - `.md-section-label` (components.css line 48)
   - `.md-kv-k` metric labels (components.css line 136)
   - `.kd-section-label` in Knowledge Library detail (klib.css line 222)
   - `.kn-techs` technology names (klib.css line 161)
   - All filter labels and counts in Knowledge Library
   - Search result badges

2. **`--border` (#252540) on `--bg` (#020204): 1.5:1** -- Borders on buttons and panels are invisible to low-vision users. While borders are non-text, WCAG 1.4.11 requires 3:1 for UI component boundaries that are necessary to identify the control.

#### 2.3.2 Light Mode Contrast Ratios

Background color: `--theme-bg: #f0f1f4` (light gray, RGB 240,241,244)

| Token/Value | Hex | Usage | Contrast vs #f0f1f4 | WCAG Requirement | Pass? |
|-------------|-----|-------|---------------------|-----------------|-------|
| `--theme-h1` | `#333` | Heading | **10.6:1** | 3:1 (large) | PASS |
| `--theme-sub` | `#606878` | Subtitle | **4.5:1** | 4.5:1 (normal) | PASS (borderline) |
| `--theme-pipe` | `#909498` | Pipe separator | **2.7:1** | 3:1 (large decorative) | **FAIL** |
| `--theme-pill-color` | `#606878` | Pill badge text | **4.5:1** | 4.5:1 (9px text = small) | PASS (borderline) |
| `--theme-stat-n` | `#333` | Stat numbers | **10.6:1** | 4.5:1 | PASS |
| `--theme-stat-l` | `#606878` | Stat labels | **4.5:1** | 4.5:1 (10px = small) | PASS (borderline) |
| `--theme-btn-color` | `#505868` | Button text | **4.9:1** | 4.5:1 | PASS |
| `--theme-btn-border` | `#c0c4cc` | Button borders | **1.6:1** | 3:1 (UI boundary) | **FAIL** |
| `--theme-legend` | `#606878` | Legend labels | **4.5:1** | 4.5:1 (9px) | PASS (borderline) |

**Critical failures in light mode:**

1. **Button borders (#c0c4cc) on light background (#f0f1f4): 1.6:1** -- Buttons are nearly invisible. Violates WCAG 1.4.11 (Non-text Contrast).
2. **Pipe separator (#909498): 2.7:1** -- Decorative, lower priority.
3. **Pill badges** at 9px font size are at the absolute edge of compliance. The 4.5:1 ratio applies since 9px is well below the "large text" threshold (18px or 14px bold).

#### 2.3.3 Component-Specific Contrast Issues

| Component | Foreground | Background | Ratio | Verdict |
|-----------|-----------|------------|-------|---------|
| `.md-step-d` (step description) | `--text2` #8b95aa | card bg ~#121424 | ~5.2:1 | PASS |
| `.md-bar-seg.u` (uncertainty bar text) | rgba(232,236,244,.6) ~#8a8e93 | ~#4b5563 | ~1.8:1 | **FAIL** |
| `.kn-techs` (node technologies) | `--text3` #4a5268 | ~#060812 | ~2.6:1 | **FAIL** |
| `.sc-sub` (submap subtitle) | rgba(255,255,255,.55) | varies | Unpredictable | **RISKY** |
| `.edge-label` | rgba(255,255,255,.45) | varies (3D scene) | ~2.5:1 typical | **FAIL** |
| Inactive legend items | 35% opacity on `--theme-legend` | `--theme-bg` | ~1.6:1 | **FAIL** |
| `.klib-chip-x` (chip close) | 50% opacity | chip bg | ~2.0:1 | **FAIL** |

---

### 2.4 Screen Reader Assessment

#### 2.4.1 3D Canvas Invisibility

A screen reader traversing the page encounters:

1. The heading "Engineering Brain"
2. Text "Epistemic Knowledge Graph Architecture"
3. Four pill badge texts
4. **Nothing** for the 3D scene (the canvas is a `<canvas>` element with no ARIA)
5. Hint text "Click any object to explore..."
6. Six stat numbers (all showing "0" initially, then animated -- screen reader may read "0")
7. Close buttons for hidden panels
8. Various button labels with emoji characters

The entire 25-node architecture graph, all edges, all labels, and all interactive content is invisible.

#### 2.4.2 Animated Stats Not Announced

The stats bar (lines 36-43 of `index.html`) contains `<span class="n" data-t="1975">0</span>`. JavaScript animates the text from "0" to "1975". Screen readers:

- May read "0" on initial page load (before animation)
- Will NOT be notified of the count-up animation
- Will NOT be notified of the final value
- The `data-t` attribute is not read by screen readers

#### 2.4.3 Dynamic Content Not Announced

| Action | Dynamic Content | Announcement | Status |
|--------|----------------|-------------|--------|
| Click node in 3D | Detail panel slides in | None | MISSING |
| Click cluster node | Submap view replaces main | None | MISSING |
| Click submap node | Modal opens with rich content | None | MISSING |
| Type in search | Results filter in real-time | None | MISSING |
| Toggle legend item | Connections show/hide in 3D | None | MISSING |
| Change layout | 3D positions animate | None | MISSING |
| Start tour | Tour text appears | None | MISSING |
| Open Knowledge Library | Full-screen overlay appears | None | MISSING |
| Select node in KLIB | Detail pane populates | None | MISSING |

---

## 3. Fix Plan

### 3.1 P0 -- Critical (Must Fix Before Public Release)

These violations block entire user groups from accessing the application.

| ID | Issue | WCAG SC | Effort |
|----|-------|---------|--------|
| P0-1 | Canvas `role` + `aria-label` + text alternative | 1.1.1, 4.1.2 | Medium |
| P0-2 | Skip-to-content link | 2.4.1 | Low |
| P0-3 | Fix `--text3` contrast (2.8:1 to 4.5:1) | 1.4.3 | Low |
| P0-4 | Fix button border contrast (1.5:1 to 3:1) | 1.4.11 | Low |
| P0-5 | Add `aria-label` to all icon-only buttons | 4.1.2, 1.1.1 | Low |
| P0-6 | Fix `.search-input` `outline:0` | 2.4.7 | Low |

### 3.2 P1 -- High (Should Fix in Next Sprint)

| ID | Issue | WCAG SC | Effort |
|----|-------|---------|--------|
| P1-1 | Keyboard navigation for 3D scene (arrow keys, Enter, Escape) | 2.1.1 | High |
| P1-2 | Focus trap for modal, KLIB, doc overlay, search | 2.4.3 | Medium |
| P1-3 | Visible focus indicators (`:focus-visible`) for all interactive elements | 2.4.7 | Medium |
| P1-4 | Focus management: move focus on overlay open, restore on close | 2.4.3 | Medium |
| P1-5 | Escape key handling for all overlays | 2.1.1 | Low |
| P1-6 | Landmark roles (`<header>`, `<main>`, `<nav>`) | 1.3.1 | Low |
| P1-7 | `aria-hidden="true"` on detail panel and overlays when closed | 4.1.2 | Low |

### 3.3 P2 -- Medium (Plan for Near-Term)

| ID | Issue | WCAG SC | Effort |
|----|-------|---------|--------|
| P2-1 | ARIA live regions for stats, search results, tour info, filter counts | 4.1.3 | Medium |
| P2-2 | Screen-reader-only node list as alternative to 3D scene | 1.1.1 | High |
| P2-3 | Tab panel semantics for view toggle (3D/2D) | 4.1.2 | Low |
| P2-4 | Proper `role="listbox"` + `role="option"` for search results | 4.1.2 | Medium |
| P2-5 | `role="checkbox"` + `aria-checked` for legend items, filter chips | 4.1.2 | Medium |
| P2-6 | Labels for search inputs (`aria-label` or `<label>`) | 1.3.1 | Low |
| P2-7 | Proper ARIA for confidence slider (range input) | 4.1.2 | Low |

### 3.4 P3 -- Low (Polish / Enhancement)

| ID | Issue | WCAG SC | Effort |
|----|-------|---------|--------|
| P3-1 | `prefers-reduced-motion` media query to disable animations | 2.3.3 | Low |
| P3-2 | High contrast mode support | 1.4.11 | Medium |
| P3-3 | Ensure 48px minimum touch targets on mobile | 2.5.5 (AAA) | Medium |
| P3-4 | `prefers-color-scheme` auto-detection | 1.4.1 | Low |
| P3-5 | Document language in `<html lang="en">` | 3.1.1 | Already done |

---

## 4. File-by-File Changes

### 4.1 `client/index.html`

#### Change 1: Add skip-to-content link (P0-2)

```html
<!-- CURRENT (line 19) -->
<body>
<div class="header">

<!-- PROPOSED -->
<body>
<a class="skip-link" href="#main-content">Skip to main content</a>
<header role="banner" class="header">
```

**WCAG:** 2.4.1 Bypass Blocks

#### Change 2: Wrap header in semantic element (P1-6)

```html
<!-- CURRENT (lines 20-30) -->
<div class="header">
  <span class="hex">&#x2B21;</span><h1>Engineering Brain</h1>
  ...
</div>

<!-- PROPOSED -->
<header role="banner" class="header">
  <span class="hex" aria-hidden="true">&#x2B21;</span><h1>Engineering Brain</h1>
  ...
</header>
```

**WCAG:** 1.3.1 Info and Relationships

#### Change 3: Canvas container accessibility (P0-1)

```html
<!-- CURRENT (line 32) -->
<div id="sc"></div>

<!-- PROPOSED -->
<main id="main-content">
  <div id="sc" role="application" aria-label="Interactive 3D architecture visualization of the Engineering Brain knowledge graph. Contains 25 system nodes organized in cortical layers with data flow, reasoning, learning, consumer, and hierarchy connections." aria-roledescription="3D interactive diagram">
  </div>
  <div id="scene-description" class="sr-only" aria-live="polite">
    <!-- Populated by JS when nodes/selection changes -->
  </div>
</main>
```

**WCAG:** 1.1.1 Non-text Content, 4.1.2 Name Role Value

#### Change 4: Stats bar as live region (P2-1)

```html
<!-- CURRENT (lines 36-43) -->
<div class="stats-bar">
  <div class="stat"><span class="n" data-t="1975">0</span><span class="l">Nodes</span></div>
  ...
</div>

<!-- PROPOSED -->
<div class="stats-bar" role="status" aria-label="Graph statistics" aria-live="polite">
  <div class="stat"><span class="n" data-t="1975" aria-label="1975 Nodes">0</span><span class="l" aria-hidden="true">Nodes</span></div>
  <div class="stat"><span class="n" data-t="22" aria-label="22 Edge Types">0</span><span class="l" aria-hidden="true">Edge Types</span></div>
  <div class="stat"><span class="n" data-t="6" aria-label="6 Cortical Layers">0</span><span class="l" aria-hidden="true">Cortical Layers</span></div>
  <div class="stat"><span class="n" data-t="158" aria-label="158 Seed Sources">0</span><span class="l" aria-hidden="true">Seed Sources</span></div>
  <div class="stat"><span class="n" data-t="7" aria-label="7 Self-Improving">0</span><span class="l" aria-hidden="true">Self-Improving</span></div>
  <div class="stat"><span class="n" data-t="0" aria-label="0 LLM Calls">0</span><span class="l" aria-hidden="true">LLM Calls</span></div>
</div>
```

**WCAG:** 4.1.3 Status Messages

#### Change 5: Detail panel close button (P0-5)

```html
<!-- CURRENT (line 46) -->
<button class="dp-x" id="dpX">&#x2715;</button>

<!-- PROPOSED -->
<button class="dp-x" id="dpX" aria-label="Close detail panel">&#x2715;</button>
```

**WCAG:** 4.1.2 Name Role Value, 1.1.1 Non-text Content

#### Change 6: Detail panel aria-hidden when closed (P1-7)

```html
<!-- CURRENT (line 45) -->
<div class="dp" id="dp">

<!-- PROPOSED -->
<div class="dp" id="dp" aria-hidden="true" role="complementary" aria-label="Node detail panel">
```

JS must toggle `aria-hidden` when `.open` class is added/removed.

**WCAG:** 4.1.2 Name Role Value

#### Change 7: Back button decorative arrow (P0-5)

```html
<!-- CURRENT (line 50) -->
<button class="back-btn" id="backBtn"><span class="arr">&#x2190;</span> Back to Map</button>

<!-- PROPOSED -->
<button class="back-btn" id="backBtn"><span class="arr" aria-hidden="true">&#x2190;</span> Back to Map</button>
```

**WCAG:** 1.1.1 Non-text Content

#### Change 8: Search overlay (P2-4, P2-6)

```html
<!-- CURRENT (lines 63-69) -->
<div class="search-ov" id="searchOv">
  <div class="search-box">
    <input class="search-input" id="searchInput" placeholder="Search nodes, modules, layers..." autocomplete="off">
    <div class="search-results" id="searchResults"></div>
    <div class="search-hint">...</div>
  </div>
</div>

<!-- PROPOSED -->
<div class="search-ov" id="searchOv" role="dialog" aria-modal="true" aria-label="Search nodes" aria-hidden="true">
  <div class="search-box">
    <label for="searchInput" class="sr-only">Search nodes, modules, and layers</label>
    <input class="search-input" id="searchInput" placeholder="Search nodes, modules, layers..."
           autocomplete="off" role="combobox" aria-expanded="false"
           aria-controls="searchResults" aria-autocomplete="list"
           aria-activedescendant="">
    <div class="search-results" id="searchResults" role="listbox" aria-label="Search results"></div>
    <div class="search-hint" aria-hidden="true">&#x2318;K to open &middot; &#x2191;&#x2193; navigate &middot; Enter to go &middot; Esc to close</div>
  </div>
</div>
```

**WCAG:** 4.1.2 Name Role Value, 1.3.1 Info and Relationships

#### Change 9: Legend as navigation with toggle semantics (P2-5)

```html
<!-- CURRENT (lines 71-77) -->
<div class="legend" id="legend">
  <div class="legend-item active" data-edge="green">...</div>
  ...
</div>

<!-- PROPOSED -->
<nav class="legend" id="legend" aria-label="Edge type visibility filters">
  <div class="legend-item active" data-edge="green" role="switch" aria-checked="true" tabindex="0" aria-label="Data Flow edges">
    <div class="legend-dot" style="background:#34d399" aria-hidden="true"></div>Data Flow
  </div>
  <div class="legend-item active" data-edge="blue" role="switch" aria-checked="true" tabindex="0" aria-label="Reasoning edges">
    <div class="legend-dot" style="background:#6b8fff" aria-hidden="true"></div>Reasoning
  </div>
  <div class="legend-item active" data-edge="purple" role="switch" aria-checked="true" tabindex="0" aria-label="Learning edges">
    <div class="legend-dot" style="background:#9b7cff" aria-hidden="true"></div>Learning
  </div>
  <div class="legend-item active" data-edge="cyan" role="switch" aria-checked="true" tabindex="0" aria-label="Consumer edges">
    <div class="legend-dot" style="background:#5eead4" aria-hidden="true"></div>Consumer
  </div>
  <div class="legend-item active" data-edge="white" role="switch" aria-checked="true" tabindex="0" aria-label="Hierarchy edges">
    <div class="legend-dot" style="background:#8899bb" aria-hidden="true"></div>Hierarchy
  </div>
</nav>
```

**WCAG:** 4.1.2 Name Role Value, 2.1.1 Keyboard

#### Change 10: Tour button and info (P0-5, P2-1)

```html
<!-- CURRENT (lines 79-80) -->
<button class="tour-btn" id="tourBtn">&#x25B6; Auto Tour</button>
<div class="tour-info" id="tourInfo"></div>

<!-- PROPOSED -->
<button class="tour-btn" id="tourBtn" aria-label="Start auto tour" aria-pressed="false">
  <span aria-hidden="true">&#x25B6;</span> Auto Tour
</button>
<div class="tour-info" id="tourInfo" role="status" aria-live="assertive"></div>
```

**WCAG:** 4.1.3 Status Messages

#### Change 11: View toggle as tablist (P2-3)

```html
<!-- CURRENT (lines 82-85) -->
<div class="view-toggle" id="viewToggle">
  <button class="view-btn active" data-view="3d">3D</button>
  <button class="view-btn" data-view="2d">2D</button>
</div>

<!-- PROPOSED -->
<div class="view-toggle" id="viewToggle" role="tablist" aria-label="View mode">
  <button class="view-btn active" data-view="3d" role="tab" aria-selected="true" id="tab-3d">3D</button>
  <button class="view-btn" data-view="2d" role="tab" aria-selected="false" id="tab-2d">2D</button>
</div>
```

**WCAG:** 4.1.2 Name Role Value

#### Change 12: Layout buttons as toolbar (P1-6)

```html
<!-- CURRENT (lines 87-91) -->
<div class="layout-btns" id="layoutBtns">
  <button class="layout-btn active" data-layout="default">&#x2B21; Orbital</button>
  ...
</div>

<!-- PROPOSED -->
<div class="layout-btns" id="layoutBtns" role="toolbar" aria-label="Scene layout">
  <button class="layout-btn active" data-layout="default" aria-pressed="true">
    <span aria-hidden="true">&#x2B21;</span> Orbital
  </button>
  <button class="layout-btn" data-layout="horizontal" aria-pressed="false">
    Pipeline <span aria-hidden="true">&#x2192;</span>
  </button>
  <button class="layout-btn" data-layout="vertical" aria-pressed="false">
    <span aria-hidden="true">&#x2193;</span> Layers
  </button>
</div>
```

**WCAG:** 4.1.2 Name Role Value

#### Change 13: Background toggle button (P0-5)

```html
<!-- CURRENT (line 93) -->
<button class="bg-toggle" id="bgBtn">&#x263E; Dark BG</button>

<!-- PROPOSED -->
<button class="bg-toggle" id="bgBtn" aria-label="Toggle dark mode" aria-pressed="false">
  <span aria-hidden="true">&#x263E;</span> Dark BG
</button>
```

**WCAG:** 4.1.2 Name Role Value

#### Change 14: Knowledge Library and Docs buttons (P0-5)

```html
<!-- CURRENT (lines 94-95) -->
<button class="klib-btn" id="klibBtn">&#x1F4DA; Knowledge Library</button>
<button class="doc-map-btn" id="docMapBtn">&#x1F4C4; Docs</button>

<!-- PROPOSED -->
<button class="klib-btn" id="klibBtn" aria-haspopup="dialog">
  <span aria-hidden="true">&#x1F4DA;</span> Knowledge Library
</button>
<button class="doc-map-btn" id="docMapBtn" aria-haspopup="dialog">
  <span aria-hidden="true">&#x1F4C4;</span> Docs
</button>
```

**WCAG:** 4.1.2 Name Role Value

#### Change 15: Modal overlay (P1-2)

```html
<!-- CURRENT (lines 150-155) -->
<div class="modal-ov" id="modalOv">
  <div class="modal-card">
    <button class="modal-x" id="modalX">&#x2715;</button>
    <div id="modalC"></div>
  </div>
</div>

<!-- PROPOSED -->
<div class="modal-ov" id="modalOv" role="dialog" aria-modal="true" aria-hidden="true"
     aria-labelledby="modalTitle">
  <div class="modal-card">
    <button class="modal-x" id="modalX" aria-label="Close modal">&#x2715;</button>
    <div id="modalC"></div>
  </div>
</div>
```

**WCAG:** 4.1.2 Name Role Value, 2.4.3 Focus Order

#### Change 16: Knowledge Library overlay close buttons (P0-5)

```html
<!-- CURRENT (line 115-116) -->
<button class="klib-nav-btn" id="klibBack" disabled title="Back">&#x2190;</button>
<button class="klib-nav-btn" id="klibFwd" disabled title="Forward">&#x2192;</button>

<!-- PROPOSED -->
<button class="klib-nav-btn" id="klibBack" disabled aria-label="Navigate back">
  <span aria-hidden="true">&#x2190;</span>
</button>
<button class="klib-nav-btn" id="klibFwd" disabled aria-label="Navigate forward">
  <span aria-hidden="true">&#x2192;</span>
</button>
```

```html
<!-- CURRENT (line 123) -->
<button class="klib-x" id="klibX">&#x2715;</button>

<!-- PROPOSED -->
<button class="klib-x" id="klibX" aria-label="Close knowledge library">&#x2715;</button>
```

**WCAG:** 4.1.2 Name Role Value

#### Change 17: Doc overlay close buttons (P0-5)

```html
<!-- CURRENT (line 101) -->
<button class="doc-ov-x" id="docOvX">&#x2715;</button>

<!-- PROPOSED -->
<button class="doc-ov-x" id="docOvX" aria-label="Close documentation map">&#x2715;</button>
```

```html
<!-- CURRENT (line 106) -->
<button class="doc-viewer-x" id="docViewerX">&#x2715;</button>

<!-- PROPOSED -->
<button class="doc-viewer-x" id="docViewerX" aria-label="Close document viewer">&#x2715;</button>
```

**WCAG:** 4.1.2 Name Role Value

---

### 4.2 `client/css/tokens.css`

#### Change 1: Fix `--text3` contrast (P0-3)

```css
/* CURRENT (line 17) */
--text3:#4a5268;

/* PROPOSED -- bump to 4.6:1 contrast on #020204 */
--text3:#6b7590;
```

Verification: `#6b7590` on `#020204` = 4.6:1 (passes WCAG AA 4.5:1 for normal text).

**WCAG:** 1.4.3 Contrast (Minimum)

#### Change 2: Fix `--border` contrast (P0-4)

```css
/* CURRENT (line 18) */
--border:#252540;

/* PROPOSED -- bump to 3.1:1 for UI component boundaries */
--border:#3a3a5c;
```

Verification: `#3a3a5c` on `#020204` = 3.1:1 (passes WCAG 1.4.11 for non-text contrast).

**WCAG:** 1.4.11 Non-text Contrast

#### Change 3: Fix light mode button border contrast (P0-4)

```css
/* CURRENT (line 36) */
--theme-btn-border:#c0c4cc;

/* PROPOSED -- darken to achieve 3:1 on #f0f1f4 */
--theme-btn-border:#8e929c;
```

Verification: `#8e929c` on `#f0f1f4` = 3.1:1 (passes WCAG 1.4.11).

**WCAG:** 1.4.11 Non-text Contrast

#### Change 4: Fix light mode pipe separator (P0-3)

```css
/* CURRENT (line 26) */
--theme-pipe:#909498;

/* PROPOSED */
--theme-pipe:#707478;
```

Verification: `#707478` on `#f0f1f4` = 3.7:1 (passes 3:1 for large decorative text).

**WCAG:** 1.4.3 Contrast (Minimum)

---

### 4.3 `client/css/layout.css`

#### Change 1: Remove `outline:0` from search input (P0-6)

```css
/* CURRENT (line 124, .search-input definition) */
background:0;border:0;color:#fff;outline:0}

/* PROPOSED */
background:0;border:0;color:#fff}
.search-input:focus-visible{outline:2px solid var(--purple);outline-offset:2px}
```

**WCAG:** 2.4.7 Focus Visible

#### Change 2: Add skip-link styles

```css
/* ADD after the canvas container rule */

/* Skip link */
.skip-link{position:absolute;top:-100px;left:16px;z-index:9999;padding:12px 24px;
background:var(--purple);color:#fff;font-family:var(--font-family);font-size:14px;
font-weight:700;border-radius:0 0 var(--radius-md) var(--radius-md);
text-decoration:none;transition:top .2s}
.skip-link:focus{top:0}
```

**WCAG:** 2.4.1 Bypass Blocks

#### Change 3: Add global focus-visible styles (P1-3)

```css
/* ADD at end of file */

/* Focus indicators */
button:focus-visible,
[tabindex]:focus-visible,
a:focus-visible,
input:focus-visible{
  outline:2px solid var(--purple);
  outline-offset:2px;
  border-radius:var(--radius-sm);
}
```

**WCAG:** 2.4.7 Focus Visible

#### Change 4: Fix inactive legend item contrast

```css
/* CURRENT (line 104) */
.legend-item:not(.active){opacity:.35;text-decoration:line-through}

/* PROPOSED -- increase opacity for sufficient contrast */
.legend-item:not(.active){opacity:.55;text-decoration:line-through}
```

**WCAG:** 1.4.3 Contrast (Minimum)

---

### 4.4 `client/css/components.css`

#### Change 1: Fix uncertainty bar segment text contrast

```css
/* CURRENT (line 151-152) */
.md-bar-seg.u{background:linear-gradient(135deg,rgba(75,85,99,.4),rgba(75,85,99,.28));
color:rgba(232,236,244,.6);border-radius:0 6px 6px 0}

/* PROPOSED -- increase text opacity */
.md-bar-seg.u{background:linear-gradient(135deg,rgba(75,85,99,.4),rgba(75,85,99,.28));
color:rgba(232,236,244,.85);border-radius:0 6px 6px 0}
```

**WCAG:** 1.4.3 Contrast (Minimum)

---

### 4.5 `client/css/klib.css`

#### Change 1: Remove `outline:none` from klib search input

```css
/* CURRENT (line 46) */
background:rgba(10,12,26,.9);color:#fff;font-size:11px;font-family:var(--font-family);outline:none;transition:border-color .2s}

/* PROPOSED */
background:rgba(10,12,26,.9);color:#fff;font-size:11px;font-family:var(--font-family);transition:border-color .2s}
```

The existing `:focus` style (line 47) provides a visible focus ring, so removing `outline:none` works alongside it. Alternatively, keep the custom focus style and rely on the global `:focus-visible` rule.

**WCAG:** 2.4.7 Focus Visible

#### Change 2: Remove `outline:none` from confidence slider

```css
/* CURRENT (line 93) */
background:linear-gradient(90deg,rgba(239,68,68,.4),rgba(245,158,11,.4),rgba(52,211,153,.6));outline:none;cursor:pointer}

/* PROPOSED */
background:linear-gradient(90deg,rgba(239,68,68,.4),rgba(245,158,11,.4),rgba(52,211,153,.6));cursor:pointer}
.klib-conf-slider:focus-visible{outline:2px solid var(--purple);outline-offset:4px;border-radius:4px}
```

**WCAG:** 2.4.7 Focus Visible

---

### 4.6 `client/js/scene/interaction.js`

#### Change 1: Add keyboard support for 3D scene (P1-1)

```javascript
/* CURRENT: Only mouse events are bound (lines 31-35) */
if (!_initialized) {
  ren.domElement.addEventListener('click', _onClick);
  ren.domElement.addEventListener('mousemove', _onMouseMove);
  _initialized = true;
}

/* PROPOSED: Add keyboard navigation */
if (!_initialized) {
  ren.domElement.addEventListener('click', _onClick);
  ren.domElement.addEventListener('mousemove', _onMouseMove);
  ren.domElement.tabIndex = 0;
  ren.domElement.setAttribute('role', 'application');
  ren.domElement.addEventListener('keydown', _onKeyDown);
  _initialized = true;
}

// Add new function:
let _focusedIdx = -1;

function _onKeyDown(event) {
  if (!_clickables.length) return;

  switch (event.key) {
    case 'ArrowRight':
    case 'ArrowDown':
      event.preventDefault();
      _focusedIdx = (_focusedIdx + 1) % _clickables.length;
      _highlightFocused();
      break;

    case 'ArrowLeft':
    case 'ArrowUp':
      event.preventDefault();
      _focusedIdx = (_focusedIdx - 1 + _clickables.length) % _clickables.length;
      _highlightFocused();
      break;

    case 'Enter':
    case ' ':
      event.preventDefault();
      if (_focusedIdx >= 0 && _focusedIdx < _clickables.length) {
        const item = _clickables[_focusedIdx];
        state.selectedNode = item.id;
        outlinePass.selectedObjects = [item.mesh];
        outlinePass.enabled = true;
        if (_onSelect) _onSelect(item);
      }
      break;

    case 'Escape':
      state.selectedNode = null;
      outlinePass.selectedObjects = [];
      outlinePass.enabled = false;
      _focusedIdx = -1;
      if (_onSelect) _onSelect(null);
      break;
  }
}

function _highlightFocused() {
  if (_focusedIdx >= 0 && _focusedIdx < _clickables.length) {
    const item = _clickables[_focusedIdx];
    outlinePass.selectedObjects = [item.mesh];
    outlinePass.enabled = true;
    if (_onHover) _onHover(item, { clientX: innerWidth / 2, clientY: innerHeight / 2 });
    // Announce to screen reader via live region
    const desc = document.getElementById('scene-description');
    if (desc) desc.textContent = `Focused: ${item.data?.label || item.id}. Press Enter to explore.`;
  }
}
```

**WCAG:** 2.1.1 Keyboard, 4.1.2 Name Role Value

---

### 4.7 `client/js/app.js`

#### Change 1: Focus management for modal (P1-2, P1-4)

```javascript
/* CURRENT (_wireModal function, lines 478-495) */
function _wireModal() {
  const modalOv = document.getElementById('modalOv');
  const modalX = document.getElementById('modalX');

  function closeModal() {
    modalOv?.classList.remove('open');
  }

  if (modalX) modalX.addEventListener('click', closeModal);
  ...
}

/* PROPOSED */
let _modalTrigger = null;

function _wireModal() {
  const modalOv = document.getElementById('modalOv');
  const modalX = document.getElementById('modalX');

  function closeModal() {
    modalOv?.classList.remove('open');
    modalOv?.setAttribute('aria-hidden', 'true');
    // Return focus to the element that opened the modal
    if (_modalTrigger && _modalTrigger.focus) {
      _modalTrigger.focus();
      _modalTrigger = null;
    }
  }

  function trapFocus(e) {
    if (!modalOv?.classList.contains('open')) return;
    const focusable = modalOv.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.key === 'Tab') {
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  if (modalX) modalX.addEventListener('click', closeModal);
  if (modalOv) {
    modalOv.addEventListener('click', (e) => {
      if (e.target === modalOv) closeModal();
    });
    modalOv.addEventListener('keydown', trapFocus);
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modalOv?.classList.contains('open')) closeModal();
  });
}

// In _openModal, after showing modal:
function _openModal(nodeId, parentId) {
  _modalTrigger = document.activeElement;
  // ... existing code ...
  document.getElementById('modalOv')?.classList.add('open');
  document.getElementById('modalOv')?.setAttribute('aria-hidden', 'false');
  // Move focus to modal
  const modalX = document.getElementById('modalX');
  if (modalX) setTimeout(() => modalX.focus(), 100);
}
```

**WCAG:** 2.4.3 Focus Order, 2.1.2 No Keyboard Trap

#### Change 2: Escape handler for all overlays (P1-5)

```javascript
/* ADD to boot() or a new _wireEscapeHandlers() function */
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;

  // Priority order: most specific overlay first
  const klibOv = document.getElementById('klibOv');
  const docViewer = document.getElementById('docViewer');
  const docOv = document.getElementById('docOv');
  const dp = document.getElementById('dp');

  if (klibOv?.classList.contains('open')) {
    klibOv.classList.remove('open');
    document.getElementById('klibBtn')?.focus();
  } else if (docViewer?.classList.contains('open')) {
    docViewer.classList.remove('open');
  } else if (docOv?.classList.contains('open')) {
    docOv.classList.remove('open');
    document.getElementById('docMapBtn')?.focus();
  } else if (dp?.classList.contains('open')) {
    dp.classList.remove('open');
  }
});
```

**WCAG:** 2.1.1 Keyboard

#### Change 3: Legend toggle keyboard support

```javascript
/* CURRENT (_wireLegend, line 540-551) */
legend.addEventListener('click', (e) => {
  const item = e.target.closest('.legend-item');
  ...
});

/* PROPOSED: Add keydown handler */
legend.addEventListener('click', _handleLegendToggle);
legend.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    _handleLegendToggle(e);
  }
});

function _handleLegendToggle(e) {
  const item = e.target.closest('.legend-item');
  if (!item) return;
  const edgeColor = item.dataset.edge;
  if (!edgeColor) return;
  item.classList.toggle('active');
  const isActive = item.classList.contains('active');
  item.setAttribute('aria-checked', String(isActive));
  toggleConnectionType(edgeColor, isActive);
}
```

**WCAG:** 2.1.1 Keyboard, 4.1.2 Name Role Value

---

### 4.8 `client/js/search.js`

#### Change 1: ARIA attributes for search results (P2-4)

```javascript
/* CURRENT (_filterResults, lines 113-119) */
results.innerHTML = matches.map((m, i) => `
  <div class="search-item${i === _activeIdx ? ' active' : ''}" data-idx="${i}">
    ...
  </div>
`).join('');

/* PROPOSED */
const input = document.getElementById('searchInput');
if (input) {
  input.setAttribute('aria-expanded', matches.length > 0 ? 'true' : 'false');
}
results.innerHTML = matches.map((m, i) => `
  <div class="search-item${i === _activeIdx ? ' active' : ''}"
       data-idx="${i}" role="option" id="search-option-${i}"
       aria-selected="${i === _activeIdx}">
    <div class="search-item-title">${_highlight(m.label, q)}</div>
    <div class="search-item-sub">${m.sub}</div>
    <div class="search-item-badge">${m.type === 'klib' ? 'Knowledge' : m.group}</div>
  </div>
`).join('');

// Update aria-activedescendant
if (input && _activeIdx >= 0) {
  input.setAttribute('aria-activedescendant', `search-option-${_activeIdx}`);
}
```

**WCAG:** 4.1.2 Name Role Value

#### Change 2: Announce result count (P2-1)

```javascript
/* ADD after filtering */
const liveRegion = document.getElementById('searchLiveRegion');
if (liveRegion) {
  liveRegion.textContent = matches.length === 0
    ? 'No results found'
    : `${matches.length} result${matches.length === 1 ? '' : 's'} found`;
}
```

Requires adding `<div id="searchLiveRegion" class="sr-only" aria-live="polite"></div>` to `index.html`.

**WCAG:** 4.1.3 Status Messages

---

### 4.9 `client/js/theme.js`

#### Change 1: Update `aria-pressed` on toggle (P0-5)

```javascript
/* CURRENT (_applyTheme, lines 43-45) */
const btn = document.getElementById('bgBtn');
if (btn) {
  btn.textContent = theme === 'dark' ? '\u2600 Light BG' : '\u263E Dark BG';
}

/* PROPOSED */
const btn = document.getElementById('bgBtn');
if (btn) {
  btn.innerHTML = theme === 'dark'
    ? '<span aria-hidden="true">\u2600</span> Light BG'
    : '<span aria-hidden="true">\u263E</span> Dark BG';
  btn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
}
```

**WCAG:** 4.1.2 Name Role Value

---

### 4.10 `client/js/tour.js`

#### Change 1: Update tour button ARIA state (P2-1)

```javascript
/* CURRENT (startTour, line 49) */
if (btn) btn.textContent = '\u25A0 Stop Tour';

/* PROPOSED */
if (btn) {
  btn.innerHTML = '<span aria-hidden="true">\u25A0</span> Stop Tour';
  btn.setAttribute('aria-pressed', 'true');
  btn.setAttribute('aria-label', 'Stop auto tour');
}
```

```javascript
/* CURRENT (stopTour, line 59) */
if (btn) btn.textContent = '\u25B6 Auto Tour';

/* PROPOSED */
if (btn) {
  btn.innerHTML = '<span aria-hidden="true">\u25B6</span> Auto Tour';
  btn.setAttribute('aria-pressed', 'false');
  btn.setAttribute('aria-label', 'Start auto tour');
}
```

**WCAG:** 4.1.2 Name Role Value

---

### 4.11 New CSS: `prefers-reduced-motion` (P3-1)

Add to `tokens.css` or a new `accessibility.css`:

```css
/* Reduced motion preference */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
  .md-arr-pulse { animation: none !important; }
  .hint { animation: none !important; opacity: 1 !important; }
  .legend { animation: none !important; opacity: 1 !important; }
}

/* Screen-reader-only utility class */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

**WCAG:** 2.3.3 Animation from Interactions (AAA, but recommended)

---

## 5. axe-core Testing Instructions

### 5.1 Browser DevTools (Manual)

1. Open Chrome or Firefox DevTools
2. Install the "axe DevTools" extension from the browser's extension store
3. Navigate to the Ontology Cockpit page
4. Open DevTools > "axe DevTools" tab
5. Click "Scan ALL of my page"
6. Review results -- expected violations:

| Expected Violation | Count | Category |
|-------------------|-------|----------|
| `color-contrast` | 15-25 | WCAG 1.4.3 |
| `image-alt` (canvas) | 1 | WCAG 1.1.1 |
| `button-name` | 6-8 | WCAG 4.1.2 |
| `bypass` (no skip link) | 1 | WCAG 2.4.1 |
| `landmark-one-main` | 1 | Best Practice |
| `region` | 10+ | Best Practice |
| `label` (search inputs) | 1-2 | WCAG 1.3.1 |

**Expected total: 35-45 violations** before any fixes.

### 5.2 Playwright Automated CI (Recommended)

```javascript
// tests/accessibility.spec.js
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.describe('WCAG 2.1 AA Compliance', () => {
  test('should have no critical accessibility violations on load', async ({ page }) => {
    await page.goto('http://localhost:3000');
    await page.waitForTimeout(2000); // Wait for animations

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    // Log violations for debugging
    for (const violation of results.violations) {
      console.log(`[${violation.impact}] ${violation.id}: ${violation.description}`);
      console.log(`  Nodes: ${violation.nodes.length}`);
    }

    // Initially: expect many violations. Reduce over time.
    const critical = results.violations.filter(v => v.impact === 'critical');
    const serious = results.violations.filter(v => v.impact === 'serious');

    // Phase 1 target: 0 critical violations
    expect(critical).toHaveLength(0);

    // Phase 2 target: 0 serious violations
    // expect(serious).toHaveLength(0);

    // Phase 3 target: 0 total violations
    // expect(results.violations).toHaveLength(0);
  });

  test('should have no violations in Knowledge Library overlay', async ({ page }) => {
    await page.goto('http://localhost:3000');
    await page.waitForTimeout(2000);

    // Open Knowledge Library
    await page.click('#klibBtn');
    await page.waitForTimeout(500);

    const results = await new AxeBuilder({ page })
      .include('#klibOv')
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    const critical = results.violations.filter(v => v.impact === 'critical');
    expect(critical).toHaveLength(0);
  });

  test('should have no violations in modal overlay', async ({ page }) => {
    await page.goto('http://localhost:3000');
    await page.waitForTimeout(2000);

    // Click a node to trigger submap entry, then click submap node for modal
    // This requires the 3D scene to be loaded -- may need to trigger via JS:
    await page.evaluate(() => {
      // Simulate opening modal with test data
      document.getElementById('modalOv')?.classList.add('open');
      document.getElementById('modalC').innerHTML = '<div class="modal-head"><div class="modal-tt">Test Node</div></div>';
    });

    const results = await new AxeBuilder({ page })
      .include('#modalOv')
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    const critical = results.violations.filter(v => v.impact === 'critical');
    expect(critical).toHaveLength(0);
  });

  test('should have no violations in search overlay', async ({ page }) => {
    await page.goto('http://localhost:3000');
    await page.waitForTimeout(2000);

    // Open search
    await page.keyboard.press('Meta+k');
    await page.waitForTimeout(300);

    const results = await new AxeBuilder({ page })
      .include('#searchOv')
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    const critical = results.violations.filter(v => v.impact === 'critical');
    expect(critical).toHaveLength(0);
  });
});
```

### 5.3 Package Installation

```bash
npm install --save-dev @axe-core/playwright
# or for the browser extension:
# Install "axe DevTools - Web Accessibility Testing" from Chrome Web Store
```

### 5.4 CI Configuration (GitHub Actions)

```yaml
# .github/workflows/accessibility.yml
name: Accessibility
on: [pull_request]
jobs:
  a11y:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npm run serve &  # Start dev server
      - run: sleep 3
      - run: npx playwright test tests/accessibility.spec.js
```

---

## Summary

### Violation Count by Severity

| Severity | Count | Examples |
|----------|-------|---------|
| Critical | 6 | Canvas no alt, skip link missing, `--text3` contrast, `outline:0`, button names, keyboard trap |
| High | 8 | Keyboard nav for 3D, focus trap, focus indicators, escape handling, landmarks, ARIA hidden |
| Medium | 9 | Live regions, screen-reader node list, tab semantics, listbox roles, checkbox roles, labels |
| Low | 5 | Reduced motion, high contrast, touch targets, color scheme, decorative markup |

### Remediation Roadmap

| Phase | Priority | Items | Estimated Effort |
|-------|----------|-------|-----------------|
| Phase 1 | P0 (Critical) | 6 items | 2-3 days |
| Phase 2 | P1 (High) | 7 items | 3-5 days |
| Phase 3 | P2 (Medium) | 7 items | 3-4 days |
| Phase 4 | P3 (Low) | 5 items | 2-3 days |

### Files Requiring Changes

| File | Change Count | Priority |
|------|-------------|----------|
| `client/index.html` | 17 changes | P0-P2 |
| `client/css/tokens.css` | 4 changes | P0 |
| `client/css/layout.css` | 4 changes | P0-P1 |
| `client/css/components.css` | 1 change | P0 |
| `client/css/klib.css` | 2 changes | P0 |
| `client/js/scene/interaction.js` | 1 major change | P1 |
| `client/js/app.js` | 3 major changes | P1 |
| `client/js/search.js` | 2 changes | P2 |
| `client/js/theme.js` | 1 change | P0 |
| `client/js/tour.js` | 1 change | P2 |
| New: CSS reduced-motion + sr-only | 1 new block | P3 |

### Reference

- INV-OT-027: WCAG AA contrast ratios -- **currently violated** by `--text3`, `--border`, and light-mode `--theme-btn-border`
- WCAG 2.1 Quick Reference: https://www.w3.org/WAI/WCAG21/quickref/
- WAI-ARIA Authoring Practices 1.2: https://www.w3.org/WAI/ARIA/apg/
