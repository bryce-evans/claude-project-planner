#!/usr/bin/env bash
# Start the render dev environment:
#   - Python server on :8080 (handles POST /task/update)
#   - Vite dev server on :5173
# Both run in the foreground; Ctrl-C stops both.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "  Generating data..."
"$SCRIPT_DIR/render.py" --data

echo "  Starting Python server on :8080..."
python3 "$SCRIPT_DIR/server.py" --port 8080 &
PYTHON_PID=$!

cleanup() {
  kill "$PYTHON_PID" 2>/dev/null
  wait "$PYTHON_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "  Starting Vite dev server on :5173..."
cd "$SCRIPT_DIR" && npm run dev
