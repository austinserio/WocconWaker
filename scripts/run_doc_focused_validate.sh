#!/usr/bin/env bash
# Doc-scoped focused Qwen validation passes (grammar/pronunciation with optional lineage).
#
# Usage:
#   DRIVE_INGEST_FILTER=Carter-WocconLanguageNorth ./scripts/run_doc_focused_validate.sh
#   DRIVE_INGEST_FILTER=Rudes DOC_TAG=rudes ./scripts/run_doc_focused_validate.sh
#
# Env:
#   DRIVE_INGEST_FILTER  — substring match for drive_ingest (required)
#   DOC_TAG              — staging subdir tag (default: slug from filter)
#   DRIVE_STAGING_BASE   — parent dir (default: drive_staging_qwen_validate)
#   PASSES               — space-separated pass specs: focus[:lineage[:tag_suffix]]
#                          default: grammar:woccon_attested:grammar_woccon_attested
#                                   grammar:proto_catawban:grammar_proto_catawban
#                                   pronunciation::pronunciation
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
set -a
source .env
set +a

FILTER="${DRIVE_INGEST_FILTER:?Set DRIVE_INGEST_FILTER (e.g. Carter-WocconLanguageNorth)}"
DOC_TAG="${DOC_TAG:-$(echo "$FILTER" | tr ' /' '__' | tr -cd '[:alnum:]_-' | head -c 48)}"
export DRIVE_INGEST_FILTER="$FILTER"
export DRIVE_INGEST_FORCE_FULL="${DRIVE_INGEST_FORCE_FULL:-1}"
export EXTRACT_PARALLEL_WORKERS="${EXTRACT_PARALLEL_WORKERS:-2}"
export PDF_OCR_PARALLEL_WORKERS="${PDF_OCR_PARALLEL_WORKERS:-2}"
export OLLAMA_KEEP_ALIVE="${INGEST_OLLAMA_KEEP_ALIVE:-10m}"
export PYTHONUNBUFFERED=1

BASE_STAGING="${DRIVE_STAGING_BASE:-woccon_language/drive_staging_qwen_validate}"
mkdir -p data/backups "$BASE_STAGING"

DEFAULT_PASSES=(
  "grammar:woccon_attested:grammar_woccon_attested"
  "grammar:proto_catawban:grammar_proto_catawban"
  "pronunciation::pronunciation"
)

if [[ -n "${PASSES:-}" ]]; then
  # shellcheck disable=SC2206
  PASS_LIST=($PASSES)
else
  PASS_LIST=("${DEFAULT_PASSES[@]}")
fi

run_pass() {
  local spec="$1"
  local focus lineage tag
  IFS=':' read -r focus lineage tag <<<"$spec"
  if [[ -z "$tag" ]]; then
    tag="${focus}${lineage:+_${lineage}}"
  fi
  export EXTRACTION_FOCUS="$focus"
  if [[ -n "$lineage" ]]; then
    export GRAMMAR_LINEAGE="$lineage"
  else
    unset GRAMMAR_LINEAGE || true
  fi
  export DRIVE_STAGING_DIR="${BASE_STAGING}/${DOC_TAG}/${tag}"
  mkdir -p "$DRIVE_STAGING_DIR"
  local log="data/backups/doc_validate_${DOC_TAG}_${tag}.log"
  echo "=== $(date -Iseconds) filter=$FILTER focus=$focus lineage=${lineage:-none} staging=$DRIVE_STAGING_DIR ===" | tee -a "$log"
  .venv/bin/python -u drive_ingest.py 2>&1 | tee -a "$log"
}

for spec in "${PASS_LIST[@]}"; do
  run_pass "$spec"
done

echo "=== Focused passes complete for $FILTER (tag=$DOC_TAG) ==="
