# Engineering Brain — Cockpit

Interactive visualization suite for the Engineering Brain knowledge graph.

## Components

| Component | Technology | Status |
|-----------|-----------|--------|
| **Server** | FastAPI + Uvicorn | Production |
| **Client** | Three.js 3D + vanilla JS | Production |
| **Desktop** | Tauri 2.0 + React | Experimental |
| **TUI** | Rust + Ratatui | Production |
| **VS Code** | TypeScript extension | Production |

## Quick Start

```bash
# Install brain + cockpit
pip install -e ../brain/ -e .

# Start server
python -m server.main

# Open http://localhost:8420
```

## API Endpoints

| Route | Method | Description |
|-------|--------|-------------|
| `/api/health` | GET | Liveness probe |
| `/api/graph` | GET | Full graph snapshot (nodes + edges) |
| `/api/graph/version` | GET | Lightweight version check |
| `/api/stats` | GET | Aggregate statistics |
| `/api/nodes` | GET | Paginated/filtered nodes |
| `/api/nodes/{id}` | GET | Single node detail |
| `/api/edges` | GET | Edge listing |
| `/api/packs` | POST | Knowledge pack creation |
| `/api/epistemic` | GET | Epistemic stats (E0-E5, freshness, contradictions) |
| `/api/stream` | GET | Server-Sent Events (live updates) |
| `/api/admin/reload` | POST | Manual brain reload |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8420` | Server port |
| `BRAIN_SEEDS_DIR` | (built-in) | Path to YAML seed files |
| `BRAIN_JSON_PATH` | — | Path to JSON brain snapshot |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `RELOAD_ENABLED` | `true` | Enable hot-reload on seed changes |

## Development

```bash
# Python tests
pytest tests/ -v

# JavaScript tests
npm ci && npx vitest run

# E2E tests (requires Playwright)
npx playwright test
```

## Client Features

- 3D orbital layout with Three.js
- Click-to-drill submaps (5 levels)
- Knowledge Library with 5 grouping modes
- Cmd+K search overlay
- Epistemic dashboard
- Auto-guided tour
- WCAG 2.1 AA keyboard navigation
