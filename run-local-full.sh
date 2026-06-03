#!/usr/bin/env bash
# Start Messenger backend + Cloudflare tunnel + control panel Vite dev server.
# Ctrl+C (or killing this script) stops all three processes.
#
# Usage:
#   ./run-local-full.sh          # tunnel + backend + panel frontend
#   ./run-local-full.sh --stop   # stop stale WocconWaker dev processes on 5173/8000 + tunnel

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

BACKEND_PID=""
VITE_PID=""
CLOUDFLARED_PID=""

WH="${CLOUDFLARE_TUNNEL_HOSTNAME:-woccon-dev.example.com}"
PUB="${PUBLIC_WEBHOOK_BASE_URL:-https://${WH}}"
TUNNEL_NAME="${CLOUDFLARE_TUNNEL_NAME:-woccon-dev}"

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

stop_cloudflared_tunnel() {
  local pid cmd
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$cmd" == *"cloudflared"* && "$cmd" == *"tunnel"* && "$cmd" == *"$TUNNEL_NAME"* ]]; then
      echo "Stopping Cloudflare tunnel (PID ${pid})"
      kill "$pid" 2>/dev/null || true
    fi
  done < <(pgrep -f "cloudflared tunnel" 2>/dev/null || true)
}

stop_all_woccon_dev() {
  stop_woccon_dev_on_port 5173
  stop_woccon_dev_on_port 8000
  stop_cloudflared_tunnel
  sleep 0.5
}

cleanup() {
  echo ""
  echo "Stopping local full stack..."
  if [[ -n "$VITE_PID" ]] && kill -0 "$VITE_PID" 2>/dev/null; then
    kill "$VITE_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$CLOUDFLARED_PID" ]] && kill -0 "$CLOUDFLARED_PID" 2>/dev/null; then
    kill "$CLOUDFLARED_PID" 2>/dev/null || true
  fi
  exit 0
}

if [[ "${1:-}" == "--stop" ]]; then
  stop_all_woccon_dev
  echo "Done."
  exit 0
fi

if [[ ! -f .env ]]; then
  echo "No .env found. Run: cp .env.example .env"
  echo "Then set VERIFY_TOKEN, PAGE_ACCESS_TOKEN, JWT/panel vars, and LLM/Foundry settings."
  echo "See LOCAL_DEV.md and docs/CONTROL_PANEL.md."
  exit 1
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
  echo "         Stop it first or set PORT to a free port, e.g. PORT=8002 ./run-local-full.sh"
  exit 1
fi

if command -v cloudflared &>/dev/null; then
  if [[ -f cloudflared.yml ]]; then
    cloudflared tunnel --config cloudflared.yml run &
  else
    echo "Warning: no cloudflared.yml — public hostname may not resolve until configured."
    echo "  See LOCAL_DEV.md (copy cloudflared-example.yml to cloudflared.yml)."
    echo "Attempting: cloudflared tunnel run $TUNNEL_NAME"
    cloudflared tunnel run "$TUNNEL_NAME" &
  fi
  CLOUDFLARED_PID=$!
  echo "Tunnel starting (PID $CLOUDFLARED_PID)..."
  sleep 3
else
  echo "Warning: cloudflared not found. Messenger webhooks will not be reachable from Facebook."
  echo "         Install cloudflared and configure a tunnel — see LOCAL_DEV.md."
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
echo "Panel UI:     http://localhost:5173/panel/login"
echo "Backend:      http://127.0.0.1:${PORT}"
echo "Webhook URL:  ${PUB}/webhook"
echo "Press Ctrl+C to stop tunnel, backend, and frontend."
echo ""

wait "$VITE_PID"
