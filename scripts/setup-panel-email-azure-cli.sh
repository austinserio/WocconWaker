#!/usr/bin/env bash
# Panel email setup helper — prints SMTP env vars for .env and Azure Container Apps.
# App code uses stdlib SMTP only (EMAIL_MODE=smtp). Fastest Azure path: SendGrid SMTP.
#
# Usage:
#   ./scripts/setup-panel-email-azure-cli.sh
#
# Requires in .env: AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP (optional for ACS notes)

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

echo "=== Woccon panel email setup ==="
echo ""
echo "The control panel sends invite and password-reset mail via SMTP (see panel_api/services/email.py)."
echo "For local dev, leave SMTP unset and use EMAIL_MODE=log (links print to server logs)."
echo ""

if [ -n "${AZURE_SUBSCRIPTION_ID:-}" ]; then
  echo "Azure subscription: $AZURE_SUBSCRIPTION_ID"
  az account set --subscription "$AZURE_SUBSCRIPTION_ID" 2>/dev/null || true
  echo ""
fi

echo "--- Recommended: SendGrid SMTP (Azure Marketplace) ---"
echo "1. Portal: Create resource → search 'SendGrid' → Create account (Free tier)."
echo "2. In SendGrid: Settings → API Keys → Create API Key (Mail Send)."
echo "3. Use these values in .env or Container App secrets:"
echo ""
cat <<'EOF'
EMAIL_MODE=smtp
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=<your-sendgrid-api-key>
SMTP_FROM=noreply@your-verified-sender-domain.com
SMTP_USE_TLS=true
PANEL_PUBLIC_BASE_URL=https://<your-container-app-fqdn>
EOF
echo ""

echo "--- Alternative: Microsoft 365 / Outlook SMTP ---"
cat <<'EOF'
EMAIL_MODE=smtp
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=<mailbox@yourdomain.com>
SMTP_PASSWORD=<app-password>
SMTP_FROM=<mailbox@yourdomain.com>
SMTP_USE_TLS=true
EOF
echo ""

echo "--- Optional: Azure Communication Services Email (REST; not used by app v1) ---"
echo "If you prefer ACS later, provision with:"
echo "  az extension add --name communication"
echo "  az communication create --name <acs-name> --resource-group <rg> --location <loc> --data-location UnitedStates"
echo "  az communication email create --name <email-service> --resource-group <rg> --location global --data-location UnitedStates"
echo "Domain DNS verification is manual in Azure Portal. Until ACS SMTP/SDK is wired, use SendGrid above."
echo ""

if [ -n "${AZURE_RESOURCE_GROUP:-}" ] && [ -n "${AZURE_CONTAINER_APP_NAME:-}" ]; then
  echo "--- Container App secret commands (fill values first) ---"
  echo "az containerapp secret set -g $AZURE_RESOURCE_GROUP -n $AZURE_CONTAINER_APP_NAME \\"
  echo "  --secrets smtp-password=<sendgrid-api-key> jwt-secret=<random>"
  echo ""
  echo "az containerapp update -g $AZURE_RESOURCE_GROUP -n $AZURE_CONTAINER_APP_NAME \\"
  echo "  --set-env-vars EMAIL_MODE=smtp SMTP_HOST=smtp.sendgrid.net SMTP_PORT=587 SMTP_USER=apikey \\"
  echo "  SMTP_FROM=noreply@yourdomain.com PANEL_PUBLIC_BASE_URL=https://<fqdn> \\"
  echo "  SMTP_PASSWORD=secretref:smtp-password"
  echo ""
else
  echo "Set AZURE_RESOURCE_GROUP and AZURE_CONTAINER_APP_NAME in .env to print containerapp secret commands."
fi

echo "Done. See docs/CONTROL_PANEL.md for team invites and production checklist."
