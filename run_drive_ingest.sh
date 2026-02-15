#!/usr/bin/env bash
# Run Drive ingest Phase 1 verify. Loads .env and uses venv if present.
# To install new deps (e.g. anthropic): source .venv/bin/activate && pip install anthropic
set -e
cd "$(dirname "$0")"
if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi
# Preserve env vars set by caller (e.g. ANTHROPIC_MODEL=..., DRIVE_INGEST_FORCE_FULL=1)
saved_anthropic_model="${ANTHROPIC_MODEL-}"
saved_staging_dir="${DRIVE_STAGING_DIR-}"
saved_force_full="${DRIVE_INGEST_FORCE_FULL-}"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
[ -n "$saved_anthropic_model" ] && export ANTHROPIC_MODEL="$saved_anthropic_model"
[ -n "$saved_staging_dir" ] && export DRIVE_STAGING_DIR="$saved_staging_dir"
[ -n "$saved_force_full" ] && export DRIVE_INGEST_FORCE_FULL="$saved_force_full"
python3 -u drive_ingest.py
