#!/usr/bin/env bash
# Fresh Qwen focused passes on Resurrecting for grammar/pronunciation validation vs Azure live.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
set -a
source .env
set +a

export DRIVE_INGEST_FILTER="${DRIVE_INGEST_FILTER:-Resurrecting}"
export DRIVE_INGEST_FORCE_FULL="${DRIVE_INGEST_FORCE_FULL:-1}"
export EXTRACT_PARALLEL_WORKERS="${EXTRACT_PARALLEL_WORKERS:-3}"
export PDF_OCR_PARALLEL_WORKERS="${PDF_OCR_PARALLEL_WORKERS:-2}"
export OLLAMA_KEEP_ALIVE="${INGEST_OLLAMA_KEEP_ALIVE:-10m}"
export PYTHONUNBUFFERED=1

BASE_STAGING="${DRIVE_STAGING_BASE:-woccon_language/drive_staging_qwen_validate}"
mkdir -p data/backups "$BASE_STAGING"

run_pass() {
  local focus="$1"
  local lineage="${2:-}"
  local tag="$3"
  export EXTRACTION_FOCUS="$focus"
  if [[ -n "$lineage" ]]; then
    export GRAMMAR_LINEAGE="$lineage"
  else
    unset GRAMMAR_LINEAGE || true
  fi
  export DRIVE_STAGING_DIR="${BASE_STAGING}/${tag}"
  mkdir -p "$DRIVE_STAGING_DIR"
  local log="data/backups/resurrecting_validate_${tag}.log"
  echo "=== $(date -Iseconds) focus=$focus lineage=${lineage:-none} staging=$DRIVE_STAGING_DIR ===" | tee -a "$log"
  .venv/bin/python -u drive_ingest.py 2>&1 | tee -a "$log"
}

run_pass grammar woccon_attested grammar_woccon_attested
run_pass grammar proto_catawban grammar_proto_catawban
run_pass pronunciation "" pronunciation

echo "=== All focused passes complete ==="
