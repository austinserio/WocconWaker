#!/usr/bin/env bash
# Remove the wrong DNS record (local-woccon.urbanindigenouscollective.org in shocktalk.io zone).
# Requires: CLOUDFLARE_API_TOKEN with Zone:DNS:Edit for shocktalk.io
# Get a token at: https://dash.cloudflare.com/profile/api-tokens (Create Token, Edit zone DNS template)

set -e

WRONG_RECORD_NAME="local-woccon.urbanindigenouscollective.org.shocktalk.io"
ZONE_NAME="shocktalk.io"

if [[ -z "$CLOUDFLARE_API_TOKEN" ]]; then
  echo "Set CLOUDFLARE_API_TOKEN (with DNS Edit permission for shocktalk.io) and run again."
  echo ""
  echo "Or delete manually: Cloudflare Dashboard → shocktalk.io → DNS → find record"
  echo "  \"$WRONG_RECORD_NAME\" (or name local-woccon.urbanindigenouscollective.org) → Delete."
  exit 1
fi

# Get zone ID for shocktalk.io
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

# Find the DNS record (match by name containing our hostname)
RECORD_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?name=$WRONG_RECORD_NAME" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if not d.get('success'):
    print('API error', file=sys.stderr)
    sys.exit(1)
recs = d.get('result', [])
# Also match if name is exactly local-woccon.urbanindigenouscollective.org (some APIs return without zone)
for r in recs:
    if 'local-woccon.urbanindigenouscollective' in r.get('name', ''):
        print(r['id'])
        break
else:
    if recs:
        print(recs[0]['id'])
    else:
        sys.exit(1)
" 2>/dev/null)

if [[ -z "$RECORD_ID" ]]; then
  echo "No matching DNS record found in $ZONE_NAME. It may already be deleted."
  exit 0
fi

# Delete the record
curl -s -X DELETE "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$RECORD_ID" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if d.get('success'):
    print('Deleted the wrong DNS record from shocktalk.io.')
else:
    print('Delete failed:', d.get('errors', d), file=sys.stderr)
    sys.exit(1)
"
