#!/usr/bin/env bash
# Provision Azure Database for PostgreSQL Flexible Server for WocconWaker production.
# Usage:
#   ./scripts/setup-azure-postgres.sh              # create server + DB + firewall rules
#   ./scripts/setup-azure-postgres.sh --add-my-ip  # only refresh client IP firewall rule
#   ./scripts/setup-azure-postgres.sh --dry-run
#
# Requires: az CLI, logged in; AZURE_SUBSCRIPTION_ID and AZURE_RESOURCE_GROUP in .env

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

DRY_RUN=false
ADD_MY_IP_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --add-my-ip) ADD_MY_IP_ONLY=true ;;
    -h|--help)
      echo "Usage: $0 [--dry-run] [--add-my-ip]"
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
# eastus2 is often restricted for Flexible Server; override with AZURE_POSTGRES_LOCATION if needed.
LOCATION="${AZURE_POSTGRES_LOCATION:-centralus}"
SERVER="${AZURE_POSTGRES_SERVER:-woccon-pg}"
DB_NAME="${AZURE_POSTGRES_DB:-woccon}"
ADMIN_USER="${AZURE_POSTGRES_ADMIN_USER:-wocconadmin}"
SKU="${AZURE_POSTGRES_SKU:-Standard_B1ms}"
TIER="${AZURE_POSTGRES_TIER:-Burstable}"
VERSION="${AZURE_POSTGRES_VERSION:-16}"
STORAGE_GB="${AZURE_POSTGRES_STORAGE_GB:-32}"

az account set --subscription "$SUB" >/dev/null

_my_public_ip() {
  curl -sS -m 10 https://ifconfig.me/ip 2>/dev/null || curl -sS -m 10 https://api.ipify.org 2>/dev/null || true
}

_add_firewall_my_ip() {
  local ip="$1"
  if [[ -z "$ip" ]]; then
    echo "Could not detect public IP for firewall rule." >&2
    return 1
  fi
  echo "Firewall: allow client IP $ip"
  if $DRY_RUN; then
    echo "[dry-run] az postgres flexible-server firewall-rule create ... AllowMyIP $ip"
    return 0
  fi
  az postgres flexible-server firewall-rule create \
    --resource-group "$RG" \
    --name "$SERVER" \
    --rule-name "AllowMyIP" \
    --start-ip-address "$ip" \
    --end-ip-address "$ip" \
    --output none 2>/dev/null || \
  az postgres flexible-server firewall-rule update \
    --resource-group "$RG" \
    --name "$SERVER" \
    --rule-name "AllowMyIP" \
    --start-ip-address "$ip" \
    --end-ip-address "$ip" \
    --output none
}

if $ADD_MY_IP_ONLY; then
  IP="$(_my_public_ip)"
  _add_firewall_my_ip "$IP"
  echo "Done. Re-run migrate or pull scripts from this machine."
  exit 0
fi

if [[ -z "${AZURE_POSTGRES_ADMIN_PASSWORD:-}" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    AZURE_POSTGRES_ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
  else
    AZURE_POSTGRES_ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24)[:24])')"
  fi
  echo "Generated admin password (save it): $AZURE_POSTGRES_ADMIN_PASSWORD"
fi

echo "=== Azure Postgres setup ==="
echo "Subscription: $SUB"
echo "Resource group: $RG"
echo "Location:       $LOCATION"
echo "Server:         $SERVER"
echo "Database:       $DB_NAME"
echo "Admin user:     $ADMIN_USER"
echo "SKU:            $TIER $SKU"
echo ""

if $DRY_RUN; then
  echo "[dry-run] Would create flexible server and database if missing."
  exit 0
fi

if ! az postgres flexible-server show --resource-group "$RG" --name "$SERVER" &>/dev/null; then
  echo "Creating PostgreSQL Flexible Server (this may take several minutes)..."
  az postgres flexible-server create \
    --resource-group "$RG" \
    --name "$SERVER" \
    --location "$LOCATION" \
    --admin-user "$ADMIN_USER" \
    --admin-password "$AZURE_POSTGRES_ADMIN_PASSWORD" \
    --sku-name "$SKU" \
    --tier "$TIER" \
    --version "$VERSION" \
    --storage-size "$STORAGE_GB" \
    --yes \
    --output none
else
  echo "Server $SERVER already exists."
fi

if ! az postgres flexible-server db show --resource-group "$RG" --server-name "$SERVER" --database-name "$DB_NAME" &>/dev/null; then
  echo "Creating database $DB_NAME..."
  az postgres flexible-server db create \
    --resource-group "$RG" \
    --server-name "$SERVER" \
    --database-name "$DB_NAME" \
    --output none
else
  echo "Database $DB_NAME already exists."
fi

echo "Configuring firewall (Allow Azure services)..."
az postgres flexible-server firewall-rule create \
  --resource-group "$RG" \
  --name "$SERVER" \
  --rule-name "AllowAzureServices" \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0 \
  --output none 2>/dev/null || true

IP="$(_my_public_ip)"
_add_firewall_my_ip "$IP"

FQDN="$(az postgres flexible-server show --resource-group "$RG" --name "$SERVER" --query fullyQualifiedDomainName -o tsv)"

# URL-encode password for connection string
ENC_PASS="$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$AZURE_POSTGRES_ADMIN_PASSWORD")"
CONN="postgresql+psycopg://${ADMIN_USER}:${ENC_PASS}@${FQDN}:5432/${DB_NAME}?sslmode=require"

echo ""
echo "=== Connection string ==="
echo "Add to .env (gitignored):"
echo ""
echo "POSTGRES_DATABASE_URL=${CONN}"
echo ""
echo "Keep local dev on SQLite:"
echo "DATABASE_URL=sqlite:///./data/woccon.db"
echo ""
echo "Next steps:"
echo "  pip install -r requirements.txt"
echo "  ./scripts/migrate_sqlite_to_postgres.py"
echo "  ./scripts/sync-azure-container-env.sh"
echo ""
echo "If your IP changes: ./scripts/setup-azure-postgres.sh --add-my-ip"
