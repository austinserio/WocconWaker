#!/usr/bin/env bash
# Unattended chain: vision-OCR + extract the local Catawba sources, then run the full Qwen
# Drive ingest. Both stages share the one UIC GPU, so they must not overlap.
#
# Stage 1 failures are logged but do not block stage 2, since the Drive ingest covers a
# different corpus and is the more expensive job to have to restart.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CATAWBA_DIR="${CATAWBA_DIR:-$HOME/Downloads/CatawbaUpload}"
mkdir -p data/backups
LOG="data/backups/overnight_$(date +%Y%m%d_%H%M%S).log"
export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-10m}"
export PYTHONUNBUFFERED=1

exec > >(tee -a "$LOG") 2>&1
echo "=== $(date -Iseconds) STAGE 1: local Catawba OCR + extract from $CATAWBA_DIR ==="
python3 scripts/ingest_local_catawba.py --dir "$CATAWBA_DIR" --dpi 300
catawba_rc=$?
echo "=== $(date -Iseconds) STAGE 1 finished rc=$catawba_rc ==="

echo "=== $(date -Iseconds) STAGE 2: full Qwen Drive ingest ==="
bash scripts/run_full_qwen_ingest.sh
ingest_rc=$?
echo "=== $(date -Iseconds) STAGE 2 finished rc=$ingest_rc ==="

echo "=== $(date -Iseconds) DONE catawba_rc=$catawba_rc ingest_rc=$ingest_rc log=$LOG ==="
exit $(( catawba_rc != 0 || ingest_rc != 0 ))
