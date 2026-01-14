#!/bin/bash
# Azure deployment script for WocconWaker
# This script helps deploy WocconWaker to Azure Container Apps

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}WocconWaker Azure Deployment Script${NC}"
echo "=========================================="

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo -e "${RED}Error: Azure CLI is not installed.${NC}"
    echo "Install it from: https://docs.microsoft.com/cli/azure/install-azure-cli"
    exit 1
fi

# Check if Docker is installed and running
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed.${NC}"
    echo "Install Docker Desktop from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}Error: Docker daemon is not running.${NC}"
    echo ""
    echo "Please start Docker Desktop and wait for it to be ready, then run this script again."
    echo ""
    echo "On macOS:"
    echo "  1. Open Docker Desktop application"
    echo "  2. Wait for the Docker icon in the menu bar to show it's running"
    echo "  3. Run this script again"
    exit 1
fi

# Check if logged in
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}Not logged in to Azure. Logging in...${NC}"
    az login
fi

# Set subscription (from repo rules)
SUBSCRIPTION_ID="58587a07-da50-4691-aa9c-f23859d66df3"
echo -e "${GREEN}Setting subscription to: ${SUBSCRIPTION_ID}${NC}"
az account set --subscription "$SUBSCRIPTION_ID"

# Configuration
RESOURCE_GROUP="rg-wocconwaker"
LOCATION="eastus"
CONTAINER_APP_ENV="wocconwaker-env"
CONTAINER_APP="wocconwaker-app"
CONTAINER_REGISTRY="wocconwaker$(date +%s)"

# Prompt for required values
echo ""
echo -e "${YELLOW}Enter Ollama Cloud configuration:${NC}"
echo "Press Enter to accept defaults (shown in brackets)"
echo ""
read -p "Ollama Cloud Endpoint [https://api.ollama.com]: " OLLAMA_CLOUD_ENDPOINT
OLLAMA_CLOUD_ENDPOINT=${OLLAMA_CLOUD_ENDPOINT:-https://api.ollama.com}
read -sp "Ollama Cloud API Key (input hidden for security): " OLLAMA_CLOUD_API_KEY
echo ""
read -p "Ollama Model [llama3:8b]: " OLLAMA_MODEL
OLLAMA_MODEL=${OLLAMA_MODEL:-llama3:8b}

echo ""
read -p "Facebook Page Access Token (optional, press Enter to skip): " PAGE_ACCESS_TOKEN
read -p "Facebook Verify Token (optional, press Enter to skip): " VERIFY_TOKEN

# Create resource group
echo ""
echo -e "${GREEN}Creating resource group: ${RESOURCE_GROUP}${NC}"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" || echo "Resource group already exists"

# Deploy infrastructure first (without image)
echo ""
echo -e "${GREEN}Deploying infrastructure using Bicep template (without image - we'll add it after building)...${NC}"
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file azure-deploy.bicep \
  --parameters \
    containerRegistryName="$CONTAINER_REGISTRY" \
    ollamaCloudEndpoint="$OLLAMA_CLOUD_ENDPOINT" \
    ollamaCloudApiKey="$OLLAMA_CLOUD_API_KEY" \
    ollamaModel="$OLLAMA_MODEL" \
    pageAccessToken="${PAGE_ACCESS_TOKEN:-}" \
    verifyToken="${VERIFY_TOKEN:-}" \
    dockerImage="" \
  --no-wait

echo ""
echo -e "${YELLOW}Infrastructure deployment started in background...${NC}"
echo "Waiting for Container Registry to be created..."
sleep 10

# Get Container Registry login server
REGISTRY_SERVER=$(az acr show --name "$CONTAINER_REGISTRY" --resource-group "$RESOURCE_GROUP" --query loginServer --output tsv 2>/dev/null)

if [ -z "$REGISTRY_SERVER" ]; then
    echo -e "${YELLOW}Waiting for Container Registry to be ready...${NC}"
    for i in {1..30}; do
        sleep 5
        REGISTRY_SERVER=$(az acr show --name "$CONTAINER_REGISTRY" --resource-group "$RESOURCE_GROUP" --query loginServer --output tsv 2>/dev/null)
        if [ -n "$REGISTRY_SERVER" ]; then
            break
        fi
        echo "  Attempt $i/30..."
    done
fi

if [ -z "$REGISTRY_SERVER" ]; then
    echo -e "${RED}Error: Could not get Container Registry server. Please check the deployment status.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Container Registry: ${REGISTRY_SERVER}${NC}"

# Build and push Docker image
echo ""
echo -e "${GREEN}Building and pushing Docker image...${NC}"
echo "Step 1: Logging into Azure Container Registry..."
if ! az acr login --name "$CONTAINER_REGISTRY"; then
    echo -e "${RED}Error: Failed to login to Container Registry${NC}"
    exit 1
fi

echo ""
echo "Step 2: Building Docker image..."
docker build -t "$REGISTRY_SERVER/wocconwaker:latest" .

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Docker build failed${NC}"
    exit 1
fi

echo ""
echo "Step 3: Pushing Docker image to registry..."
docker push "$REGISTRY_SERVER/wocconwaker:latest"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Docker push failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Image pushed successfully!${NC}"

# Wait for infrastructure deployment to complete
echo ""
echo -e "${YELLOW}Waiting for infrastructure deployment to complete...${NC}"
az deployment group wait \
  --resource-group "$RESOURCE_GROUP" \
  --name "azure-deploy" \
  --created \
  --timeout 15m

# Update Container App with the image
echo ""
echo -e "${GREEN}Updating Container App with Docker image...${NC}"
az containerapp update \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$REGISTRY_SERVER/wocconwaker:latest"

# Get Container App URL
echo ""
echo -e "${GREEN}Getting Container App URL...${NC}"
APP_URL=$(az containerapp show \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv 2>/dev/null || echo "")

if [ -n "$APP_URL" ]; then
    echo -e "${GREEN}Container App URL: https://${APP_URL}${NC}"
    echo -e "${GREEN}Health check: https://${APP_URL}/health${NC}"
else
    echo -e "${YELLOW}Container App URL not available yet. Check the Azure portal.${NC}"
fi

echo ""
echo -e "${GREEN}Deployment complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Build and push your Docker image to the Container Registry"
echo "2. Update the Container App to use the new image"
echo "3. Configure your Facebook Messenger webhook to point to: https://${APP_URL}/webhook"

