#!/usr/bin/env bash
# Setup Microsoft Foundry (Llama / HF model) via Azure CLI for WocconWaker.
# When done, set LOCAL_LLM=false and the env vars below to use Foundry.
# Uses subscription from .cursorrules: 58587a07-da50-4691-aa9c-f23859d66df3

set -e
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-58587a07-da50-4691-aa9c-f23859d66df3}"
RESOURCE_GROUP="${FOUNDRY_RESOURCE_GROUP:-woccon-foundry-rg}"
LOCATION="${FOUNDRY_LOCATION:-eastus2}"
ACCOUNT_NAME="${FOUNDRY_ACCOUNT_NAME:-woccon-foundry}"
# Deployment name you'll use in FOUNDRY_DEPLOYMENT (e.g. Llama-3-8B-Instruct)
DEPLOYMENT_NAME="${FOUNDRY_DEPLOYMENT_NAME:-Llama-3-8B-Instruct}"

echo "=== Foundry setup (Azure CLI) ==="
echo "Subscription: $SUBSCRIPTION_ID"
echo "Resource group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "Account: $ACCOUNT_NAME"
echo "Deployment name: $DEPLOYMENT_NAME"
echo ""

# Install extension if needed
if ! az extension show --name cognitiveservices 2>/dev/null; then
  echo "Adding cognitiveservices extension..."
  az extension add --name cognitiveservices
fi

az account set --subscription "$SUBSCRIPTION_ID"
echo "Creating resource group if not exists..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none 2>/dev/null || true

echo "Creating Foundry (AIServices) account if not exists..."
if ! az cognitiveservices account show --name "$ACCOUNT_NAME" --resource-group "$RESOURCE_GROUP" 2>/dev/null; then
  az cognitiveservices account create \
    --name "$ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --custom-domain "$ACCOUNT_NAME" \
    --location "$LOCATION" \
    --kind AIServices \
    --sku S0 \
    --output none
  echo "Created account $ACCOUNT_NAME."
else
  echo "Account $ACCOUNT_NAME already exists."
fi

echo ""
echo "Listing available models (look for Llama / Meta 8B instruct)..."
az cognitiveservices account list-models \
  --name "$ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --output table 2>/dev/null || az cognitiveservices account list-models \
  --name "$ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP" 2>/dev/null | head -80

echo ""
echo "To create a model deployment, use the model name/version/format from the list above."
echo "Example for a Meta Llama 3 8B Instruct model (adjust name/version/format to match list):"
echo "  az cognitiveservices account deployment create \\"
echo "    -n $ACCOUNT_NAME -g $RESOURCE_GROUP \\"
echo "    --deployment-name $DEPLOYMENT_NAME \\"
echo "    --model-name <model-name> --model-version <version> --model-format Meta \\"
echo "    --sku-name GlobalStandard --sku-capacity 1"
echo ""
echo "Fetching endpoint and key for .env..."
ENDPOINT=$(az cognitiveservices account show \
  --name "$ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.endpoints.\"Azure AI Model Inference API\"" -o tsv 2>/dev/null || echo "")
# OpenAI-compatible endpoint for SDK is often the Azure OpenAI endpoint
OPENAI_ENDPOINT=$(az cognitiveservices account show \
  --name "$ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.endpoints.\"Azure OpenAI\"" -o tsv 2>/dev/null || echo "")

if [ -z "$ENDPOINT" ]; then
  ENDPOINT=$(az cognitiveservices account show \
    --name "$ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.endpoint" -o tsv 2>/dev/null || echo "")
fi
if [ -z "$OPENAI_ENDPOINT" ] && [ -n "$ENDPOINT" ]; then
  # Some resources expose inference at .services.ai.azure.com; SDK may need .openai.azure.com
  OPENAI_ENDPOINT="${ENDPOINT}"
fi
KEY=$(az cognitiveservices account keys list \
  --name "$ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "key1" -o tsv 2>/dev/null || echo "")

CHOSEN_ENDPOINT="${OPENAI_ENDPOINT:-$ENDPOINT}"
echo ""
echo "=== Add these to your .env to test Foundry (LOCAL_LLM=false) ==="
echo ""
echo "LOCAL_LLM=false"
echo "FOUNDRY_ENDPOINT=$CHOSEN_ENDPOINT"
echo "FOUNDRY_API_KEY=$KEY"
echo "FOUNDRY_DEPLOYMENT=$DEPLOYMENT_NAME"
if echo "$CHOSEN_ENDPOINT" | grep -q 'services\.ai\.azure\.com'; then
  echo "FOUNDRY_INFERENCE_API_VERSION=2024-05-01-preview"
elif echo "$CHOSEN_ENDPOINT" | grep -q 'openai\.azure\.com'; then
  echo "FOUNDRY_API_VERSION=2024-10-21"
else
  echo "# If FOUNDRY_ENDPOINT is *.services.ai.azure.com, set FOUNDRY_INFERENCE_API_VERSION=2024-05-01-preview"
  echo "# If it is *.openai.azure.com, set FOUNDRY_API_VERSION=2024-10-21"
fi
echo ""
echo "Then run: python app.py  (or WOCCON_MODE=server python app.py)"
echo "No local Ollama will start; all LLM calls go to Foundry."
