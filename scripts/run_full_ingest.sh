#!/usr/bin/env bash
# Full Drive corpus ingest on UIC (unified qwen2.5vl:32b, parallel workers, text cache).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
set -a
source .env
set +a

export DRIVE_STAGING_DIR="${DRIVE_STAGING_DIR:-woccon_language/drive_staging_local}"
unset DRIVE_INGEST_FORCE_FULL
unset DRIVE_INGEST_FILTER
export EXTRACT_PARALLEL_WORKERS="${EXTRACT_PARALLEL_WORKERS:-3}"
export PDF_OCR_PARALLEL_WORKERS="${PDF_OCR_PARALLEL_WORKERS:-2}"
export OLLAMA_KEEP_ALIVE="${INGEST_OLLAMA_KEEP_ALIVE:-10m}"
export PYTHONUNBUFFERED=1

mkdir -p data/backups
LOG="${INGEST_LOG:-data/backups/full_ingest.log}"
echo "=== $(date -Iseconds) starting full drive_ingest ===" >>"$LOG"
exec .venv/bin/python -u drive_ingest.py >>"$LOG" 2>&1
