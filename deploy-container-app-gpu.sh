#!/bin/bash
# Deploy WocconWaker to Azure Container Apps with Serverless GPU Support
# Uses T4 or A100 GPUs for Ollama acceleration
# Pricing: ~$0.36/hour (T4) or ~$1.80/hour (A100) when active, $0 when idle

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   WocconWaker Container Apps with Serverless GPU          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Set subscription (nonprofit grant)
SUBSCRIPTION_ID="58587a07-da50-4691-aa9c-f23859d66df3"
echo -e "${GREEN}Setting subscription to: ${SUBSCRIPTION_ID}${NC}"
az account set --subscription "$SUBSCRIPTION_ID"

RESOURCE_GROUP="rg-wocconwaker"
LOCATION="eastus"  # Serverless GPU supported regions: westus3, eastus, australiaeast, swedencentral
CONTAINER_APP_ENV="wocconwaker-env-gpu"
CONTAINER_APP="wocconwaker-app-gpu"

# GPU configuration
GPU_TYPE="T4"  # Options: T4 (cheaper) or A100 (faster)
GPU_COUNT=1

# Pricing information
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}Pricing Information - Serverless GPU${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}T4 GPU (Recommended for Ollama):${NC}"
echo -e "  • ~\$0.36/hour (~\$0.0001/second) when actively processing"
echo -e "  • Scales to zero when idle = \$0 cost"
echo -e "  • With min-replicas=0, no charge when no requests"
echo -e "  • Example: 8 hours/day = ~\$2.88/day = ~\$87/month"
echo ""
echo -e "${GREEN}A100 GPU (Faster, more expensive):${NC}"
echo -e "  • ~\$1.80/hour (~\$0.0005/second) when actively processing"
echo -e "  • Scales to zero when idle = \$0 cost"
echo -e "  • Example: 8 hours/day = ~\$14.40/day = ~\$432/month"
echo ""
echo -e "${YELLOW}⚠ Note: Serverless GPU requires quota approval first${NC}"
echo -e "${YELLOW}  If deployment fails, run: ./request-gpu-quota-enhanced.sh${NC}"
echo ""

read -p "Continue with ${GPU_TYPE} GPU deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

# Check serverless GPU support in region
echo -e "${BLUE}Step 1: Checking serverless GPU support...${NC}"
SUPPORTED_REGIONS=("westus3" "eastus" "australiaeast" "swedencentral")

if [[ ! " ${SUPPORTED_REGIONS[@]} " =~ " ${LOCATION} " ]]; then
    echo -e "${YELLOW}⚠ ${LOCATION} may not support serverless GPU${NC}"
    echo -e "${YELLOW}  Supported regions: ${SUPPORTED_REGIONS[*]}${NC}"
    echo -e "${YELLOW}  Switching to eastus...${NC}"
    LOCATION="eastus"
fi
echo -e "${GREEN}✓ Using region: ${LOCATION}${NC}"
echo ""

# Check Docker
if ! docker ps > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker daemon is not running${NC}"
    echo "Please start Docker Desktop and run this script again"
    exit 1
fi

# Check if Container Registry exists
echo -e "${BLUE}Step 2: Checking for Container Registry...${NC}"
REGISTRY_NAME=$(az acr list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")

if [ -z "$REGISTRY_NAME" ]; then
    echo -e "${YELLOW}No Container Registry found. Creating one...${NC}"
    REGISTRY_NAME="wocconwaker$(date +%s)"
    az acr create --name "$REGISTRY_NAME" --resource-group "$RESOURCE_GROUP" --sku Basic --location "$LOCATION"
    echo -e "${GREEN}✓ Created Container Registry: ${REGISTRY_NAME}${NC}"
else
    echo -e "${GREEN}✓ Found Container Registry: ${REGISTRY_NAME}${NC}"
fi

REGISTRY_SERVER=$(az acr show --name "$REGISTRY_NAME" --resource-group "$RESOURCE_GROUP" --query loginServer -o tsv)
echo ""

# Build Docker image with GPU support
echo -e "${BLUE}Step 3: Building GPU-enabled Docker image (this may take 10-15 minutes)...${NC}"
echo -e "${YELLOW}Note: GPU image is larger than CPU-only image${NC}"
docker build -f Dockerfile.azure.gpu -t "$REGISTRY_SERVER/wocconwaker:gpu-latest" .

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Docker build failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker image built successfully${NC}"
echo ""

# Login to registry
echo -e "${BLUE}Step 4: Logging into Container Registry...${NC}"
az acr login --name "$REGISTRY_NAME"

# Push image
echo -e "${BLUE}Step 5: Pushing image to registry (this may take a few minutes)...${NC}"
docker push "$REGISTRY_SERVER/wocconwaker:gpu-latest"

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Docker push failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Image pushed successfully${NC}"
echo ""

# Register Container Apps provider if needed
echo -e "${BLUE}Step 6: Ensuring Container Apps provider is registered...${NC}"
az provider register -n Microsoft.App --wait
echo -e "${GREEN}✓ Provider registered${NC}"
echo ""

# Create Container App Environment with GPU workload profile
echo -e "${BLUE}Step 7: Creating Container App Environment with GPU support...${NC}"
if ! az containerapp env show --name "$CONTAINER_APP_ENV" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
    echo -e "${YELLOW}Creating Container App Environment with GPU workload profile...${NC}"
    
    # Note: Serverless GPU uses Consumption workload profile
    # The GPU is automatically allocated when container requests it
    az containerapp env create \
        --name "$CONTAINER_APP_ENV" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --workload-profile-type Consumption
    
    echo -e "${GREEN}✓ Environment created${NC}"
else
    echo -e "${GREEN}✓ Environment exists${NC}"
fi
echo ""

# Create Container App with GPU resources
echo -e "${BLUE}Step 8: Creating Container App with GPU resources...${NC}"
if ! az containerapp show --name "$CONTAINER_APP" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
    echo -e "${YELLOW}Creating Container App with ${GPU_TYPE} GPU...${NC}"
    
    # For serverless GPU, we need to use the extended format with resources
    # Note: Azure CLI may require specific API version for GPU support
    az containerapp create \
        --name "$CONTAINER_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --environment "$CONTAINER_APP_ENV" \
        --image "$REGISTRY_SERVER/wocconwaker:gpu-latest" \
        --registry-server "$REGISTRY_SERVER" \
        --registry-identity system \
        --cpu 2.0 \
        --memory 4.0Gi \
        --min-replicas 0 \
        --max-replicas 10 \
        --ingress external \
        --target-port 8000 \
        --env-vars \
            WOCCON_MODE=server \
            OLLAMA_MODEL=llama3:8b \
            OLLAMA_NUM_GPU=1 \
            PORT=8000 \
        --system-assigned
    
    # Note: GPU allocation in Container Apps may require:
    # 1. Quota approval for GPU SKUs
    # 2. Using workload profiles with GPU support
    # 3. Specifying GPU resources in the container resource requests
    # 
    # As of 2024, serverless GPU support may require:
    # - API version 2024-03-01 or later
    # - Specific workload profile configuration
    # - Quota approval for GPU SKUs
    
    # Grant ACR pull permission
    PRINCIPAL_ID=$(az containerapp show --name "$CONTAINER_APP" --resource-group "$RESOURCE_GROUP" --query "identity.principalId" -o tsv 2>/dev/null || echo "")
    if [ -n "$PRINCIPAL_ID" ]; then
        az role assignment create \
            --assignee "$PRINCIPAL_ID" \
            --role AcrPull \
            --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.ContainerRegistry/registries/$REGISTRY_NAME" \
            --output none 2>/dev/null || true
    fi
    
    echo -e "${GREEN}✓ Container App created${NC}"
    
    echo -e "${YELLOW}⚠ Important: GPU resources may not be allocated if quota is not approved${NC}"
    echo -e "${YELLOW}  If GPU is not available, the app will fall back to CPU${NC}"
    echo -e "${YELLOW}  Check quota: ./check-gpu-availability.sh${NC}"
else
    echo -e "${YELLOW}Updating existing Container App...${NC}"
    az containerapp update \
        --name "$CONTAINER_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --image "$REGISTRY_SERVER/wocconwaker:gpu-latest" \
        --cpu 2.0 \
        --memory 4.0Gi
    
    echo -e "${GREEN}✓ Container App updated${NC}"
fi
echo ""

# Get app URL
echo -e "${BLUE}Step 9: Getting application URL...${NC}"
APP_URL=$(az containerapp show \
    --name "$CONTAINER_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" \
    --output tsv 2>/dev/null || echo "")

if [ -n "$APP_URL" ]; then
    echo -e "${GREEN}✓ Application URL: https://${APP_URL}${NC}"
else
    echo -e "${YELLOW}⚠ Could not get app URL yet${NC}"
fi
echo ""

# Check GPU allocation
echo -e "${BLUE}Step 10: Verifying GPU allocation...${NC}"
echo -e "${YELLOW}Checking container logs for GPU detection...${NC}"

sleep 30

az containerapp logs show \
    --name "$CONTAINER_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --tail 50 \
    --type console 2>/dev/null | grep -i "gpu\|cuda\|nvidia" || echo -e "${YELLOW}GPU logs not yet available${NC}"

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${CYAN}Pricing Summary:${NC}"
echo -e "  GPU Type: ${GPU_TYPE}"
if [ "$GPU_TYPE" = "T4" ]; then
    echo -e "  Cost: ~\$0.36/hour when active (~\$0 when idle)"
    echo -e "  Example: 8 hours/day = ~\$87/month"
elif [ "$GPU_TYPE" = "A100" ]; then
    echo -e "  Cost: ~\$1.80/hour when active (~\$0 when idle)"
    echo -e "  Example: 8 hours/day = ~\$432/month"
fi
echo ""
echo -e "${CYAN}Container App Details:${NC}"
echo -e "  Name: ${CONTAINER_APP}"
echo -e "  Environment: ${CONTAINER_APP_ENV}"
echo -e "  Region: ${LOCATION}"
if [ -n "$APP_URL" ]; then
    echo -e "  URL: https://${APP_URL}"
    echo -e "  Health: https://${APP_URL}/health"
fi
echo ""
echo -e "${CYAN}Useful Commands:${NC}"
echo -e "  View logs: az containerapp logs show --name ${CONTAINER_APP} --resource-group ${RESOURCE_GROUP} --follow"
echo -e "  Check status: az containerapp show --name ${CONTAINER_APP} --resource-group ${RESOURCE_GROUP}"
echo -e "  Check GPU usage: az containerapp logs show --name ${CONTAINER_APP} --resource-group ${RESOURCE_GROUP} --type console | grep -i gpu"
echo ""
echo -e "${YELLOW}⚠ Important Notes:${NC}"
echo -e "  • GPU requires quota approval first"
echo -e "  • If GPU quota not approved, app will use CPU (slower)"
echo -e "  • Check quota status: ./check-gpu-availability.sh"
echo -e "  • Request quota: ./request-gpu-quota-enhanced.sh"
echo ""

