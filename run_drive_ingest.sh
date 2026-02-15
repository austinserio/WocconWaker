#!/usr/bin/env bash
# Run Drive ingest Phase 1 verify. Loads .env and uses venv if present.
# To install new deps (e.g. anthropic): source .venv/bin/activate && pip install anthropic
set -e
cd "$(dirname "$0")"
if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
python3 -u drive_ingest.py
