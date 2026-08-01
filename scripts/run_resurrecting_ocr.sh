#!/usr/bin/env bash
# Run Resurrecting PDF benchmark ingest on UIC (or locally). Detached-safe.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
set -a
source .env
set +a

export DRIVE_INGEST_FILTER="${DRIVE_INGEST_FILTER:-Resurrecting}"
export DRIVE_STAGING_DIR="${DRIVE_STAGING_DIR:-woccon_language/drive_staging_bench}"
export DRIVE_INGEST_FORCE_FULL="${DRIVE_INGEST_FORCE_FULL:-1}"
export EXTRACT_PARALLEL_WORKERS="${EXTRACT_PARALLEL_WORKERS:-3}"
export PDF_OCR_PARALLEL_WORKERS="${PDF_OCR_PARALLEL_WORKERS:-2}"
export OLLAMA_KEEP_ALIVE="${INGEST_OLLAMA_KEEP_ALIVE:-10m}"
export PYTHONUNBUFFERED=1

mkdir -p data/backups
LOG="${INGEST_LOG:-data/backups/resurrecting_pdf.log}"
echo "=== $(date -Iseconds) starting drive_ingest ===" >>"$LOG"
exec .venv/bin/python -u drive_ingest.py >>"$LOG" 2>&1
