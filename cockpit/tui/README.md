# ontology-map

[![CI](https://github.com/gustavoschneiter/ontology-map/actions/workflows/ci.yml/badge.svg)](https://github.com/gustavoschneiter/ontology-map/actions/workflows/ci.yml)
[![Crates.io](https://img.shields.io/crates/v/ontology-map-tui)](https://crates.io/crates/ontology-map-tui)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)

Terminal UI for spatial code architecture visualization. See your codebase as an interactive force-directed graph rendered with Braille characters.

## Install

### One-liner (macOS / Linux)

```bash
curl -LsSf https://github.com/gustavoschneiter/ontology-map/releases/latest/download/install.sh | sh
```

### Cargo

```bash
cargo install ontology-map-tui
```

### From Source

```bash
git clone https://github.com/gustavoschneiter/ontology-map.git
cd ontology-map/tui
cargo install --path .
```

## Usage

```bash
# Analyze current directory
ontology-map

# Analyze a specific project
ontology-map /path/to/project

# JSON output (for piping to other tools)
ontology-map --json /path/to/project

# Print stats only (no TUI)
ontology-map --stats

# Disable git integration
ontology-map --no-git

# Limit file count
ontology-map --max-files 1000
```

## Keybindings

| Key | Action |
|-----|--------|
| `h` `j` `k` `l` / Arrows | Pan viewport |
| `+` / `-` | Zoom in / out |
| `0` | Reset view |
| `Tab` / `Shift+Tab` | Cycle through nodes |
| `Enter` | Toggle detail panel |
| `/` | Open fuzzy search |
| `s` | Cycle sort mode |
| `e` | Toggle edges |
| `n` | Toggle labels |
| `t` | Toggle git time-travel |
| `c` | Toggle churn heatmap |
| `b` | Toggle blame overlay |
| `Esc` | Deselect / close search |
| `q` / `Ctrl+C` | Quit |

## Supported Languages

| Language | Adapter | Extracts |
|----------|---------|----------|
| Python | tree-sitter | modules, classes, functions, decorators |
| JavaScript | tree-sitter | modules, functions, classes, exports, components |
| TypeScript | tree-sitter | modules, functions, classes, interfaces, types, exports |
| Go | tree-sitter | packages, functions, structs, interfaces, methods |
| Rust | tree-sitter | modules, functions, structs, enums, traits, impls |
| Java | tree-sitter | packages, classes, interfaces, methods |
| C# | tree-sitter | namespaces, classes, interfaces, methods |
| Docker Compose | YAML parser | services, networks, volumes |

## Shell Completions

Shell completions are included in release archives. Install them for your shell:

### Bash

```bash
cp completions/ontology-map.bash /usr/local/share/bash-completion/completions/ontology-map
```

### Zsh

```bash
cp completions/_ontology-map /usr/local/share/zsh/site-functions/_ontology-map
```

### Fish

```bash
cp completions/ontology-map.fish ~/.config/fish/completions/ontology-map.fish
```

## Man Page

A man page is included in release archives:

```bash
cp man/ontology-map.1 /usr/local/share/man/man1/
```

## License

MIT License. See [LICENSE](../LICENSE).
