#!/bin/bash
# Alternative methods to request GPU quota when NCASv3_T4 isn't showing in support portal

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Alternative GPU Quota Request Methods                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Set subscription
WOCCON_SUBSCRIPTION="2fef1120-5b1e-4224-9b93-091eb5d5424e"
az account set --subscription "$WOCCON_SUBSCRIPTION"
SUB_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)

echo -e "${YELLOW}NCASv3_T4 Family IS available in West US 2, but may not show${NC}"
echo -e "${YELLOW}in the standard support portal dropdown. Try these methods:${NC}"
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Method 1: Direct Usage + Quotas Page (RECOMMENDED)${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}This bypasses the support portal and goes directly to quotas:${NC}"
echo ""
USAGE_QUOTA_URL="https://portal.azure.com/#@${TENANT_ID}/resource/subscriptions/${SUB_ID}/providers/Microsoft.Compute/locations/westus2/usages"
echo "$USAGE_QUOTA_URL"
echo ""
echo "Steps:"
echo "  1. Open the URL above"
echo "  2. Find 'Standard NCASv3_T4 Family' in the list"
echo "  3. Click 'Request quota increase' button"
echo "  4. Enter New limit: 4"
echo "  5. Submit"
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Method 2: Support Request with Manual Description${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo "If Method 1 doesn't work, use Support Request but describe it manually:"
echo ""
echo "1. Go to: https://portal.azure.com/#view/Microsoft_Azure_Support/HelpAndSupportBlade/~/overview"
echo "2. Click 'Create a support request'"
echo "3. Fill in:"
echo "   - Problem type: Service and subscription limits (quotas)"
echo "   - Subscription: Azure subscription 1"
echo "   - Quota type: Compute-VM (cores-vCPUs) subscription limit increases"
echo "   - (If NCASv3_T4 isn't in dropdown, select ANY GPU option or 'Other')"
echo ""
echo "4. In the Details/Description field, write:"
echo -e "${GREEN}   'Requesting quota increase for Standard NCASv3_T4 Family${NC}"
echo -e "${GREEN}   vCPUs in West US 2 region.${NC}"
echo -e "${GREEN}   ${NC}"
echo -e "${GREEN}   Subscription ID: ${SUB_ID}${NC}"
echo -e "${GREEN}   Region: westus2${NC}"
echo -e "${GREEN}   Quota Type: Standard NCASv3_T4 Family${NC}"
echo -e "${GREEN}   Current Limit: 0${NC}"
echo -e "${GREEN}   Requested Limit: 4 vCPUs${NC}"
echo -e "${GREEN}   ${NC}"
echo -e "${GREEN}   This quota is needed to deploy Standard_NC4as_T4_v3 VM${NC}"
echo -e "${GREEN}   for GPU-accelerated workloads.'${NC}"
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Method 3: Alternative GPU Option (NC6s_v3)${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo "If NCASv3_T4 still doesn't work, try requesting 'Standard NC Family vCPUs':"
echo "  - This covers NC6s_v3 (V100 GPU - better performance)"
echo "  - Request: 6 vCPUs"
echo "  - Region: westus2"
echo "  - Cost: ~$0.90/hour (vs $0.50/hour for T4)"
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Method 4: Direct Quota Request URL${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
QUOTA_REQUEST_URL="https://aka.ms/ProdportalCRP/#blade/Microsoft_Azure_Capacity/UsageAndQuota.ReactView/Parameters/%7B%22subscriptionId%22:%22${SUB_ID}%22,%22command%22:%22openQuotaApprovalBlade%22,%22quotas%22:[%7B%22location%22:%22westus2%22,%22providerId%22:%22Microsoft.Compute%22,%22resourceName%22:%22Standard%20NCASv3_T4%20Family%22,%22quotaRequest%22:%7B%22properties%22:%7B%22limit%22:4,%22unit%22:%22Count%22,%22name%22:%7B%22value%22:%22Standard%20NCASv3_T4%20Family%22%7D%7D%7D%7D]%7D"
echo "$QUOTA_REQUEST_URL"
echo ""
echo "This URL should pre-fill the quota request form."
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Why NCASv3_T4 Might Not Show in Dropdown${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Possible reasons:"
echo "  1. GPU quotas sometimes require paid support plan"
echo "  2. Dropdown may not include all GPU families"
echo "  3. Portal UI may filter out zero-quota options"
echo ""
echo "Solution: Use Method 1 (direct Usage + Quotas page) or Method 2"
echo "         (support request with manual description)"
echo ""

echo -e "${GREEN}Opening Method 1 (Direct Usage + Quotas)...${NC}"
if command -v open &> /dev/null; then
    open "$USAGE_QUOTA_URL"
elif command -v xdg-open &> /dev/null; then
    xdg-open "$USAGE_QUOTA_URL"
else
    echo "Please open: $USAGE_QUOTA_URL"
fi

echo ""

