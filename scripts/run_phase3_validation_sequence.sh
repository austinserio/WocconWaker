#!/usr/bin/env bash
# Phase 3: sequential focused Qwen validation passes (Carter, Woccon-by-Carter, Rudes, Grammar Guide).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
set -a
source .env
set +a

export DRIVE_INGEST_FORCE_FULL=1
export EXTRACT_PARALLEL_WORKERS="${EXTRACT_PARALLEL_WORKERS:-2}"
export PYTHONUNBUFFERED=1

run_doc() {
  local filter="$1"
  local tag="$2"
  shift 2
  export DRIVE_INGEST_FILTER="$filter"
  export DOC_TAG="$tag"
  if [[ $# -gt 0 ]]; then
    export PASSES="$*"
  else
    unset PASSES || true
  fi
  bash scripts/run_doc_focused_validate.sh
}

run_doc "Carter-WocconLanguageNorth" carter1980
run_doc "Woccon by Carter" woccon_by_carter
run_doc "Rudes" rudes grammar:siouan_comparative:grammar_siouan pronunciation::pronunciation
run_doc "Pronunciation Guide" grammar_pron_guide grammar::grammar pronunciation::pronunciation

echo "=== Phase 3 validation sequence complete ==="
