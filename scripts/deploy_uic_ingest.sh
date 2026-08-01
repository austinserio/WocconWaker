#!/usr/bin/env bash
# Deploy WocconWaker to UIC WSL and run a command with local Ollama (no Mac round trip).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SSH_HOST="${INGEST_SSH_HOST:-100.71.124.8}"
SSH_USER="${INGEST_SSH_USER:-info@urbanindigenouscollective.org}"
SSH_KEY="${INGEST_SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"
REMOTE_DIR="${INGEST_REMOTE_ROOT:-/root/WocconWaker}"
RSYNC_SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new"

remote() {
  $RSYNC_SSH "${SSH_USER}@${SSH_HOST}" "wsl -e bash -lc \"$*\""
}

echo "=== Deploy code to UIC WSL:${REMOTE_DIR} ==="
remote "mkdir -p ${REMOTE_DIR}"

tar -cf - \
  --exclude=.venv \
  --exclude=.git \
  --exclude='data/backups' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='node_modules' \
  --exclude='panel/dist' \
  -C "$ROOT" . \
  | $RSYNC_SSH "${SSH_USER}@${SSH_HOST}" "wsl -e bash -lc \"tar xf - -C ${REMOTE_DIR}\""

echo "=== Sync ingest archive + text cache ==="
remote "mkdir -p ${REMOTE_DIR}/data/ingest_sources ${REMOTE_DIR}/data/ingest_text_cache"
if [[ -d "$ROOT/data/ingest_sources" ]]; then
  tar -cf - -C "$ROOT/data" ingest_sources \
    | $RSYNC_SSH "${SSH_USER}@${SSH_HOST}" "wsl -e bash -lc \"tar xf - -C ${REMOTE_DIR}/data\""
fi
if [[ -d "$ROOT/data/ingest_text_cache" ]]; then
  tar -cf - -C "$ROOT/data" ingest_text_cache \
    | $RSYNC_SSH "${SSH_USER}@${SSH_HOST}" "wsl -e bash -lc \"tar xf - -C ${REMOTE_DIR}/data\""
fi

echo "=== Write server .env (OLLAMA_URL=127.0.0.1) ==="
if [[ ! -f "$ROOT/.env" ]]; then
  echo "Missing .env on Mac" >&2
  exit 1
fi
# shellcheck disable=SC2016
grep -v '^OLLAMA_URL=' "$ROOT/.env" | $RSYNC_SSH "${SSH_USER}@${SSH_HOST}" "wsl -e bash -lc \"cat > ${REMOTE_DIR}/.env\""
remote "if grep -q '^OLLAMA_URL=' ${REMOTE_DIR}/.env; then sed -i 's|^OLLAMA_URL=.*|OLLAMA_URL=http://127.0.0.1:11434|' ${REMOTE_DIR}/.env; else echo OLLAMA_URL=http://127.0.0.1:11434 >> ${REMOTE_DIR}/.env; fi"

CREDS=$(grep '^GOOGLE_APPLICATION_CREDENTIALS=' "$ROOT/.env" | cut -d= -f2- | tr -d '"')
if [[ -n "$CREDS" && -f "$CREDS" ]]; then
  remote "mkdir -p ${REMOTE_DIR}/secrets"
  tar -cf - -C "$(dirname "$CREDS")" "$(basename "$CREDS")" \
    | $RSYNC_SSH "${SSH_USER}@${SSH_HOST}" "wsl -e bash -lc \"tar xf - -C ${REMOTE_DIR}/secrets\""
  CREDS_REMOTE="${REMOTE_DIR}/secrets/$(basename "$CREDS")"
  remote "if grep -q '^GOOGLE_APPLICATION_CREDENTIALS=' ${REMOTE_DIR}/.env; then sed -i 's|^GOOGLE_APPLICATION_CREDENTIALS=.*|GOOGLE_APPLICATION_CREDENTIALS=${CREDS_REMOTE}|' ${REMOTE_DIR}/.env; else echo GOOGLE_APPLICATION_CREDENTIALS=${CREDS_REMOTE} >> ${REMOTE_DIR}/.env; fi"
fi

echo "=== Install Python deps on server ==="
remote "cd ${REMOTE_DIR} && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt"

if [[ $# -eq 0 ]]; then
  echo "Deploy complete. Pass a command to run on server, e.g.:"
  echo "  $0 'cd ${REMOTE_DIR} && set -a && source .env && set +a && .venv/bin/python drive_ingest.py'"
  exit 0
fi

echo "=== Run on server: $* ==="
remote "cd ${REMOTE_DIR} && set -a && source .env && set +a && export EXTRACT_PARALLEL_WORKERS=\${EXTRACT_PARALLEL_WORKERS:-3} PDF_OCR_PARALLEL_WORKERS=\${PDF_OCR_PARALLEL_WORKERS:-2} && $*"
