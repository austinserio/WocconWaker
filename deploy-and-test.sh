#!/bin/bash
# Script to deploy updated Docker image to Azure and test it

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}WocconWaker Azure Deployment & Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check Azure CLI
if ! command -v az &> /dev/null; then
    echo -e "${RED}Error: Azure CLI is not installed${NC}"
    exit 1
fi

# Check if logged in
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}Not logged in to Azure. Logging in...${NC}"
    az login
fi

# Try to find the resource group
echo -e "${BLUE}Looking for existing resources...${NC}"
RESOURCE_GROUP=$(az group list --query "[?contains(name, 'woccon') || contains(name, 'Woccon')].name" -o tsv | head -1)

if [ -z "$RESOURCE_GROUP" ]; then
    echo -e "${YELLOW}No existing resource group found.${NC}"
    echo -e "${YELLOW}Please provide your Azure resource group name, or press Enter to use 'rg-wocconwaker':${NC}"
    read -p "Resource Group: " RESOURCE_GROUP
    RESOURCE_GROUP=${RESOURCE_GROUP:-rg-wocconwaker}
fi

echo -e "${GREEN}Using resource group: ${RESOURCE_GROUP}${NC}"

# Check if resource group exists
if ! az group show --name "$RESOURCE_GROUP" &>/dev/null; then
    echo -e "${YELLOW}Resource group doesn't exist. Creating it...${NC}"
    az group create --name "$RESOURCE_GROUP" --location eastus
fi

# Find Container Registry
echo -e "${BLUE}Looking for Container Registry...${NC}"
REGISTRY_NAME=$(az acr list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")

if [ -z "$REGISTRY_NAME" ]; then
    echo -e "${YELLOW}No Container Registry found.${NC}"
    echo -e "${YELLOW}Please provide your Container Registry name, or we'll create one:${NC}"
    read -p "Registry Name (or press Enter to create new): " REGISTRY_NAME
    
    if [ -z "$REGISTRY_NAME" ]; then
        REGISTRY_NAME="wocconwaker$(date +%s)"
        echo -e "${GREEN}Creating new Container Registry: ${REGISTRY_NAME}${NC}"
        az acr create --name "$REGISTRY_NAME" --resource-group "$RESOURCE_GROUP" --sku Basic
    fi
fi

REGISTRY_SERVER=$(az acr show --name "$REGISTRY_NAME" --resource-group "$RESOURCE_GROUP" --query loginServer -o tsv)
echo -e "${GREEN}Using Container Registry: ${REGISTRY_SERVER}${NC}"

# Find Container App
echo -e "${BLUE}Looking for Container App...${NC}"
APP_NAME=$(az containerapp list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")

if [ -z "$APP_NAME" ]; then
    echo -e "${YELLOW}No Container App found.${NC}"
    echo -e "${YELLOW}Please provide your Container App name, or press Enter to use 'wocconwaker-app':${NC}"
    read -p "App Name: " APP_NAME
    APP_NAME=${APP_NAME:-wocconwaker-app}
fi

echo -e "${GREEN}Using Container App: ${APP_NAME}${NC}"
echo ""

# Build Docker image
echo -e "${BLUE}Step 1: Building Docker image...${NC}"
echo -e "${YELLOW}This may take several minutes...${NC}"
docker build -f Dockerfile.azure -t "$REGISTRY_SERVER/wocconwaker:latest" .

if [ $? -ne 0 ]; then
    echo -e "${RED}Docker build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker image built successfully${NC}"
echo ""

# Login to registry
echo -e "${BLUE}Step 2: Logging into Container Registry...${NC}"
az acr login --name "$REGISTRY_NAME"

# Push image
echo -e "${BLUE}Step 3: Pushing image to registry...${NC}"
echo -e "${YELLOW}This may take several minutes...${NC}"
docker push "$REGISTRY_SERVER/wocconwaker:latest"

if [ $? -ne 0 ]; then
    echo -e "${RED}Docker push failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Image pushed successfully${NC}"
echo ""

# Update Container App
echo -e "${BLUE}Step 4: Updating Container App...${NC}"
az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$REGISTRY_SERVER/wocconwaker:latest" \
  --cpu 2.0 \
  --memory 4.0Gi

echo -e "${GREEN}✓ Container App updated${NC}"
echo ""

# Get app URL
echo -e "${BLUE}Step 5: Getting application URL...${NC}"
APP_URL=$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv 2>/dev/null || echo "")

if [ -z "$APP_URL" ]; then
    echo -e "${YELLOW}⚠ Could not get app URL${NC}"
else
    echo -e "${GREEN}Application URL: https://${APP_URL}${NC}"
fi

echo ""
echo -e "${BLUE}Step 6: Waiting for app to start (this may take 1-2 minutes)...${NC}"
sleep 30

# Check logs
echo -e "${BLUE}Step 7: Checking recent logs...${NC}"
az containerapp logs show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --tail 50 \
  --type console 2>/dev/null | tail -30 || echo -e "${YELLOW}Could not fetch logs${NC}"

echo ""
echo -e "${BLUE}Step 8: Testing health endpoint...${NC}"
if [ -n "$APP_URL" ]; then
    for i in {1..5}; do
        echo -e "${YELLOW}Attempt $i/5...${NC}"
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://${APP_URL}/health" 2>/dev/null || echo "000")
        
        if [ "$HTTP_CODE" == "200" ]; then
            echo -e "${GREEN}✓ Health check passed (HTTP $HTTP_CODE)${NC}"
            HEALTH_RESPONSE=$(curl -s --max-time 10 "https://${APP_URL}/health" 2>/dev/null || echo "")
            echo "Response: $HEALTH_RESPONSE"
            break
        else
            echo -e "${YELLOW}Health check returned HTTP $HTTP_CODE, waiting...${NC}"
            sleep 10
        fi
    done
else
    echo -e "${YELLOW}⚠ Cannot test health endpoint (no URL)${NC}"
fi

echo ""
echo -e "${BLUE}Step 9: Testing API endpoint...${NC}"
if [ -n "$APP_URL" ]; then
    echo -e "${YELLOW}Sending test message...${NC}"
    TEST_RESPONSE=$(curl -s -X POST "https://${APP_URL}/message" \
      -H "Content-Type: application/json" \
      -d '{"text": "What is the Woccon word for water?", "user_id": "test_user"}' \
      --max-time 60 2>/dev/null || echo "")
    
    if [ -n "$TEST_RESPONSE" ]; then
        echo -e "${GREEN}✓ API responded${NC}"
        echo "Response: $TEST_RESPONSE" | head -c 500
        echo ""
    else
        echo -e "${YELLOW}⚠ No response from API (may still be initializing)${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Cannot test API endpoint (no URL)${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "To monitor logs:"
echo "  az containerapp logs show --name $APP_NAME --resource-group $RESOURCE_GROUP --follow"
echo ""
if [ -n "$APP_URL" ]; then
    echo "Application URL: https://${APP_URL}"
    echo "Health check: https://${APP_URL}/health"
fi




