#!/usr/bin/env bash
# Pull a staging directory from UIC WSL (default: drive_staging_qwen_full).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_HOST="${INGEST_SSH_HOST:-100.71.124.8}"
SSH_USER="${INGEST_SSH_USER:-info@urbanindigenouscollective.org}"
SSH_KEY="${INGEST_SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"
REMOTE_DIR="${INGEST_REMOTE_ROOT:-/root/WocconWaker}"
REL="${1:-woccon_language/drive_staging_qwen_full}"

mkdir -p "$ROOT/$(dirname "$REL")"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "${SSH_USER}@${SSH_HOST}" \
  "wsl -e bash -lc \"tar cf - -C ${REMOTE_DIR}/$(dirname "$REL") $(basename "$REL") 2>/dev/null || true\"" \
  | tar xf - -C "$ROOT/$(dirname "$REL")" 2>/dev/null || true
echo "Pulled $REL to $ROOT/$REL"
