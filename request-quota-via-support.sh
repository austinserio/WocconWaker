#!/bin/bash
# Alternative method: Request quota via Support Request

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  Alternative: Request GPU Quota via Support Request       ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "If you can't find 'Usage + quotas', use Support Request instead:"
echo ""
echo "STEP 1: Open this URL:"
echo "https://portal.azure.com/#view/Microsoft_Azure_Support/HelpAndSupportBlade/~/overview"
echo ""
echo "STEP 2: Click 'Create a support request'"
echo ""
echo "STEP 3: Fill in the form:"
echo "  - Problem type: Service and subscription limits (quotas)"
echo "  - Subscription: Azure subscription 1"
echo "  - Quota type: Compute-VM (cores-vCPUs) subscription limit increases"
echo ""
echo "STEP 4: In the Details tab:"
echo "  - Region: westus2"
echo "  - Quota: Standard NCASv3_T4 Family"
echo "  - New limit: 4 vCPUs"
echo ""
echo "STEP 5: Submit the request"
echo ""
read -p "Open Support Request page? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    open "https://portal.azure.com/#view/Microsoft_Azure_Support/HelpAndSupportBlade/~/overview" 2>/dev/null || \
    xdg-open "https://portal.azure.com/#view/Microsoft_Azure_Support/HelpAndSupportBlade/~/overview" 2>/dev/null || \
    echo "Please open: https://portal.azure.com/#view/Microsoft_Azure_Support/HelpAndSupportBlade/~/overview"
fi







