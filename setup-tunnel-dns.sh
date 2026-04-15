#!/usr/bin/env bash
# Add DNS for your tunnel hostname via cloudflared (after `cloudflared tunnel login`).
# Set CLOUDFLARE_TUNNEL_ID and CLOUDFLARE_TUNNEL_HOSTNAME in .env (see .env.example).

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

TUNNEL_ID="${CLOUDFLARE_TUNNEL_ID:?Set CLOUDFLARE_TUNNEL_ID in .env (output of cloudflared tunnel create)}"
HOSTNAME="${CLOUDFLARE_TUNNEL_HOSTNAME:?Set CLOUDFLARE_TUNNEL_HOSTNAME in .env (e.g. woccon-dev.example.com)}"

echo "Adding DNS: $HOSTNAME -> tunnel $TUNNEL_ID"
echo "(Uses the account you're logged into via cloudflared tunnel login.)"
echo ""

if ! command -v cloudflared &>/dev/null; then
  echo "Error: cloudflared not found. Install it and add to PATH."
  exit 1
fi

cloudflared tunnel route dns "$TUNNEL_ID" "$HOSTNAME"

echo ""
echo "Done. If you saw an error about the wrong zone, run: cloudflared tunnel login"
echo "with the Cloudflare account that owns the DNS zone for $HOSTNAME, then run this script again."
