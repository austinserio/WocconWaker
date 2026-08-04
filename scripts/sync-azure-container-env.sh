#!/usr/bin/env bash
# Sync .env values to Azure Container App (wocconwaker-app-central).
# Secrets go to Container App secrets; other vars as plain env.
# Usage: ./scripts/sync-azure-container-env.sh [--dry-run]
#
# Requires: az CLI, logged in; AZURE_* in .env

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

APP="${AZURE_CONTAINER_APP_NAME:-wocconwaker-app-central}"
RG="${AZURE_RESOURCE_GROUP:-rg-wocconwaker}"
SUB="${AZURE_SUBSCRIPTION_ID:-}"

if [[ -z "$SUB" ]]; then
  echo "Set AZURE_SUBSCRIPTION_ID in .env" >&2
  exit 1
fi

az account set --subscription "$SUB" >/dev/null

FQDN="$(az containerapp show --name "$APP" --resource-group "$RG" \
  --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || true)"
if [[ -z "$FQDN" ]]; then
  echo "Container app $APP not found in $RG" >&2
  exit 1
fi

# Always use the Container App FQDN for invite links in Azure (ignore localhost from .env).
PANEL_PUBLIC_BASE_URL="https://${FQDN}"
PANEL_CORS_ORIGINS="https://${FQDN}"
PUBLIC_WEBHOOK_BASE_URL="https://${FQDN}"
AZURE_CONTAINER_APP_WEBHOOK_URL="https://${FQDN}"

echo "=== Sync Azure Container App env ==="
echo "App:     $APP"
echo "Group:   $RG"
echo "URL:     https://${FQDN}"
echo "Panel:   ${PANEL_PUBLIC_BASE_URL}/panel/"
echo ""

# --- secrets (name=value for az containerapp secret set) ---
SECRET_ARGS=()
add_secret() {
  local name="$1"
  local val="$2"
  [[ -z "$val" ]] && return
  # Trim whitespace/newlines — common cause of Messenger send failures in Azure.
  val="$(printf '%s' "$val" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -z "$val" ]] && return
  SECRET_ARGS+=("${name}=${val}")
}

add_secret "jwt-secret" "${JWT_SECRET:-}"
add_secret "smtp-password" "${SMTP_PASSWORD:-}"
add_secret "foundry-api-key" "${FOUNDRY_API_KEY:-}"
add_secret "anthropic-api-key" "${ANTHROPIC_API_KEY:-}"
add_secret "panel-admin-password" "${PANEL_ADMIN_PASSWORD:-}"
add_secret "page-access-token" "${PAGE_ACCESS_TOKEN:-}"
add_secret "ingest-drive-secret" "${INGEST_DRIVE_SECRET:-}"

# Postgres for production: prefer POSTGRES_DATABASE_URL (local .env can keep sqlite DATABASE_URL)
AZURE_DB_URL="${POSTGRES_DATABASE_URL:-}"
if [[ -z "$AZURE_DB_URL" && "${DATABASE_URL:-}" == postgresql* ]]; then
  AZURE_DB_URL="${DATABASE_URL}"
fi
if [[ -n "$AZURE_DB_URL" && "$AZURE_DB_URL" == postgresql* ]]; then
  add_secret "database-url" "$AZURE_DB_URL"
fi

# --- plain env vars (aligned with local .env) ---
ENV_VARS=(
  "WOCCON_MODE=${WOCCON_MODE:-server}"
  "PORT=${PORT:-8000}"
  "LOCAL_LLM=${LOCAL_LLM:-false}"
  "OLLAMA_URL=${OLLAMA_URL:-}"
  "OLLAMA_MODEL=${OLLAMA_MODEL:-}"
  "OLLAMA_VISION_MODEL=${OLLAMA_VISION_MODEL:-}"
  "EXTRACT_PARALLEL_WORKERS=${EXTRACT_PARALLEL_WORKERS:-3}"
  "PDF_OCR_PARALLEL_WORKERS=${PDF_OCR_PARALLEL_WORKERS:-2}"
  "PDF_OCR_UNLOAD_TEXT_MODEL=${PDF_OCR_UNLOAD_TEXT_MODEL:-true}"
  "PDF_OCR_UNLOAD_VISION_MODEL=${PDF_OCR_UNLOAD_VISION_MODEL:-false}"
  "ENABLE_TYPING_INDICATORS=${ENABLE_TYPING_INDICATORS:-false}"
  "FOUNDRY_ENDPOINT=${FOUNDRY_ENDPOINT:-}"
  "FOUNDRY_DEPLOYMENT=${FOUNDRY_DEPLOYMENT:-}"
  "FOUNDRY_API_VERSION=${FOUNDRY_API_VERSION:-2024-05-01-preview}"
  "FOUNDRY_INFERENCE_API_VERSION=${FOUNDRY_INFERENCE_API_VERSION:-2024-05-01-preview}"
  "ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-}"
  "VERIFY_TOKEN=${VERIFY_TOKEN:-}"
  "DRIVE_FOLDER_ID=${DRIVE_FOLDER_ID:-}"
  "WOCCON_DICTIONARY_PATH=${WOCCON_DICTIONARY_PATH:-woccon_language/dictionary_unified.json}"
  "WOCCON_RULES_PATH=${WOCCON_RULES_PATH:-woccon_language/rules_unified.json}"
  "JWT_EXPIRE_MINUTES=${JWT_EXPIRE_MINUTES:-1440}"
  "PANEL_ADMIN_EMAIL=${PANEL_ADMIN_EMAIL:-}"
  "PANEL_CORS_ORIGINS=${PANEL_CORS_ORIGINS}"
  "PANEL_PUBLIC_BASE_URL=${PANEL_PUBLIC_BASE_URL}"
  "PUBLIC_WEBHOOK_BASE_URL=${PUBLIC_WEBHOOK_BASE_URL}"
  "AZURE_CONTAINER_APP_WEBHOOK_URL=${AZURE_CONTAINER_APP_WEBHOOK_URL}"
  "WOCCON_UPLOAD_DIR=${WOCCON_UPLOAD_DIR:-data/uploads}"
  "INGEST_SOURCES_DIR=${INGEST_SOURCES_DIR:-data/ingest_sources}"
  "INGEST_TEXT_CACHE_DIR=${INGEST_TEXT_CACHE_DIR:-data/ingest_text_cache}"
  "DUPLICATE_THRESHOLD=${DUPLICATE_THRESHOLD:-0.85}"
  "PANEL_IMPORT_COMMUNITY=${PANEL_IMPORT_COMMUNITY:-false}"
  "EMAIL_MODE=${EMAIL_MODE:-log}"
  "SMTP_HOST=${SMTP_HOST:-}"
  "SMTP_PORT=${SMTP_PORT:-587}"
  "SMTP_USER=${SMTP_USER:-}"
  "SMTP_FROM=${SMTP_FROM:-}"
  "SMTP_USE_TLS=${SMTP_USE_TLS:-true}"
  "INVITE_EXPIRE_HOURS=${INVITE_EXPIRE_HOURS:-168}"
  "PASSWORD_RESET_EXPIRE_HOURS=${PASSWORD_RESET_EXPIRE_HOURS:-24}"
  "WOCCON_BASE_VOCAB_DRIVE_ID=${WOCCON_BASE_VOCAB_DRIVE_ID:-}"
  "WOCCON_PRONUNCIATION_DRIVE_ID=${WOCCON_PRONUNCIATION_DRIVE_ID:-}"
)

# Secret references (must match secret names above)
[[ -n "${FOUNDRY_API_KEY:-}" ]] && ENV_VARS+=("FOUNDRY_API_KEY=secretref:foundry-api-key")
[[ -n "${ANTHROPIC_API_KEY:-}" ]] && ENV_VARS+=("ANTHROPIC_API_KEY=secretref:anthropic-api-key")
[[ -n "${JWT_SECRET:-}" ]] && ENV_VARS+=("JWT_SECRET=secretref:jwt-secret")
[[ -n "${SMTP_PASSWORD:-}" ]] && ENV_VARS+=("SMTP_PASSWORD=secretref:smtp-password")
[[ -n "${PANEL_ADMIN_PASSWORD:-}" ]] && ENV_VARS+=("PANEL_ADMIN_PASSWORD=secretref:panel-admin-password")
[[ -n "${PAGE_ACCESS_TOKEN:-}" ]] && ENV_VARS+=("PAGE_ACCESS_TOKEN=secretref:page-access-token")
[[ -n "${INGEST_DRIVE_SECRET:-}" ]] && ENV_VARS+=("INGEST_DRIVE_SECRET=secretref:ingest-drive-secret")
if [[ -n "$AZURE_DB_URL" && "$AZURE_DB_URL" == postgresql* ]]; then
  ENV_VARS+=("DATABASE_URL=secretref:database-url")
else
  ENV_VARS+=("DATABASE_URL=${DATABASE_URL:-sqlite:///./data/woccon.db}")
fi

if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" && -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]]; then
  echo "NOTE: GOOGLE_APPLICATION_CREDENTIALS is a local file path."
  echo "      Drive ingest in Azure needs the JSON mounted or a different secret strategy."
  echo "      Not syncing that path to Container Apps."
  echo ""
fi

if [[ -z "$AZURE_DB_URL" || "$AZURE_DB_URL" == sqlite* ]]; then
  echo "NOTE: No POSTGRES_DATABASE_URL set. Container will use SQLite (ephemeral unless you mount a volume)."
  echo "      Run ./scripts/setup-azure-postgres.sh and set POSTGRES_DATABASE_URL in .env."
  echo ""
elif [[ "$AZURE_DB_URL" == postgresql* ]]; then
  echo "Database: PostgreSQL via secret database-url"
  echo ""
fi

if $DRY_RUN; then
  echo "[dry-run] Would set secrets (${#SECRET_ARGS[@]}): ${SECRET_ARGS[*]//=*/=***}"
  echo "[dry-run] Would set env vars (${#ENV_VARS[@]} keys)"
  exit 0
fi

if [[ ${#SECRET_ARGS[@]} -gt 0 ]]; then
  echo "Updating Container App secrets..."
  az containerapp secret set \
    --name "$APP" \
    --resource-group "$RG" \
    --secrets "${SECRET_ARGS[@]}" \
    --output none
fi

echo "Updating Container App environment..."
az containerapp update \
  --name "$APP" \
  --resource-group "$RG" \
  --set-env-vars "${ENV_VARS[@]}" \
  --output none

echo ""
echo "Done. New revision should include:"
echo "  Control panel API: https://${FQDN}/api/"
echo "  Control panel UI:  https://${FQDN}/panel/login"
echo "  Health:            https://${FQDN}/health"
echo ""
echo "If the image predates panel/dist, rebuild and deploy: docker build -f Dockerfile.azure ..."
