#!/bin/bash
# Deploy GPU Spot VM for WocconWaker with Ollama
# Uses NCasT4_v3 (T4 GPU) - best for Ollama inference
# Spot pricing: ~$0.10/hour (~$72/month if 24/7)

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Deploy GPU Spot VM (NCasT4_v3 - T4 GPU)                 ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID in .env (see .env.example)}"
echo -e "${GREEN}Setting subscription to: ${SUBSCRIPTION_ID}${NC}"
az account set --subscription "$SUBSCRIPTION_ID"

# Configuration
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP_GPU:?Set AZURE_RESOURCE_GROUP_GPU in .env (see .env.example)}"
LOCATION="eastus"  # Try this first, will check others if needed
VM_NAME="wocconwaker-gpu-spot"
VM_SIZE="NC4as_T4_v3"  # T4 GPU, 4 vCPU, 28GB RAM
USERNAME="azureuser"
ADMIN_PASSWORD=$(openssl rand -base64 32 2>/dev/null || echo "ChangeMe123!")

# Pricing information
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}Pricing Information${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}Spot VM Pricing (NCasT4_v3):${NC}"
echo -e "  • ~\$0.10/hour (~\$2.40/day if 24/7)"
echo -e "  • ~\$72/month if running 24/7"
echo -e "  • With \$2,000 grant: ~27 months of continuous operation"
echo ""
echo -e "${YELLOW}⚠ Important: Spot VMs can be evicted with 30 seconds notice${NC}"
echo -e "${YELLOW}  Save your work frequently and set up auto-shutdown script${NC}"
echo ""

read -p "Continue with deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

# Create resource group if it doesn't exist
echo -e "${BLUE}Step 1: Creating resource group...${NC}"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" 2>/dev/null || true
echo -e "${GREEN}✓ Resource group ready${NC}"
echo ""

# Check VM size availability
echo -e "${BLUE}Step 2: Checking VM size availability in ${LOCATION}...${NC}"
AVAILABLE=$(az vm list-sizes --location "$LOCATION" --query "[?name=='${VM_SIZE}']" -o tsv 2>/dev/null || echo "")

if [ -z "$AVAILABLE" ]; then
    echo -e "${YELLOW}⚠ ${VM_SIZE} not available in ${LOCATION}, trying other regions...${NC}"
    
    # Try other regions
    OTHER_REGIONS=("westus2" "westus3" "southcentralus" "northeurope")
    LOCATION_FOUND=""
    
    for region in "${OTHER_REGIONS[@]}"; do
        echo -e "  Checking ${region}..."
        if az vm list-sizes --location "$region" --query "[?name=='${VM_SIZE}']" -o tsv 2>/dev/null | grep -q "$VM_SIZE"; then
            LOCATION_FOUND="$region"
            echo -e "  ${GREEN}✓ Found in ${region}${NC}"
            break
        fi
    done
    
    if [ -z "$LOCATION_FOUND" ]; then
        echo -e "${RED}✗ ${VM_SIZE} not available in any checked region${NC}"
        echo -e "${YELLOW}You may need to request GPU quota first${NC}"
        echo -e "  Run: ./request-gpu-quota-enhanced.sh"
        exit 1
    fi
    
    LOCATION="$LOCATION_FOUND"
    echo -e "${GREEN}Using region: ${LOCATION}${NC}"
else
    echo -e "${GREEN}✓ ${VM_SIZE} available in ${LOCATION}${NC}"
fi
echo ""

# Try to create Spot VM
echo -e "${BLUE}Step 3: Creating Spot VM (this may take 5-10 minutes)...${NC}"
echo -e "${YELLOW}Note: Spot VMs use underutilized capacity${NC}"
echo -e "${YELLOW}If this fails, you may need to request GPU quota first${NC}"
echo ""

# Create network resources first
VNET_NAME="${VM_NAME}-vnet"
SUBNET_NAME="${VM_NAME}-subnet"
NSG_NAME="${VM_NAME}-nsg"

echo -e "${BLUE}  Creating virtual network...${NC}"
az network vnet create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VNET_NAME" \
    --address-prefix "10.0.0.0/16" \
    --subnet-name "$SUBNET_NAME" \
    --subnet-prefix "10.0.0.0/24" \
    --output none 2>/dev/null || true

echo -e "${BLUE}  Creating network security group...${NC}"
az network nsg create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$NSG_NAME" \
    --output none 2>/dev/null || true

# Allow SSH
az network nsg rule create \
    --resource-group "$RESOURCE_GROUP" \
    --nsg-name "$NSG_NAME" \
    --name "SSH" \
    --priority 1000 \
    --protocol Tcp \
    --destination-port-ranges 22 \
    --access Allow \
    --output none 2>/dev/null || true

# Allow HTTP/HTTPS
az network nsg rule create \
    --resource-group "$RESOURCE_GROUP" \
    --nsg-name "$NSG_NAME" \
    --name "HTTP" \
    --priority 1001 \
    --protocol Tcp \
    --destination-port-ranges 8000 \
    --access Allow \
    --output none 2>/dev/null || true

echo -e "${BLUE}  Creating Spot VM...${NC}"
VM_CREATE_OUTPUT=$(az vm create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --image "Ubuntu2204" \
    --size "$VM_SIZE" \
    --location "$LOCATION" \
    --admin-username "$USERNAME" \
    --admin-password "$ADMIN_PASSWORD" \
    --vnet-name "$VNET_NAME" \
    --subnet "$SUBNET_NAME" \
    --nsg "$NSG_NAME" \
    --public-ip-sku Standard \
    --priority Spot \
    --max-price -1 \
    --eviction-policy Deallocate \
    --output json 2>&1) || VM_CREATE_ERROR="$VM_CREATE_OUTPUT"

if [ -n "$VM_CREATE_ERROR" ]; then
    if echo "$VM_CREATE_ERROR" | grep -qi "quota\|QuotaExceeded\|ZonalAllocationFailed"; then
        echo -e "${RED}✗ GPU quota exceeded or not available${NC}"
        echo ""
        echo -e "${YELLOW}You need to request GPU quota first:${NC}"
        echo -e "  ./request-gpu-quota-enhanced.sh"
        echo ""
        echo -e "${YELLOW}Or try a different region:${NC}"
        echo -e "  Edit this script and change LOCATION variable"
        exit 1
    else
        echo -e "${RED}✗ VM creation failed:${NC}"
        echo "$VM_CREATE_ERROR"
        exit 1
    fi
fi

PUBLIC_IP=$(echo "$VM_CREATE_OUTPUT" | jq -r '.publicIpAddress' 2>/dev/null || echo "")
PRIVATE_IP=$(echo "$VM_CREATE_OUTPUT" | jq -r '.privateIpAddress' 2>/dev/null || echo "")

echo -e "${GREEN}✓ VM created successfully${NC}"
echo ""

# Get public IP if not in output
if [ -z "$PUBLIC_IP" ]; then
    PUBLIC_IP=$(az vm show -d \
        --resource-group "$RESOURCE_GROUP" \
        --name "$VM_NAME" \
        --query publicIps -o tsv 2>/dev/null || echo "")
fi

echo -e "${BLUE}Step 4: Setting up GPU drivers and Ollama...${NC}"
echo -e "${YELLOW}This may take 10-15 minutes...${NC}"
echo ""

# Create setup script
SETUP_SCRIPT=$(cat <<'EOF'
#!/bin/bash
set -e

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install NVIDIA drivers (for T4 GPU)
sudo apt-get install -y ubuntu-drivers-common
sudo ubuntu-drivers autoinstall

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
fi

# Install Ollama with GPU support
curl -fsSL https://ollama.com/install.sh | sh

# Install Python and dependencies
sudo apt-get install -y python3 python3-pip git

# Create application directory
mkdir -p /home/azureuser/wocconwaker
cd /home/azureuser/wocconwaker

# Pull Ollama model
ollama pull llama3:8b

# Create systemd service for auto-start
cat > /tmp/wocconwaker.service <<'SERVICE_EOF'
[Unit]
Description=WocconWaker with Ollama
After=network.target

[Service]
Type=simple
User=azureuser
WorkingDirectory=/home/azureuser/wocconwaker
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE_EOF

sudo mv /tmp/wocconwaker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wocconwaker.service

echo "Setup complete! GPU drivers and Ollama installed."
nvidia-smi
EOF
)

# Copy and run setup script
echo -e "${BLUE}  Uploading setup script...${NC}"
echo "$SETUP_SCRIPT" > /tmp/setup-gpu-vm.sh
chmod +x /tmp/setup-gpu-vm.sh

# Wait for VM to be ready
echo -e "${BLUE}  Waiting for VM to be ready (30 seconds)...${NC}"
sleep 30

# Run setup via SSH (using password authentication)
echo -e "${BLUE}  Running setup script on VM...${NC}"
sshpass -p "$ADMIN_PASSWORD" ssh \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=30 \
    "${USERNAME}@${PUBLIC_IP}" \
    "bash -s" < /tmp/setup-gpu-vm.sh || {
    echo -e "${YELLOW}⚠ SSH connection failed, trying alternative method...${NC}"
    echo -e "${YELLOW}You may need to manually connect and run the setup${NC}"
    echo ""
    echo -e "${CYAN}Manual setup commands:${NC}"
    echo "$SETUP_SCRIPT"
}

echo ""
echo -e "${GREEN}✓ Setup initiated${NC}"
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${CYAN}VM Details:${NC}"
echo -e "  Name: ${VM_NAME}"
echo -e "  Size: ${VM_SIZE} (T4 GPU)"
echo -e "  Region: ${LOCATION}"
echo -e "  Public IP: ${PUBLIC_IP}"
echo -e "  Username: ${USERNAME}"
echo -e "  Password: ${ADMIN_PASSWORD}"
echo ""
echo -e "${CYAN}Pricing:${NC}"
echo -e "  Spot VM: ~\$0.10/hour (~\$72/month if 24/7)"
echo -e "  Current cost: ~\$2.40/day if running 24/7"
echo ""
echo -e "${CYAN}Connection:${NC}"
echo -e "  ssh ${USERNAME}@${PUBLIC_IP}"
echo -e "  Password: ${ADMIN_PASSWORD}"
echo ""
echo -e "${CYAN}Next Steps:${NC}"
echo -e "  1. SSH into the VM: ssh ${USERNAME}@${PUBLIC_IP}"
echo -e "  2. Verify GPU: nvidia-smi"
echo -e "  3. Test Ollama: ollama run llama3:8b"
echo -e "  4. Deploy your app (see app.py deployment instructions)"
echo ""
echo -e "${YELLOW}⚠ Spot VM Warning:${NC}"
echo -e "  • VM can be evicted with 30 seconds notice"
echo -e "  • Save work frequently"
echo -e "  • Consider auto-shutdown script"
echo -e "  • Check eviction status: az vm show -d -g ${RESOURCE_GROUP} -n ${VM_NAME} --query \"evictionPolicy\""
echo ""
echo -e "${CYAN}Useful Commands:${NC}"
echo -e "  Stop VM: az vm deallocate -g ${RESOURCE_GROUP} -n ${VM_NAME}"
echo -e "  Start VM: az vm start -g ${RESOURCE_GROUP} -n ${VM_NAME}"
echo -e "  View status: az vm show -d -g ${RESOURCE_GROUP} -n ${VM_NAME}"
echo -e "  Delete VM: az vm delete -g ${RESOURCE_GROUP} -n ${VM_NAME} --yes"
echo ""

