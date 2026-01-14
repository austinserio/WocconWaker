#!/bin/bash
# Deploy WocconWaker to Azure Container Apps with local Ollama

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}WocconWaker Container Apps Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Set subscription
SUBSCRIPTION_ID="2fef1120-5b1e-4224-9b93-091eb5d5424e"
echo -e "${GREEN}Setting subscription to: ${SUBSCRIPTION_ID}${NC}"
az account set --subscription "$SUBSCRIPTION_ID"

RESOURCE_GROUP="rg-wocconwaker"
LOCATION="eastus"
CONTAINER_APP_ENV="wocconwaker-env"
CONTAINER_APP="wocconwaker-app"

# Check Docker
if ! docker ps > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker daemon is not running${NC}"
    echo "Please start Docker Desktop and run this script again"
    exit 1
fi

# Check if Container Registry exists
echo -e "${BLUE}Checking for Container Registry...${NC}"
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

# Build Docker image
echo -e "${BLUE}Step 1: Building Docker image (this may take 5-10 minutes)...${NC}"
docker build -f Dockerfile.azure -t "$REGISTRY_SERVER/wocconwaker:latest" .

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Docker build failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker image built successfully${NC}"
echo ""

# Login to registry
echo -e "${BLUE}Step 2: Logging into Container Registry...${NC}"
az acr login --name "$REGISTRY_NAME"

# Push image
echo -e "${BLUE}Step 3: Pushing image to registry (this may take a few minutes)...${NC}"
docker push "$REGISTRY_SERVER/wocconwaker:latest"

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Docker push failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Image pushed successfully${NC}"
echo ""

# Register Container Apps provider if needed
echo -e "${BLUE}Step 4: Ensuring Container Apps provider is registered...${NC}"
az provider register -n Microsoft.App --wait
echo -e "${GREEN}✓ Provider registered${NC}"
echo ""

# Check if Container App Environment exists
echo -e "${BLUE}Step 5: Checking Container App Environment...${NC}"
if ! az containerapp env show --name "$CONTAINER_APP_ENV" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
    echo -e "${YELLOW}Creating Container App Environment...${NC}"
    az containerapp env create \
        --name "$CONTAINER_APP_ENV" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION"
    echo -e "${GREEN}✓ Environment created${NC}"
else
    echo -e "${GREEN}✓ Environment exists${NC}"
fi
echo ""

# Check if Container App exists
echo -e "${BLUE}Step 6: Checking Container App...${NC}"
if ! az containerapp show --name "$CONTAINER_APP" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
    echo -e "${YELLOW}Creating Container App...${NC}"
    az containerapp create \
        --name "$CONTAINER_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --environment "$CONTAINER_APP_ENV" \
        --image "$REGISTRY_SERVER/wocconwaker:latest" \
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
            PORT=8000 \
        --system-assigned
    
    # Grant ACR pull permission
    PRINCIPAL_ID=$(az containerapp show --name "$CONTAINER_APP" --resource-group "$RESOURCE_GROUP" --query "identity.principalId" -o tsv)
    az role assignment create \
        --assignee "$PRINCIPAL_ID" \
        --role AcrPull \
        --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.ContainerRegistry/registries/$REGISTRY_NAME" \
        --output none
    
    echo -e "${GREEN}✓ Container App created${NC}"
else
    echo -e "${YELLOW}Updating existing Container App...${NC}"
    az containerapp update \
        --name "$CONTAINER_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --image "$REGISTRY_SERVER/wocconwaker:latest" \
        --cpu 2.0 \
        --memory 4.0Gi
    
    echo -e "${GREEN}✓ Container App updated${NC}"
fi
echo ""

# Get app URL
echo -e "${BLUE}Step 7: Getting application URL...${NC}"
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

# Wait for app to start
echo -e "${BLUE}Step 8: Waiting for app to initialize (this may take 1-2 minutes)...${NC}"
echo -e "${YELLOW}The app needs to:${NC}"
echo -e "${YELLOW}  1. Start the container${NC}"
echo -e "${YELLOW}  2. Install and start Ollama${NC}"
echo -e "${YELLOW}  3. Pull the llama3:8b model (first time only, ~4.7GB)${NC}"
echo -e "${YELLOW}  4. Initialize the assistant${NC}"
echo ""

sleep 30

# Check logs
echo -e "${BLUE}Step 9: Checking recent logs...${NC}"
az containerapp logs show \
    --name "$CONTAINER_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --tail 50 \
    --type console 2>/dev/null | tail -30 || echo -e "${YELLOW}Could not fetch logs${NC}"

echo ""
echo -e "${BLUE}Step 10: Testing endpoints...${NC}"

if [ -n "$APP_URL" ]; then
    # Test health endpoint
    echo -e "${YELLOW}Testing health endpoint...${NC}"
    for i in {1..10}; do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://${APP_URL}/health" 2>/dev/null || echo "000")
        
        if [ "$HTTP_CODE" == "200" ]; then
            echo -e "${GREEN}✓ Health check passed (HTTP $HTTP_CODE)${NC}"
            HEALTH_RESPONSE=$(curl -s --max-time 10 "https://${APP_URL}/health" 2>/dev/null || echo "")
            echo "  Response: $HEALTH_RESPONSE"
            break
        else
            echo -e "${YELLOW}  Attempt $i/10: HTTP $HTTP_CODE, waiting 10 seconds...${NC}"
            sleep 10
        fi
    done
    
    echo ""
    
    # Test API endpoint
    echo -e "${YELLOW}Testing API endpoint with a simple query...${NC}"
    TEST_RESPONSE=$(curl -s -X POST "https://${APP_URL}/message" \
        -H "Content-Type: application/json" \
        -d '{"text": "What is the Woccon word for water?", "user_id": "test_user"}' \
        --max-time 120 2>/dev/null || echo "")
    
    if [ -n "$TEST_RESPONSE" ] && [ "$TEST_RESPONSE" != "null" ]; then
        echo -e "${GREEN}✓ API responded successfully${NC}"
        echo "  Response preview:"
        echo "$TEST_RESPONSE" | python3 -m json.tool 2>/dev/null | head -20 || echo "$TEST_RESPONSE" | head -c 500
        echo ""
    else
        echo -e "${YELLOW}⚠ API not responding yet (may still be initializing Ollama/model)${NC}"
        echo -e "${YELLOW}  This is normal on first deployment - model pull can take 5-10 minutes${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Cannot test endpoints (no URL available)${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Useful commands:"
echo "  View logs: az containerapp logs show --name $CONTAINER_APP --resource-group $RESOURCE_GROUP --follow"
echo "  Check status: az containerapp show --name $CONTAINER_APP --resource-group $RESOURCE_GROUP"
if [ -n "$APP_URL" ]; then
    echo "  App URL: https://${APP_URL}"
    echo "  Health: https://${APP_URL}/health"
fi
echo ""




