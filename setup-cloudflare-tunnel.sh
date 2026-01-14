#!/bin/bash
# Cloudflare Tunnel setup script for woccon.urbanindigenouscollective.org
# Run this AFTER completing: cloudflared tunnel login and cloudflared tunnel create wocconwaker

set -e

TUNNEL_NAME="wocconwaker"
HOSTNAME="woccon.urbanindigenouscollective.org"
LOCAL_SERVICE="http://localhost:8000"

echo "Setting up Cloudflare Tunnel for $HOSTNAME..."
echo ""

# Get tunnel ID
TUNNEL_ID=$(cloudflared tunnel list --output json 2>/dev/null | python3 -c "import sys, json; data = json.load(sys.stdin); tunnels = [t for t in data if t.get('name') == '$TUNNEL_NAME']; print(tunnels[0]['id'] if tunnels else '')" 2>/dev/null)

if [ -z "$TUNNEL_ID" ]; then
    # Try alternative method
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep -i "$TUNNEL_NAME" | awk '{print $1}' | head -1)
fi

if [ -z "$TUNNEL_ID" ]; then
    echo "Error: Tunnel '$TUNNEL_NAME' not found."
    echo "Available tunnels:"
    cloudflared tunnel list 2>/dev/null || echo "  (Could not list tunnels)"
    echo ""
    echo "Please run: cloudflared tunnel create $TUNNEL_NAME"
    exit 1
fi

echo "Found tunnel ID: $TUNNEL_ID"
echo ""

# Create DNS route
echo "Creating DNS route..."
cloudflared tunnel route dns $TUNNEL_NAME $HOSTNAME

# Create config directory
sudo mkdir -p /etc/cloudflared

# Find credentials file
CREDENTIALS_FILE="$HOME/.cloudflared/$TUNNEL_ID.json"
if [ ! -f "$CREDENTIALS_FILE" ]; then
    echo "Error: Credentials file not found at $CREDENTIALS_FILE"
    exit 1
fi

# Create config file
echo "Creating config file..."
sudo tee /etc/cloudflared/config.yml > /dev/null << CONFIG_EOF
tunnel: $TUNNEL_ID
credentials-file: $CREDENTIALS_FILE

ingress:
  - hostname: $HOSTNAME
    service: $LOCAL_SERVICE
  - service: http_status:404
CONFIG_EOF

# Copy credentials to accessible location (cloudflared service runs as root)
sudo cp $CREDENTIALS_FILE /etc/cloudflared/$TUNNEL_ID.json
sudo chmod 600 /etc/cloudflared/$TUNNEL_ID.json

# Update config to use the copied credentials file
sudo tee /etc/cloudflared/config.yml > /dev/null << CONFIG_EOF
tunnel: $TUNNEL_ID
credentials-file: /etc/cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: $HOSTNAME
    service: $LOCAL_SERVICE
  - service: http_status:404
CONFIG_EOF

# Install as systemd service
echo "Installing Cloudflared as systemd service..."
sudo cloudflared service install

# Start and enable service
echo "Starting Cloudflared service..."
sudo systemctl start cloudflared
sudo systemctl enable cloudflared

# Check status
echo ""
echo "Checking service status..."
sudo systemctl status cloudflared --no-pager | head -15

echo ""
echo "✅ Cloudflare Tunnel setup complete!"
echo ""
echo "Your application should be available at:"
echo "  https://$HOSTNAME"
echo ""
echo "Webhook URL:"
echo "  https://$HOSTNAME/webhook"
echo ""
echo "Verify token: wakad"

