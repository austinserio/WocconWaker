#!/bin/bash
# Azure VM deployment script for WocconWaker (self-hosted Ollama)
# Creates a VM with D2s_v3 size and sets up self-hosted Ollama

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}WocconWaker Azure VM Deployment Script${NC}"
echo "=========================================="

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo -e "${RED}Error: Azure CLI is not installed.${NC}"
    exit 1
fi

# Check if logged in
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}Not logged in to Azure. Logging in...${NC}"
    az login
fi

# Use current default subscription (user should have set the correct one)
CURRENT_SUB=$(az account show --query id -o tsv)
echo -e "${GREEN}Using subscription: ${CURRENT_SUB}${NC}"
echo -e "${YELLOW}Current account: $(az account show --query user.name -o tsv)${NC}"

# Configuration
RESOURCE_GROUP="rg-wocconwaker"
LOCATION="westus2"  # Changed from eastus due to capacity restrictions
VM_NAME="wocconwaker-vm"
VM_SIZE="Standard_D2s_v3"  # 2 vCPU, 8GB RAM - start small, can resize to D4s_v3 later
ADMIN_USERNAME="woccon"
IMAGE="Ubuntu2204"  # Ubuntu 22.04 LTS

echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Location: $LOCATION"
echo "  VM Name: $VM_NAME"
echo "  VM Size: $VM_SIZE (can resize to D4s_v3 later)"
echo "  OS: Ubuntu 22.04 LTS"
echo ""

# Create resource group if it doesn't exist
if ! az group show --name "$RESOURCE_GROUP" &> /dev/null; then
    echo -e "${GREEN}Creating resource group: $RESOURCE_GROUP${NC}"
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION"
else
    echo -e "${GREEN}Resource group already exists: $RESOURCE_GROUP${NC}"
fi

# Generate SSH key if it doesn't exist
SSH_KEY_PATH="$HOME/.ssh/wocconwaker_azure_key"
if [ ! -f "$SSH_KEY_PATH" ]; then
    echo -e "${GREEN}Generating SSH key...${NC}"
    ssh-keygen -t rsa -b 4096 -f "$SSH_KEY_PATH" -N "" -C "wocconwaker-azure"
fi

# Create VM
echo -e "${GREEN}Creating VM: $VM_NAME${NC}"
echo "This may take a few minutes..."

az vm create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VM_NAME" \
  --image "$IMAGE" \
  --size "$VM_SIZE" \
  --admin-username "$ADMIN_USERNAME" \
  --ssh-key-values "$SSH_KEY_PATH.pub" \
  --public-ip-sku Standard \
  --location "$LOCATION" \
  --output table

# Get VM IP address
VM_IP=$(az vm show -d --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --query publicIps -o tsv)
echo ""
echo -e "${GREEN}VM created successfully!${NC}"
echo "  VM Name: $VM_NAME"
echo "  Public IP: $VM_IP"
echo "  SSH: ssh -i $SSH_KEY_PATH $ADMIN_USERNAME@$VM_IP"
echo ""

# Open port 8000 for the application
echo -e "${GREEN}Opening port 8000 for the application...${NC}"
az vm open-port --port 8000 --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --priority 1100

# Create setup script to upload to VM
echo -e "${GREEN}Preparing setup script...${NC}"
cat > /tmp/wocconwaker-setup.sh << 'SETUP_EOF'
#!/bin/bash
set -e

LOG_FILE="/home/$USER/wocconwaker-setup.log"
REPO_DIR="/home/$USER/WocconWaker"

echo "$(date): Starting WocconWaker setup" | tee -a "$LOG_FILE"

# Update system
sudo apt-get update | tee -a "$LOG_FILE"

# Install Python and dependencies
sudo apt-get install -y python3-pip python3-venv git curl tmux | tee -a "$LOG_FILE"

# Install Ollama
if ! command -v ollama &> /dev/null; then
    echo "$(date): Installing Ollama" | tee -a "$LOG_FILE"
    curl -fsSL https://ollama.com/install.sh | sh | tee -a "$LOG_FILE"
fi

# Clone repository
if [ ! -d "$REPO_DIR/.git" ]; then
    echo "$(date): Cloning repository" | tee -a "$LOG_FILE"
    git clone https://github.com/austinserio/WocconWaker.git "$REPO_DIR" | tee -a "$LOG_FILE"
else
    echo "$(date): Repository exists, pulling latest" | tee -a "$LOG_FILE"
    cd "$REPO_DIR"
    git pull | tee -a "$LOG_FILE"
fi

cd "$REPO_DIR"

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "$(date): Installing Python dependencies" | tee -a "$LOG_FILE"
pip install --upgrade pip | tee -a "$LOG_FILE"
pip install -r requirements.txt | tee -a "$LOG_FILE"

# Pull Ollama model
echo "$(date): Pulling Ollama model (llama3:8b)" | tee -a "$LOG_FILE"
ollama pull llama3:8b | tee -a "$LOG_FILE"

# Create systemd service for Ollama
sudo tee /etc/systemd/system/ollama.service > /dev/null << 'SERVICE_EOF'
[Unit]
Description=Ollama Service
After=network.target

[Service]
Type=simple
User=woccon
Environment="HOME=/home/woccon"
ExecStart=/usr/local/bin/ollama serve
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE_EOF

sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl start ollama

# Create systemd service for WocconWaker app
sudo tee /etc/systemd/system/wocconwaker.service > /dev/null << 'APP_SERVICE_EOF'
[Unit]
Description=WocconWaker Application
After=network.target ollama.service
Requires=ollama.service

[Service]
Type=simple
User=woccon
WorkingDirectory=/home/woccon/WocconWaker
Environment="PATH=/home/woccon/WocconWaker/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="WOCCON_MODE=server"
Environment="PORT=8000"
Environment="OLLAMA_URL=http://localhost:11434/v1/chat"
ExecStart=/home/woccon/WocconWaker/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
APP_SERVICE_EOF

sudo systemctl daemon-reload
sudo systemctl enable wocconwaker
sudo systemctl start wocconwaker

echo "$(date): Setup complete!" | tee -a "$LOG_FILE"
echo "Services started. Check status with: sudo systemctl status ollama wocconwaker"
SETUP_EOF

# Copy setup script to VM
echo -e "${GREEN}Copying setup script to VM...${NC}"
scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no /tmp/wocconwaker-setup.sh $ADMIN_USERNAME@$VM_IP:/home/$ADMIN_USERNAME/

# Run setup script on VM
echo -e "${GREEN}Running setup script on VM (this will take 10-15 minutes)...${NC}"
echo "  - Installing Ollama"
echo "  - Installing Python dependencies"
echo "  - Pulling llama3:8b model"
echo "  - Setting up services"
echo ""
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no $ADMIN_USERNAME@$VM_IP "chmod +x /home/$ADMIN_USERNAME/wocconwaker-setup.sh && sudo /home/$ADMIN_USERNAME/wocconwaker-setup.sh"

echo ""
echo -e "${GREEN}Deployment complete!${NC}"
echo ""
echo "VM Details:"
echo "  IP Address: http://$VM_IP:8000"
echo "  SSH: ssh -i $SSH_KEY_PATH $ADMIN_USERNAME@$VM_IP"
echo ""
echo "Useful commands:"
echo "  Check status: ssh -i $SSH_KEY_PATH $ADMIN_USERNAME@$VM_IP 'sudo systemctl status ollama wocconwaker'"
echo "  View logs: ssh -i $SSH_KEY_PATH $ADMIN_USERNAME@$VM_IP 'sudo journalctl -u wocconwaker -f'"
echo "  Stop VM: az vm stop --resource-group $RESOURCE_GROUP --name $VM_NAME"
echo "  Start VM: az vm start --resource-group $RESOURCE_GROUP --name $VM_NAME"
echo "  Resize to D4s_v3: az vm resize --resource-group $RESOURCE_GROUP --name $VM_NAME --size Standard_D4s_v3"
echo ""

