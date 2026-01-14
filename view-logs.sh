#!/bin/bash
# View Container App logs with better formatting

echo "Fetching recent logs (last 100 lines)..."
echo ""

az containerapp logs show \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --tail 100 \
  --type console 2>&1 | \
  while IFS= read -r line; do
    if [[ $line == *'"Log":'* ]]; then
      log_msg=$(echo "$line" | sed 's/.*"Log": "\([^"]*\)".*/\1/')
      if [[ -n "$log_msg" && "$log_msg" != *"Connecting"* && "$log_msg" != *"Successfully Connected"* ]]; then
        echo "$log_msg"
      fi
    fi
  done | tail -50
