# GPU Access Guide for Azure (Nonprofit Grant)

This guide provides comprehensive information about getting GPU access on Azure for the WocconWaker project, including all pricing details and multiple deployment options.

## Quick Start

1. **Check availability and pricing**: `./check-gpu-availability.sh`
2. **If quota is available**: Choose a deployment option below
3. **If quota is needed**: `./request-gpu-quota-enhanced.sh`

## Pricing Overview

### Option 1: Spot VMs (Best for Always-On)

**NCasT4_v3 (T4 GPU) - Recommended for Ollama**

| Metric | Standard VM | Spot VM |
|--------|------------|---------|
| **Hourly cost** | ~$0.35/hour | ~$0.10/hour |
| **Daily cost (24/7)** | ~$8.40/day | ~$2.40/day |
| **Monthly cost (24/7)** | ~$252/month | ~$72/month |
| **Grant coverage** | ~8 months | ~27 months |

**Pros:**
- Lowest cost for 24/7 operation
- Full control over the VM
- Can install custom software

**Cons:**
- Can be evicted with 30 seconds notice
- No SLA guarantee
- Requires quota approval

**Deploy:** `./deploy-gpu-spot-vm.sh`

---

### Option 2: Container Apps Serverless GPU (Best for Intermittent Use)

**T4 GPU**

| Metric | Cost |
|--------|------|
| **Active cost** | ~$0.36/hour (~$0.0001/second) |
| **Idle cost** | $0 (scales to zero) |
| **8 hours/day** | ~$2.88/day (~$87/month) |
| **Grant coverage** | ~694 days of 8-hour usage |

**A100 GPU (if needed)**

| Metric | Cost |
|--------|------|
| **Active cost** | ~$1.80/hour (~$0.0005/second) |
| **Idle cost** | $0 (scales to zero) |
| **8 hours/day** | ~$14.40/day (~$432/month) |
| **Grant coverage** | ~138 days of 8-hour usage |

**Pros:**
- Only pay when processing requests
- Scales to zero automatically
- No eviction risk
- Best cost efficiency for intermittent workloads

**Cons:**
- Requires quota approval
- Cold start latency (~30-60 seconds)
- Less control than dedicated VM

**Deploy:** `./deploy-container-app-gpu.sh`

---

### Option 3: Standard VM (Best for Scheduled Workloads)

**NCasT4_v3**

| Metric | Cost |
|--------|------|
| **Hourly cost** | ~$0.35/hour |
| **4 hours/day** | ~$1.40/day (~$42/month) |
| **Grant coverage** | ~1,428 days (4 hrs/day) |

**Pros:**
- No eviction risk
- Consistent performance
- Full control

**Cons:**
- More expensive than Spot
- Requires quota approval
- Must manage start/stop manually for cost savings

---

## Budget Analysis for $2,000 Grant

### Scenario 1: Always-On Spot VM
- **Cost**: ~$72/month
- **Duration**: ~27 months
- **Best for**: Continuous service, always available

### Scenario 2: Serverless GPU (8 hours/day)
- **Cost**: ~$87/month
- **Duration**: ~23 months  
- **Best for**: Regular business hours usage

### Scenario 3: Serverless GPU (4 hours/day)
- **Cost**: ~$43/month
- **Duration**: ~46 months
- **Best for**: Part-time or scheduled workloads

### Scenario 4: Spot VM (Scheduled - 8 hours/day)
- **Cost**: ~$24/month (0.10 * 8 * 30)
- **Duration**: ~83 months
- **Best for**: Cost-optimized scheduled workloads

## Deployment Options

### 1. Check GPU Availability

```bash
./check-gpu-availability.sh
```

This script will:
- Check current quota status
- Show Spot VM availability
- Display pricing for all options
- Provide recommendations

### 2. Deploy Spot VM (Recommended for Most Cases)

```bash
./deploy-gpu-spot-vm.sh
```

**What it does:**
- Creates NCasT4_v3 Spot VM
- Installs NVIDIA drivers
- Sets up Ollama with GPU support
- Configures auto-start service

**Cost**: ~$0.10/hour (~$72/month if 24/7)

### 3. Deploy Serverless GPU

```bash
./deploy-container-app-gpu.sh
```

**What it does:**
- Creates Container App with serverless GPU
- Deploys GPU-enabled Docker image
- Configures auto-scaling
- Scales to zero when idle

**Cost**: ~$0.36/hour when active, $0 when idle

### 4. Multi-Region Deployment

```bash
./deploy-gpu-multiregion.sh
```

**What it does:**
- Tries multiple regions in parallel
- First successful region wins
- Useful when capacity is limited

### 5. Request GPU Quota

```bash
./request-gpu-quota-enhanced.sh
```

**What it does:**
- Opens Azure Portal with pre-filled quota request
- Includes nonprofit grant context
- Requests multiple regions
- Provides escalation path

**Timeline**: Typically 1-2 business days

### 6. Monitor Quota Approval

```bash
./monitor-quota-approval.sh
```

**What it does:**
- Checks current quota status
- Shows which regions/SKUs are approved
- Provides next steps

## GPU Specifications

### NCasT4_v3 (T4 GPU) - Recommended

- **GPU**: NVIDIA T4 (16GB VRAM)
- **vCPUs**: 4
- **RAM**: 28GB
- **Best for**: Ollama inference, medium workloads
- **Spot pricing**: ~$0.10/hour

### NC6s_v3 (V100 GPU)

- **GPU**: NVIDIA V100 (16GB VRAM)
- **vCPUs**: 6
- **RAM**: 112GB
- **Best for**: Training, larger models
- **Spot pricing**: ~$0.60/hour
- **Standard pricing**: ~$2.00/hour

### NV6 (M60 GPU)

- **GPU**: NVIDIA M60 (8GB VRAM)
- **vCPUs**: 6
- **RAM**: 56GB
- **Best for**: Budget option, older GPU
- **Spot pricing**: ~$0.27/hour
- **Standard pricing**: ~$0.90/hour

## Quota Requirements

All GPU options on Azure require quota approval. Unlike RunPod (instant access), Azure has quota gates for:

1. **Standard VMs**: Require quota
2. **Spot VMs**: Require quota (but use underutilized capacity)
3. **Serverless GPUs**: Require quota

**Quota Request Process:**
1. Run `./request-gpu-quota-enhanced.sh`
2. Fill out form with nonprofit context
3. Wait 1-2 business days for approval
4. Monitor with `./monitor-quota-approval.sh`

**Escalation (if delayed):**
- Open support ticket with "Urgent" severity
- Emphasize nonprofit educational mission
- Reference small quota request (4 cores)

## Recommendations

### For Your Use Case (Ollama with llama3:8b)

**Best Option**: **Spot VM (NCasT4_v3)**
- Cost: ~$72/month for 24/7 operation
- Performance: Excellent for inference
- Budget: ~27 months with $2,000 grant
- Setup: Automated deployment script

**Alternative**: **Serverless GPU (T4)**
- Cost: ~$87/month for 8 hours/day
- Better for: Intermittent usage patterns
- Benefit: Scales to zero when idle

### Cost Optimization Tips

1. **Use Spot VMs**: Save ~70% vs standard
2. **Schedule operations**: Run only when needed
3. **Set up auto-shutdown**: For Spot VMs during off-hours
4. **Monitor usage**: Use Azure Cost Management
5. **Serverless for intermittent**: Scales to zero automatically

## Troubleshooting

### "Quota Exceeded" Error

**Solution**: Request quota first
```bash
./request-gpu-quota-enhanced.sh
```

### "No Capacity" Error

**Solutions**:
1. Try different region: `./deploy-gpu-multiregion.sh`
2. Try Spot pricing (uses underutilized capacity)
3. Wait and try again later

### GPU Not Detected in Container

**Solutions**:
1. Check quota is approved: `./monitor-quota-approval.sh`
2. Verify GPU-enabled Dockerfile is used
3. Check container logs for GPU detection

### Spot VM Eviction

**Prevention**:
- Save work frequently
- Set up auto-save scripts
- Use eviction policy: `Deallocate` (saves state)

## Comparison with RunPod

| Feature | Azure (Spot VM) | RunPod |
|---------|----------------|--------|
| **Setup time** | 5-10 minutes | Instant |
| **Quota required** | Yes (1-2 days) | No |
| **Cost (T4)** | ~$0.10/hour | ~$0.29/hour |
| **Eviction risk** | Yes (30s notice) | No |
| **Grant coverage** | ~27 months | ~9 months |
| **Best for** | Long-term, budget-conscious | Immediate, short-term |

**Azure Advantage**: 3x cheaper, better long-term value
**RunPod Advantage**: Instant access, no quota needed

## Additional Resources

- **Azure Pricing Calculator**: https://azure.microsoft.com/pricing/calculator/
- **VM Pricing**: https://azure.microsoft.com/pricing/details/virtual-machines/linux/
- **Container Apps Pricing**: https://azure.microsoft.com/pricing/details/container-apps/
- **Quota Documentation**: https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits

## Next Steps

1. **Check availability**: `./check-gpu-availability.sh`
2. **Review pricing**: See pricing overview above
3. **Choose deployment option**: Based on your usage pattern
4. **Request quota** (if needed): `./request-gpu-quota-enhanced.sh`
5. **Deploy**: Run the appropriate deployment script
6. **Monitor costs**: Set up budget alerts in Azure Portal

---

**Note**: All pricing is approximate and may vary by region and time. Check Azure Pricing Calculator for exact current pricing. Nonprofit grant pricing may differ from standard pricing.

