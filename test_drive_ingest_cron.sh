#!/usr/bin/env bash
# Test that the Drive ingest runs correctly when invoked twice (e.g. as cron would).
# Runs ingest once, waits 30 seconds, runs again. Use this to verify before relying on cron.
set -e
cd "$(dirname "$0")"
echo "=== First ingest run ==="
./run_drive_ingest.sh
echo ""
echo "=== Waiting 30 seconds ==="
sleep 30
echo "=== Second ingest run ==="
./run_drive_ingest.sh
echo ""
echo "=== Done: two runs 30s apart completed ==="
