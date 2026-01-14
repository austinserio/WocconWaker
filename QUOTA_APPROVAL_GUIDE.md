# How to Check GPU Quota Approval Status

## Quick Check Methods

### Method 1: Azure Portal Quota Page (Easiest)

1. Go to: https://portal.azure.com/#view/Microsoft_Azure_Capacity/QuotaMenuBlade/~/overview
2. Set **Location:** `westus2`
3. Find **"Standard NCASv3_T4 Family vCPUs"**
4. Check the **"Current limit"** column:
   - **0** = Not approved yet ❌
   - **4 or higher** = Approved! ✅

**This is the fastest way to check!**

### Method 2: Support Requests

1. In Azure Portal, go to: **Help + Support** → **Support requests**
2. Find your quota request (should be the most recent one)
3. Check the status:
   - **"Open"** = Still being reviewed
   - **"Closed"** = Check details to see if approved or denied

### Method 3: Email Notification

Azure will send you an email when the quota is approved. Check your email inbox associated with your Azure account.

## Timeline

- **Typical:** 1-2 business days
- **Fastest:** 4-24 hours (sometimes)
- **Maximum:** Up to 5 business days

## After Approval

Once you see the quota limit is **4** (or higher), run:

```bash
./migrate-to-gpu.sh
```

This will automatically:
- Resize your VM to GPU (NC4as_T4_v3)
- Install NVIDIA drivers
- Install CUDA
- Configure Ollama to use GPU

## Quick Status Check Command

You can also run this script anytime:
```bash
./check-quota-status.sh
```

Or check manually via Azure CLI:
```bash
az vm list-usage --location westus2 --output table | grep "NCASv3_T4"
```

This will show:
- Current limit
- Current usage
- (Limit > 0 means approved!)







