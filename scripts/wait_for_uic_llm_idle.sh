#!/usr/bin/env bash
# Wait until policy tracker (and other discovery jobs) release the shared UIC LLM,
# then acquire a flock so only one Woccon GPU job runs at a time.
set -euo pipefail
POLL_SEC="${UIC_LLM_WAIT_POLL_SEC:-60}"
MAX_WAIT_SEC="${UIC_LLM_WAIT_MAX_SEC:-86400}"
LOCK_FILE="${UIC_LLM_LOCK_FILE:-/tmp/woccon_uic_llm.lock}"

echo "=== $(date -Iseconds) waiting for UIC LLM idle (max ${MAX_WAIT_SEC}s) ==="
elapsed=0
while pgrep -f run_discovery >/dev/null 2>&1 || pgrep -f "drive_ingest.py" >/dev/null 2>&1; do
  if [[ "$elapsed" -ge "$MAX_WAIT_SEC" ]]; then
    echo "Timeout waiting for LLM idle after ${MAX_WAIT_SEC}s" >&2
    exit 1
  fi
  echo "  $(date -Iseconds) policy/ingest still running; sleep ${POLL_SEC}s"
  sleep "$POLL_SEC"
  elapsed=$((elapsed + POLL_SEC))
done

echo "=== $(date -Iseconds) acquiring GPU lock ${LOCK_FILE} ==="
exec 200>"$LOCK_FILE"
if ! flock -w "$MAX_WAIT_SEC" 200; then
  echo "Timeout waiting for GPU lock after ${MAX_WAIT_SEC}s" >&2
  exit 1
fi
echo "=== $(date -Iseconds) starting: $* ==="
exec "$@"
