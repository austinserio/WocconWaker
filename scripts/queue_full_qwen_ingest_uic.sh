#!/usr/bin/env bash
# Deploy WocconWaker to UIC and start full Qwen ingest after policy tracker releases GPU.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Deploy to UIC ==="
./scripts/deploy_uic_ingest.sh

REMOTE_DIR="${INGEST_REMOTE_ROOT:-/root/WocconWaker}"
SSH_HOST="${INGEST_SSH_HOST:-100.71.124.8}"
SSH_USER="${INGEST_SSH_USER:-info@urbanindigenouscollective.org}"
SSH_KEY="${INGEST_SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"

echo "=== Queue full Qwen ingest (wait for policy tracker, then nohup) ==="
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "${SSH_USER}@${SSH_HOST}" \
  "wsl -e bash -lc \"cd ${REMOTE_DIR} && mkdir -p data/backups && chmod +x scripts/run_full_qwen_ingest.sh scripts/wait_for_uic_llm_idle.sh && nohup bash scripts/wait_for_uic_llm_idle.sh bash scripts/run_full_qwen_ingest.sh >> data/backups/full_qwen_ingest_launcher.log 2>&1 &\""

echo "Queued. Monitor: ssh ... tail -f ${REMOTE_DIR}/data/backups/full_qwen_ingest.log"
