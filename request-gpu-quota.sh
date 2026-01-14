#!/bin/bash
# Script to open Azure Portal for GPU quota request

echo "=========================================="
echo "GPU Quota Request for WocconWaker"
echo "=========================================="
echo ""
echo "Your subscription needs GPU quota to use GPU VMs."
echo ""
echo "Opening Azure Portal with quota request pre-filled..."
echo ""

# Get subscription ID
SUB_ID=$(az account show --query id -o tsv)
SUB_NAME=$(az account show --query name -o tsv)

echo "Subscription: $SUB_NAME ($SUB_ID)"
echo ""

# Direct quota request URL (from Azure error message format)
QUOTA_URL="https://aka.ms/ProdportalCRP/#blade/Microsoft_Azure_Capacity/UsageAndQuota.ReactView/Parameters/%7B%22subscriptionId%22:%22${SUB_ID}%22,%22command%22:%22openQuotaApprovalBlade%22,%22quotas%22:[%7B%22location%22:%22westus2%22,%22providerId%22:%22Microsoft.Compute%22,%22resourceName%22:%22Standard%20NCASv3_T4%20Family%22,%22quotaRequest%22:%7B%22properties%22:%7B%22limit%22:4,%22unit%22:%22Count%22,%22name%22:%7B%22value%22:%22Standard%20NCASv3_T4%20Family%22%7D%7D%7D%7D]%7D"

echo "Opening browser..."
if command -v open &> /dev/null; then
    open "$QUOTA_URL"
elif command -v xdg-open &> /dev/null; then
    xdg-open "$QUOTA_URL"
else
    echo "Please open this URL in your browser:"
    echo "$QUOTA_URL"
fi

echo ""
echo "On the quota request page:"
echo "1. Review the pre-filled request (Standard NCASv3_T4 Family, 4 cores, westus2)"
echo "2. Click 'Request quota increase' or 'Submit'"
echo "3. Wait for approval (typically 1-2 business days)"
echo ""
echo "Alternative: Request NC6s_v3 (V100 GPU) quota:"
echo "  - Quota type: Standard NC Family vCPUs"
echo "  - Request: 6 vCPUs"
echo "  - Region: westus2"
