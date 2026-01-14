#!/bin/bash
# Quick script to check Azure deployment status

echo "Checking deployment status..."
echo ""

# Get the latest deployment
DEPLOYMENT_NAME=$(az deployment group list \
  --resource-group rg-wocconwaker \
  --query "[0].name" \
  --output tsv 2>/dev/null)

if [ -z "$DEPLOYMENT_NAME" ]; then
  echo "No deployment found. The deployment might still be starting..."
  exit 1
fi

echo "Deployment: $DEPLOYMENT_NAME"
echo ""

# Check deployment status
az deployment group show \
  --resource-group rg-wocconwaker \
  --name "$DEPLOYMENT_NAME" \
  --query "{provisioningState:properties.provisioningState,correlationId:properties.correlationId}" \
  --output table

echo ""
echo "For detailed progress, run:"
echo "az deployment operation group list --resource-group rg-wocconwaker --name $DEPLOYMENT_NAME"











