#!/usr/bin/env bash
# Poll UIC until policy tracker discovery is idle, queue full Qwen reingest, run completeness check.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REPORT="${ROOT}/data/uic_reingest_monitor_report.json"
SSH_KEY="${INGEST_SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"
SSH_HOST="${INGEST_SSH_HOST:-100.71.124.8}"
SSH_USER="${INGEST_SSH_USER:-info@urbanindigenouscollective.org}"
REMOTE_DIR="${INGEST_REMOTE_ROOT:-/root/WocconWaker}"
POLL_SEC="${UIC_LLM_WAIT_POLL_SEC:-60}"
MAX_WAIT_SEC="${UIC_LLM_WAIT_MAX_SEC:-7200}"
STAGING_DIR="${DRIVE_STAGING_DIR:-woccon_language/drive_staging_qwen_full}"

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ERRORS=()
REINGEST_CMD=""
REINGEST_EXIT=""
COMPLETENESS_SUMMARY=""
UIC_STATUS="unknown"
COMPLETED_AT=""

remote() {
  ssh -i "$SSH_KEY" -o ConnectTimeout=30 -o StrictHostKeyChecking=accept-new \
    "${SSH_USER}@${SSH_HOST}" "wsl -e bash -lc \"$*\""
}

check_uic_status() {
  remote "pgrep -af run_discovery 2>/dev/null || true; echo '---'; pgrep -af drive_ingest.py 2>/dev/null || true; echo '---'; tail -3 /opt/policy-tracker/logs/*.log 2>/dev/null | tail -3 || true"
}

is_policy_idle() {
  local out
  out="$(remote "pgrep -f run_discovery >/dev/null 2>&1 && echo busy || echo idle" 2>/dev/null || echo ssh_fail)"
  [[ "$out" == *idle* ]]
}

is_ingest_running() {
  remote "pgrep -f drive_ingest.py >/dev/null 2>&1 && echo running || echo idle" 2>/dev/null | grep -q running
}

write_report() {
  mkdir -p "$(dirname "$REPORT")"
  python3 - <<PY
import json
from pathlib import Path
report = {
    "started_at": "$STARTED_AT",
    "uic_ingest_status": """$UIC_STATUS""",
    "completed_at": "$COMPLETED_AT" or None,
    "reingest_command_run": """$REINGEST_CMD""",
    "reingest_exit_code": ${REINGEST_EXIT:-null},
    "completeness_summary": """$COMPLETENESS_SUMMARY""",
    "errors": $(python3 -c "import json; print(json.dumps(${ERRORS_JSON:-'[]'}))" 2>/dev/null || echo '[]'),
}
Path("$REPORT").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
PY
}

echo "=== Monitor started $STARTED_AT ==="
elapsed=0
while ! is_policy_idle; do
  UIC_STATUS="policy_analyzer_running step=$(remote 'tail -1 /opt/policy-tracker/logs/*.log 2>/dev/null | grep -oE "step=[0-9]+/[0-9]+" | tail -1 || echo unknown')"
  echo "$(date -Iseconds) waiting for policy analyzer: $UIC_STATUS"
  if [[ "$elapsed" -ge "$MAX_WAIT_SEC" ]]; then
    ERRORS+=("Timeout waiting for policy analyzer after ${MAX_WAIT_SEC}s")
    UIC_STATUS="timeout_waiting_for_policy_analyzer"
    write_report
    exit 1
  fi
  sleep "$POLL_SEC"
  elapsed=$((elapsed + POLL_SEC))
done

UIC_STATUS="policy_analyzer_idle"
echo "$(date -Iseconds) Policy analyzer idle. Deploying and queueing full Qwen reingest..."

if ! ./scripts/queue_full_qwen_ingest_uic.sh >> "${ROOT}/data/backups/uic_reingest_monitor.log" 2>&1; then
  ERRORS+=("queue_full_qwen_ingest_uic.sh failed")
  write_report
  exit 1
fi

REINGEST_CMD="./scripts/queue_full_qwen_ingest_uic.sh (remote: wait_for_uic_llm_idle.sh + run_full_qwen_ingest.sh, EXTRACT_COMPLETENESS_FAIL=1)"
UIC_STATUS="qwen_reingest_queued"

# Wait for ingest to start then finish
sleep 30
elapsed=0
MAX_INGEST_WAIT="${UIC_REINGEST_MAX_WAIT_SEC:-14400}"
while is_ingest_running || remote "test -f ${REMOTE_DIR}/data/backups/full_qwen_ingest_launcher.log && ! grep -q 'starting full Qwen drive_ingest' ${REMOTE_DIR}/data/backups/full_qwen_ingest.log 2>/dev/null && pgrep -f wait_for_uic_llm_idle >/dev/null 2>&1"; do
  progress="$(remote "tail -5 ${REMOTE_DIR}/data/backups/full_qwen_ingest.log 2>/dev/null | tail -1" || echo "")"
  UIC_STATUS="qwen_reingest_running: ${progress:0:120}"
  echo "$(date -Iseconds) $UIC_STATUS"
  if [[ "$elapsed" -ge "$MAX_INGEST_WAIT" ]]; then
    ERRORS+=("Timeout waiting for Qwen reingest after ${MAX_INGEST_WAIT}s")
    write_report
    exit 1
  fi
  sleep "$POLL_SEC"
  elapsed=$((elapsed + POLL_SEC))
done

# Capture exit from log
REINGEST_TAIL="$(remote "tail -30 ${REMOTE_DIR}/data/backups/full_qwen_ingest.log 2>/dev/null" || echo "")"
if echo "$REINGEST_TAIL" | grep -qE "ERROR|Traceback|Phase 1 ingest failed"; then
  REINGEST_EXIT=1
  ERRORS+=("Reingest log shows errors")
else
  REINGEST_EXIT=0
fi

UIC_STATUS="qwen_reingest_complete exit=${REINGEST_EXIT}"
echo "$(date -Iseconds) Running completeness check on UIC..."

COMPLETENESS_OUT="$(remote "cd ${REMOTE_DIR} && set -a && source .env && set +a && .venv/bin/python scripts/check_extraction_completeness.py --bulk --staging-dir ${STAGING_DIR} 2>&1" || true)"
COMPLETENESS_SUMMARY="$(echo "$COMPLETENESS_OUT" | tail -20 | tr '\n' ' ' | sed 's/"/\\"/g')"
echo "$COMPLETENESS_OUT"

COMPLETENESS_EXIT=0
echo "$COMPLETENESS_OUT" | grep -q "missing=" && COMPLETENESS_EXIT=1 || true

COMPLETED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ERRORS_JSON="$(python3 -c "import json; print(json.dumps(${ERRORS[@]+${ERRORS[@]@Q}}))" 2>/dev/null || echo '[]')"
write_report

echo "=== Monitor complete $COMPLETED_AT ==="
exit "${REINGEST_EXIT:-0}"
