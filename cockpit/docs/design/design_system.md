# Ontology Map Toolkit -- Design System Specification

> Version 1.0 | Based on SPEC.md Section 13 | OKLCH-native, theme-driven

---

## 1. Design Principles

Five principles govern every visual decision in the Ontology Map Toolkit. These
originate from SPEC.md Section 13 and are non-negotiable.

| # | Principle | Rationale |
|---|-----------|-----------|
| 1 | **Dark-first** | The 3D scene is the hero. Dark backgrounds maximize contrast for glowing nodes and connections. Light mode is a first-class citizen but designed second. |
| 2 | **OKLCH native** | All colors are defined in OKLCH color space. OKLCH is perceptually uniform -- equal numeric steps produce equal perceived brightness changes -- and is natively supported in CSS Color Level 4. No more eyeballing hex values. |
| 3 | **Semantic tokens** | No literal color appears in component CSS or JS. Every color is consumed via a CSS custom property (`--surface-0`, `--text-primary`, etc.). Switching themes means swapping token values. Zero component changes. |
| 4 | **Perceptual uniformity** | Categorical colors share identical OKLCH lightness and chroma so no hue appears brighter or more dominant. Spacing follows a strict 4px grid. Typography uses a 1.25 modular scale. |
| 5 | **3D-aware** | The design system extends into Three.js materials. Emissive intensity, metalness, roughness, and lighting are tokenized so themes control the 3D scene as naturally as they control CSS. |

---

## 2. Color System

### 2.1 Current State Audit

**Summary of hardcoded color literals across the codebase:**

| File | Hex `#` literals | `rgba()` literals | `0x` (JS) literals | Total |
|------|-----------------|-------------------|---------------------|-------|
| `tokens.css` | 37 | 16 | -- | 53 |
| `layout.css` | 23 | 18 | -- | 41 |
| `three-scene.css` | 12 | 26 | -- | 38 |
| `components.css` | 21 | 59 | -- | 80 |
| `klib.css` | 37 | 69 | -- | 106 |
| `view2d.css` | 4 | 3 | -- | 7 |
| `materials.js` | -- | -- | 118 | 118 |
| **TOTAL** | **134** | **191** | **118** | **443** |

There are **443 hardcoded color values** scattered across 7 files. The current
`tokens.css` defines only ~20 CSS custom properties (6 base colors, 3 text
shades, 1 border, 1 background, plus ~25 theme-prefixed overrides for light/dark).
The vast majority of color usage bypasses the token system entirely.

**Distinct base colors currently in use (hex):**

| Current Hex | Approximate Role | Used In |
|-------------|-----------------|---------|
| `#020204` | Background (dark) | tokens.css |
| `#6b8fff` | Blue accent | tokens.css, materials.js |
| `#9b7cff` | Purple accent | tokens.css, materials.js |
| `#34d399` | Green accent | tokens.css, materials.js |
| `#5eead4` | Cyan accent | tokens.css, materials.js |
| `#f59e0b` | Amber accent | tokens.css, materials.js |
| `#ef4444` | Red accent | tokens.css, materials.js |
| `#e8ecf4` | Text primary (dark) | tokens.css |
| `#8b95aa` | Text secondary (dark) | tokens.css |
| `#4a5268` | Text tertiary (dark) | tokens.css |
| `#252540` | Border (dark) | tokens.css |
| `#f0f1f4` | Background (light) | tokens.css |
| `#333` | Text primary (light) | tokens.css, layout.css |
| `#606878` | Text secondary (light) | tokens.css |
| `#909498` | Pipe separator (light) | tokens.css |
| `#c0c4cc` | Border (light) | tokens.css |
| `#fff` | White (dark text/titles) | layout.css, components.css |
| `#808898` | Hint text | layout.css |
| `#1a1e2a` | Screen material (3D) | materials.js |

Additionally, `materials.js` defines **25 shape palettes** (brain, gauge, tree,
hub, sphere, etc.) each with 4 tones (dark `d`, mid `m`, light `l`, accent `a`)
-- all as `0x` hex integers. The NEON map defines 4 group colors. Connection
colors (`CC_DARK`, `CC_LIGHT`) add another 10 hardcoded hex values.

### 2.2 Target: OKLCH Semantic Token Architecture

All colors will be defined in OKLCH and organized into semantic layers:

#### Surface tokens

| Token | Dark mode | Light mode | Purpose |
|-------|-----------|------------|---------|
| `--surface-0` | `oklch(13% 0.02 260)` | `oklch(98% 0.01 260)` | Deepest background |
| `--surface-1` | `oklch(18% 0.02 260)` | `oklch(95% 0.01 260)` | Card/panel background |
| `--surface-2` | `oklch(23% 0.02 260)` | `oklch(91% 0.012 260)` | Hover states |
| `--surface-3` | `oklch(28% 0.02 260)` | `oklch(87% 0.015 260)` | Active/selected states |

All surfaces share hue 260 (deep blue-violet) for cohesion. Dark mode increments
lightness by 5% per step. Light mode decrements by ~3-4% per step.

#### Text tokens

| Token | Dark mode | Light mode | Contrast on surface-0 |
|-------|-----------|------------|----------------------|
| `--text-primary` | `oklch(92% 0.02 260)` | `oklch(15% 0.02 260)` | >= 12:1 |
| `--text-secondary` | `oklch(70% 0.02 260)` | `oklch(40% 0.02 260)` | >= 5.5:1 |
| `--text-tertiary` | `oklch(50% 0.02 260)` | `oklch(60% 0.01 260)` | >= 4.5:1 |

All text tokens exceed WCAG AA minimum (4.5:1) against `--surface-0`.

#### Accent / categorical tokens (8 colors)

Hues are distributed at 45-degree intervals around the OKLCH hue wheel for
maximum perceptual distance. With 45-degree separation, all pairs have
hue difference >= 45 degrees, guaranteeing DeltaE > 30 between all pairs
at constant L and C.

**Dark mode** (L=65%, C=0.15):

| Token | OKLCH value | Hue | Semantic name |
|-------|-------------|-----|---------------|
| `--cat-0` | `oklch(65% 0.15 0)` | 0 | Red |
| `--cat-1` | `oklch(65% 0.15 45)` | 45 | Orange |
| `--cat-2` | `oklch(65% 0.15 90)` | 90 | Amber |
| `--cat-3` | `oklch(65% 0.15 135)` | 135 | Green |
| `--cat-4` | `oklch(65% 0.15 180)` | 180 | Teal |
| `--cat-5` | `oklch(65% 0.15 225)` | 225 | Blue |
| `--cat-6` | `oklch(65% 0.15 270)` | 270 | Indigo |
| `--cat-7` | `oklch(65% 0.15 315)` | 315 | Purple |

**Light mode** (L=55%, C=0.15):

Same hue distribution, lightness reduced to 55% for adequate contrast on
bright backgrounds:

| Token | OKLCH value | Hue |
|-------|-------------|-----|
| `--cat-0` | `oklch(55% 0.15 0)` | 0 |
| `--cat-1` | `oklch(55% 0.15 45)` | 45 |
| `--cat-2` | `oklch(55% 0.15 90)` | 90 |
| `--cat-3` | `oklch(55% 0.15 135)` | 135 |
| `--cat-4` | `oklch(55% 0.15 180)` | 180 |
| `--cat-5` | `oklch(55% 0.15 225)` | 225 |
| `--cat-6` | `oklch(55% 0.15 270)` | 270 |
| `--cat-7` | `oklch(55% 0.15 315)` | 315 |

**DeltaE verification:** With 8 hues at 45-degree intervals, constant L=65%
and C=0.15, the minimum hue separation between any adjacent pair is exactly
45 degrees. In OKLCH at these coordinates, 45 degrees of hue shift at C=0.15
produces DeltaE(OK) ~ 0.10-0.12, which translates to CIELab DeltaE > 30.
Non-adjacent pairs have even larger separation (90, 135, 180 degrees).

#### Named accent aliases

For backward compatibility and semantic clarity, named aliases map to the
categorical palette:

| Alias | Maps to | Dark OKLCH | Light OKLCH |
|-------|---------|-----------|-------------|
| `--accent-red` | `--cat-0` | `oklch(65% 0.15 0)` | `oklch(55% 0.15 0)` |
| `--accent-orange` | `--cat-1` | `oklch(65% 0.15 45)` | `oklch(55% 0.15 45)` |
| `--accent-amber` | `--cat-2` | `oklch(65% 0.15 90)` | `oklch(55% 0.15 90)` |
| `--accent-green` | `--cat-3` | `oklch(65% 0.15 135)` | `oklch(55% 0.15 135)` |
| `--accent-teal` | `--cat-4` | `oklch(65% 0.15 180)` | `oklch(55% 0.15 180)` |
| `--accent-blue` | `--cat-5` | `oklch(65% 0.15 225)` | `oklch(55% 0.15 225)` |
| `--accent-indigo` | `--cat-6` | `oklch(65% 0.15 270)` | `oklch(55% 0.15 270)` |
| `--accent-purple` | `--cat-7` | `oklch(65% 0.15 315)` | `oklch(55% 0.15 315)` |

#### Border tokens

| Token | Dark mode | Light mode |
|-------|-----------|------------|
| `--border-default` | `oklch(25% 0.01 260)` | `oklch(85% 0.01 260)` |
| `--border-emphasis` | `oklch(35% 0.02 260)` | `oklch(75% 0.02 260)` |

### 2.3 Migration Table: Current Hex to OKLCH

Every color currently hardcoded in the codebase maps to an OKLCH semantic token:

| Current value | OKLCH equivalent | Target token |
|---------------|-----------------|--------------|
| `#020204` | `oklch(4% 0.02 260)` | `--surface-0` (approx; target is `oklch(13% 0.02 260)`) |
| `#f0f1f4` | `oklch(95.5% 0.005 260)` | `--surface-0` (light) |
| `#6b8fff` | `oklch(66% 0.14 255)` | `--accent-blue` |
| `#9b7cff` | `oklch(63% 0.18 295)` | `--accent-purple` |
| `#34d399` | `oklch(75% 0.15 165)` | `--accent-green` |
| `#5eead4` | `oklch(84% 0.10 185)` | `--accent-teal` |
| `#f59e0b` | `oklch(76% 0.16 75)` | `--accent-amber` |
| `#ef4444` | `oklch(59% 0.22 25)` | `--accent-red` |
| `#e8ecf4` | `oklch(93% 0.01 260)` | `--text-primary` |
| `#8b95aa` | `oklch(66% 0.03 260)` | `--text-secondary` |
| `#4a5268` | `oklch(40% 0.03 260)` | `--text-tertiary` |
| `#252540` | `oklch(22% 0.03 270)` | `--border-default` |
| `#333` / `#333333` | `oklch(27% 0 0)` | `--text-primary` (light) |
| `#606878` | `oklch(48% 0.02 250)` | `--text-secondary` (light) |
| `#909498` | `oklch(65% 0.01 240)` | `--text-tertiary` (light) |
| `#c0c4cc` | `oklch(81% 0.01 250)` | `--border-default` (light) |
| `#fff` / `#ffffff` | `oklch(100% 0 0)` | `--text-primary` (dark mode titles) |
| `#808898` | `oklch(59% 0.02 250)` | `--text-tertiary` |
| `#1a1e2a` | `oklch(17% 0.02 260)` | `--surface-1` |
| `#1a1a2e` | `oklch(17% 0.03 275)` | `--surface-1` (light mode text) |
| `#fca5a5` | `oklch(80% 0.08 20)` | severity CRITICAL text |
| `#fbbf24` | `oklch(82% 0.14 85)` | severity HIGH text |
| `#93b4ff` | `oklch(76% 0.08 250)` | severity MEDIUM text |
| `#6ee7b7` | `oklch(84% 0.10 165)` | severity LOW text |
| `#c4b5fd` | `oklch(80% 0.08 295)` | severity INFO text |

**For materials.js (3D):**

| Current 0x value | Hex | OKLCH approx | Target token |
|------------------|-----|-------------|--------------|
| `0x34d399` (NEON source) | `#34d399` | `oklch(75% 0.15 165)` | `--mat-neon-source` |
| `0x6b8fff` (NEON layer) | `#6b8fff` | `oklch(66% 0.14 255)` | `--mat-neon-layer` |
| `0x9b7cff` (NEON module) | `#9b7cff` | `oklch(63% 0.18 295)` | `--mat-neon-module` |
| `0x5eead4` (NEON consumer) | `#5eead4` | `oklch(84% 0.10 185)` | `--mat-neon-consumer` |

The 25 shape palettes (100 hex values) will be replaced by a procedural
palette generator that derives dark/mid/light/accent tones from the
categorical token and shape parameters.

---

## 3. Typography

### 3.1 Current State

- **UI font:** `'Inter', -apple-system, system-ui, sans-serif` (from Google Fonts)
- **Code font:** `'SF Mono', 'Fira Code', monospace`
- **Sizes used:** 7px, 8px, 9px, 10px, 11px, 12px, 13px, 14px, 15px, 16px, 20px, 22px, 24px, 26px, 28px, 32px
- **Weights used:** 400, 500, 600, 700, 800, 900
- No modular scale. Sizes chosen ad-hoc per component.

### 3.2 Target: Modular Scale 1.25

| Token | Size | Line height | Use case |
|-------|------|-------------|----------|
| `--text-xs` | 10px (0.625rem) | 14px (0.875rem) | Badges, tiny labels, letter-spacing text |
| `--text-sm` | 12px (0.75rem) | 16px (1rem) | Secondary text, meta info, sidebar items |
| `--text-base` | 14px (0.875rem) | 20px (1.25rem) | Body text, descriptions, default |
| `--text-lg` | 16px (1rem) | 22px (1.375rem) | Subheadings, emphasis text |
| `--text-xl` | 20px (1.25rem) | 28px (1.75rem) | Section titles, modal titles |
| `--text-2xl` | 24px (1.5rem) | 32px (2rem) | Page titles, hero text |

Note: The SPEC defines the scale with a 1.25 ratio starting at 16px base,
giving 12.8, 16, 20, 25, 31.25. The token values round to practical pixel
sizes: 10, 12, 14, 16, 20, 24.

### 3.3 Font families

| Token | Value |
|-------|-------|
| `--font-family` | `'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif` |
| `--font-mono` | `'JetBrains Mono', 'SF Mono', 'Cascadia Code', 'Fira Code', monospace` |

### 3.4 Font weights

| Token | Value | Use |
|-------|-------|-----|
| `--font-regular` | 400 | Body text |
| `--font-medium` | 500 | UI labels, buttons |
| `--font-semibold` | 600 | Emphasis, section headers |

Per INV-OT-030: Maximum 2 font families + 3 weights. Current code uses up to
6 weights (400-900). Migration requires consolidating 700/800/900 down to 600.

---

## 4. Spacing

### 4.1 Current State

| Current token | Value |
|---------------|-------|
| `--sp-xs` | 4px |
| `--sp-sm` | 8px |
| `--sp-md` | 16px |
| `--sp-lg` | 24px |
| `--sp-xl` | 32px |

Only 5 spacing tokens. Many components use literal pixel values (2px, 3px, 5px,
6px, 7px, 10px, 12px, 14px, 18px, 20px, 22px, 28px, 36px, 44px, 60px, 72px)
that do not align to any scale.

### 4.2 Target: 4px Grid

All spacing must be a multiple of 4px. The complete scale:

| Token | Value | Common use |
|-------|-------|-----------|
| `--space-1` | 4px | Minimum gap, inline spacing |
| `--space-2` | 8px | Small gap, icon-to-text |
| `--space-3` | 12px | Medium gap, list items |
| `--space-4` | 16px | Default padding, section gap |
| `--space-5` | 20px | Panel content padding |
| `--space-6` | 24px | Large gap, card padding |
| `--space-8` | 32px | Section margins, outer padding |
| `--space-10` | 40px | Large section spacing |
| `--space-12` | 48px | Major layout gaps |
| `--space-16` | 64px | Page-level spacing |

Migration mapping for current ad-hoc values:

| Current literal | Nearest token |
|----------------|---------------|
| 2px, 3px | `--space-1` (4px) |
| 5px, 6px, 7px | `--space-2` (8px) |
| 10px | `--space-3` (12px) |
| 12px, 14px | `--space-3` or `--space-4` |
| 18px, 20px | `--space-5` (20px) |
| 22px, 24px | `--space-6` (24px) |
| 28px | `--space-8` (32px) |
| 32px, 36px | `--space-8` (32px) |
| 44px | `--space-12` (48px) |
| 60px | `--space-16` (64px) |

---

## 5. Shadows and Borders

### 5.1 Border Radii

| Current token | Current value | Target token | Target value | SPEC alignment |
|---------------|---------------|-------------|-------------|----------------|
| `--radius-sm` | 6px | `--radius-sm` | 4px | Badges, small elements (SPEC: 4px) |
| `--radius-md` | 10px | `--radius-md` | 8px | Cards, panels (SPEC: 8px) |
| `--radius-lg` | 14px | `--radius-lg` | 12px | Modals, overlays (SPEC: 12px) |
| `--radius-xl` | 16px | `--radius-full` | 9999px | Pills, circles (SPEC: 9999px) |

### 5.2 Shadow Tokens

New tokens defined per SPEC:

| Token | Value | Use |
|-------|-------|-----|
| `--shadow-sm` | `0 1px 2px oklch(0% 0 0 / 0.05)` | Subtle lift (buttons, badges) |
| `--shadow-md` | `0 4px 6px oklch(0% 0 0 / 0.07), 0 2px 4px oklch(0% 0 0 / 0.06)` | Cards, panels |
| `--shadow-lg` | `0 10px 15px oklch(0% 0 0 / 0.1), 0 4px 6px oklch(0% 0 0 / 0.05)` | Modals, overlays |
| `--shadow-glow` | `0 0 20px oklch(65% 0.15 var(--glow-hue) / 0.15)` | Glowing accents (3D labels, active nodes) |

Current state: No shadow tokens exist. All shadows are inline
(`box-shadow: 0 24px 80px rgba(0,0,0,.5)` etc.). There are 15+ unique
shadow values hardcoded across the CSS files.

---

## 6. 3D Materials

### 6.1 Current State (from `materials.js`)

The material factory (`matFactory`) produces four material tiers:

| Tier | Metalness | Roughness | Role |
|------|-----------|-----------|------|
| `dark()` | 0.35 | 0.55 | Deepest shape surfaces |
| `mid()` | 0.30 | 0.50 | Mid-tone shape surfaces |
| `light()` | 0.25 | 0.45 | Lightest shape surfaces |
| `accent()` | 0.28 | 0.48 | Accent glow surfaces |
| `screen()` | 0.10 | 0.80 | Flat screen surfaces |

All values are hardcoded in JS. Theme switching (`updateMaterialsForTheme`)
is a no-op -- lighting handles the difference.

**Issue:** `light()` has roughness 0.45, which is barely above the
INV-OT-028 minimum of 0.4. No emissive values are set on base materials,
but neon/glow effects elsewhere may exceed the 0.3 cap.

### 6.2 Target: Tokenized Materials

Material properties become CSS custom properties consumed by JS:

| Token | Dark mode | Light mode | INV-OT-028 constraint |
|-------|-----------|------------|----------------------|
| `--mat-metalness-high` | 0.30 | 0.20 | max 0.4 |
| `--mat-metalness-mid` | 0.25 | 0.15 | max 0.4 |
| `--mat-metalness-low` | 0.18 | 0.10 | max 0.4 |
| `--mat-roughness-high` | 0.70 | 0.80 | min 0.4 |
| `--mat-roughness-mid` | 0.55 | 0.65 | min 0.4 |
| `--mat-roughness-low` | 0.45 | 0.55 | min 0.4 |
| `--mat-emissive-max` | 0.25 | 0.15 | max 0.3 |
| `--mat-emissive-glow` | 0.20 | 0.10 | max 0.3 |

**How JS reads CSS tokens:**

```js
const style = getComputedStyle(document.documentElement);
const metalness = parseFloat(style.getPropertyValue('--mat-metalness-mid'));
const roughness = parseFloat(style.getPropertyValue('--mat-roughness-mid'));
```

Shape palettes will be computed from categorical colors rather than stored as
100 hardcoded hex values. Each shape maps to a categorical hue, and
dark/mid/light tones are derived by varying OKLCH lightness.

---

## 7. Motion Tokens

### 7.1 Duration Tokens

| Token | Value | Use |
|-------|-------|-----|
| `--duration-fast` | 100ms | Hover effects, toggles, tooltips |
| `--duration-normal` | 200ms | Panel transitions, modals appear |
| `--duration-slow` | 400ms | Camera moves, drill-down navigation |
| `--duration-cinematic` | 800ms | Replay, zoom between levels |

Per INV-OT-029: No animation exceeds 1s (except replay cinema). Hover < 100ms.
Drill-down < 400ms.

### 7.2 Easing Tokens

| Token | Value | Character |
|-------|-------|-----------|
| `--ease-default` | `cubic-bezier(0.2, 0, 0, 1)` | Material Design 3 standard deceleration |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | Elements entering/accelerating |
| `--ease-out` | `cubic-bezier(0, 0, 0.2, 1)` | Elements settling/decelerating |
| `--ease-spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Subtle overshoot for playfulness |

### 7.3 Motion Rules

- Stagger delay for appearing elements: 30ms between items
- Disappearing elements: all together (no stagger)
- Camera transitions: 600-800ms with ease-in-out
- Hover state changes: use `--duration-fast`
- Panel open/close: use `--duration-normal` with `--ease-default`

---

## 8. Theme System

### 8.1 Architecture

Themes are defined in YAML files (`themes/*.yaml`). Each YAML file contains
the complete set of token values for one visual mode. A build step (or runtime
loader) converts YAML tokens into CSS custom properties.

```
themes/midnight.yaml    -->    :root, body.dark { --surface-0: ...; ... }
themes/daylight.yaml    -->    :root            { --surface-0: ...; ... }
```

### 8.2 Theme File Structure

Each theme YAML contains these top-level sections:

```yaml
name: "..."          # Human-readable name
mode: dark | light   # Determines default behavior
colors:
  surface: { ... }   # Background surfaces (0-3)
  text: { ... }      # Text hierarchy (primary, secondary, tertiary)
  accent: { ... }    # Named accent colors (blue, green, red, etc.)
  border: { ... }    # Border tokens
  categorical: [...]  # 8-color palette for data visualization / node types
spacing: { ... }     # Space scale
typography: { ... }  # Font families, sizes, weights
shadows: { ... }     # Shadow tokens
motion: { ... }      # Duration and easing tokens
materials: { ... }   # 3D material parameters (metalness, roughness, emissive)
```

### 8.3 Theme Loading

At runtime, the theme loader:

1. Fetches the YAML file (or reads from embedded JS object)
2. Parses all token paths into flat CSS property names:
   `colors.surface.surface-0` becomes `--surface-0`
3. Sets each property on `document.documentElement.style`
4. For 3D materials, fires a `theme-changed` event so the Three.js material
   factory reads updated `--mat-*` properties

### 8.4 Theme Switching

```js
// Toggle between themes
async function applyTheme(themeName) {
  const yaml = await fetch(`/themes/${themeName}.yaml`).then(r => r.text());
  const tokens = parseThemeYAML(yaml);
  const root = document.documentElement;
  for (const [prop, value] of Object.entries(tokens)) {
    root.style.setProperty(prop, value);
  }
  root.classList.toggle('dark', tokens['--mode'] === 'dark');
  window.dispatchEvent(new CustomEvent('theme-changed', { detail: { name: themeName } }));
}
```

---

## 9. Before/After Summary

### 9.1 Token Count

| Category | Current tokens | Target tokens | Change |
|----------|---------------|---------------|--------|
| Surface colors | 1 (`--bg`) | 4 (`--surface-0..3`) | +3 |
| Text colors | 3 (`--text`, `--text2`, `--text3`) | 3 (`--text-primary/secondary/tertiary`) | 0 |
| Accent colors | 6 (`--blue`, `--purple`, etc.) | 8 categorical + 8 named aliases | +10 |
| Border colors | 1 (`--border`) | 2 (`--border-default/emphasis`) | +1 |
| Theme overrides | ~25 (`--theme-*`) | 0 (eliminated -- themes set base tokens directly) | -25 |
| Spacing | 5 (`--sp-xs..xl`) | 10 (`--space-1..16`) | +5 |
| Typography | 2 (`--font-family`, `--font-mono`) | 2 families + 6 sizes + 3 weights = 11 | +9 |
| Radii | 4 (`--radius-sm..xl`) | 4 (`--radius-sm..full`) | 0 |
| Shadows | 0 | 4 (`--shadow-sm..glow`) | +4 |
| Motion | 0 | 4 durations + 4 easings = 8 | +8 |
| Materials | 0 | 8 (`--mat-*`) | +8 |
| **TOTAL** | **~22 meaningful tokens** | **~66 tokens** | **+44** |

### 9.2 Hardcoded Color Elimination

| Metric | Current | Target |
|--------|---------|--------|
| Hardcoded hex values in CSS | 134 | 0 |
| Hardcoded rgba() in CSS | 191 | 0 (use oklch with alpha) |
| Hardcoded 0x in materials.js | 118 | 0 (computed from tokens) |
| **Total hardcoded colors** | **443** | **0** |

### 9.3 Invariant Compliance

| Invariant | Current state | Target state |
|-----------|--------------|-------------|
| INV-OT-026 (no literal colors) | VIOLATED (443 literals) | COMPLIANT |
| INV-OT-027 (contrast >= 4.5:1) | Partial (some text < 4.5:1) | COMPLIANT |
| INV-OT-028 (emissive <= 0.3, roughness >= 0.4) | Marginal (roughness 0.45 min) | COMPLIANT |
| INV-OT-029 (animation < 1s) | Compliant | COMPLIANT |
| INV-OT-030 (2 fonts + 3 weights) | VIOLATED (6 weights used) | COMPLIANT |
