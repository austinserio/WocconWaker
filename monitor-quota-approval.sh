#!/bin/bash
# Monitor GPU Quota Approval Status
# Checks quota status and notifies when approved

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
echo -e "${BLUE}║   GPU Quota Approval Status Monitor                        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Set subscription (nonprofit grant)
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID in .env (see .env.example)}"
az account set --subscription "$SUBSCRIPTION_ID"

SUB_NAME=$(az account show --query name -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)

echo -e "${CYAN}Subscription: ${SUB_NAME}${NC}"
echo ""

# Regions to check
REGIONS=("eastus" "westus2" "westus3")

# GPU families to check
declare -A GPU_FAMILIES
GPU_FAMILIES["NCasT4_v3"]="Standard NCASv3_T4 Family"
GPU_FAMILIES["NC6s_v3"]="Standard NC Family"

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Current Quota Status${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

APPROVED=()
PENDING=()

for gpu_key in "${!GPU_FAMILIES[@]}"; do
    family_name="${GPU_FAMILIES[$gpu_key]}"
    echo -e "${CYAN}Checking: ${family_name}${NC}"
    
    for region in "${REGIONS[@]}"; do
        QUOTA_INFO=$(az vm list-usage \
            --location "$region" \
            --query "[?name.value=='${family_name}'].{current:currentValue, limit:limit}" \
            -o tsv 2>/dev/null || echo "")
        
        if [ -n "$QUOTA_INFO" ]; then
            CURRENT=$(echo "$QUOTA_INFO" | awk '{print $1}')
            LIMIT=$(echo "$QUOTA_INFO" | awk '{print $2}')
            
            if [ "$LIMIT" -gt 0 ] 2>/dev/null && [ "$LIMIT" != "0" ]; then
                echo -e "  ${GREEN}✓ ${region}: ${CURRENT}/${LIMIT} cores (APPROVED)${NC}"
                APPROVED+=("${region}:${gpu_key}")
            else
                echo -e "  ${YELLOW}⚠ ${region}: ${CURRENT}/${LIMIT} cores (PENDING)${NC}"
                PENDING+=("${region}:${gpu_key}")
            fi
        else
            echo -e "  ${YELLOW}⚠ ${region}: Unable to retrieve quota${NC}"
            PENDING+=("${region}:${gpu_key}")
        fi
    done
    echo ""
done

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Summary${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

if [ ${#APPROVED[@]} -gt 0 ]; then
    echo -e "${GREEN}✓ GPU Quota APPROVED! You can deploy now.${NC}"
    echo ""
    echo -e "${CYAN}Next Steps:${NC}"
    echo -e "  1. Deploy Spot VM: ./deploy-gpu-spot-vm.sh"
    echo -e "  2. Or deploy Serverless GPU: ./deploy-container-app-gpu.sh"
    echo ""
    echo -e "${CYAN}Pricing Reminder:${NC}"
    echo -e "  • Spot VM: ~\$0.10/hour (~\$72/month if 24/7)"
    echo -e "  • Serverless GPU: ~\$0.36/hour when active (~\$0 when idle)"
    echo ""
else
    echo -e "${YELLOW}⚠ Quota still pending approval${NC}"
    echo ""
    echo -e "${CYAN}Current Status:${NC}"
    echo -e "  • Quota requests are typically approved within 1-2 business days"
    echo -e "  • Nonprofit grants may take slightly longer"
    echo ""
    echo -e "${CYAN}Actions:${NC}"
    echo -e "  1. Check support request status:"
    echo -e "     https://portal.azure.com/#view/Microsoft_Azure_Support/HelpAndSupportBlade/~/overview"
    echo -e "  2. If more than 2 business days, escalate:"
    echo -e "     Open new support ticket with 'Urgent' severity"
    echo -e "  3. Check quota page directly:"
    for region in "${REGIONS[@]}"; do
        echo -e "     https://portal.azure.com/#@${TENANT_ID}/resource/subscriptions/${SUBSCRIPTION_ID}/providers/Microsoft.Compute/locations/${region}/usages"
    done
    echo ""
fi

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Monitoring Options${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${CYAN}Continuous Monitoring:${NC}"
echo -e "  Run this script periodically: ./monitor-quota-approval.sh"
echo ""
echo -e "${CYAN}Email Notifications:${NC}"
echo -e "  Azure will send email when quota is approved"
echo -e "  Check: ${SUB_NAME} notification settings"
echo ""

