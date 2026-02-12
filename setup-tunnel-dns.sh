#!/usr/bin/env bash
# Add DNS for local-woccon.urbanindigenouscollective.org via cloudflared.
# Must be logged in as the UIC account (owner of urbanindigenouscollective.org):
#   cloudflared tunnel login
# Then run this script once.

set -e
cd "$(dirname "$0")"

TUNNEL_ID="41f20a16-ca3d-45bb-90c3-5fa255509cf5"
HOSTNAME="local-woccon.urbanindigenouscollective.org"

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
echo "and sign in with the UIC account that owns urbanindigenouscollective.org, then run this script again."
