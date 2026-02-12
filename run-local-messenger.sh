#!/usr/bin/env bash
# Run the app locally for Messenger development.
# Starts the UIC Cloudflare tunnel (local-woccon) and the app; Ctrl+C stops both.
# Webhook: https://local-woccon.urbanindigenouscollective.org/webhook (see LOCAL_DEV.md)

set -e
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "No .env found. Create one with:"
  echo "  VERIFY_TOKEN=test-key-beta"
  echo "  PAGE_ACCESS_TOKEN=your_token"
  echo "  WOCCON_MODE=server"
  echo "  PORT=8000"
  echo "  LOCAL_LLM=false   # use Azure Foundry (same as production); true = local Ollama"
  echo "  FOUNDRY_ENDPOINT=https://woccon-foundry.services.ai.azure.com"
  echo "  FOUNDRY_API_KEY=..."
  echo "  FOUNDRY_DEPLOYMENT=Meta-Llama-3.1-8B-Instruct"
  echo "  FOUNDRY_API_VERSION=2024-05-01-preview"
  echo "See LOCAL_DEV.md for full setup."
  exit 1
fi

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
    cloudflared tunnel --config cloudflared.yml run local-woccon &
  else
    echo "Warning: no cloudflared.yml — local-woccon.urbanindigenouscollective.org will not resolve until you:"
    echo "  1. cloudflared tunnel create local-woccon"
    echo "  2. Add DNS CNAME: local-woccon -> <TUNNEL_ID>.cfargotunnel.com (in Cloudflare for urbanindigenouscollective.org)"
    echo "  3. Copy cloudflared-example.yml to cloudflared.yml and set tunnel ID + credentials path"
    echo "  See LOCAL_DEV.md 'Webhook URL not resolving?'"
    cloudflared tunnel run local-woccon &
  fi
  CLOUDFLARED_PID=$!
  echo "Tunnel starting (PID $CLOUDFLARED_PID)..."
  sleep 3
else
  echo "Warning: cloudflared not found. Install it and add to PATH."
fi

echo "Starting WocconWaker on http://0.0.0.0:${PORT}"
echo "Webhook URL: https://local-woccon.urbanindigenouscollective.org/webhook"
echo ""

"$PYTHON" app.py
