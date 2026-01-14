# How to Navigate to Quota Requests (Step-by-Step)

You're currently on the billing page. Here's how to get to the quota request page:

## Method 1: Direct Navigation (Easiest)

1. **In the Azure Portal top search bar, type:** `subscriptions`
2. **Click on "Subscriptions"** (the service, not billing subscriptions)
3. **Click on your subscription name:** "Azure subscription 1"
4. **In the left sidebar**, scroll down and click **"Usage + quotas"**
5. **Search for:** `NCASv3_T4` or `NC`
6. **Click "Request quota increase"** on "Standard NCASv3_T4 Family vCPUs"

## Method 2: Direct URL

Try this direct link (should take you straight to Usage + Quotas):

```
https://portal.azure.com/#view/SubscriptionsBlade
```

Then:
1. Click on "Azure subscription 1"
2. In left sidebar → "Usage + quotas"
3. Search for "NCASv3_T4"
4. Click "Request quota increase"

## Method 3: Via Support Request (Alternative)

If you can't find "Usage + quotas", use Support:

1. In Azure Portal search bar, type: `support requests`
2. Click "Create a support request"
3. Fill in:
   - Problem type: **Service and subscription limits (quotas)**
   - Subscription: **Azure subscription 1**
   - Quota type: **Compute-VM (cores-vCPUs) subscription limit increases**
4. Details:
   - Region: **westus2**
   - Quota: **Standard NCASv3_T4 Family**
   - New limit: **4**

## Visual Guide

The key difference:
- ❌ You're on: **Billing** → Subscription overview (billing page)
- ✅ You need: **Subscriptions** → "Azure subscription 1" → Usage + quotas (resource page)







