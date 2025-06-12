#!/bin/bash

# Script to run WocconWaker with comprehensive logging

LOG_FILE="woccon_debug.log"
PID_FILE="woccon_app.pid"

echo "$(date): Starting WocconWaker with debug logging" | tee -a "$LOG_FILE"

# Kill existing process if running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "$(date): Killing existing process $OLD_PID" | tee -a "$LOG_FILE"
        kill "$OLD_PID"
        sleep 2
    fi
    rm -f "$PID_FILE"
fi

# Set environment variables for debugging
export ENABLE_TYPING_INDICATORS=true

# Run the app with all output redirected to log file
echo "$(date): Starting Python app with logging to $LOG_FILE" | tee -a "$LOG_FILE"
python3 app.py 2>&1 | tee -a "$LOG_FILE" &

# Save the PID
echo $! > "$PID_FILE"
echo "$(date): App started with PID $(cat $PID_FILE)" | tee -a "$LOG_FILE"

echo ""
echo "🚀 WocconWaker is starting..."
echo "📝 All logs are being written to: $LOG_FILE"
echo "🔍 To watch logs in real-time: tail -f $LOG_FILE"
echo "🛑 To stop the server: kill \$(cat $PID_FILE)"
echo ""
echo "✅ Server should be running at http://localhost:8000"
echo ""