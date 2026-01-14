#!/bin/bash
# Simple script to show quota request instructions

TENANT_ID=$(az account show --query tenantId -o tsv)
SUB_ID=$(az account show --query id -o tsv)
SUB_NAME=$(az account show --query name -o tsv)

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     GPU Quota Request Instructions                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Why? GPU VMs are capacity-limited, so Azure requires explicit"
echo "     quota approval (even for admins) to manage allocation."
echo ""
echo "Subscription: $SUB_NAME"
echo ""
echo "════════════════════════════════════════════════════════════"
echo "STEP 1: Copy this URL and open in your browser:"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "https://portal.azure.com/#@${TENANT_ID}/resource/subscriptions/${SUB_ID}/providers/Microsoft.Compute/locations/westus2/usages"
echo ""
echo "════════════════════════════════════════════════════════════"
echo "STEP 2: On that page:"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "  1. Use the search/filter box, type: NCASv3_T4"
echo "  2. Find: 'Standard NCASv3_T4 Family vCPUs'"
echo "  3. Click: 'Request quota increase' button"
echo "  4. Enter: 4 (vCPUs)"
echo "  5. Region: westus2 (should be pre-selected)"
echo "  6. Click: 'Submit'"
echo ""
echo "════════════════════════════════════════════════════════════"
echo "After Approval (1-2 business days):"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "  Run: ./migrate-to-gpu.sh"
echo ""
echo "════════════════════════════════════════════════════════════"







