# CI/CD Pipeline Specification — Ontology Map Toolkit

> Status: **Draft** | Date: 2026-02-27 | Scope: build, test, lint, visual regression, bundle enforcement

---

## 1. pyproject.toml Complete Specification

Replace the current `pyproject.toml` with:

```toml
[project]
name = "ontology-map-toolkit"
version = "0.1.0"
description = "Framework for spatial 3D representations of software systems"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
authors = [
    { name = "Gustavo Schneiter" },
]
keywords = ["ontology", "visualization", "3d", "knowledge-graph", "software-architecture"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.14",
    "Topic :: Software Development :: Documentation",
    "Topic :: Scientific/Engineering :: Visualization",
]

dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pyyaml>=6.0",
    "jsonschema>=4.20.0",
    "click>=8.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "playwright>=1.49.0",
    "pytest-playwright>=0.5.0",
    "pre-commit>=4.0.0",
    "Pillow>=10.0.0",
]
tui = [
    "textual>=0.89.0",
]
adapters = [
    "falkordb>=1.0.0",
    "neo4j>=5.0.0",
    "httpx>=0.27.0",
]

[project.urls]
Homepage = "https://github.com/gustavoschneiter/ontology-map-toolkit"
Documentation = "https://github.com/gustavoschneiter/ontology-map-toolkit#readme"
Repository = "https://github.com/gustavoschneiter/ontology-map-toolkit"
Issues = "https://github.com/gustavoschneiter/ontology-map-toolkit/issues"

[project.scripts]
ontology-map = "ontology_map_toolkit.cli:main"

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
include = ["ontology_map_toolkit*"]

[tool.setuptools.package-data]
ontology_map_toolkit = ["py.typed"]

# ── Ruff ──────────────────────────────────────────────────────────────
[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src", "server", "tests"]

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "TCH",  # flake8-type-checking
    "RUF",  # ruff-specific rules
]
ignore = [
    "E501",   # line too long (handled by formatter)
]

[tool.ruff.lint.isort]
known-first-party = ["ontology_map_toolkit", "server"]

# ── Mypy ──────────────────────────────────────────────────────────────
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = ["uvicorn.*", "falkordb.*", "neo4j.*", "textual.*"]
ignore_missing_imports = true

# ── Pytest ────────────────────────────────────────────────────────────
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "visual: visual regression tests requiring playwright",
]
```

### Package Stub

The `src/ontology_map_toolkit/` package needs at minimum two files:

**`src/ontology_map_toolkit/__init__.py`**:
```python
"""Ontology Map Toolkit — spatial 3D representations of software systems."""

__version__ = "0.1.0"
```

**`src/ontology_map_toolkit/cli.py`**:
```python
"""CLI entry point for ontology-map command."""

from __future__ import annotations

import click


@click.group()
@click.version_option()
def main() -> None:
    """Ontology Map Toolkit — spatial 3D representations of software systems."""


@main.command()
@click.option("--port", default=8420, help="Port to serve on.")
@click.option("--host", default="127.0.0.1", help="Host to bind to.")
@click.option("--seeds", default=None, help="Path to brain seeds directory.")
@click.option("--brain-json", default=None, help="Path to brain JSON snapshot.")
def serve(port: int, host: str, seeds: str | None, brain_json: str | None) -> None:
    """Start the development server."""
    import uvicorn

    from server.main import _create_app
    from server.config import Config

    cfg = Config(host=host, port=port)
    if seeds:
        cfg = Config(**{**cfg.__dict__, "brain_seeds_dir": seeds})
    if brain_json:
        cfg = Config(**{**cfg.__dict__, "brain_json_path": brain_json})

    app = _create_app(cfg)
    uvicorn.run(app, host=host, port=port, log_level="info")


@main.command()
@click.argument("project_dir", type=click.Path(exists=True))
@click.option("--output", "-o", default="graph_data.json", help="Output file path.")
def render(project_dir: str, output: str) -> None:
    """Scan a project directory and generate graph_data.json."""
    click.echo(f"Scanning {project_dir}...")
    click.echo(f"Output: {output}")
    # TODO: implement adapter pipeline (codebase AST, openapi, docker-compose)
    click.echo("render command not yet implemented")
```

---

## 2. GitHub Actions Workflows

### 2.1 `.github/workflows/ci.yml` — Main CI

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  # ── Python Tests (matrix) ───────────────────────────────────────────
  python-tests:
    name: "Tests / Python ${{ matrix.python-version }}"
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.14"]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          allow-prereleases: true

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ matrix.python-version }}-${{ hashFiles('pyproject.toml') }}
          restore-keys: pip-${{ matrix.python-version }}-

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run tests
        run: pytest tests/ -v --tb=short --junitxml=reports/test-results.xml

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results-py${{ matrix.python-version }}
          path: reports/test-results.xml

  # ── Python Lint ─────────────────────────────────────────────────────
  python-lint:
    name: "Lint / Python"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Ruff check
        run: ruff check src/ server/ tests/ --output-format=github

      - name: Ruff format check
        run: ruff format --check src/ server/ tests/

      - name: Mypy strict
        run: mypy src/ server/ --strict

  # ── JS Lint ─────────────────────────────────────────────────────────
  js-lint:
    name: "Lint / JavaScript"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: "22"

      - name: Install eslint
        run: npm install --save-dev eslint@9 @eslint/js globals

      - name: Create eslint config
        run: |
          cat > eslint.config.mjs << 'ESLINT_EOF'
          import js from "@eslint/js";
          import globals from "globals";

          export default [
            js.configs.recommended,
            {
              languageOptions: {
                ecmaVersion: 2024,
                sourceType: "module",
                globals: {
                  ...globals.browser,
                },
              },
              rules: {
                "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
                "no-console": "off",
                "prefer-const": "error",
                "no-var": "error",
              },
            },
            {
              ignores: [
                "client/js/data/**",
                "node_modules/**",
              ],
            },
          ];
          ESLINT_EOF

      - name: Run eslint
        run: npx eslint client/js/ --max-warnings 0

  # ── Schema Validation ──────────────────────────────────────────────
  schema-validate:
    name: "Validate / JSON Schemas"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install jsonschema
        run: pip install jsonschema>=4.20.0

      - name: Validate schemas are well-formed
        run: |
          python - << 'PYEOF'
          import json
          import sys
          from pathlib import Path
          from jsonschema import Draft202012Validator

          schema_dir = Path("schemas")
          errors = 0

          for schema_file in schema_dir.glob("*.json"):
              print(f"Validating {schema_file}...")
              with open(schema_file) as f:
                  schema = json.load(f)
              try:
                  Draft202012Validator.check_schema(schema)
                  print(f"  OK — valid JSON Schema 2020-12")
              except Exception as e:
                  print(f"  FAIL — {e}")
                  errors += 1

              # Validate embedded examples
              if "examples" in schema:
                  validator = Draft202012Validator(schema)
                  for i, example in enumerate(schema["examples"]):
                      errs = list(validator.iter_errors(example))
                      if errs:
                          print(f"  FAIL — example[{i}]: {errs[0].message}")
                          errors += 1
                      else:
                          print(f"  OK — example[{i}] validates")

          if errors:
              print(f"\n{errors} schema error(s) found")
              sys.exit(1)
          print("\nAll schemas valid")
          PYEOF

  # ── Bundle Size ─────────────────────────────────────────────────────
  bundle-size:
    name: "Check / Bundle Size"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check client bundle size
        run: |
          chmod +x scripts/check-bundle-size.sh
          scripts/check-bundle-size.sh

      - name: Comment PR with size report
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            if (fs.existsSync('reports/bundle-size.md')) {
              const body = fs.readFileSync('reports/bundle-size.md', 'utf8');
              github.rest.issues.createComment({
                issue_number: context.issue.number,
                owner: context.repo.owner,
                repo: context.repo.repo,
                body: body,
              });
            }
```

### 2.2 `.github/workflows/visual-regression.yml` — Visual Regression

```yaml
name: Visual Regression

on:
  pull_request:
    branches: [main]
    paths:
      - "client/**"
      - "server/**"
      - "schemas/**"
      - "themes/**"

concurrency:
  group: visual-${{ github.ref }}
  cancel-in-progress: true

jobs:
  visual-regression:
    name: "Visual / Screenshot Diff"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Install Playwright browsers
        run: playwright install chromium --with-deps

      - name: Start dev server
        run: |
          python -m server.main --host 127.0.0.1 --port 8420 &
          SERVER_PID=$!
          echo "SERVER_PID=$SERVER_PID" >> "$GITHUB_ENV"

          # Wait for server to be ready
          for i in $(seq 1 30); do
            if curl -sf http://127.0.0.1:8420/api/health > /dev/null 2>&1; then
              echo "Server ready after ${i}s"
              break
            fi
            sleep 1
          done

      - name: Take screenshots
        run: |
          python - << 'PYEOF'
          import asyncio
          from pathlib import Path
          from playwright.async_api import async_playwright

          SCREENSHOTS = [
              ("default-view", "http://127.0.0.1:8420", {"width": 1920, "height": 1080}),
              ("mobile-view", "http://127.0.0.1:8420", {"width": 390, "height": 844}),
              ("dark-1080p", "http://127.0.0.1:8420", {"width": 1920, "height": 1080}),
          ]

          async def main():
              out = Path("reports/screenshots/current")
              out.mkdir(parents=True, exist_ok=True)

              async with async_playwright() as p:
                  browser = await p.chromium.launch()

                  for name, url, viewport in SCREENSHOTS:
                      page = await browser.new_page(viewport_size=viewport)
                      await page.goto(url, wait_until="networkidle")
                      # Wait for 3D scene to stabilize
                      await page.wait_for_timeout(3000)
                      await page.screenshot(
                          path=str(out / f"{name}.png"),
                          full_page=False,
                      )
                      print(f"  captured {name} ({viewport['width']}x{viewport['height']})")
                      await page.close()

                  await browser.close()

          asyncio.run(main())
          PYEOF

      - name: Download baseline screenshots
        uses: actions/cache@v4
        id: baseline-cache
        with:
          path: reports/screenshots/baseline
          key: visual-baseline-${{ github.base_ref }}-${{ hashFiles('client/**', 'themes/**') }}
          restore-keys: |
            visual-baseline-${{ github.base_ref }}-
            visual-baseline-main-

      - name: Compare screenshots
        id: compare
        run: |
          mkdir -p reports/screenshots/diff

          python - << 'PYEOF'
          import json
          import sys
          from pathlib import Path

          baseline_dir = Path("reports/screenshots/baseline")
          current_dir = Path("reports/screenshots/current")
          diff_dir = Path("reports/screenshots/diff")
          results = []

          if not baseline_dir.exists() or not any(baseline_dir.glob("*.png")):
              print("No baseline found — saving current as new baseline")
              baseline_dir.mkdir(parents=True, exist_ok=True)
              for f in current_dir.glob("*.png"):
                  import shutil
                  shutil.copy(f, baseline_dir / f.name)
              results.append({"status": "new_baseline", "message": "First run — baseline created"})
          else:
              try:
                  from PIL import Image, ImageChops
                  import math

                  for current_file in sorted(current_dir.glob("*.png")):
                      baseline_file = baseline_dir / current_file.name
                      name = current_file.stem

                      if not baseline_file.exists():
                          results.append({"name": name, "status": "new", "diff_pct": 100.0})
                          continue

                      img_a = Image.open(baseline_file).convert("RGB")
                      img_b = Image.open(current_file).convert("RGB")

                      if img_a.size != img_b.size:
                          results.append({"name": name, "status": "size_changed",
                                          "old_size": list(img_a.size), "new_size": list(img_b.size)})
                          continue

                      diff = ImageChops.difference(img_a, img_b)
                      diff.save(str(diff_dir / f"{name}-diff.png"))

                      pixels = list(diff.getdata())
                      total_diff = sum(sum(p) for p in pixels)
                      max_diff = len(pixels) * 255 * 3
                      pct = (total_diff / max_diff) * 100 if max_diff > 0 else 0

                      status = "pass" if pct < 0.5 else "fail"
                      results.append({"name": name, "status": status, "diff_pct": round(pct, 3)})

              except ImportError:
                  print("Pillow not installed — pixel diff skipped, doing byte comparison")
                  for current_file in sorted(current_dir.glob("*.png")):
                      baseline_file = baseline_dir / current_file.name
                      name = current_file.stem
                      if not baseline_file.exists():
                          results.append({"name": name, "status": "new"})
                      elif current_file.read_bytes() == baseline_file.read_bytes():
                          results.append({"name": name, "status": "pass", "diff_pct": 0})
                      else:
                          results.append({"name": name, "status": "changed"})

          with open("reports/screenshots/results.json", "w") as f:
              json.dump(results, f, indent=2)

          # Generate markdown summary
          md = ["## Visual Regression Report\n"]
          has_failures = False
          for r in results:
              if r.get("status") == "new_baseline":
                  md.append(f"- Baseline created (first run)\n")
              elif r.get("status") == "pass":
                  md.append(f"- `{r['name']}` — PASS (diff: {r.get('diff_pct', 0)}%)\n")
              elif r.get("status") == "new":
                  md.append(f"- `{r['name']}` — NEW (no baseline)\n")
              else:
                  has_failures = True
                  md.append(f"- `{r['name']}` — **CHANGED** (diff: {r.get('diff_pct', '?')}%)\n")

          if has_failures:
              md.append("\n> Visual changes detected. Review the diff images in the artifacts.\n")

          with open("reports/visual-regression.md", "w") as f:
              f.writelines(md)

          if has_failures:
              print("Visual differences detected")

          PYEOF

      - name: Upload screenshots
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: visual-regression-screenshots
          path: reports/screenshots/

      - name: Comment PR with visual report
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            if (fs.existsSync('reports/visual-regression.md')) {
              const body = fs.readFileSync('reports/visual-regression.md', 'utf8');
              github.rest.issues.createComment({
                issue_number: context.issue.number,
                owner: context.repo.owner,
                repo: context.repo.repo,
                body: body,
              });
            }

      - name: Stop server
        if: always()
        run: kill $SERVER_PID 2>/dev/null || true

      - name: Update baseline cache
        if: github.event_name == 'pull_request' && success()
        run: |
          # Baseline is updated via cache key — new screenshots become baseline
          # when the cache key changes (client/** or themes/** hash changes)
          cp -r reports/screenshots/current/* reports/screenshots/baseline/ 2>/dev/null || true
```

---

## 3. Pre-commit Configuration

File: `.pre-commit-config.yaml`

```yaml
# .pre-commit-config.yaml
# Install: pip install pre-commit && pre-commit install

repos:
  # ── Standard hooks ──────────────────────────────────────────────────
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
        args: [--markdown-linebreak-ext=md]
      - id: end-of-file-fixer
      - id: check-yaml
        args: [--allow-multiple-documents]
      - id: check-json
      - id: check-merge-conflict
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: detect-private-key

  # ── Ruff (lint + format) ────────────────────────────────────────────
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
        types_or: [python, pyi]
      - id: ruff-format
        types_or: [python, pyi]

  # ── JSON Schema validation ─────────────────────────────────────────
  - repo: local
    hooks:
      - id: validate-json-schemas
        name: Validate JSON Schemas
        entry: python -c "
          import json, sys;
          from pathlib import Path;
          from jsonschema import Draft202012Validator;
          errors = 0;
          schemas = sorted(Path('schemas').glob('*.json'));
          [schemas or sys.exit(0)];
          exec('''
          for f in schemas:
              try:
                  Draft202012Validator.check_schema(json.loads(f.read_text()))
                  print(f\"  OK {f}\")
              except Exception as e:
                  print(f\"  FAIL {f}: {e}\")
                  errors += 1
          if errors:
              print(f\"{errors} schema error(s)\")
              sys.exit(1)
          print(\"All schemas valid\")
          ''')
          "
        language: python
        additional_dependencies: ["jsonschema>=4.20.0"]
        files: ^schemas/.*\.json$
        pass_filenames: false

  # ── YAML lint (themes + schemas) ────────────────────────────────────
  - repo: https://github.com/adrienverge/yamllint
    rev: v1.35.1
    hooks:
      - id: yamllint
        args: [-d, "{extends: relaxed, rules: {line-length: {max: 150}}}"]
        files: ^(themes|schemas)/.*\.ya?ml$

  # ── Bundle size guard ──────────────────────────────────────────────
  - repo: local
    hooks:
      - id: bundle-size-check
        name: Check client bundle size
        entry: bash scripts/check-bundle-size.sh
        language: system
        files: ^client/
        pass_filenames: false
```

---

## 4. Bundle Size Enforcement

File: `scripts/check-bundle-size.sh`

```bash
#!/usr/bin/env bash
# scripts/check-bundle-size.sh
#
# Enforce the SPEC bundle size budget:
#   Phase 0+1 (initial load) < 250 KB gzip
#   Total client/ < 500 KB gzip
#
# Exits 0 if within budget, 1 if over budget.
# Writes a markdown report to reports/bundle-size.md

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────
CLIENT_DIR="client"
BUDGET_INITIAL_KB=250      # Phase 0+1: HTML + CSS + core JS (no data/)
BUDGET_TOTAL_KB=500        # Everything in client/
REPORT_DIR="reports"

# ── Setup ─────────────────────────────────────────────────────────────
mkdir -p "$REPORT_DIR"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# ── Measure by file type ─────────────────────────────────────────────
measure_gzip() {
    local pattern="$1"
    local label="$2"
    local exclude="${3:-}"

    local total_raw=0
    local total_gz=0
    local count=0

    while IFS= read -r -d '' file; do
        if [ -n "$exclude" ] && echo "$file" | grep -q "$exclude"; then
            continue
        fi
        raw_size=$(wc -c < "$file")
        gz_file="$TMPDIR/$(basename "$file").gz"
        gzip -c "$file" > "$gz_file"
        gz_size=$(wc -c < "$gz_file")
        total_raw=$((total_raw + raw_size))
        total_gz=$((total_gz + gz_size))
        count=$((count + 1))
    done < <(find "$CLIENT_DIR" -name "$pattern" -type f -print0 2>/dev/null)

    echo "$label|$count|$total_raw|$total_gz"
}

# ── Collect metrics ──────────────────────────────────────────────────
html_stats=$(measure_gzip "*.html" "HTML")
css_stats=$(measure_gzip "*.css" "CSS")
js_core_stats=$(measure_gzip "*.js" "JS (core)" "data/")
js_data_stats=$(measure_gzip "*.js" "JS (data)" "")
font_stats=$(measure_gzip "*.woff2" "Fonts")

# Parse JS data — we need to subtract core from total to isolate data/
js_all_gz=$(echo "$js_data_stats" | cut -d'|' -f4)
js_core_gz=$(echo "$js_core_stats" | cut -d'|' -f4)
js_data_only_gz=$((js_all_gz - js_core_gz))

# ── Calculate totals ─────────────────────────────────────────────────
html_gz=$(echo "$html_stats" | cut -d'|' -f4)
css_gz=$(echo "$css_stats" | cut -d'|' -f4)

initial_gz=$((html_gz + css_gz + js_core_gz))
initial_kb=$((initial_gz / 1024))

# Total gzip of entire client/
total_gz_file="$TMPDIR/client-total.tar.gz"
tar czf "$total_gz_file" "$CLIENT_DIR" 2>/dev/null
total_gz=$(wc -c < "$total_gz_file")
total_kb=$((total_gz / 1024))

# ── Budget check ─────────────────────────────────────────────────────
initial_pass="PASS"
total_pass="PASS"
exit_code=0

if [ "$initial_kb" -gt "$BUDGET_INITIAL_KB" ]; then
    initial_pass="FAIL"
    exit_code=1
fi

if [ "$total_kb" -gt "$BUDGET_TOTAL_KB" ]; then
    total_pass="FAIL"
    exit_code=1
fi

# ── Console output ───────────────────────────────────────────────────
echo "=== Bundle Size Report ==="
echo ""
printf "%-20s %8s %8s\n" "Type" "Raw" "Gzip"
printf "%-20s %8s %8s\n" "----" "---" "----"

for stats in "$html_stats" "$css_stats" "$js_core_stats"; do
    label=$(echo "$stats" | cut -d'|' -f1)
    raw=$(echo "$stats" | cut -d'|' -f3)
    gz=$(echo "$stats" | cut -d'|' -f4)
    printf "%-20s %7sB %7sB\n" "$label" "$raw" "$gz"
done

printf "%-20s %8s %7sB\n" "JS (data/)" "-" "$js_data_only_gz"
echo ""
echo "Phase 0+1 (initial): ${initial_kb} KB gzip [${initial_pass}] (budget: ${BUDGET_INITIAL_KB} KB)"
echo "Total client/:       ${total_kb} KB gzip [${total_pass}] (budget: ${BUDGET_TOTAL_KB} KB)"

# ── Markdown report ──────────────────────────────────────────────────
cat > "$REPORT_DIR/bundle-size.md" << MDEOF
## Bundle Size Report

| Type | Files | Raw | Gzip |
|------|------:|----:|-----:|
| HTML | $(echo "$html_stats" | cut -d'|' -f2) | $(echo "$html_stats" | cut -d'|' -f3) B | $(echo "$html_stats" | cut -d'|' -f4) B |
| CSS | $(echo "$css_stats" | cut -d'|' -f2) | $(echo "$css_stats" | cut -d'|' -f3) B | $(echo "$css_stats" | cut -d'|' -f4) B |
| JS (core) | $(echo "$js_core_stats" | cut -d'|' -f2) | $(echo "$js_core_stats" | cut -d'|' -f3) B | $(echo "$js_core_stats" | cut -d'|' -f4) B |
| JS (data/) | — | — | ${js_data_only_gz} B |

### Budget

| Metric | Measured | Budget | Status |
|--------|----------|--------|--------|
| **Phase 0+1 (initial load)** | ${initial_kb} KB | ${BUDGET_INITIAL_KB} KB | ${initial_pass} |
| **Total client/** | ${total_kb} KB | ${BUDGET_TOTAL_KB} KB | ${total_pass} |

> Phase 0+1 = HTML + CSS + core JS (excludes \`client/js/data/\`).
> Budget from SPEC Section 11: Lightweight Architecture.
MDEOF

exit "$exit_code"
```

---

## 5. Development Workflow — Makefile

File: `Makefile`

```makefile
# Makefile — Ontology Map Toolkit
# Usage: make <target>

.DEFAULT_GOAL := help
SHELL := /bin/bash

PYTHON := python3
VENV := .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

# ── Setup ─────────────────────────────────────────────────────────────

.PHONY: install
install: $(VENV)/bin/activate ## Install all dependencies (dev + adapters)
	$(PIP) install -e ".[dev,adapters]"
	$(PY) -m playwright install chromium

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip

.PHONY: install-hooks
install-hooks: ## Install pre-commit hooks
	$(VENV)/bin/pre-commit install

# ── Development ───────────────────────────────────────────────────────

.PHONY: dev
dev: ## Start development server on port 8420
	$(PY) -m server.main --host 127.0.0.1 --port 8420

.PHONY: dev-seeds
dev-seeds: ## Start dev server loading from brain seeds
	$(PY) -m server.main --host 127.0.0.1 --port 8420 --seeds ../brains/src/engineering_brain/seeds

# ── Testing ───────────────────────────────────────────────────────────

.PHONY: test
test: ## Run all tests
	$(PY) -m pytest tests/ -v --tb=short

.PHONY: test-fast
test-fast: ## Run tests excluding slow and visual
	$(PY) -m pytest tests/ -v --tb=short -m "not slow and not visual"

.PHONY: test-visual
test-visual: ## Run visual regression tests (requires playwright)
	$(PY) -m pytest tests/ -v -m visual

.PHONY: test-cov
test-cov: ## Run tests with coverage
	$(PY) -m pytest tests/ -v --cov=server --cov=src/ontology_map_toolkit --cov-report=term --cov-report=html:reports/coverage

# ── Linting ───────────────────────────────────────────────────────────

.PHONY: lint
lint: lint-py lint-format lint-types ## Run all linters

.PHONY: lint-py
lint-py: ## Run ruff linter
	$(VENV)/bin/ruff check src/ server/ tests/

.PHONY: lint-format
lint-format: ## Check formatting
	$(VENV)/bin/ruff format --check src/ server/ tests/

.PHONY: lint-types
lint-types: ## Run mypy type checker
	$(VENV)/bin/mypy src/ server/ --strict

.PHONY: fix
fix: ## Auto-fix lint + format issues
	$(VENV)/bin/ruff check --fix src/ server/ tests/
	$(VENV)/bin/ruff format src/ server/ tests/

# ── Schemas ───────────────────────────────────────────────────────────

.PHONY: validate-schemas
validate-schemas: ## Validate all JSON schemas in schemas/
	$(PY) -c "\
	import json, sys; \
	from pathlib import Path; \
	from jsonschema import Draft202012Validator; \
	errs = 0; \
	[print(f'  OK {f}') if not Draft202012Validator.check_schema(json.loads(f.read_text())) else None for f in sorted(Path('schemas').glob('*.json'))]; \
	print('All schemas valid') \
	"

# ── Bundle ────────────────────────────────────────────────────────────

.PHONY: bundle-check
bundle-check: ## Check client bundle size against budget
	bash scripts/check-bundle-size.sh

# ── Build ─────────────────────────────────────────────────────────────

.PHONY: build
build: lint test bundle-check ## Full build: lint + test + bundle check
	$(PY) -m build
	@echo "Build artifacts in dist/"

.PHONY: docker
docker: ## Build Docker image
	docker build -t ontology-map-toolkit:latest .

# ── Clean ─────────────────────────────────────────────────────────────

.PHONY: clean
clean: ## Remove build artifacts and caches
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	rm -rf reports/ .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ── Help ──────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
```

---

## Quick Reference — Command Map

| Task | Command |
|------|---------|
| First-time setup | `make install && make install-hooks` |
| Start dev server | `make dev` or `ontology-map serve --port 8420` |
| Run all tests | `make test` |
| Run fast tests | `make test-fast` |
| Run linters | `make lint` |
| Auto-fix lint | `make fix` |
| Check bundle size | `make bundle-check` |
| Full build | `make build` |
| Docker image | `make docker` |
| Validate schemas | `make validate-schemas` |

### CLI Usage (after `pip install -e .`)

```bash
# Start dev server
ontology-map serve --port 8420

# Scan project and generate graph
ontology-map render ./my-project -o graph_data.json
```

---

## CI/CD Flow Diagram

```
  PR opened / push to main
         |
         v
  ┌──────────────────────────────────────────────────────┐
  │                    ci.yml                              │
  │                                                        │
  │  ┌─────────────┐  ┌───────────┐  ┌─────────────────┐ │
  │  │ python-tests │  │ python-   │  │ schema-validate │ │
  │  │ (3.11/3.12/ │  │ lint      │  │                 │ │
  │  │  3.14)      │  │ ruff+mypy │  │                 │ │
  │  └─────────────┘  └───────────┘  └─────────────────┘ │
  │                                                        │
  │  ┌─────────────┐  ┌───────────┐                       │
  │  │ js-lint     │  │ bundle-   │                       │
  │  │ eslint      │  │ size      │                       │
  │  └─────────────┘  └───────────┘                       │
  └──────────────────────────────────────────────────────┘
         |
         v  (PR only)
  ┌──────────────────────────────────┐
  │  visual-regression.yml           │
  │                                  │
  │  Start server                    │
  │  Playwright screenshots          │
  │  Pixel diff vs baseline          │
  │  Post report as PR comment       │
  └──────────────────────────────────┘
```

All five CI jobs in `ci.yml` run in parallel. The visual regression workflow runs independently, triggered only on PRs that touch `client/`, `server/`, `schemas/`, or `themes/`.
