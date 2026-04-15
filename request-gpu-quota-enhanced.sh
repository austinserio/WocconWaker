#!/bin/bash
# Enhanced GPU Quota Request Script with Nonprofit Context
# Requests quota for multiple GPU families and regions simultaneously

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
echo -e "${BLUE}║   Enhanced GPU Quota Request (Nonprofit Grant)             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID in .env (see .env.example)}"
echo -e "${GREEN}Setting subscription to: ${SUBSCRIPTION_ID}${NC}"
az account set --subscription "$SUBSCRIPTION_ID"

SUB_ID=$(az account show --query id -o tsv)
SUB_NAME=$(az account show --query name -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)

echo -e "${CYAN}Subscription: ${SUB_NAME}${NC}"
echo -e "${CYAN}Subscription ID: ${SUB_ID}${NC}"
echo -e "${CYAN}Tenant ID: ${TENANT_ID}${NC}"
echo ""

# Pricing context
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Pricing Context for Quota Request${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}Requesting quota for these GPU options:${NC}"
echo ""
echo -e "${CYAN}1. NCasT4_v3 (T4 GPU) - Recommended${NC}"
echo -e "   • Standard: ~\$0.35/hour (~\$252/month if 24/7)"
echo -e "   • Spot: ~\$0.10/hour (~\$72/month if 24/7)"
echo -e "   • Requesting: 4 cores"
echo ""
echo -e "${CYAN}2. Container Apps Serverless GPU (T4)${NC}"
echo -e "   • ~\$0.36/hour when active (~\$0 when idle)"
echo -e "   • Best for intermittent workloads"
echo ""
echo -e "${CYAN}Budget Impact:${NC}"
echo -e "   • With \$2,000 grant, you can run:"
echo -e "   • Spot VM 24/7: ~27 months"
echo -e "   • Serverless GPU (8 hrs/day): ~694 days"
echo ""

read -p "Continue with quota request? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Quota request cancelled."
    exit 0
fi

# Regions to request
REGIONS=("eastus" "westus2" "westus3")

# GPU families to request (with cores)
declare -A GPU_REQUESTS
GPU_REQUESTS["Standard NCASv3_T4 Family"]="4"
GPU_REQUESTS["Standard NC Family"]="6"

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Opening Quota Request Portal${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

# Build quota request URL (for first region and GPU family)
PRIMARY_REGION="westus2"
PRIMARY_GPU="Standard NCASv3_T4 Family"
PRIMARY_CORES="4"

QUOTA_URL="https://aka.ms/ProdportalCRP/#blade/Microsoft_Azure_Capacity/UsageAndQuota.ReactView/Parameters/%7B%22subscriptionId%22:%22${SUB_ID}%22,%22command%22:%22openQuotaApprovalBlade%22,%22quotas%22:[%7B%22location%22:%22${PRIMARY_REGION}%22,%22providerId%22:%22Microsoft.Compute%22,%22resourceName%22:%22${PRIMARY_GPU}%22,%22quotaRequest%22:%7B%22properties%22:%7B%22limit%22:${PRIMARY_CORES},%22unit%22:%22Count%22,%22name%22:%7B%22value%22:%22${PRIMARY_GPU}%22%7D%7D%7D%7D]%7D"

echo -e "${CYAN}Step 1: Requesting primary GPU quota${NC}"
echo -e "${YELLOW}Opening Azure Portal...${NC}"
echo ""

if command -v open &> /dev/null; then
    open "$QUOTA_URL"
elif command -v xdg-open &> /dev/null; then
    xdg-open "$QUOTA_URL"
else
    echo -e "${YELLOW}Please open this URL in your browser:${NC}"
    echo "$QUOTA_URL"
fi

echo ""
echo -e "${CYAN}Step 2: Quota Request Details${NC}"
echo -e "${YELLOW}Fill out the quota request form with:${NC}"
echo ""
echo -e "${GREEN}Required Information:${NC}"
echo -e "  • Problem type: Service and subscription limits (quotas)"
echo -e "  • Subscription: ${SUB_NAME}"
echo -e "  • Quota type: Compute-VM (cores-vCPUs) subscription limit increases"
echo -e "  • SKU family: Standard NCASv3_T4 Family"
echo -e "  • Region: ${PRIMARY_REGION} (and other regions)"
echo -e "  • New limit: 4 cores"
echo ""
echo -e "${GREEN}Justification (for nonprofit grant):${NC}"
echo -e "  Use this template for 'Details' field:"
echo ""
cat << 'JUSTIFICATION_EOF'
We are requesting GPU quota for a nonprofit language preservation project (WocconWaker) 
focused on preserving and teaching the Woccon language (extinct Eastern Siouan language).

Project Details:
- Nonprofit organization with $2,000 Azure grant
- Using Ollama LLM (llama3:8b) for language analysis and education
- GPU acceleration needed for faster inference (currently using CPU-only)

Request Details:
- GPU Family: NCasT4_v3 (T4 GPU) - cost-effective for our use case
- Cores Requested: 4 cores (single VM or serverless GPU)
- Regions: eastus, westus2, westus3 (for availability flexibility)

Cost Impact:
- Using Spot pricing: ~$0.10/hour (~$72/month) - well within grant budget
- Or serverless GPU: pay-per-use, scales to zero when idle

Use Case:
- Language learning application with conversational AI
- Educational tool for teaching extinct Woccon language
- Supports nonprofit educational mission

Thank you for considering this request.
JUSTIFICATION_EOF

echo ""
echo ""

echo -e "${CYAN}Step 3: Additional Quota Requests${NC}"
echo -e "${YELLOW}After submitting the first request, request quotas for:${NC}"
echo ""

for gpu_family in "${!GPU_REQUESTS[@]}"; do
    cores="${GPU_REQUESTS[$gpu_family]}"
    echo -e "${CYAN}${gpu_family}${NC}"
    for region in "${REGIONS[@]}"; do
        if [ "$region" != "$PRIMARY_REGION" ] || [ "$gpu_family" != "$PRIMARY_GPU" ]; then
            echo -e "  • Region: ${region}, Cores: ${cores}"
        fi
    done
done

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Escalation Path (if request is delayed)${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}If quota request is not approved within 2 business days:${NC}"
echo ""
echo -e "${GREEN}1. Open Support Request:${NC}"
echo -e "   https://portal.azure.com/#view/Microsoft_Azure_Support/HelpAndSupportBlade/~/overview"
echo ""
echo -e "${GREEN}2. Create New Support Request:${NC}"
echo -e "   • Issue type: Service and subscription limits (quotas)"
echo -e "   • Subscription: ${SUB_NAME}"
echo -e "   • Quota type: Compute-VM (cores-vCPUs) subscription limit increases"
echo -e "   • Severity: C - Moderate impact"
echo -e "   • Title: 'Urgent: GPU Quota Request for Nonprofit Language Preservation Project'"
echo ""
echo -e "${GREEN}3. In description, emphasize:${NC}"
echo -e "   • Nonprofit grant recipient"
echo -e "   • Educational/language preservation mission"
echo -e "   • Small quota request (4 cores)"
echo -e "   • Cost-effective usage pattern (Spot or serverless)"
echo ""
echo -e "${GREEN}4. Check Quota Status:${NC}"
echo -e "   Run: ./monitor-quota-approval.sh"
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Direct Links${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${CYAN}Quota Status Page:${NC}"
echo -e "  https://portal.azure.com/#@${TENANT_ID}/resource/subscriptions/${SUB_ID}/providers/Microsoft.Compute/locations/${PRIMARY_REGION}/usages"
echo ""
echo -e "${CYAN}Support Requests:${NC}"
echo -e "  https://portal.azure.com/#view/Microsoft_Azure_Support/HelpAndSupportBlade/~/overview"
echo ""
echo -e "${CYAN}Pricing Calculator:${NC}"
echo -e "  https://azure.microsoft.com/pricing/details/virtual-machines/linux/"
echo ""

echo -e "${GREEN}✓ Quota request portal opened${NC}"
echo -e "${YELLOW}Please complete the form and submit your request${NC}"
echo ""

