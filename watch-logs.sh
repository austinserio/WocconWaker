#!/bin/bash
# Watch Container App logs in real-time

echo "Watching WocconWaker logs (Ctrl+C to stop)..."
echo ""

az containerapp logs show \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --follow \
  --type console 2>&1 | grep -E "F " | sed 's/.*"Log": "\([^"]*\)".*/\1/' | grep -v "Connecting\|Successfully Connected"

