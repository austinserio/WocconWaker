#!/bin/bash
# Quick monitoring script for WocconWaker deployment

APP_NAME="wocconwaker-app"
RESOURCE_GROUP="rg-wocconwaker"
APP_URL="wocconwaker-app.ambitiousbush-8d24e4e0.eastus.azurecontainerapps.io"

echo "=========================================="
echo "WocconWaker Deployment Monitor"
echo "=========================================="
echo ""

echo "📊 Container App Status:"
az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "{name:name, fqdn:properties.configuration.ingress.fqdn, provisioningState:properties.provisioningState, latestRevision:properties.latestRevisionName}" \
  -o json

echo ""
echo "📈 Revision Status:"
az containerapp revision list \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "[0].{name:name, active:properties.active, replicas:properties.replicas, healthState:properties.healthState}" \
  -o json

echo ""
echo "📝 Recent Logs (last 20 lines):"
az containerapp logs show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --tail 20 \
  --type console 2>/dev/null | tail -20 || echo "No logs available yet"

echo ""
echo "🏥 Health Check:"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://${APP_URL}/health" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" == "200" ]; then
    echo "✅ Health endpoint responding (HTTP $HTTP_CODE)"
    curl -s --max-time 10 "https://${APP_URL}/health" | python3 -m json.tool 2>/dev/null || curl -s --max-time 10 "https://${APP_URL}/health"
else
    echo "⏳ Health endpoint not ready yet (HTTP $HTTP_CODE)"
    echo "   This is normal - Ollama is still starting/pulling model"
fi

echo ""
echo "=========================================="
echo "Webhook URL: https://${APP_URL}/webhook"
echo "=========================================="



