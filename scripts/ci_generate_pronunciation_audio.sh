#!/usr/bin/env bash
# Generate or verify pronunciation MP3s for CI / Docker build.
# Primary operator workflow: generate on UIC, pull via pull_uic_pronunciation_audio.sh, commit.
# This script is the GitHub Actions fallback when committed clips are missing.
# Requires: Python 3.10–3.12, espeak-ng, ffmpeg, pip install -r requirements-tts.txt
#
# Usage:
#   ./scripts/ci_generate_pronunciation_audio.sh              # generate from staging JSON
#   ./scripts/ci_generate_pronunciation_audio.sh --verify-only # check manifest + MP3 count

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="${PRONUNCIATION_STAGING:-woccon_language/drive_staging/English-Woccon.json}"
AUDIO_DIR="${PRONUNCIATION_AUDIO_DIR:-data/pronunciation_audio}"
export HF_HOME="${HF_HOME:-$ROOT/data/hf_cache}"
MIN_CLIPS="${PRONUNCIATION_MIN_CLIPS:-50}"

verify_only() {
  local manifest="$ROOT/$AUDIO_DIR/manifest.json"
  if [[ ! -f "$manifest" ]]; then
    echo "Missing pronunciation manifest: $manifest" >&2
    exit 1
  fi
  local count
  count="$(find "$ROOT/$AUDIO_DIR" -maxdepth 1 -name '*.mp3' | wc -l | tr -d ' ')"
  if [[ "$count" -lt "$MIN_CLIPS" ]]; then
    echo "Expected at least $MIN_CLIPS MP3 clips, found $count in $ROOT/$AUDIO_DIR" >&2
    exit 1
  fi
  echo "Verified $count pronunciation clip(s) in $AUDIO_DIR"
}

if [[ "${1:-}" == "--verify-only" ]]; then
  verify_only
  exit 0
fi

if [[ ! -f "$ROOT/$STAGING" ]]; then
  echo "Staging lexicon not found: $ROOT/$STAGING" >&2
  exit 1
fi

mkdir -p "$ROOT/$HF_HOME" "$ROOT/$AUDIO_DIR"

python3 "$ROOT/scripts/generate_pronunciation_audio.py" \
  --staging "$ROOT/$STAGING" \
  --audio-dir "$ROOT/$AUDIO_DIR"

verify_only
