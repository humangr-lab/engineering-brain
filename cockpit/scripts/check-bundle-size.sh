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

# -- Configuration -----------------------------------------------------------
CLIENT_DIR="client"
BUDGET_INITIAL_KB=250      # Phase 0+1: HTML + CSS + core JS (no data/)
BUDGET_TOTAL_KB=500        # Everything in client/
REPORT_DIR="reports"

if [ ! -d "$CLIENT_DIR" ]; then
    echo "ERROR: $CLIENT_DIR directory not found"
    exit 1
fi

# -- Setup -------------------------------------------------------------------
mkdir -p "$REPORT_DIR"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# -- Measure by file type ---------------------------------------------------
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

# -- Collect metrics ---------------------------------------------------------
html_stats=$(measure_gzip "*.html" "HTML")
css_stats=$(measure_gzip "*.css" "CSS")
js_core_stats=$(measure_gzip "*.js" "JS (core)" "data/")
js_data_stats=$(measure_gzip "*.js" "JS (data)" "")
font_stats=$(measure_gzip "*.woff2" "Fonts")

# Parse JS data -- subtract core from total to isolate data/
js_all_gz=$(echo "$js_data_stats" | cut -d'|' -f4)
js_core_gz=$(echo "$js_core_stats" | cut -d'|' -f4)
js_data_only_gz=$((js_all_gz - js_core_gz))

# -- Calculate totals -------------------------------------------------------
html_gz=$(echo "$html_stats" | cut -d'|' -f4)
css_gz=$(echo "$css_stats" | cut -d'|' -f4)

initial_gz=$((html_gz + css_gz + js_core_gz))
initial_kb=$((initial_gz / 1024))

# Total gzip of entire client/
total_gz_file="$TMPDIR/client-total.tar.gz"
tar czf "$total_gz_file" "$CLIENT_DIR" 2>/dev/null
total_gz=$(wc -c < "$total_gz_file")
total_kb=$((total_gz / 1024))

# -- Budget check -----------------------------------------------------------
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

# -- Console output ---------------------------------------------------------
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

# -- Markdown report --------------------------------------------------------
cat > "$REPORT_DIR/bundle-size.md" << MDEOF
## Bundle Size Report

| Type | Files | Raw | Gzip |
|------|------:|----:|-----:|
| HTML | $(echo "$html_stats" | cut -d'|' -f2) | $(echo "$html_stats" | cut -d'|' -f3) B | $(echo "$html_stats" | cut -d'|' -f4) B |
| CSS | $(echo "$css_stats" | cut -d'|' -f2) | $(echo "$css_stats" | cut -d'|' -f3) B | $(echo "$css_stats" | cut -d'|' -f4) B |
| JS (core) | $(echo "$js_core_stats" | cut -d'|' -f2) | $(echo "$js_core_stats" | cut -d'|' -f3) B | $(echo "$js_core_stats" | cut -d'|' -f4) B |
| JS (data/) | -- | -- | ${js_data_only_gz} B |

### Budget

| Metric | Measured | Budget | Status |
|--------|----------|--------|--------|
| **Phase 0+1 (initial load)** | ${initial_kb} KB | ${BUDGET_INITIAL_KB} KB | ${initial_pass} |
| **Total client/** | ${total_kb} KB | ${BUDGET_TOTAL_KB} KB | ${total_pass} |

> Phase 0+1 = HTML + CSS + core JS (excludes \`client/js/data/\`).
> Budget from SPEC Section 11: Lightweight Architecture.
MDEOF

exit "$exit_code"
