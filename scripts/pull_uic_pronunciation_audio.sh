#!/usr/bin/env bash
# Pull data/pronunciation_audio/ (+ manifest) from UIC WSL to Mac for commit or docker build.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_HOST="${INGEST_SSH_HOST:-100.71.124.8}"
SSH_USER="${INGEST_SSH_USER:-info@urbanindigenouscollective.org}"
SSH_KEY="${INGEST_SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"
REMOTE_DIR="${INGEST_REMOTE_ROOT:-/root/WocconWaker}"
RELPATH="data/pronunciation_audio"
RSYNC_SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new"

mkdir -p "$ROOT/$RELPATH"

$RSYNC_SSH "${SSH_USER}@${SSH_HOST}" \
  "wsl -e bash -lc 'test -f ${REMOTE_DIR}/${RELPATH}/manifest.json || { echo \"Missing ${REMOTE_DIR}/${RELPATH}/manifest.json on UIC — run generate_pronunciation_audio.py first\" >&2; exit 1; }; tar cf - -C ${REMOTE_DIR}/${RELPATH} .'" \
  | tar xf - -C "$ROOT/$RELPATH"

count="$(find "$ROOT/$RELPATH" -maxdepth 1 -name '*.mp3' | wc -l | tr -d ' ')"
echo "Pulled $count MP3 clip(s) + manifest to $ROOT/$RELPATH"
