# Azure Deployment Guide for WocconWaker

This guide walks you through deploying WocconWaker to Azure using Azure Container Apps with Ollama Cloud for LLM inference.

## Prerequisites

1. **Azure Account**: Personal account (austin.c.serio@gmail.com) with $200 credit
2. **Azure CLI**: Installed and configured
3. **Docker**: Installed for building container images
4. **Ollama Cloud Account**: Sign up at https://ollama.com (Free, Pro $20/mo, or Max $100/mo)

## Quick Start

### 1. Set Up Ollama Cloud

1. Sign up for Ollama Cloud at https://ollama.com
2. Get your API key from your Ollama Cloud account settings
3. Choose your plan:
   - **Free**: Access to cloud models (good for testing)
   - **Pro**: $20/month with enhanced usage limits
   - **Max**: $100/month with 5x Pro limits

### 2. Configure Environment Variables

Create a `.env` file (or set environment variables):

```bash
# Required - Ollama Cloud
OLLAMA_CLOUD_ENDPOINT=https://api.ollama.com
OLLAMA_CLOUD_API_KEY=your-ollama-cloud-api-key-here
OLLAMA_MODEL=llama3:8b

# Optional (for Facebook Messenger)
PAGE_ACCESS_TOKEN=your-page-access-token
VERIFY_TOKEN=your-verify-token
```

### 3. Deploy Infrastructure

Run the deployment script:

```bash
./deploy-azure.sh
```

Or manually deploy using Bicep:

```bash
az group create --name rg-wocconwaker --location eastus

az deployment group create \
  --resource-group rg-wocconwaker \
  --template-file azure-deploy.bicep \
  --parameters \
    ollamaCloudApiKey="your-ollama-cloud-api-key" \
    ollamaModel="llama3:8b" \
    containerRegistryName="wocconwaker-$(date +%s)"
```

### 4. Build and Push Docker Image

```bash
# Login to Container Registry
REGISTRY_NAME=$(az acr list --resource-group rg-wocconwaker --query "[0].name" -o tsv)
az acr login --name $REGISTRY_NAME

# Get registry server
REGISTRY_SERVER=$(az acr show --name $REGISTRY_NAME --resource-group rg-wocconwaker --query loginServer -o tsv)

# Build image
docker build -t $REGISTRY_SERVER/wocconwaker:latest .

# Push image
docker push $REGISTRY_SERVER/wocconwaker:latest
```

### 5. Update Container App with Image

```bash
az containerapp update \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --image $REGISTRY_SERVER/wocconwaker:latest
```

### 6. Get Application URL

```bash
az containerapp show \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv
```

## Cost Estimation

### Monthly Costs (Estimated)

- **Azure Container Apps**: $10-20/month (consumption plan, light usage)
- **Ollama Cloud**: 
  - Free tier: $0 (limited usage)
  - Pro tier: $20/month (recommended for production)
  - Max tier: $100/month (high usage)
- **Container Registry**: ~$5/month (Basic tier)
- **Total**: 
  - Free tier: ~$15-25/month
  - Pro tier: ~$35-45/month
  - Max tier: ~$115-125/month

All well within your $200 Azure credit!

### Cost Optimization Tips

1. Set `minReplicas: 0` to scale to zero when not in use
2. Use consumption plan for Container Apps
3. Start with Ollama Cloud Free tier for testing
4. Monitor usage and upgrade to Pro only if needed
5. Set up budget alerts in Azure Cost Management

## Configuration

### Environment Variables

All configuration is done via environment variables in the Container App:

- `OLLAMA_CLOUD_ENDPOINT`: Ollama Cloud API endpoint (default: https://api.ollama.com)
- `OLLAMA_CLOUD_API_KEY`: Your Ollama Cloud API key (stored as secret)
- `OLLAMA_MODEL`: Model name (e.g., llama3:8b)
- `WOCCON_MODE`: Set to `server` for production
- `PORT`: Application port (8000)

### Scaling Configuration

Edit `azure-deploy.bicep` to adjust:

- `minReplicas`: Minimum instances (0 for cost savings)
- `maxReplicas`: Maximum instances (10 default)
- `containerCpu`: CPU allocation (0.5 default)
- `containerMemory`: Memory allocation (1.0 GiB default)

## Monitoring

### View Logs

```bash
az containerapp logs show \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --follow
```

### Health Check

```bash
curl https://your-app-url.azurecontainerapps.io/health
```

## Troubleshooting

### Container App fails to start

1. Check logs: `az containerapp logs show --name wocconwaker-app --resource-group rg-wocconwaker`
2. Verify environment variables are set correctly
3. Check Ollama Cloud API key is valid

### API authentication errors

1. Verify `OLLAMA_CLOUD_API_KEY` is correct
2. Check your Ollama Cloud account is active
3. Ensure you haven't exceeded usage limits

### High costs

1. Set `minReplicas: 0` to scale to zero
2. Monitor Ollama Cloud usage
3. Consider downgrading Ollama Cloud tier if usage is low
4. Set up budget alerts

## Migration Between Subscriptions

See `azure-migration-guide.md` for detailed migration instructions.

## Security Best Practices

1. Store API keys as secrets in Container App (already configured)
2. Use Managed Identity where possible
3. Enable HTTPS only (already configured)
4. Regularly rotate API keys
5. Monitor for unusual activity

## Ollama Cloud vs Self-Hosted

**Why Ollama Cloud?**
- No infrastructure management
- Predictable costs ($0-100/month)
- Automatic scaling
- Always up-to-date models
- Data sovereignty (Ollama doesn't use your data for training)

**When to Self-Host?**
- Need maximum data control
- Very high usage (may be cheaper)
- Custom model requirements
- Compliance requirements

## Support

For issues or questions:
1. Check logs: `az containerapp logs show`
2. Review Azure Portal for resource status
3. Verify all environment variables are set correctly
4. Check Ollama Cloud account status and usage
