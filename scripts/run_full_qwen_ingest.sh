#!/usr/bin/env bash
# Full Drive corpus Qwen extract for Rules Capture Certainty (Phase 1).
# Writes to drive_staging_qwen_full — does NOT overwrite Opus drive_staging.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
set -a
source .env
set +a

export DRIVE_STAGING_DIR="${DRIVE_STAGING_DIR:-woccon_language/drive_staging_qwen_full}"
export DRIVE_INGEST_FORCE_FULL="${DRIVE_INGEST_FORCE_FULL:-1}"
unset DRIVE_INGEST_FILTER
unset EXTRACTION_FOCUS
unset GRAMMAR_LINEAGE
export EXTRACT_PARALLEL_WORKERS="${EXTRACT_PARALLEL_WORKERS:-2}"
export PDF_OCR_PARALLEL_WORKERS="${PDF_OCR_PARALLEL_WORKERS:-2}"
export OLLAMA_KEEP_ALIVE="${INGEST_OLLAMA_KEEP_ALIVE:-10m}"
export EXTRACT_COMPLETENESS_FAIL="${EXTRACT_COMPLETENESS_FAIL:-1}"
export PYTHONUNBUFFERED=1

mkdir -p data/backups "$(dirname "$DRIVE_STAGING_DIR")"
LOG="${INGEST_LOG:-data/backups/full_qwen_ingest.log}"
echo "=== $(date -Iseconds) starting full Qwen drive_ingest staging=$DRIVE_STAGING_DIR ===" | tee -a "$LOG"
exec .venv/bin/python -u drive_ingest.py 2>&1 | tee -a "$LOG"
