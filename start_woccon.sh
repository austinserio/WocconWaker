#!/bin/bash

# Exit on error
set -e

# Start Ollama as a background service
echo "Starting Ollama service..."
nohup ollama serve > ollama.log 2>&1 &

# Wait for Ollama to be ready
echo "Waiting for Ollama to be available..."
MAX_RETRIES=30
count=0
while ! curl -s http://localhost:11434/api/version &>/dev/null; do
    sleep 2
    count=$((count+1))
    if [ $count -ge $MAX_RETRIES ]; then
        echo "Ollama failed to start after $MAX_RETRIES retries"
        exit 1
    fi
done
echo "Ollama is ready!"

# Set environment variables
export WOCCON_MODE=server
export PORT=8000
# Add any other environment variables your app needs
# export LLAMA_MODEL_PATH="/workspace/models/llama3-8b"
# export T5_MODEL_PATH="/workspace/models/t5-base"

# Start the Woccon server with nohup
echo "Starting Woccon server..."
cd /workspace/wocconwaker/WocconWaker  # Update this with your actual path
nohup python app.py > woccon.log 2>&1 &

# Save PID to file for easier management later
echo $! > woccon.pid

echo "Services started successfully! Check logs at:"
echo "- Ollama: $(pwd)/ollama.log"
echo "- Woccon: $(pwd)/woccon.log"