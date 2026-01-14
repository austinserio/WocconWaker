#!/bin/bash
# Check for recent errors in Container App logs

echo "Checking for recent errors (last 200 lines)..."
echo ""

az containerapp logs show \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --tail 200 \
  --type console 2>&1 | \
  grep -E "(ERROR|Error|error|Traceback|Exception|❌|🚨)" -A 3 | \
  tail -50



