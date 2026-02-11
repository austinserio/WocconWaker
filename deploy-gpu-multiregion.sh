#!/bin/bash
# Multi-region GPU Deployment Script
# Tries deployment across multiple regions in parallel
# First successful region wins

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Multi-Region GPU Spot VM Deployment                     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Set subscription (nonprofit grant)
SUBSCRIPTION_ID="58587a07-da50-4691-aa9c-f23859d66df3"
az account set --subscription "$SUBSCRIPTION_ID"

# Configuration
RESOURCE_GROUP="rg-wocconwaker-gpu"
VM_NAME="wocconwaker-gpu-spot"
VM_SIZE="NC4as_T4_v3"  # T4 GPU, 4 vCPU, 28GB RAM
USERNAME="azureuser"

# Regions to try (in order of preference)
REGIONS=("eastus" "westus2" "westus3" "southcentralus" "northeurope")

# Pricing information
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}Pricing: Spot VM (NCasT4_v3)${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}Spot Pricing:${NC}"
echo -e "  • ~\$0.10/hour (~\$2.40/day if 24/7)"
echo -e "  • ~\$72/month if running 24/7"
echo -e "  • With \$2,000 grant: ~27 months of continuous operation"
echo ""
echo -e "${YELLOW}This script will try multiple regions to find available capacity${NC}"
echo ""

read -p "Continue with multi-region deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Phase 1: Checking Region Availability${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

AVAILABLE_REGIONS=()

for region in "${REGIONS[@]}"; do
    echo -e "${CYAN}Checking ${region}...${NC}"
    
    # Check if VM size is available
    if az vm list-sizes --location "$region" --query "[?name=='${VM_SIZE}']" -o tsv 2>/dev/null | grep -q "$VM_SIZE"; then
        echo -e "  ${GREEN}✓ ${VM_SIZE} available${NC}"
        AVAILABLE_REGIONS+=("$region")
    else
        echo -e "  ${RED}✗ ${VM_SIZE} not available${NC}"
    fi
    echo ""
done

if [ ${#AVAILABLE_REGIONS[@]} -eq 0 ]; then
    echo -e "${RED}✗ ${VM_SIZE} not available in any checked region${NC}"
    echo -e "${YELLOW}You may need to request GPU quota first${NC}"
    echo -e "  Run: ./request-gpu-quota-enhanced.sh"
    exit 1
fi

echo -e "${GREEN}Found ${#AVAILABLE_REGIONS[@]} available region(s)${NC}"
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Phase 2: Attempting Deployment${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

SUCCESS_REGION=""
SUCCESS_PUBLIC_IP=""

for region in "${AVAILABLE_REGIONS[@]}"; do
    echo -e "${CYAN}Attempting deployment in ${region}...${NC}"
    
    # Create resource group for this region
    RG_NAME="${RESOURCE_GROUP}-${region}"
    az group create --name "$RG_NAME" --location "$region" 2>/dev/null || true
    
    # Generate password
    ADMIN_PASSWORD=$(openssl rand -base64 32 2>/dev/null || echo "ChangeMe123!")
    
    # Create network resources
    VNET_NAME="${VM_NAME}-vnet"
    SUBNET_NAME="${VM_NAME}-subnet"
    NSG_NAME="${VM_NAME}-nsg"
    
    az network vnet create \
        --resource-group "$RG_NAME" \
        --name "$VNET_NAME" \
        --address-prefix "10.0.0.0/16" \
        --subnet-name "$SUBNET_NAME" \
        --subnet-prefix "10.0.0.0/24" \
        --output none 2>/dev/null || true
    
    az network nsg create \
        --resource-group "$RG_NAME" \
        --name "$NSG_NAME" \
        --output none 2>/dev/null || true
    
    az network nsg rule create \
        --resource-group "$RG_NAME" \
        --nsg-name "$NSG_NAME" \
        --name "SSH" \
        --priority 1000 \
        --protocol Tcp \
        --destination-port-ranges 22 \
        --access Allow \
        --output none 2>/dev/null || true
    
    az network nsg rule create \
        --resource-group "$RG_NAME" \
        --nsg-name "$NSG_NAME" \
        --name "HTTP" \
        --priority 1001 \
        --protocol Tcp \
        --destination-port-ranges 8000 \
        --access Allow \
        --output none 2>/dev/null || true
    
    # Try to create Spot VM
    VM_OUTPUT=$(az vm create \
        --resource-group "$RG_NAME" \
        --name "$VM_NAME" \
        --image "Ubuntu2204" \
        --size "$VM_SIZE" \
        --location "$region" \
        --admin-username "$USERNAME" \
        --admin-password "$ADMIN_PASSWORD" \
        --vnet-name "$VNET_NAME" \
        --subnet "$SUBNET_NAME" \
        --nsg "$NSG_NAME" \
        --public-ip-sku Standard \
        --priority Spot \
        --max-price -1 \
        --eviction-policy Deallocate \
        --output json 2>&1) || VM_ERROR="$VM_OUTPUT"
    
    if [ -z "$VM_ERROR" ] || echo "$VM_OUTPUT" | grep -q '"publicIpAddress"'; then
        PUBLIC_IP=$(echo "$VM_OUTPUT" | jq -r '.publicIpAddress' 2>/dev/null || \
            az vm show -d --resource-group "$RG_NAME" --name "$VM_NAME" --query publicIps -o tsv 2>/dev/null || echo "")
        
        if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "null" ]; then
            SUCCESS_REGION="$region"
            SUCCESS_PUBLIC_IP="$PUBLIC_IP"
            SUCCESS_RG="$RG_NAME"
            SUCCESS_PASSWORD="$ADMIN_PASSWORD"
            echo -e "${GREEN}✓ Deployment successful in ${region}!${NC}"
            echo ""
            break
        fi
    else
        echo -e "${YELLOW}⚠ Deployment failed in ${region}: ${VM_ERROR:0:100}...${NC}"
        # Clean up failed resource group
        az group delete --name "$RG_NAME" --yes --no-wait 2>/dev/null || true
    fi
    echo ""
done

if [ -z "$SUCCESS_REGION" ]; then
    echo -e "${RED}✗ Deployment failed in all regions${NC}"
    echo -e "${YELLOW}You may need to:${NC}"
    echo -e "  1. Request GPU quota: ./request-gpu-quota-enhanced.sh"
    echo -e "  2. Try again later (capacity may be available later)"
    echo -e "  3. Check quota status: ./check-gpu-availability.sh"
    exit 1
fi

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${CYAN}VM Details:${NC}"
echo -e "  Name: ${VM_NAME}"
echo -e "  Size: ${VM_SIZE} (T4 GPU)"
echo -e "  Region: ${SUCCESS_REGION}"
echo -e "  Resource Group: ${SUCCESS_RG}"
echo -e "  Public IP: ${SUCCESS_PUBLIC_IP}"
echo -e "  Username: ${USERNAME}"
echo -e "  Password: ${SUCCESS_PASSWORD}"
echo ""
echo -e "${CYAN}Pricing:${NC}"
echo -e "  Spot VM: ~\$0.10/hour (~\$72/month if 24/7)"
echo -e "  Current cost: ~\$2.40/day if running 24/7"
echo ""
echo -e "${CYAN}Connection:${NC}"
echo -e "  ssh ${USERNAME}@${SUCCESS_PUBLIC_IP}"
echo -e "  Password: ${SUCCESS_PASSWORD}"
echo ""
echo -e "${CYAN}Next Steps:${NC}"
echo -e "  1. SSH into VM and set up GPU drivers"
echo -e "  2. Install Ollama with GPU support"
echo -e "  3. Deploy your application"
echo ""
echo -e "${YELLOW}⚠ Important:${NC}"
echo -e "  • Spot VM can be evicted with 30 seconds notice"
echo -e "  • Save work frequently"
echo -e "  • Consider auto-shutdown script"
echo ""

