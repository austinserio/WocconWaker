#!/usr/bin/env bash
# Start control panel backend + Vite dev server together.
# Ctrl+C (or killing this script) stops both processes.
#
# Usage:
#   ./run-panel-dev.sh          # start backend + frontend
#   ./run-panel-dev.sh --stop   # stop stale WocconWaker dev processes on 5173/8000

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

BACKEND_PID=""
VITE_PID=""

is_woccon_dev_process() {
  local cmd="$1"
  [[ "$cmd" == *"WocconWaker/panel"* ]] \
    || [[ "$cmd" == *"WocconWaker"* && "$cmd" == *"app.py"* ]] \
    || [[ "$cmd" == *"WocconWaker"* && "$cmd" == *"uvicorn app:app"* ]]
}

stop_woccon_dev_on_port() {
  local port=$1
  local pid cmd
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if is_woccon_dev_process "$cmd"; then
      echo "Stopping WocconWaker dev process on :${port} (PID ${pid})"
      kill "$pid" 2>/dev/null || true
    fi
  done < <(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
}

stop_all_woccon_dev() {
  stop_woccon_dev_on_port 5173
  stop_woccon_dev_on_port 8000
  sleep 0.5
}

cleanup() {
  echo ""
  echo "Stopping panel dev..."
  if [[ -n "$VITE_PID" ]] && kill -0 "$VITE_PID" 2>/dev/null; then
    kill "$VITE_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  exit 0
}

if [[ "${1:-}" == "--stop" ]]; then
  stop_all_woccon_dev
  echo "Done."
  exit 0
fi

trap cleanup EXIT INT TERM

VENV_DIR=".venv"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment in $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
fi
PYTHON="$VENV_DIR/bin/python"

if ! "$PYTHON" -c "import fastapi" 2>/dev/null; then
  echo "Installing Python dependencies into $VENV_DIR..."
  "$PYTHON" -m pip install -r requirements.txt -q
fi

if [[ ! -d panel/node_modules ]]; then
  echo "Installing panel frontend dependencies..."
  (cd panel && npm install)
fi

export WOCCON_MODE=server
export PORT="${PORT:-8000}"

stop_all_woccon_dev

if lsof -tiTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Warning: port 8000 is still in use by another process (not WocconWaker)."
  echo "         Stop it first or set PORT to a free port, e.g. PORT=8002 ./run-panel-dev.sh"
  exit 1
fi

echo "Starting backend on http://127.0.0.1:${PORT} ..."
"$PYTHON" app.py &
BACKEND_PID=$!

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Backend failed to start. Check logs above."
    exit 1
  fi
  sleep 1
done

echo "Starting panel frontend on http://localhost:5173/panel/login ..."
(cd panel && npm run dev) &
VITE_PID=$!

echo ""
echo "Panel UI:  http://localhost:5173/panel/login"
echo "Backend:   http://127.0.0.1:${PORT}"
echo "Press Ctrl+C to stop both."
echo ""

wait "$VITE_PID"
