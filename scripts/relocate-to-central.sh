#!/usr/bin/env bash
# Provision Woccon production stack in Central US (co-located with Postgres).
# Does NOT delete or modify East US 2 resources. Run teardown separately.
#
# Usage:
#   ./scripts/relocate-to-central.sh [--dry-run] [--skip-build]
#
# After success, update .env AZURE_* vars (script can patch .env) and:
#   ./scripts/sync-azure-container-env.sh
#   Update Facebook Messenger webhook to the new FQDN/webhook

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

DRY_RUN=false
SKIP_BUILD=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --skip-build) SKIP_BUILD=true ;;
    -h|--help)
      echo "Usage: $0 [--dry-run] [--skip-build]"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

SUB="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID in .env}"
RG="${AZURE_RESOURCE_GROUP:-rg-wocconwaker}"
LOCATION="${AZURE_LOCATION:-centralus}"
ACR_NAME="${AZURE_ACR_NAME:-wocconwakerwicus}"
ENV_NAME="${AZURE_CONTAINER_APP_ENV:-wocconwaker-env-central}"
# Always provision the Central cutover app (ignore legacy East name in .env).
APP_NAME="${AZURE_RELOCATE_APP_NAME:-wocconwaker-app-central}"
IMAGE_TAG="${AZURE_IMAGE_TAG:-latest}"

az account set --subscription "$SUB" >/dev/null

echo "=== Relocate to Central US (no East teardown) ==="
echo "Subscription: $SUB"
echo "Resource group: $RG"
echo "Location:     $LOCATION"
echo "ACR:          $ACR_NAME"
echo "Environment:  $ENV_NAME"
echo "Container app: $APP_NAME"
echo ""

if $DRY_RUN; then
  echo "[dry-run] Would create ACR, env, app, build image, and print next steps."
  exit 0
fi

# --- ACR ---
if ! az acr show --name "$ACR_NAME" --resource-group "$RG" &>/dev/null; then
  echo "Creating ACR $ACR_NAME in $LOCATION..."
  az acr create \
    --name "$ACR_NAME" \
    --resource-group "$RG" \
    --location "$LOCATION" \
    --sku Basic \
    --admin-enabled false \
    --output none
else
  echo "ACR $ACR_NAME already exists."
fi
ACR_SERVER="$(az acr show --name "$ACR_NAME" --resource-group "$RG" --query loginServer -o tsv)"
IMAGE="${ACR_SERVER}/wocconwaker:${IMAGE_TAG}"

if ! $SKIP_BUILD; then
  echo "Building image in ACR (may take ~10 min)..."
  az acr build \
    --registry "$ACR_NAME" \
    --resource-group "$RG" \
    --image "wocconwaker:${IMAGE_TAG}" \
    --file Dockerfile.azure \
    "$ROOT" \
    --output none
else
  echo "Skipping ACR build (--skip-build)."
fi

# --- Container Apps environment ---
if ! az containerapp env show --name "$ENV_NAME" --resource-group "$RG" &>/dev/null; then
  echo "Creating Container Apps environment $ENV_NAME..."
  az containerapp env create \
    --name "$ENV_NAME" \
    --resource-group "$RG" \
    --location "$LOCATION" \
    --output none
else
  echo "Environment $ENV_NAME already exists."
fi

# --- Container app ---
if az containerapp show --name "$APP_NAME" --resource-group "$RG" &>/dev/null; then
  echo "Updating existing Container App $APP_NAME..."
  az containerapp update \
    --name "$APP_NAME" \
    --resource-group "$RG" \
    --image "$IMAGE" \
    --output none
else
  echo "Creating Container App $APP_NAME..."
  az containerapp create \
    --name "$APP_NAME" \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "$IMAGE" \
    --registry-server "$ACR_SERVER" \
    --registry-identity system \
    --cpu 1.0 \
    --memory 2.0Gi \
    --min-replicas 1 \
    --max-replicas 5 \
    --ingress external \
    --target-port 8000 \
    --system-assigned \
    --output none

  PRINCIPAL_ID="$(az containerapp show --name "$APP_NAME" --resource-group "$RG" \
    --query identity.principalId -o tsv)"
  ACR_ID="$(az acr show --name "$ACR_NAME" --resource-group "$RG" --query id -o tsv)"
  if [[ -n "$PRINCIPAL_ID" && -n "$ACR_ID" ]]; then
    echo "Granting AcrPull to container app identity..."
    az role assignment create \
      --assignee "$PRINCIPAL_ID" \
      --role AcrPull \
      --scope "$ACR_ID" \
      --output none 2>/dev/null || true
  fi
fi

FQDN="$(az containerapp show --name "$APP_NAME" --resource-group "$RG" \
  --query properties.configuration.ingress.fqdn -o tsv)"

# Patch .env with Central targets (preserve other keys)
python3 <<PY
from pathlib import Path
import re
root = Path("$ROOT/.env")
lines = root.read_text(encoding="utf-8").splitlines() if root.is_file() else []
updates = {
    "AZURE_LOCATION": "$LOCATION",
    "AZURE_ACR_NAME": "$ACR_NAME",
    "AZURE_CONTAINER_APP_ENV": "$ENV_NAME",
    "AZURE_CONTAINER_APP_NAME": "$APP_NAME",
    "AZURE_CONTAINER_APP_WEBHOOK_URL": "https://${FQDN}/webhook",
}
seen = set()
out = []
for line in lines:
    key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else ""
    if key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, val in updates.items():
    if key not in seen:
        out.append(f"{key}={val}")
root.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
print("Updated .env with Central AZURE_* targets.")
PY

# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"
export AZURE_CONTAINER_APP_NAME="$APP_NAME"

echo ""
echo "Syncing secrets and env to Central Container App..."
"$ROOT/scripts/sync-azure-container-env.sh"

echo ""
echo "=============================================="
echo "Central stack ready (East US 2 unchanged)"
echo "=============================================="
echo "Panel:    https://${FQDN}/panel/login"
echo "API:      https://${FQDN}/api/"
echo "Health:   https://${FQDN}/health"
echo "Webhook:  https://${FQDN}/webhook"
echo ""
echo "Next steps:"
echo "  1. Verify panel login, lexicon (403), library (12 docs)"
echo "  2. Update Facebook Messenger webhook to the URL above"
echo "  3. When satisfied, explicitly request East teardown:"
echo "     ./scripts/teardown-east-resources.sh --confirm"
echo ""
echo "Rollback: keep East app until teardown; revert webhook to:"
echo "  https://wocconwaker-app.icyglacier-d3593e65.eastus2.azurecontainerapps.io/webhook"
