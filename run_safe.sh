#!/bin/bash

# Safer script to run WocconWaker with logging

set -e  # Exit on any error

LOG_FILE="woccon_debug.log"
PID_FILE="woccon_app.pid"

echo "$(date): Starting WocconWaker safely"

# Function to cleanup on exit
cleanup() {
    echo "$(date): Cleanup triggered"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
        if [ -n "$PID" ] && ps -p "$PID" > /dev/null 2>&1; then
            echo "$(date): Stopping process $PID"
            kill "$PID" 2>/dev/null || true
            sleep 2
            # Force kill if still running
            if ps -p "$PID" > /dev/null 2>&1; then
                kill -9 "$PID" 2>/dev/null || true
            fi
        fi
        rm -f "$PID_FILE"
    fi
}

# Set trap for cleanup
trap cleanup EXIT INT TERM

# Kill any existing process
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "$(date): Killing existing process $OLD_PID"
        kill "$OLD_PID" 2>/dev/null || true
        sleep 3
        # Force kill if needed
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            kill -9 "$OLD_PID" 2>/dev/null || true
        fi
    fi
    rm -f "$PID_FILE"
fi

# Clear old log file
> "$LOG_FILE"

# Set environment variables
export ENABLE_TYPING_INDICATORS=true
export PYTHONUNBUFFERED=1

echo "$(date): Starting Python app" | tee -a "$LOG_FILE"

# Start the app in background and redirect output
python3 app.py >> "$LOG_FILE" 2>&1 &
APP_PID=$!

# Save PID
echo $APP_PID > "$PID_FILE"
echo "$(date): App started with PID $APP_PID" | tee -a "$LOG_FILE"

# Wait a moment to see if it starts successfully
sleep 3

if ps -p $APP_PID > /dev/null 2>&1; then
    echo "✅ WocconWaker started successfully!"
    echo "📝 Logs: tail -f $LOG_FILE"
    echo "🌐 Server: http://localhost:8000"
    echo "🛑 Stop: kill $APP_PID"
    echo ""
    echo "Press Ctrl+C to stop the server"
    
    # Wait for the process to finish or be interrupted
    wait $APP_PID
else
    echo "❌ App failed to start. Check logs:"
    tail -20 "$LOG_FILE"
    exit 1
fi