#!/bin/bash
# Script to migrate WocconWaker VM from CPU (D4s_v3) to GPU (NC6s_v3)

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Migrating WocconWaker VM to GPU (NC6s_v3)${NC}"

# Check if Azure CLI is installed and logged in
if ! command -v az &> /dev/null; then
    echo -e "${RED}Azure CLI is not installed. Please install it first.${NC}"
    exit 1
fi

if ! az account show &> /dev/null; then
    echo -e "${RED}Not logged into Azure. Please run 'az login' first.${NC}"
    exit 1
fi

# Set subscription
CURRENT_SUB=$(az account show --query id -o tsv)
echo -e "${GREEN}Using subscription: ${CURRENT_SUB}${NC}"
az account set --subscription "$CURRENT_SUB"

# Configuration
RESOURCE_GROUP="rg-wocconwaker"
VM_NAME="wocconwaker-vm"
# Try NC4as_T4_v3 first (T4 GPU, available without quota), then NC6s_v3 (V100, requires quota)
PREFERRED_SIZE="Standard_NC6s_v3"
FALLBACK_SIZE="Standard_NC4as_T4_v3"
NEW_VM_SIZE=""

# Check current VM size
CURRENT_SIZE=$(az vm show --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --query "hardwareProfile.vmSize" -o tsv)
echo -e "${YELLOW}Current VM size: ${CURRENT_SIZE}${NC}"

if [[ "$CURRENT_SIZE" == "$PREFERRED_SIZE" ]] || [[ "$CURRENT_SIZE" == "$FALLBACK_SIZE" ]]; then
    echo -e "${GREEN}VM is already a GPU VM (${CURRENT_SIZE}). No migration needed.${NC}"
    exit 0
fi

# Check GPU availability in current region
echo -e "${YELLOW}Checking GPU availability...${NC}"
CURRENT_LOCATION=$(az vm show --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --query "location" -o tsv)
echo -e "${YELLOW}Current location: ${CURRENT_LOCATION}${NC}"

# Check if preferred size (NC6s_v3) is available
echo -e "Checking ${PREFERRED_SIZE}..."
RESTRICTIONS_PREFERRED=$(az vm list-skus --location "$CURRENT_LOCATION" --size "$PREFERRED_SIZE" --output json 2>/dev/null | jq -r '.[0].restrictions // []' 2>/dev/null || echo '[]')

if [ "$RESTRICTIONS_PREFERRED" == "[]" ] || [ -z "$RESTRICTIONS_PREFERRED" ]; then
    NEW_VM_SIZE="$PREFERRED_SIZE"
    echo -e "${GREEN}✓ ${PREFERRED_SIZE} is available (V100 GPU)${NC}"
else
    # Try fallback size (NC4as_T4_v3)
    echo -e "${YELLOW}${PREFERRED_SIZE} requires quota. Checking ${FALLBACK_SIZE}...${NC}"
    RESTRICTIONS_FALLBACK=$(az vm list-skus --location "$CURRENT_LOCATION" --size "$FALLBACK_SIZE" --output json 2>/dev/null | jq -r '.[0].restrictions // []' 2>/dev/null || echo '[]')
    
    if [ "$RESTRICTIONS_FALLBACK" == "[]" ] || [ -z "$RESTRICTIONS_FALLBACK" ]; then
        NEW_VM_SIZE="$FALLBACK_SIZE"
        echo -e "${GREEN}✓ ${FALLBACK_SIZE} is available (T4 GPU - good performance, no quota needed)${NC}"
        echo -e "${YELLOW}Note: T4 is smaller than V100 but still provides GPU acceleration${NC}"
    else
        echo -e "${RED}Neither GPU VM size is available. Quota required.${NC}"
        echo -e "${YELLOW}Run: ./request-gpu-quota.sh to request quota${NC}"
        exit 1
    fi
fi

# Stop the VM
echo -e "${YELLOW}Stopping VM...${NC}"
az vm deallocate --resource-group "$RESOURCE_GROUP" --name "$VM_NAME"

# Resize the VM
echo -e "${YELLOW}Resizing VM to ${NEW_VM_SIZE}...${NC}"
az vm resize --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --size "$NEW_VM_SIZE"

# If region changed, we'd need to recreate, but let's try resize first
if [ "$CURRENT_LOCATION" != "$AVAILABLE_REGION" ]; then
    echo -e "${YELLOW}Note: GPU is available in ${AVAILABLE_REGION} but VM is in ${CURRENT_LOCATION}${NC}"
    echo -e "${YELLOW}Resize will attempt in current location first...${NC}"
fi

# Start the VM
echo -e "${YELLOW}Starting VM...${NC}"
az vm start --resource-group "$RESOURCE_GROUP" --name "$VM_NAME"

# Get VM IP
VM_IP=$(az vm show -d --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --query publicIps -o tsv)
echo -e "${GREEN}VM is now running at ${VM_IP}${NC}"

# Wait for VM to be ready
echo -e "${YELLOW}Waiting for VM to be ready...${NC}"
sleep 30

# SSH key path
SSH_KEY_PATH="$HOME/.ssh/wocconwaker_azure_key"
ADMIN_USERNAME="woccon"

# Install NVIDIA drivers and CUDA
echo -e "${YELLOW}Installing NVIDIA drivers and CUDA...${NC}"
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no $ADMIN_USERNAME@$VM_IP << 'ENDSSH'
set -e

# Update system
sudo apt-get update

# Install NVIDIA drivers (Ubuntu 22.04)
sudo apt-get install -y nvidia-driver-535 nvidia-utils-535

# Install CUDA toolkit (for Ollama GPU support)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update
sudo apt-get install -y cuda-toolkit-12-3

# Add CUDA to PATH
echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# Reboot to load drivers
echo "NVIDIA drivers installed. VM will reboot in 60 seconds..."
sudo shutdown -r +1
ENDSSH

echo -e "${GREEN}GPU drivers installation initiated. VM will reboot.${NC}"
echo -e "${YELLOW}After reboot, verify GPU with: nvidia-smi${NC}"
echo -e "${YELLOW}Then restart Ollama service - it should automatically use GPU.${NC}"

echo -e "${GREEN}Migration to GPU complete!${NC}"
echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. Wait for VM to reboot (~2 minutes)"
echo -e "  2. SSH in and run: nvidia-smi (to verify GPU)"
echo -e "  3. Restart Ollama: sudo systemctl restart ollama"
echo -e "  4. Restart WocconWaker: sudo systemctl restart wocconwaker"

