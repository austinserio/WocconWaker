#!/usr/bin/env bash
# Pull staging + ingest archives from UIC WSL to Mac.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_HOST="${INGEST_SSH_HOST:-100.71.124.8}"
SSH_USER="${INGEST_SSH_USER:-info@urbanindigenouscollective.org}"
SSH_KEY="${INGEST_SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"
REMOTE_DIR="${INGEST_REMOTE_ROOT:-/root/WocconWaker}"
RSYNC_SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new"

pull_dir() {
  local relpath="$1"
  mkdir -p "$ROOT/$relpath"
  $RSYNC_SSH "${SSH_USER}@${SSH_HOST}" \
    "wsl -e bash -lc 'tar cf - -C ${REMOTE_DIR}/${relpath} . 2>/dev/null || true'" \
    | tar xf - -C "$ROOT/$relpath" 2>/dev/null || true
  echo "Pulled $relpath"
}

pull_dir woccon_language/drive_staging_local
pull_dir data/ingest_sources
pull_dir data/ingest_text_cache

echo "Done. Review staging at $ROOT/woccon_language/drive_staging_local/"
