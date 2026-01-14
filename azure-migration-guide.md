# Azure Migration Guide for WocconWaker

This guide helps you migrate WocconWaker between Azure subscriptions.

## Prerequisites

- Azure CLI installed and configured
- Access to both source and target Azure subscriptions
- Docker installed (for building images)

## Migration Steps

### 1. Export Current Infrastructure

From the source subscription:

```bash
# Set your source subscription
az account set --subscription "source-subscription-id"

# Export the resource group as an ARM template
az group export --name rg-wocconwaker --output-file wocconwaker-template.json
```

### 2. Prepare Target Subscription

```bash
# Set your target subscription
az account set --subscription "target-subscription-id"

# Create the resource group in the target subscription
az group create --name rg-wocconwaker --location eastus
```

### 3. Update Configuration

Before deploying to the new subscription, update the following:

1. **Ollama Cloud API Key**: Use the same Ollama Cloud account (no changes needed)
2. **Container Registry**: Update the registry name (must be globally unique)
3. **Environment Variables**: Ensure all environment variables are set correctly

### 4. Deploy to Target Subscription

Option A: Using Bicep template (recommended):

```bash
# Deploy using the Bicep template
az deployment group create \
  --resource-group rg-wocconwaker \
  --template-file azure-deploy.bicep \
  --parameters \
    ollamaCloudApiKey="your-ollama-cloud-api-key" \
    ollamaModel="llama3:8b" \
    containerRegistryName="wocconwaker-$(date +%s)"
```

Option B: Using exported ARM template:

```bash
# Deploy the exported template
az deployment group create \
  --resource-group rg-wocconwaker \
  --template-file wocconwaker-template.json
```

### 5. Update Environment Variables

Update the Container App environment variables:

```bash
az containerapp update \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --set-env-vars \
    OLLAMA_CLOUD_ENDPOINT="https://api.ollama.com" \
    OLLAMA_CLOUD_API_KEY="your-ollama-cloud-api-key" \
    OLLAMA_MODEL="llama3:8b"
```

### 6. Verify Deployment

```bash
# Get the Container App URL
az containerapp show \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --query properties.configuration.ingress.fqdn \
  --output tsv

# Test the health endpoint
curl https://your-app-url.azurecontainerapps.io/health
```

## Key Points for Migration

1. **Resource Names**: Most resource names can be reused, except Container Registry (must be globally unique)
2. **API Keys**: Must be regenerated in the new subscription
3. **Data**: No persistent data is stored in Azure, so no data migration needed
4. **Docker Images**: Rebuild and push to the new Container Registry

## Cost Considerations

- Export/import operations are free
- New resources will incur costs in the target subscription
- Remember to delete resources in the source subscription after migration

## Troubleshooting

### Container App fails to start

Check logs:
```bash
az containerapp logs show \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --follow
```

### API authentication errors

Verify your Ollama Cloud API key is correct:
```bash
az containerapp show \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --query "properties.template.containers[0].env"
```

## Rollback Plan

If migration fails:

1. Keep the source subscription resources running
2. Fix issues in the target subscription
3. Re-deploy once issues are resolved
4. Delete source resources only after successful migration

