# GPU Quota Request Guide

## Why Quota is Needed (Even as Admin)

Even as an admin, Azure requires explicit quota requests for GPU VMs because:
- GPU hardware is capacity-constrained (limited supply)
- Azure manages GPU allocation to ensure availability
- This prevents accidental over-allocation

## What to Request

You need to request quota for one of these:

**Option 1: Standard NCASv3_T4 Family** (T4 GPU - Good performance)
- Request: **4 vCPUs** (for NC4as_T4_v3 VM)
- Region: **westus2**
- Approx cost: ~$0.50/hour

**Option 2: Standard NC Family vCPUs** (V100 GPU - Better performance)
- Request: **6 vCPUs** (for NC6s_v3 VM)  
- Region: **westus2**
- Approx cost: ~$0.90/hour

## How to Request Quota (Manual Steps)

### Method 1: Azure Portal (Direct Link)

1. **Go directly to Usage + Quotas:**
   - Open: https://portal.azure.com
   - Search for "Subscriptions" in the top search bar
   - Click on your subscription ("Azure subscription 1")
   - In the left menu, click **"Usage + quotas"**
   - Filter/search for: **"NC"** or **"GPU"**

2. **Request Increase:**
   - Find: **"Standard NCASv3_T4 Family"** or **"Standard NC Family vCPUs"**
   - Click **"Request quota increase"**
   - Select Region: **westus2**
   - Enter New limit: **4** (for T4) or **6** (for V100)
   - Click **"Submit"**

### Method 2: Azure Portal Support Request

1. Go to: https://portal.azure.com/#view/Microsoft_Azure_Support/HelpAndSupportBlade/~/overview
2. Click **"Create a support request"**
3. Fill in:
   - Issue type: **Service and subscription limits (quotas)**
   - Subscription: **Azure subscription 1**
   - Quota type: **Compute-VM (cores-vCPUs) subscription limit increases**
4. In the Details tab:
   - Select Region: **westus2**
   - Select Quota: **Standard NCASv3_T4 Family** (or **Standard NC Family vCPUs**)
   - Enter New limit: **4** (or **6** for V100)
5. Submit the request

### Method 3: Direct URL (Copy-Paste)

Try this direct URL to Usage + Quotas:
```
https://portal.azure.com/#@$(az account show --query tenantId -o tsv)/resource/subscriptions/$(az account show --query id -o tsv)/providers/Microsoft.Compute/locations/westus2/usages
```

## After Approval

Once quota is approved (1-2 business days), run:
```bash
./migrate-to-gpu.sh
```

The script will automatically resize your VM and install GPU drivers.







