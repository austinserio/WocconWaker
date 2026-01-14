#!/bin/bash
# Quick script to check Container App status

echo "Checking Container App status..."
echo ""

az containerapp show \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --query "{
    provisioningState:properties.provisioningState,
    latestRevision:properties.latestRevisionName,
    fqdn:properties.configuration.ingress.fqdn,
    image:properties.template.containers[0].image
  }" \
  --output table

echo ""
echo "Recent revisions:"
az containerapp revision list \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --query "[].{name:name,active:properties.active,healthState:properties.healthState,provisioningState:properties.provisioningState,createdTime:properties.createdTime}" \
  --output table \
  | head -5











