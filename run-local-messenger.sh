#!/usr/bin/env bash
# Run the app locally for Messenger development.
# Starts Cloudflare tunnel (if cloudflared.yml exists) and the app; Ctrl+C stops both.
# Copy .env.example to .env and set VERIFY_TOKEN, PAGE_ACCESS_TOKEN, LLM vars, and optionally
# CLOUDFLARE_TUNNEL_HOSTNAME / PUBLIC_WEBHOOK_BASE_URL for printed URLs. See LOCAL_DEV.md.

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

if [[ ! -f .env ]]; then
  echo "No .env found. Run: cp .env.example .env"
  echo "Then set VERIFY_TOKEN, PAGE_ACCESS_TOKEN, WOCCON_MODE=server, PORT, and LLM/Foundry vars."
  echo "See LOCAL_DEV.md and CLAUDE.md."
  exit 1
fi

WH="${CLOUDFLARE_TUNNEL_HOSTNAME:-woccon-dev.example.com}"
PUB="${PUBLIC_WEBHOOK_BASE_URL:-https://${WH}}"

export WOCCON_MODE=server
export PORT="${PORT:-8000}"

# Use a venv so we don't hit "externally-managed-environment" on Homebrew Python (PEP 668)
VENV_DIR=".venv"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment in $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
fi
PYTHON="$VENV_DIR/bin/python"

# Ensure dependencies are installed in the venv
if ! "$PYTHON" -c "import transformers" 2>/dev/null; then
  echo "Installing dependencies into $VENV_DIR..."
  "$PYTHON" -m pip install -r requirements.txt -q
fi

# Start Cloudflare tunnel in background (so Facebook can reach localhost)
CLOUDFLARED_PID=""
cleanup() {
  if [[ -n "$CLOUDFLARED_PID" ]] && kill -0 "$CLOUDFLARED_PID" 2>/dev/null; then
    echo "Stopping tunnel (PID $CLOUDFLARED_PID)..."
    kill "$CLOUDFLARED_PID" 2>/dev/null || true
  fi
  exit 0
}
trap cleanup EXIT INT TERM

if command -v cloudflared &>/dev/null; then
  if [[ -f cloudflared.yml ]]; then
    cloudflared tunnel --config cloudflared.yml run &
  else
    echo "Warning: no cloudflared.yml — public hostname will not resolve until you:"
    echo "  1. cloudflared tunnel create <name>"
    echo "  2. Add DNS CNAME: your host -> <TUNNEL_ID>.cfargotunnel.com"
    echo "  3. Copy cloudflared-example.yml to cloudflared.yml and set tunnel ID + credentials path"
    echo "  See LOCAL_DEV.md"
    TN="${CLOUDFLARE_TUNNEL_NAME:-woccon-dev}"
    echo "Attempting: cloudflared tunnel run $TN (set CLOUDFLARE_TUNNEL_NAME in .env to change)"
    cloudflared tunnel run "$TN" &
  fi
  CLOUDFLARED_PID=$!
  echo "Tunnel starting (PID $CLOUDFLARED_PID)..."
  sleep 3
else
  echo "Warning: cloudflared not found. Install it and add to PATH."
fi

echo "Starting WocconWaker on http://0.0.0.0:${PORT}"
echo "Webhook URL (set CLOUDFLARE_TUNNEL_HOSTNAME / PUBLIC_WEBHOOK_BASE_URL in .env to match): ${PUB}/webhook"
echo ""

"$PYTHON" app.py
