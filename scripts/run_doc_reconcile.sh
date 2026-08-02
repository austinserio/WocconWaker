#!/usr/bin/env bash
# Doc-scoped live + Qwen reconcile (topic checklist + fuzzy gap report).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DOC="${1:?Usage: $0 <document-filter> [source-filter]}"
SOURCE="${2:-$DOC}"
LIVE="${LIVE_RULES:-data/backups/azure_live_rules.json}"
STAGING="${QWEN_STAGING:-woccon_language/drive_staging_qwen_validate}"
OUT_DIR="${RECONCILE_OUT_DIR:-data/backups/reconcile}"

mkdir -p "$OUT_DIR"
TAG="$(echo "$DOC" | tr ' /' '_' | tr -cd '[:alnum:]_-' | head -c 48)"

.venv/bin/python scripts/check_rule_topic_coverage.py \
  --document "$DOC" \
  --live "$LIVE" \
  --staging "$STAGING" \
  --compare-live "$LIVE" \
  --json-out "$OUT_DIR/${TAG}_topic_coverage.json"

.venv/bin/python scripts/compare_qwen_vs_azure_live.py \
  --live "$LIVE" \
  --staging "$STAGING" \
  --source-filter "$SOURCE" \
  --out "$OUT_DIR/${TAG}_qwen_vs_live.json"

echo "Reconcile reports in $OUT_DIR/${TAG}_*.json"
