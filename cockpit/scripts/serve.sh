#!/bin/bash
# Dev server startup script
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Starting Ontology Cockpit server..."
echo "  Port: 8420"
echo "  Client: http://localhost:8420"
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"
else
    source .venv/bin/activate
fi

# Start server
python -m server.main "$@"
