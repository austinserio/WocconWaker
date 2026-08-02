#!/usr/bin/env bash
# Phase 1: diff Opus baseline vs Qwen full staging (falls back to drive_staging_local if full not pulled yet).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OLD="${DIFF_OLD:-woccon_language/drive_staging}"
NEW="${DIFF_NEW:-woccon_language/drive_staging_qwen_full}"
OUT="${DIFF_JSON_OUT:-data/backups/full_qwen_vs_opus_diff.json}"

if [[ ! -d "$NEW" ]] || [[ -z "$(find "$NEW" -maxdepth 1 -name '*.json' ! -name manifest.json ! -name sync_state.json 2>/dev/null | head -1)" ]]; then
  echo "Note: $NEW empty or missing; using drive_staging_local (partial Qwen run)" >&2
  NEW="woccon_language/drive_staging_local"
fi

.venv/bin/python scripts/diff_staging_runs.py \
  --old "$OLD" \
  --new "$NEW" \
  --json-out "$OUT"

echo "Diff written to $OUT (cultural bucket included in JSON; triage grammar/pronunciation only)"
