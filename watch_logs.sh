#!/bin/bash

# Script to watch WocconWaker logs with filtering options

LOG_FILE="woccon_debug.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "❌ Log file $LOG_FILE not found. Run ./run_with_logging.sh first"
    exit 1
fi

echo "📋 Watching logs from $LOG_FILE"
echo "🔍 Press Ctrl+C to stop watching"
echo "📝 Recent logs:"
echo "=================="

# Show last 20 lines first
tail -20 "$LOG_FILE"

echo ""
echo "🔄 Live updates:"
echo "=================="

# Watch for new entries
tail -f "$LOG_FILE" | while read line; do
    # Highlight important debug lines
    if [[ "$line" == *"[DEBUG]"* ]]; then
        echo "🐛 $line"
    elif [[ "$line" == *"ERROR"* ]]; then
        echo "❌ $line"
    elif [[ "$line" == *"Warning"* ]]; then
        echo "⚠️  $line"
    elif [[ "$line" == *"webhook"* ]]; then
        echo "📡 $line"
    else
        echo "$line"
    fi
done