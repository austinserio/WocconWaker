#!/bin/bash
# Manual deployment script for debugging Container App issues

set -e

RG="rg-wocconwaker"
ACR_NAME="wocconwaker1766368936"
APP_NAME="wocconwaker-app"
ENV_NAME="wocconwaker-env"
IMAGE="$ACR_NAME.azurecr.io/wocconwaker:latest"

echo "Creating Container App with manual CLI..."

# Check if app exists and delete it
if az containerapp show --name "$APP_NAME" --resource-group "$RG" &>/dev/null; then
    echo "Deleting existing app..."
    az containerapp delete --name "$APP_NAME" --resource-group "$RG" --yes
    sleep 10
fi

# Create the container app with proper configuration
az containerapp create \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --environment "$ENV_NAME" \
  --image "$IMAGE" \
  --registry-server "$ACR_NAME.azurecr.io" \
  --registry-identity system \
  --cpu 1.0 \
  --memory 2.0Gi \
  --min-replicas 0 \
  --max-replicas 10 \
  --ingress external \
  --target-port 8000 \
  --env-vars \
    WOCCON_MODE=server \
    OLLAMA_CLOUD_ENDPOINT=https://api.ollama.com \
    OLLAMA_MODEL=llama3:8b \
    PORT=8000 \
  --system-assigned

echo "Waiting for app to be created..."
sleep 5

# Get the managed identity principal ID
PRINCIPAL_ID=$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --query "identity.principalId" \
  --output tsv)

echo "Principal ID: $PRINCIPAL_ID"

# Grant ACR pull permission
echo "Granting ACR pull permission..."
az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role AcrPull \
  --scope "/subscriptions/58587a07-da50-4691-aa9c-f23859d66df3/resourceGroups/$RG/providers/Microsoft.ContainerRegistry/registries/$ACR_NAME"

echo "Deployment complete!"
echo ""
echo "Check status:"
echo "  az containerapp show --name $APP_NAME --resource-group $RG"
echo "  az containerapp logs show --name $APP_NAME --resource-group $RG --follow"
