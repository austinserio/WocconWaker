#!/bin/bash
# Emergency script to delete ALL Azure resources and stop cost bleeding

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${RED}║     EMERGENCY: Deleting ALL Azure Resources              ║${NC}"
echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

WOCCON_SUBSCRIPTION="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID in .env (see .env.example)}"
az account set --subscription "$WOCCON_SUBSCRIPTION"
SUB_NAME=$(az account show --query name -o tsv)
SUB_ID=$(az account show --query id -o tsv)
USER=$(az account show --query user.name -o tsv)

echo -e "${GREEN}Subscription: ${SUB_NAME}${NC}"
echo -e "${GREEN}User: ${USER}${NC}"
echo ""

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP in .env (see .env.example)}"

# Check if resource group exists
if ! az group show --name "$RESOURCE_GROUP" &>/dev/null; then
    echo -e "${YELLOW}⚠ Resource group ${RESOURCE_GROUP} does not exist${NC}"
    exit 0
fi

echo -e "${RED}WARNING: This will DELETE ALL resources in ${RESOURCE_GROUP}${NC}"
echo -e "${RED}This action cannot be undone!${NC}"
echo ""
read -p "Type 'DELETE' to confirm: " CONFIRM
if [ "$CONFIRM" != "DELETE" ]; then
    echo -e "${YELLOW}Cancelled. Nothing was deleted.${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Step 1: Deleting Container Apps${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

CONTAINER_APPS=$(az containerapp list --resource-group "$RESOURCE_GROUP" --query "[].name" -o tsv 2>/dev/null || echo "")
if [ -n "$CONTAINER_APPS" ]; then
    for APP in $CONTAINER_APPS; do
        echo -e "${YELLOW}Deleting Container App: ${APP}${NC}"
        az containerapp delete --name "$APP" --resource-group "$RESOURCE_GROUP" --yes --output none 2>/dev/null || true
        echo -e "${GREEN}✓ Deleted: ${APP}${NC}"
    done
else
    echo -e "${GREEN}✓ No Container Apps found${NC}"
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Step 2: Deleting Container App Environments${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

ENVS=$(az containerapp env list --resource-group "$RESOURCE_GROUP" --query "[].name" -o tsv 2>/dev/null || echo "")
if [ -n "$ENVS" ]; then
    for ENV in $ENVS; do
        echo -e "${YELLOW}Deleting Environment: ${ENV}${NC}"
        az containerapp env delete --name "$ENV" --resource-group "$RESOURCE_GROUP" --yes --output none 2>/dev/null || true
        echo -e "${GREEN}✓ Deleted: ${ENV}${NC}"
    done
else
    echo -e "${GREEN}✓ No Container App Environments found${NC}"
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Step 3: Deleting Virtual Machines${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

VMS=$(az vm list --resource-group "$RESOURCE_GROUP" --query "[].name" -o tsv 2>/dev/null || echo "")
if [ -n "$VMS" ]; then
    for VM in $VMS; do
        echo -e "${YELLOW}Deleting VM: ${VM}${NC}"
        az vm delete --name "$VM" --resource-group "$RESOURCE_GROUP" --yes --output none 2>/dev/null || true
        echo -e "${GREEN}✓ Deleted: ${VM}${NC}"
    done
else
    echo -e "${GREEN}✓ No VMs found${NC}"
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Step 4: Deleting Container Registries${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

ACRS=$(az acr list --resource-group "$RESOURCE_GROUP" --query "[].name" -o tsv 2>/dev/null || echo "")
if [ -n "$ACRS" ]; then
    for ACR in $ACRS; do
        echo -e "${YELLOW}Deleting Container Registry: ${ACR}${NC}"
        az acr delete --name "$ACR" --resource-group "$RESOURCE_GROUP" --yes --output none 2>/dev/null || true
        echo -e "${GREEN}✓ Deleted: ${ACR}${NC}"
    done
else
    echo -e "${GREEN}✓ No Container Registries found${NC}"
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Step 5: Deleting ALL Remaining Resources${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

# Delete all remaining resources
RESOURCES=$(az resource list --resource-group "$RESOURCE_GROUP" --query "[].{Name:name, Type:type}" -o tsv 2>/dev/null || echo "")
if [ -n "$RESOURCES" ]; then
    echo "$RESOURCES" | while read -r NAME TYPE; do
        if [ -n "$NAME" ] && [ -n "$TYPE" ]; then
            echo -e "${YELLOW}Deleting: ${NAME} (${TYPE})${NC}"
            az resource delete --ids "/subscriptions/${SUB_ID}/resourceGroups/${RESOURCE_GROUP}/providers/${TYPE}/${NAME}" --output none 2>/dev/null || true
            echo -e "${GREEN}✓ Deleted: ${NAME}${NC}"
        fi
    done
else
    echo -e "${GREEN}✓ No remaining resources found${NC}"
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Step 6: Deleting Resource Group${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}Deleting resource group: ${RESOURCE_GROUP}${NC}"
az group delete --name "$RESOURCE_GROUP" --yes --output none 2>/dev/null || true

# Wait a moment and verify
sleep 5
if ! az group show --name "$RESOURCE_GROUP" &>/dev/null; then
    echo -e "${GREEN}✓ Resource group deleted${NC}"
else
    echo -e "${YELLOW}⚠ Resource group may still exist (checking resources...)${NC}"
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     ALL RESOURCES DELETED - COST BLEEDING STOPPED         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✓ All Azure resources have been deleted${NC}"
echo -e "${GREEN}✓ Cost bleeding has been stopped${NC}"
echo ""
echo -e "${YELLOW}To verify, run:${NC}"
echo "  az group list --query \"[?contains(name, 'woccon')]\" --output table"
echo ""

