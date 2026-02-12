#!/usr/bin/env bash
# Run the app locally for Messenger development.
# Then start a tunnel (e.g. cloudflared tunnel --url http://localhost:8000) and point Facebook webhook at it.

set -e
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "No .env found. Create one with:"
  echo "  VERIFY_TOKEN=test-key-beta"
  echo "  PAGE_ACCESS_TOKEN=your_token"
  echo "  WOCCON_MODE=server"
  echo "  PORT=8000"
  echo "  LOCAL_LLM=true   # or false for Foundry"
  echo "See LOCAL_DEV.md for full setup."
  exit 1
fi

export WOCCON_MODE=server
export PORT="${PORT:-8000}"

echo "Starting WocconWaker on http://0.0.0.0:${PORT}"
echo "Start a tunnel (e.g. cloudflared tunnel --url http://localhost:${PORT}) and set Facebook webhook to https://YOUR-TUNNEL-URL/webhook"
echo ""

python app.py
