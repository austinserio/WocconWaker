#!/usr/bin/env bash
# Remove a mistaken Cloudflare DNS record (e.g. created in the wrong zone).
# Requires CLOUDFLARE_API_TOKEN with Zone:DNS:Edit for the target zone.
# Set in .env: CLOUDFLARE_CLEANUP_ZONE, CLOUDFLARE_WRONG_RECORD_NAME (exact DNS name),
# and optionally CLOUDFLARE_RECORD_MATCH_SUBSTRING to pick a record when the API returns several.
# Get a token at: https://dash.cloudflare.com/profile/api-tokens

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

ZONE_NAME="${CLOUDFLARE_CLEANUP_ZONE:?Set CLOUDFLARE_CLEANUP_ZONE in .env (Cloudflare zone, e.g. example.com)}"
WRONG_RECORD_NAME="${CLOUDFLARE_WRONG_RECORD_NAME:?Set CLOUDFLARE_WRONG_RECORD_NAME in .env (full record name to query)}"
MATCH_SUB="${CLOUDFLARE_RECORD_MATCH_SUBSTRING:-}"

if [[ -z "$CLOUDFLARE_API_TOKEN" ]]; then
  echo "Set CLOUDFLARE_API_TOKEN in .env and run again."
  exit 1
fi

export CLOUDFLARE_RECORD_MATCH_SUBSTRING="$MATCH_SUB"

# Get zone ID
ZONE_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=$ZONE_NAME" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if not d.get('success') or not d.get('result'):
    print('Zone not found or token invalid', file=sys.stderr)
    sys.exit(1)
print(d['result'][0]['id'])
" 2>/dev/null)

if [[ -z "$ZONE_ID" ]]; then
  echo "Could not get zone ID for $ZONE_NAME. Check your token and zone name."
  exit 1
fi

RECORD_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?name=$WRONG_RECORD_NAME" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" | python3 -c "
import json, sys, os
d = json.load(sys.stdin)
if not d.get('success'):
    print('API error', file=sys.stderr)
    sys.exit(1)
recs = d.get('result', [])
if not recs:
    sys.exit(1)
match_sub = (os.environ.get('CLOUDFLARE_RECORD_MATCH_SUBSTRING') or '').strip()
for r in recs:
    if not match_sub or match_sub in r.get('name', ''):
        print(r['id'])
        break
else:
    print(recs[0]['id'])
" 2>/dev/null)

if [[ -z "$RECORD_ID" ]]; then
  echo "No matching DNS record found in $ZONE_NAME. It may already be deleted."
  exit 0
fi

curl -s -X DELETE "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$RECORD_ID" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if d.get('success'):
    print('Deleted DNS record in zone (cleanup complete).')
else:
    print('Delete failed:', d.get('errors', d), file=sys.stderr)
    sys.exit(1)
"
