#!/bin/bash

# Simple script to show logs without infinite loops

LOG_FILE="woccon_debug.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "❌ Log file $LOG_FILE not found"
    echo "Run ./run_safe.sh first"
    exit 1
fi

echo "📋 Recent logs from $LOG_FILE:"
echo "======================================="

# Show last 30 lines
tail -30 "$LOG_FILE"

echo ""
echo "======================================="
echo "🔍 To see live updates: tail -f $LOG_FILE"
echo "🎯 To see specific events:"
echo "   grep 'webhook' $LOG_FILE"
echo "   grep 'BUG DETECTED' $LOG_FILE"
echo "   grep 'TRACE' $LOG_FILE"