#!/bin/bash
# Build Docker image and update Container App

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

RESOURCE_GROUP="rg-wocconwaker"
CONTAINER_APP="wocconwaker-app"

# Get the Container Registry name (use the most recent one)
CONTAINER_REGISTRY=$(az acr list --resource-group "$RESOURCE_GROUP" --query "sort_by([], &creationDate)[-1].name" --output tsv)

if [ -z "$CONTAINER_REGISTRY" ]; then
    echo -e "${RED}Error: No Container Registry found${NC}"
    exit 1
fi

echo -e "${GREEN}Using Container Registry: ${CONTAINER_REGISTRY}${NC}"

# Get registry server
REGISTRY_SERVER=$(az acr show --name "$CONTAINER_REGISTRY" --resource-group "$RESOURCE_GROUP" --query loginServer --output tsv)
echo -e "${GREEN}Registry Server: ${REGISTRY_SERVER}${NC}"

# Check Docker
if ! docker info &> /dev/null; then
    echo -e "${RED}Error: Docker daemon is not running${NC}"
    echo "Please start Docker Desktop and try again"
    exit 1
fi

# Login to registry
echo ""
echo -e "${GREEN}Step 1: Logging into Azure Container Registry...${NC}"
az acr login --name "$CONTAINER_REGISTRY"

# Build image
echo ""
echo -e "${GREEN}Step 2: Building Docker image...${NC}"
docker build -t "$REGISTRY_SERVER/wocconwaker:latest" .

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Docker build failed${NC}"
    exit 1
fi

# Push image
echo ""
echo -e "${GREEN}Step 3: Pushing Docker image to registry...${NC}"
docker push "$REGISTRY_SERVER/wocconwaker:latest"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Docker push failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Step 4: Updating Container App with new image...${NC}"
az containerapp update \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$REGISTRY_SERVER/wocconwaker:latest"

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Success! Container App updated with your image${NC}"
    echo ""
    APP_URL=$(az containerapp show \
      --name "$CONTAINER_APP" \
      --resource-group "$RESOURCE_GROUP" \
      --query "properties.configuration.ingress.fqdn" \
      --output tsv 2>/dev/null || echo "")
    
    if [ -n "$APP_URL" ]; then
        echo -e "${GREEN}Your app is available at: https://${APP_URL}${NC}"
        echo -e "${GREEN}Health check: https://${APP_URL}/health${NC}"
    fi
else
    echo -e "${RED}Error: Failed to update Container App${NC}"
    exit 1
fi











