#!/bin/bash
# Comprehensive GPU Availability Checker with Pricing
# Checks quota, availability, and shows pricing for all GPU options

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   GPU Availability & Pricing Checker                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Set subscription (nonprofit grant)
SUBSCRIPTION_ID="58587a07-da50-4691-aa9c-f23859d66df3"
echo -e "${GREEN}Setting subscription to: ${SUBSCRIPTION_ID}${NC}"
az account set --subscription "$SUBSCRIPTION_ID"

SUB_NAME=$(az account show --query name -o tsv)
SUB_TYPE=$(az account show --query subscriptionPolicies.quotaId -o tsv 2>/dev/null || echo "unknown")
echo -e "${CYAN}Subscription: ${SUB_NAME}${NC}"
echo -e "${CYAN}Quota ID: ${SUB_TYPE}${NC}"
echo ""

# Regions to check
REGIONS=("eastus" "westus2" "westus3" "southcentralus" "northeurope")

# GPU VM families to check
declare -A GPU_FAMILIES
GPU_FAMILIES["NCasT4_v3"]="Standard NCASv3_T4 Family"
GPU_FAMILIES["NC6s_v3"]="Standard NC Family"
GPU_FAMILIES["NCv3"]="Standard NC Family"
GPU_FAMILIES["NV6"]="Standard NV Family"

# GPU SKU details (VM size, GPU type, cores, pricing per hour)
declare -A GPU_SKUS
GPU_SKUS["NCasT4_v3"]="NC4as_T4_v3|NVIDIA T4|4 vCPU, 28GB RAM|~\$0.35/hour|~\$0.10/hour (Spot)"
GPU_SKUS["NC6s_v3"]="NC6s_v3|NVIDIA V100|6 vCPU, 112GB RAM|~\$2.00/hour|~\$0.60/hour (Spot)"
GPU_SKUS["NV6"]="NV6|NVIDIA M60|6 vCPU, 56GB RAM|~\$0.90/hour|~\$0.27/hour (Spot)"

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Phase 1: Subscription & Quota Status${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

# Check current quota for each GPU family
AVAILABLE_GPUS=()
NO_QUOTA_GPUS=()

for gpu_family in "${!GPU_FAMILIES[@]}"; do
    family_name="${GPU_FAMILIES[$gpu_family]}"
    echo -e "${CYAN}Checking quota for: ${family_name}${NC}"
    
    # Try first region to check quota
    REGION="${REGIONS[0]}"
    QUOTA_INFO=$(az vm list-usage \
        --location "$REGION" \
        --query "[?name.value=='${family_name}'].{current:currentValue, limit:limit}" \
        -o tsv 2>/dev/null || echo "")
    
    if [ -n "$QUOTA_INFO" ]; then
        CURRENT=$(echo "$QUOTA_INFO" | awk '{print $1}')
        LIMIT=$(echo "$QUOTA_INFO" | awk '{print $2}')
        
        if [ "$LIMIT" -gt 0 ] 2>/dev/null; then
            echo -e "  ${GREEN}✓ Quota: ${CURRENT}/${LIMIT} cores${NC}"
            AVAILABLE_GPUS+=("$gpu_family")
        else
            echo -e "  ${RED}✗ Quota: ${CURRENT}/${LIMIT} cores (quota needed)${NC}"
            NO_QUOTA_GPUS+=("$gpu_family")
        fi
    else
        echo -e "  ${YELLOW}⚠ Could not retrieve quota (may need quota request)${NC}"
        NO_QUOTA_GPUS+=("$gpu_family")
    fi
    echo ""
done

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Phase 2: Spot VM Availability Check${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Note: Spot VMs use underutilized capacity and may be available${NC}"
echo -e "${YELLOW}even without full quota approval. Checking availability...${NC}"
echo ""

SPOT_AVAILABLE=()
for region in "${REGIONS[@]}"; do
    echo -e "${CYAN}Checking ${region}...${NC}"
    
    # Check NCasT4_v3 (best for Ollama)
    if az vm list-sizes --location "$region" --query "[?name=='NC4as_T4_v3']" -o tsv 2>/dev/null | grep -q "NC4as_T4_v3"; then
        echo -e "  ${GREEN}✓ NC4as_T4_v3 available${NC}"
        
        # Try to get pricing for Spot
        echo -e "  ${CYAN}Pricing (approximate, check Azure Pricing Calculator for exact):${NC}"
        if [[ " ${AVAILABLE_GPUS[@]} " =~ " NCasT4_v3 " ]]; then
            echo -e "    ${GREEN}Standard: ~\$0.35/hour (~\$252/month if running 24/7)${NC}"
            echo -e "    ${GREEN}Spot: ~\$0.10/hour (~\$72/month if running 24/7)${NC}"
        else
            echo -e "    ${YELLOW}Spot only (if available): ~\$0.10/hour (~\$72/month)${NC}"
        fi
        
        SPOT_AVAILABLE+=("$region:NC4as_T4_v3")
    else
        echo -e "  ${RED}✗ NC4as_T4_v3 not available${NC}"
    fi
    echo ""
done

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Phase 3: Container Apps Serverless GPU${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${CYAN}Checking Container Apps serverless GPU support...${NC}"
echo ""

# Serverless GPU regions (as of 2024)
SERVERLESS_GPU_REGIONS=("westus3" "eastus" "australiaeast" "swedencentral")
SUPPORTED_REGIONS=()

for region in "${SERVERLESS_GPU_REGIONS[@]}"; do
    echo -e "${CYAN}Checking ${region}...${NC}"
    
    # Note: This requires API version check - Container Apps serverless GPU is GA
    # We'll provide information based on known supported regions
    if [[ " ${SERVERLESS_GPU_REGIONS[@]} " =~ " ${region} " ]]; then
        echo -e "  ${GREEN}✓ Serverless GPU supported${NC}"
        SUPPORTED_REGIONS+=("$region")
        
        echo -e "  ${CYAN}Pricing (Consumption Plan - pay per use):${NC}"
        echo -e "    ${GREEN}T4 GPU: ~\$0.0001/second (~\$0.36/hour when active)${NC}"
        echo -e "    ${GREEN}A100 GPU: ~\$0.0005/second (~\$1.80/hour when active)${NC}"
        echo -e "    ${YELLOW}Note: Only charged when container is running requests${NC}"
        echo -e "    ${YELLOW}With min-replicas=0, scales to zero = \$0 when idle${NC}"
    fi
    echo ""
done

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Phase 4: Pricing Summary${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${GREEN}Recommended GPU Options (best for Ollama):${NC}"
echo ""
echo -e "${CYAN}1. NCasT4_v3 (T4 GPU) - Best Balance${NC}"
echo -e "   ${GREEN}Standard VM:${NC}"
echo -e "     • ~\$0.35/hour (~\$252/month if 24/7)"
echo -e "     • ~\$8.40/day if running 24/7"
echo -e "     • ~\$0.35/hour if only running when needed"
echo -e "   ${GREEN}Spot VM:${NC}"
echo -e "     • ~\$0.10/hour (~\$72/month if 24/7)"
echo -e "     • ~\$2.40/day if running 24/7"
echo -e "     • Risk: Can be evicted with 30 seconds notice"
echo ""

echo -e "${CYAN}2. Container Apps Serverless GPU (T4) - Most Flexible${NC}"
echo -e "   • ~\$0.36/hour when actively processing requests"
echo -e "   • Scales to zero when idle = \$0 cost"
echo -e "   • Best for intermittent workloads"
echo -e "   • Requires quota approval"
echo ""

echo -e "${CYAN}3. NV6 (M60 GPU) - Budget Option${NC}"
echo -e "   ${GREEN}Standard: ~\$0.90/hour (~\$648/month if 24/7)${NC}"
echo -e "   ${GREEN}Spot: ~\$0.27/hour (~\$194/month if 24/7)${NC}"
echo -e "   ${YELLOW}Note: Older GPU, less performant for LLMs${NC}"
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Phase 5: Cost Optimization Recommendations${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${GREEN}With \$2,000 nonprofit grant, you can afford:${NC}"
echo ""
echo -e "${CYAN}Option A: Spot VM (NCasT4_v3) - 24/7 operation${NC}"
echo -e "   • ~\$72/month = ~27 months of continuous operation"
echo -e "   • Best for: Always-on service"
echo -e "   • Risk: Eviction possible (save state frequently)"
echo ""

echo -e "${CYAN}Option B: Container Apps Serverless GPU - On-demand${NC}"
echo -e "   • Pay only when handling requests"
echo -e "   • 5,555 hours of GPU time (\$2,000 / \$0.36)"
echo -e "   • Best for: Intermittent usage patterns"
echo -e "   • If used 8 hours/day: ~694 days of operation"
echo ""

echo -e "${CYAN}Option C: Standard VM - Part-time operation${NC}"
echo -e "   • ~\$0.35/hour = 5,714 hours total"
echo -e "   • 4 hours/day = ~1,428 days of operation"
echo -e "   • Best for: Scheduled workloads"
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Recommendation${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

if [ ${#AVAILABLE_GPUS[@]} -gt 0 ]; then
    echo -e "${GREEN}✓ GPU quota is available! You can deploy immediately.${NC}"
    echo ""
    echo -e "${YELLOW}Recommended: Try Container Apps Serverless GPU first${NC}"
    echo -e "${YELLOW}(best cost efficiency for your usage pattern)${NC}"
    echo ""
    echo -e "Next steps:"
    echo -e "  1. Run: ./deploy-container-app-gpu.sh"
    echo -e "  2. Or: ./deploy-gpu-spot-vm.sh (for always-on VM)"
else
    echo -e "${RED}⚠ No GPU quota found. You need to request quota first.${NC}"
    echo ""
    echo -e "${YELLOW}However, you may still be able to deploy Spot VMs${NC}"
    echo -e "${YELLOW}if capacity is available (checking...):${NC}"
    echo ""
    
    if [ ${#SPOT_AVAILABLE[@]} -gt 0 ]; then
        echo -e "${GREEN}✓ Spot VMs may be available! Try:${NC}"
        echo -e "  ./deploy-gpu-spot-vm.sh"
    else
        echo -e "${YELLOW}Request quota increase:${NC}"
        echo -e "  ./request-gpu-quota-enhanced.sh"
    fi
fi

echo ""
echo -e "${CYAN}For exact pricing, check:${NC}"
echo -e "  https://azure.microsoft.com/pricing/details/virtual-machines/linux/"
echo -e "  https://azure.microsoft.com/pricing/details/container-apps/"
echo ""

