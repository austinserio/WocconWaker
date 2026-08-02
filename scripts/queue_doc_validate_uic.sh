#!/usr/bin/env bash
# Queue doc-focused Qwen validation on UIC after policy tracker releases GPU.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DOC="${1:?Usage: $0 <doc-filter> [doc-tag]}"
TAG="${2:-}"

echo "=== Deploy to UIC ==="
./scripts/deploy_uic_ingest.sh

REMOTE_DIR="${INGEST_REMOTE_ROOT:-/root/WocconWaker}"
SSH_HOST="${INGEST_SSH_HOST:-100.71.124.8}"
SSH_USER="${INGEST_SSH_USER:-info@urbanindigenouscollective.org}"
SSH_KEY="${INGEST_SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "${SSH_USER}@${SSH_HOST}" \
  "wsl -e bash -lc \"cd ${REMOTE_DIR} && mkdir -p data/backups && chmod +x scripts/run_doc_focused_validate.sh scripts/wait_for_uic_llm_idle.sh && export DRIVE_INGEST_FILTER='${DOC}'${TAG:+ && export DOC_TAG='${TAG}'} && nohup bash scripts/wait_for_uic_llm_idle.sh bash scripts/run_doc_focused_validate.sh >> data/backups/doc_validate_${DOC//[^a-zA-Z0-9]/_}_launcher.log 2>&1 &\""

echo "Queued doc validation for ${DOC}. Monitor UIC data/backups/doc_validate_*.log"
