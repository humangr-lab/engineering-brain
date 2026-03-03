# Ontology Map — VS Code Extension

Spatial code architecture visualization for Visual Studio Code. See your codebase as an interactive force-directed graph.

## Features

- **Interactive graph**: Pan, zoom, and click nodes to navigate your codebase
- **Force-directed layout**: Automatic spatial arrangement based on code dependencies
- **Color-coded nodes**: Each symbol type (module, class, function, etc.) has a distinct color
- **Click-to-open**: Click any node to jump to the source file in the editor
- **Live refresh**: Debounced re-analysis on file save
- **Tooltip details**: Hover over nodes to see type, file path, and line count
- **Toolbar controls**: Toggle labels, edges, fit view, and manual refresh

## Requirements

- The `ontology-map` TUI binary must be installed and available in your `PATH`
- Install it with: `cargo install ontology-map-tui`
- Or download from [GitHub Releases](https://github.com/gustavoschneiter/ontology-map/releases)

## Usage

1. Open a project folder in VS Code
2. Run **Ontology Map: Open Architecture View** from the Command Palette (`Cmd+Shift+P`)
3. Or use the keyboard shortcut: `Cmd+Shift+M` (macOS) / `Ctrl+Shift+M` (Windows/Linux)

## Commands

| Command | Description | Shortcut |
|---------|-------------|----------|
| `Ontology Map: Open Architecture View` | Open the graph panel | `Cmd+Shift+M` |
| `Ontology Map: Refresh Graph` | Re-analyze the workspace | — |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `ontology-map.binaryPath` | `"ontology-map"` | Path to the ontology-map binary |
| `ontology-map.maxFiles` | `5000` | Maximum number of files to analyze |
| `ontology-map.maxCommits` | `200` | Maximum git commits to analyze |

## Graph Interaction

| Action | Effect |
|--------|--------|
| **Click node** | Open source file in editor |
| **Hover node** | Show tooltip with type, path, line count |
| **Drag canvas** | Pan the viewport |
| **Scroll** | Zoom in/out |
| **Labels button** | Toggle node labels |
| **Edges button** | Toggle dependency edges |
| **Fit button** | Fit all nodes in view |
| **Refresh button** | Re-analyze project |

## Node Colors

| Type | Color |
|------|-------|
| Module / Namespace | Blue |
| Class | Purple |
| Function | Green |
| Method | Dark Green |
| Export | Teal |
| Component | Orange |
| Hook | Pink |
| Struct | Light Purple |
| Interface / Trait | Light Blue |

## Known Issues

- Very large projects (>5000 nodes) may take several seconds to render
- The force simulation runs synchronously in the webview — initial layout may take a moment

## License

MIT License. See [LICENSE](../LICENSE).
