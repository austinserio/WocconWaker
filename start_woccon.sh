#!/bin/bash

LOG_FILE="/workspace/wocconwaker/wocconwaker.log"
REPO_DIR="/workspace/wocconwaker/WocconWaker"
mkdir -p "$REPO_DIR"
echo "$(date): Starting WocconWaker setup" >> "$LOG_FILE"

# Install necessary tools
apt-get update && apt-get install -y tmux git curl >> "$LOG_FILE" 2>&1

# Clone or update the repo
if [ ! -d "$REPO_DIR/.git" ]; then
    echo "$(date): Cloning repository" >> "$LOG_FILE"
    git clone -b ollama https://<REDACTED_GITHUB_PAT>@github.com/austinserio/WocconWaker.git "$REPO_DIR" >> "$LOG_FILE" 2>&1
else
    echo "$(date): Repository exists, pulling latest" >> "$LOG_FILE"
    cd "$REPO_DIR"
    git reset --hard HEAD >> "$LOG_FILE" 2>&1
    git pull >> "$LOG_FILE" 2>&1
fi

# Install Ollama if not already installed
if ! command -v ollama &> /dev/null; then
    echo "$(date): Installing Ollama" >> "$LOG_FILE"
    curl -fsSL https://ollama.com/install.sh | sh >> "$LOG_FILE" 2>&1
fi

# Install Python dependencies
cd "$REPO_DIR"
pip install --upgrade pip >> "$LOG_FILE" 2>&1
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121 >> "$LOG_FILE" 2>&1

# Kill existing tmux session
if tmux has-session -t myapp 2>/dev/null; then
    echo "$(date): Killing existing TMUX session" >> "$LOG_FILE"
    tmux kill-session -t myapp
fi

# Create a new tmux session and run everything
echo "$(date): Starting new TMUX session" >> "$LOG_FILE"
tmux new-session -d -s myapp "
cd $REPO_DIR && \
ollama serve & \
sleep 2 && \
ollama pull llama3:8b && \
uvicorn app:app --host 0.0.0.0 --port 8000
"

echo "$(date): WocconWaker setup complete" >> "$LOG_FILE"