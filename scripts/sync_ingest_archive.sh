#!/usr/bin/env bash
# Pull ingest source archive and text cache from UIC server to Mac backups.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SSH_HOST="${INGEST_SSH_HOST:-100.71.124.8}"
SSH_USER="${INGEST_SSH_USER:-info@urbanindigenouscollective.org}"
SSH_KEY="${INGEST_SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"
REMOTE_ROOT="${INGEST_REMOTE_ROOT:-~/WocconWaker}"
STAMP="$(date +%Y%m%d_%H%M%S)"
DEST="$ROOT/data/backups/ingest_archive_${STAMP}"

mkdir -p "$DEST"
RSYNC_SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new"

echo "Syncing ingest_sources from ${SSH_USER}@${SSH_HOST}:${REMOTE_ROOT}/data/ingest_sources/"
rsync -av -e "$RSYNC_SSH" "${SSH_USER}@${SSH_HOST}:${REMOTE_ROOT}/data/ingest_sources/" "$DEST/ingest_sources/" || true

echo "Syncing ingest_text_cache from ${SSH_USER}@${SSH_HOST}:${REMOTE_ROOT}/data/ingest_text_cache/"
rsync -av -e "$RSYNC_SSH" "${SSH_USER}@${SSH_HOST}:${REMOTE_ROOT}/data/ingest_text_cache/" "$DEST/ingest_text_cache/" || true

echo "Done. Archive at $DEST"
