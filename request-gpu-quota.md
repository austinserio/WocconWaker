# Request GPU Quota for Azure Subscription

Your subscription needs GPU quota to use NC6s_v3 VMs. Here's how to request it:

## Option 1: Azure Portal (Recommended)

1. Go to https://portal.azure.com
2. Navigate to **Subscriptions** → Your subscription → **Usage + quotas**
3. Search for "NC" or "GPU" 
4. Find "Standard NC Family vCPUs" or "NCv3 Series"
5. Click **Request quota increase**
6. Select region: **eastus** or **westus2**
7. Enter requested quota: **6 vCPUs** (for NC6s_v3)
8. Submit request

## Option 2: Azure CLI

```bash
# Check current quota
az vm list-usage --location eastus --output table | grep -i "nc\|gpu"

# Request quota increase (requires support ticket)
az support tickets create \
  --ticket-type "Technical" \
  --title "Request GPU VM Quota Increase" \
  --description "Requesting quota for Standard_NC6s_v3 VMs for AI/ML workload" \
  --problem-classification "/providers/Microsoft.Support/services/quota_service_guid/problemTypes/nc_problem_type_guid" \
  --severity "minimal"
```

## Option 3: Try Alternative GPU VM Sizes

If NC6s_v3 is not available, try:
- **Standard_NV6ads_A10_v5** (A10 GPU, newer, may have better availability)
- **Standard_NC4as_T4_v3** (T4 GPU, smaller but cheaper)

## After Quota Approval

Once quota is approved (usually 1-2 business days), run:
```bash
./migrate-to-gpu.sh
```

