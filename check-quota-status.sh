#!/bin/bash
# Script to check GPU quota request status

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     Checking GPU Quota Request Status                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

SUB_ID=$(az account show --query id -o tsv)
SUB_NAME=$(az account show --query name -o tsv)

echo "Subscription: $SUB_NAME"
echo ""
echo "════════════════════════════════════════════════════════════"
echo "Method 1: Check in Azure Portal"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "1. Go back to the quota page:"
echo "   https://portal.azure.com/#view/Microsoft_Azure_Capacity/QuotaMenuBlade/~/overview"
echo ""
echo "2. Set Location: westus2"
echo ""
echo "3. Find 'Standard NCASv3_T4 Family vCPUs'"
echo ""
echo "4. Check the 'Current limit' column:"
echo "   - Still 0 = Not approved yet"
echo "   - Shows 4 (or higher) = Approved! ✅"
echo ""
echo "════════════════════════════════════════════════════════════"
echo "Method 2: Check Support Requests"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "1. Go to: Help + Support → Support requests"
echo ""
echo "2. Look for your quota request"
echo "   Status will show:"
echo "   - 'Open' = Still being reviewed"
echo "   - 'Closed' = Approved or Denied (check details)"
echo ""
echo "════════════════════════════════════════════════════════════"
echo "Method 3: Try the Migration Script"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Once approved, run:"
echo "  ./migrate-to-gpu.sh"
echo ""
echo "If quota is approved, it will proceed. If not, you'll get"
echo "an error saying quota is still 0."
echo ""
echo "════════════════════════════════════════════════════════════"
echo "Timeline"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Typical approval time: 1-2 business days"
echo "Sometimes faster: 4-24 hours"
echo "You'll also get an email when it's approved"
echo ""







