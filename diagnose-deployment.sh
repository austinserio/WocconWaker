#!/bin/bash
# Comprehensive diagnostic script for Azure Container App deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

RESOURCE_GROUP="rg-wocconwaker"
APP_NAME="wocconwaker-app"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}WocconWaker Deployment Diagnostics${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo -e "${RED}Error: Azure CLI is not installed${NC}"
    exit 1
fi

# Check if logged in
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}Not logged in to Azure. Logging in...${NC}"
    az login
fi

# Set subscription
SUBSCRIPTION_ID="58587a07-da50-4691-aa9c-f23859d66df3"
echo -e "${GREEN}Setting subscription to: ${SUBSCRIPTION_ID}${NC}"
az account set --subscription "$SUBSCRIPTION_ID"
echo ""

# 1. Check Container App status
echo -e "${BLUE}1. Container App Status:${NC}"
if az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" &>/dev/null; then
    echo -e "${GREEN}✓ Container App exists${NC}"
    
    # Get provisioning state
    PROV_STATE=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.provisioningState" \
        --output tsv 2>/dev/null || echo "unknown")
    
    echo "  Provisioning State: $PROV_STATE"
    
    # Get latest revision
    LATEST_REV=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.latestRevisionName" \
        --output tsv 2>/dev/null || echo "unknown")
    
    echo "  Latest Revision: $LATEST_REV"
    
    # Get FQDN
    FQDN=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.configuration.ingress.fqdn" \
        --output tsv 2>/dev/null || echo "unknown")
    
    echo "  FQDN: $FQDN"
    
    # Get image
    IMAGE=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.template.containers[0].image" \
        --output tsv 2>/dev/null || echo "unknown")
    
    echo "  Image: $IMAGE"
    
    # Get resource allocation
    CPU=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.template.containers[0].resources.cpu" \
        --output tsv 2>/dev/null || echo "unknown")
    
    MEMORY=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.template.containers[0].resources.memory" \
        --output tsv 2>/dev/null || echo "unknown")
    
    echo "  CPU: $CPU"
    echo "  Memory: $MEMORY"
    
    # Get replica status
    MIN_REPLICAS=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.template.scale.minReplicas" \
        --output tsv 2>/dev/null || echo "unknown")
    
    MAX_REPLICAS=$(az containerapp show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.template.scale.maxReplicas" \
        --output tsv 2>/dev/null || echo "unknown")
    
    echo "  Replicas: $MIN_REPLICAS - $MAX_REPLICAS"
    
else
    echo -e "${RED}✗ Container App does not exist${NC}"
fi

echo ""

# 2. Check revision health
echo -e "${BLUE}2. Revision Health:${NC}"
if [ "$LATEST_REV" != "unknown" ]; then
    REV_HEALTH=$(az containerapp revision show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --revision "$LATEST_REV" \
        --query "properties.healthState" \
        --output tsv 2>/dev/null || echo "unknown")
    
    if [ "$REV_HEALTH" == "Healthy" ]; then
        echo -e "${GREEN}✓ Revision is Healthy${NC}"
    else
        echo -e "${YELLOW}⚠ Revision Health: $REV_HEALTH${NC}"
    fi
    
    # Get active replicas
    ACTIVE_REPLICAS=$(az containerapp revision show \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --revision "$LATEST_REV" \
        --query "properties.replicas" \
        --output tsv 2>/dev/null || echo "0")
    
    echo "  Active Replicas: $ACTIVE_REPLICAS"
else
    echo -e "${YELLOW}⚠ Cannot check revision health (revision unknown)${NC}"
fi

echo ""

# 3. Check environment variables
echo -e "${BLUE}3. Environment Variables:${NC}"
ENV_VARS=$(az containerapp show \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.template.containers[0].env" \
    --output json 2>/dev/null || echo "[]")

if [ "$ENV_VARS" != "[]" ]; then
    echo "$ENV_VARS" | jq -r '.[] | "  \(.name): \(if .secretRef then "[SECRET: \(.secretRef)]" else .value end)"' 2>/dev/null || echo "  (Unable to parse env vars)"
    
    # Check for critical env vars
    HAS_OLLAMA_CLOUD_KEY=$(echo "$ENV_VARS" | jq -r '.[] | select(.name == "OLLAMA_CLOUD_API_KEY" or .secretRef == "ollama-cloud-api-key") | .name' 2>/dev/null || echo "")
    if [ -n "$HAS_OLLAMA_CLOUD_KEY" ]; then
        echo -e "${GREEN}✓ Ollama Cloud API key is configured${NC}"
    else
        echo -e "${YELLOW}⚠ Ollama Cloud API key not found${NC}"
    fi
    
    HAS_OLLAMA_ENDPOINT=$(echo "$ENV_VARS" | jq -r '.[] | select(.name == "OLLAMA_CLOUD_ENDPOINT") | .value' 2>/dev/null || echo "")
    if [ -n "$HAS_OLLAMA_ENDPOINT" ]; then
        echo -e "${GREEN}✓ Ollama Cloud endpoint: $HAS_OLLAMA_ENDPOINT${NC}"
    else
        echo -e "${YELLOW}⚠ Ollama Cloud endpoint not configured${NC}"
    fi
else
    echo -e "${YELLOW}⚠ No environment variables found${NC}"
fi

echo ""

# 4. Check logs (recent errors)
echo -e "${BLUE}4. Recent Logs (last 20 lines):${NC}"
echo -e "${YELLOW}Fetching logs...${NC}"
az containerapp logs show \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --tail 20 \
    --type console 2>/dev/null | tail -20 || echo -e "${YELLOW}  (Unable to fetch logs)${NC}"

echo ""
echo ""

# 5. Test health endpoint
echo -e "${BLUE}5. Health Endpoint Test:${NC}"
if [ "$FQDN" != "unknown" ] && [ -n "$FQDN" ]; then
    HEALTH_URL="https://${FQDN}/health"
    echo "  Testing: $HEALTH_URL"
    
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$HEALTH_URL" 2>/dev/null || echo "000")
    
    if [ "$HTTP_CODE" == "200" ]; then
        echo -e "${GREEN}✓ Health endpoint is responding (HTTP $HTTP_CODE)${NC}"
        HEALTH_RESPONSE=$(curl -s --max-time 10 "$HEALTH_URL" 2>/dev/null || echo "")
        echo "  Response: $HEALTH_RESPONSE"
    elif [ "$HTTP_CODE" == "000" ]; then
        echo -e "${RED}✗ Health endpoint is not reachable (timeout or connection error)${NC}"
    else
        echo -e "${YELLOW}⚠ Health endpoint returned HTTP $HTTP_CODE${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Cannot test health endpoint (FQDN unknown)${NC}"
fi

echo ""

# 6. Summary and recommendations
echo -e "${BLUE}6. Summary and Recommendations:${NC}"
echo ""

ISSUES=0

if [ "$PROV_STATE" != "Succeeded" ]; then
    echo -e "${RED}✗ Issue: Container App provisioning state is not Succeeded${NC}"
    ISSUES=$((ISSUES + 1))
fi

if [ "$REV_HEALTH" != "Healthy" ] && [ "$REV_HEALTH" != "unknown" ]; then
    echo -e "${RED}✗ Issue: Revision is not healthy${NC}"
    ISSUES=$((ISSUES + 1))
fi

if [ "$ACTIVE_REPLICAS" == "0" ] && [ "$MIN_REPLICAS" == "0" ]; then
    echo -e "${YELLOW}⚠ Note: App is scaled to zero (minReplicas=0). It will start on first request.${NC}"
fi

if [ "$CPU" == "1.0" ]; then
    echo -e "${YELLOW}⚠ Recommendation: Consider increasing CPU to 1.5 for better performance${NC}"
fi

if [ "$MEMORY" == "2.0Gi" ] || [ "$MEMORY" == "2Gi" ]; then
    echo -e "${YELLOW}⚠ Recommendation: Consider increasing memory to 3.0Gi for better stability${NC}"
fi

if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✓ No critical issues detected${NC}"
else
    echo -e "${RED}✗ Found $ISSUES critical issue(s)${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Diagnostics Complete${NC}"
echo -e "${BLUE}========================================${NC}"




