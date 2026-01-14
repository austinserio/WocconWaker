# Azure Deployment Fix - Local Ollama on Azure CPU

## Problem Identified

The `Dockerfile.azure` was missing Ollama installation, but the application expects a local Ollama instance running in the container. This caused the deployment to fail.

## Fixes Applied

### 1. Updated Dockerfile.azure

Added Ollama installation to the Dockerfile:

```dockerfile
# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Ensure Ollama is in PATH
ENV PATH="/usr/local/bin:${PATH}"
```

### 2. Increased Resources

Updated default resources in `azure-deploy.bicep`:
- **CPU**: 1.5 → **2.0** (Ollama needs more CPU for quantized models)
- **Memory**: 3.0Gi → **4.0Gi** (Ollama models need more memory)

### 3. How It Works

1. **Dockerfile installs Ollama** during image build
2. **app.py starts Ollama** on container startup via `start_ollama()` function
3. **Ollama pulls the quantized model** (`llama3:8b`) on first use
4. **Application connects** to `http://localhost:11434` (local Ollama)

## Deployment Steps

### 1. Rebuild Docker Image

```bash
# Get Container Registry info
REGISTRY_NAME=$(az acr list --resource-group rg-wocconwaker --query "[0].name" -o tsv)
REGISTRY_SERVER=$(az acr show --name $REGISTRY_NAME --resource-group rg-wocconwaker --query loginServer -o tsv)

# Login
az acr login --name $REGISTRY_NAME

# Build with the fixed Dockerfile
docker build -f Dockerfile.azure -t $REGISTRY_SERVER/wocconwaker:latest .

# Push
docker push $REGISTRY_SERVER/wocconwaker:latest
```

### 2. Update Container App with Increased Resources

```bash
az containerapp update \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --image $REGISTRY_SERVER/wocconwaker:latest \
  --cpu 2.0 \
  --memory 4.0Gi
```

### 3. Verify Deployment

```bash
# Check logs (watch for Ollama startup)
az containerapp logs show \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --follow

# Test health endpoint
APP_URL=$(az containerapp show \
  --name wocconwaker-app \
  --resource-group rg-wocconwaker \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

curl https://${APP_URL}/health
```

## Expected Startup Sequence

When the container starts, you should see in the logs:

1. `Starting Ollama 🦙`
2. `🚀  Launched: ollama serve &> ollama.log &`
3. `🟢  Ollama is now listening on 11434`
4. `Checking if LLaMA model 'llama3:8b' is available...`
5. `Model 'llama3:8b' pulled successfully.` (on first run)
6. `Assistant initialization complete!`

## Troubleshooting

### Ollama won't start

- Check logs: `az containerapp logs show --name wocconwaker-app --resource-group rg-wocconwaker`
- Verify Ollama is installed: Look for "Could not find 'ollama'" errors
- Check resources: Ensure CPU >= 2.0 and Memory >= 4.0Gi

### Model pull fails

- First pull can take time (model is ~4.7GB quantized)
- Check network connectivity in logs
- Verify sufficient memory (4.0Gi should be enough)

### Health check fails

- Startup probe allows up to 200 seconds (20 failures × 10 seconds)
- Check if Ollama is running: Look for "Ollama already up on port 11434"
- Verify assistant initialization completes

### Performance issues

- Consider increasing CPU to 2.0+ if responses are slow
- Monitor memory usage - quantized models still need RAM
- Check Ollama logs: `ollama.log` in container

## Resource Recommendations

- **Minimum**: 2.0 CPU, 4.0Gi Memory
- **Recommended**: 2.0 CPU, 4.0Gi Memory (for llama3:8b quantized)
- **For larger models**: 2.0+ CPU, 6.0Gi+ Memory

## Cost Impact

- **2.0 CPU, 4.0Gi**: ~$20-30/month (consumption plan, moderate usage)
- **With minReplicas=0**: Scales to zero when idle (saves cost)
- **Cold start**: First request after scale-to-zero takes ~30-60 seconds (Ollama startup + model load)

## Notes

- Ollama runs **inside the container** (not as a separate service)
- Model is pulled on first use and cached in container storage
- Each replica has its own Ollama instance and model cache
- Quantized models (llama3:8b) are optimized for CPU inference




