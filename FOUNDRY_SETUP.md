# Microsoft Foundry setup via Azure CLI

Use Foundry (Llama or Hugging Face–equivalent model on Azure) when **LOCAL_LLM** is not set or is false. All setup can be done with Azure CLI.

## 1. One-time setup

```bash
# Use project subscription (see .cursorrules)
export AZURE_SUBSCRIPTION_ID="58587a07-da50-4691-aa9c-f23859d66df3"
az login
az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# Install Foundry CLI extension
az extension add --name cognitiveservices
```

## 2. Run the setup script

From the repo root:

```bash
chmod +x setup-foundry-azure-cli.sh
./setup-foundry-azure-cli.sh
```

This will:

- Create a resource group and Foundry (AIServices) account if they don’t exist
- List available models (look for Llama / Meta 8B Instruct)
- Print the endpoint and key to add to your `.env`

Optional overrides (before running the script):

- `FOUNDRY_RESOURCE_GROUP` (default: `woccon-foundry-rg`)
- `FOUNDRY_LOCATION` (default: `eastus2`)
- `FOUNDRY_ACCOUNT_NAME` (default: `woccon-foundry`)
- `FOUNDRY_DEPLOYMENT_NAME` (default: `Llama-3-8B-Instruct`)

## 3. Create a model deployment

After the script lists models, create a deployment. Use the **name**, **version**, and **format** from the list (e.g. `Meta` for Llama). Example:

```bash
ACCOUNT_NAME="woccon-foundry"
RESOURCE_GROUP="woccon-foundry-rg"
DEPLOYMENT_NAME="Llama-3-8B-Instruct"

# Replace <model-name>, <version>, <format> with values from list-models output
az cognitiveservices account deployment create \
  -n "$ACCOUNT_NAME" -g "$RESOURCE_GROUP" \
  --deployment-name "$DEPLOYMENT_NAME" \
  --model-name "<model-name>" \
  --model-version "<version>" \
  --model-format Meta \
  --sku-name GlobalStandard \
  --sku-capacity 1
```

To see the exact model names and formats:

```bash
az cognitiveservices account list-models \
  -n "$ACCOUNT_NAME" -g "$RESOURCE_GROUP" \
  -o table
```

## 4. Get endpoint and key for .env

```bash
# Endpoint (use Azure OpenAI endpoint for the OpenAI SDK)
az cognitiveservices account show -n "$ACCOUNT_NAME" -g "$RESOURCE_GROUP" \
  --query "properties.endpoints.\"Azure OpenAI\"" -o tsv

# If that is empty, try:
az cognitiveservices account show -n "$ACCOUNT_NAME" -g "$RESOURCE_GROUP" \
  --query "properties.endpoint" -o tsv

# API key
az cognitiveservices account keys list -n "$ACCOUNT_NAME" -g "$RESOURCE_GROUP" \
  --query "key1" -o tsv
```

## 5. Test the Foundry version

A `.env` file is already present with your Foundry credentials (endpoint, key, deployment). Ensure you have the `openai` package:

```bash
pip install -r requirements.txt
# or: pip install openai
```

Then run the app (no local Ollama will start; load .env manually if your app doesn't):

```bash
# If your app doesn't load .env automatically, export first:
export $(grep -v '^#' .env | xargs)

python app.py
# Or: WOCCON_MODE=server python app.py
```

Chat and lessons will use the Foundry deployment (Llama-3-8B-Instruct, not OpenAI models).

---

## 6. GitHub → Azure deployment (azure-foundry branch)

Pushing the `azure-foundry` branch triggers a GitHub Actions workflow that builds the app (Dockerfile.azure) and deploys to Azure Container Apps.

**One-time setup**

1. **Create Azure resources** (if not already): in the same subscription, create a resource group and Container App environment/app. From the repo root:
   ```bash
   # Uses subscription 2fef1120, creates rg-wocconwaker, ACR, wocconwaker-env, wocconwaker-app
   ./deploy-container-app.sh
   ```
   This creates the ACR and Container App; the first image may be local-Ollama. After the workflow runs, the app will use Foundry.

2. **Create a service principal** (for GitHub to deploy):
   ```bash
   az ad sp create-for-rbac --name "WocconWaker-GitHub" --role contributor \
     --scopes /subscriptions/2fef1120-5b1e-4224-9b93-091eb5d5424e/resourceGroups/rg-wocconwaker \
     --sdk-auth
   ```
   Use the JSON output to fill GitHub secrets (or set the four fields below).

3. **GitHub repo secrets** (Settings → Secrets and variables → Actions): add
   - `AZURE_CLIENT_ID`
   - `AZURE_TENANT_ID`
   - `AZURE_SUBSCRIPTION_ID` = `2fef1120-5b1e-4224-9b93-091eb5d5424e`
   - `AZURE_CLIENT_SECRET`
   - `FOUNDRY_ENDPOINT` = `https://woccon-foundry.openai.azure.com`
   - `FOUNDRY_API_KEY` = (your Foundry key)
   - `FOUNDRY_DEPLOYMENT` = `Llama-3-8B-Instruct`

After pushing to `azure-foundry`, the workflow builds, pushes the image to ACR, and updates the Container App. The run summary shows the app URL and **Messenger webhook URL** (`https://<fqdn>/webhook`).
