#!/usr/bin/env bash
# Delete East US 2 Container Apps resources after Central cutover is validated.
# Does NOT delete Postgres (Central) or Foundry (woccon-foundry-rg).
#
# Usage:
#   ./scripts/teardown-east-resources.sh --confirm
#
# Requires typing the resource group name to prevent accidents.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

CONFIRM=false
for arg in "$@"; do
  case "$arg" in
    --confirm) CONFIRM=true ;;
    -h|--help)
      echo "Usage: $0 --confirm"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

if ! $CONFIRM; then
  echo "Refusing to delete anything without --confirm" >&2
  echo "This removes East US 2: textbelt, wocconwaker-app, wocconwaker-env, wocconwakerwi ACR, orphan workspace." >&2
  exit 1
fi

SUB="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID in .env}"
RG="${AZURE_RESOURCE_GROUP:-rg-wocconwaker}"
EAST_APP="${AZURE_EAST_APP_NAME:-wocconwaker-app}"
EAST_ENV="${AZURE_EAST_ENV_NAME:-wocconwaker-env}"
EAST_ACR="${AZURE_EAST_ACR_NAME:-wocconwakerwi}"
TEXTBELT_APP="${AZURE_TEXTBELT_APP_NAME:-textbelt}"
WORKSPACE="${AZURE_EAST_WORKSPACE_NAME:-workspace-rgwocconwakertACm}"

az account set --subscription "$SUB" >/dev/null

echo "=== Teardown East US 2 resources in $RG ==="
echo "Will NOT delete: woccon-pg (Postgres), woccon-foundry-rg"
echo ""
read -r -p "Type resource group name to confirm deletion [$RG]: " TYPED
if [[ "$TYPED" != "$RG" ]]; then
  echo "Aborted (resource group mismatch)." >&2
  exit 1
fi

delete_if_exists() {
  local kind="$1"
  local name="$2"
  shift 2
  if "$@" show --name "$name" --resource-group "$RG" &>/dev/null; then
    echo "Deleting $kind $name..."
    "$@" delete --name "$name" --resource-group "$RG" --yes --output none
  else
    echo "Skip $kind $name (not found)"
  fi
}

delete_if_exists "Container App" "$TEXTBELT_APP" az containerapp
delete_if_exists "Container App" "$EAST_APP" az containerapp
delete_if_exists "Container Apps env" "$EAST_ENV" az containerapp env
delete_if_exists "ACR" "$EAST_ACR" az acr

if az monitor log-analytics workspace show --resource-group "$RG" --workspace-name "$WORKSPACE" &>/dev/null; then
  echo "Deleting Log Analytics workspace $WORKSPACE..."
  az monitor log-analytics workspace delete \
    --resource-group "$RG" \
    --workspace-name "$WORKSPACE" \
    --yes \
    --force \
    --output none 2>/dev/null || echo "Note: workspace delete may fail if still linked; remove manually in portal."
else
  echo "Skip workspace $WORKSPACE (not found)"
fi

echo ""
echo "East teardown complete. Central app should be your production target."
echo "Foundry remains in woccon-foundry-rg (East US 2)."
