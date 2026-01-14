# Help: Finding GPU Quota on Quota Page

You're on the right page! Here's how to find the GPU quota:

## Step-by-Step on the Quota Page

1. **Set Filters First:**
   - **Location/Region:** Select `westus2` from the dropdown
   - **Subscription:** Make sure "Azure subscription 1" is selected
   - **Provider:** Should be "Microsoft.Compute"
   - Click **"Apply"** or **"Search"** to filter

2. **Clear any existing search**, then scroll through the list

3. **Look for these in the list:**
   - `Standard NCASv3_T4 Family vCPUs`
   - `Standard NC Family vCPUs` (for V100 GPU)
   - Anything starting with `NC` or `NCAS`

4. **Try Different Search Terms:**
   - `NC` (most general - should show all NC family quotas)
   - `T4`
   - `NCAS`
   - `GPU`

5. **If you find it:**
   - Click the row or the **"Request quota increase"** button
   - Enter: **4** vCPUs
   - Region: **westus2**
   - Submit

## If You Still Can't Find It

The quota might not be listed if:
- Your subscription doesn't have access to GPU quotas yet
- You need to request via Support instead

**Try Support Request instead:**
1. Go to: Help + Support → Create a support request
2. Problem type: **Service and subscription limits (quotas)**
3. Quota type: **Compute-VM (cores-vCPUs) subscription limit increases**
4. Details: Region westus2, Quota "Standard NCASv3_T4 Family", Limit 4

## What the Quota Names Look Like

Look for entries like:
- `Standard NCASv3_T4 Family vCPUs` ← This is what you want (T4 GPU)
- `Standard NC Family vCPUs` ← Alternative (V100 GPU, requires 6 vCPUs)

They should show:
- Current limit: 0
- Current usage: 0
- A button/link: "Request quota increase"







