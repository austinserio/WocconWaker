# Microsoft Foundry setup via Azure CLI

Use Foundry (Llama or Hugging Face–equivalent model on Azure) when **LOCAL_LLM** is not set or is false. All setup can be done with Azure CLI.

## 0. Configure `.env` for scripts

From the repo root:

```bash
cp .env.example .env
```

Set at least `AZURE_SUBSCRIPTION_ID` in `.env` before running `setup-foundry-azure-cli.sh` or other Azure helper scripts. Shell scripts load `.env` automatically via [scripts/load_repo_env.sh](scripts/load_repo_env.sh).

## 1. One-time setup

```bash
az login
az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# Install Foundry CLI extension
az extension add --name cognitiveservices
```

(`AZURE_SUBSCRIPTION_ID` can be exported from your filled `.env`.)

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

Optional overrides (environment variables — add to `.env` or export):

- `FOUNDRY_RESOURCE_GROUP` (default: `woccon-foundry-rg`)
- `FOUNDRY_LOCATION` (default: `eastus2`)
- `FOUNDRY_ACCOUNT_NAME` (default: `woccon-foundry`)
- `FOUNDRY_DEPLOYMENT_NAME` (default: `Llama-3-8B-Instruct`)

## 3. Create a model deployment

After the script lists models, create a deployment. Use the **name**, **version**, and **format** from the list (e.g. `Meta` for Llama). Example (replace names with your account / resource group / model from `list-models`):

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

Put the values in `.env` as `FOUNDRY_ENDPOINT`, `FOUNDRY_API_KEY`, and `FOUNDRY_DEPLOYMENT` (see [.env.example](.env.example)).

## 5. Test the Foundry version

Ensure you have dependencies:

```bash
pip install -r requirements.txt
```

Run the app (`app.py` loads `.env` when `python-dotenv` is installed):

```bash
python app.py
# Or: WOCCON_MODE=server python app.py
```

Chat and lessons will use your Foundry deployment (not OpenAI’s consumer API).

---

## 6. GitHub → Azure deployment (`azure-foundry` branch)

Pushing the `azure-foundry` branch triggers a GitHub Actions workflow that builds the app (`Dockerfile.azure`) and deploys to Azure Container Apps.

**One-time setup**

1. **Create Azure resources** (resource group, Container Apps environment, ACR, Container App) in your subscription — use the Azure Portal, Bicep/Terraform, or your own deploy script. Note the resource group name and container app name.

2. **Repository variables** (Settings → Secrets and variables → Actions → **Variables**): set
   - `AZURE_RESOURCE_GROUP` – resource group containing the Container App and ACR
   - `AZURE_CONTAINER_APP_NAME` – Container App name
   - Optionally `ACR_IMAGE_NAME` – Docker image repository name (default `wocconwaker` if unset)

3. **Create a service principal** (for GitHub to deploy), scoped to your resource group:

   ```bash
   az ad sp create-for-rbac --name "WocconWaker-GitHub" --role contributor \
     --scopes /subscriptions/<YOUR_SUBSCRIPTION_ID>/resourceGroups/<YOUR_RESOURCE_GROUP> \
     --sdk-auth
   ```

   Store the resulting JSON as the `AZURE_CREDENTIALS` **secret** (or use OIDC per [Azure/login](https://github.com/Azure/login) docs).

4. **GitHub secrets** (Settings → Secrets and variables → Actions): add
   - `AZURE_CREDENTIALS` – output of `create-for-rbac --sdk-auth` (JSON) if using that login method
   - `FOUNDRY_ENDPOINT`
   - `FOUNDRY_API_KEY`
   - `FOUNDRY_DEPLOYMENT`

After pushing to `azure-foundry`, the workflow builds, pushes the image to ACR, and updates the Container App. The run summary shows the app URL and Messenger webhook URL (`https://<fqdn>/webhook`).

**Migrating an existing fork:** if the workflow previously used hardcoded resource names, define repository variables `AZURE_RESOURCE_GROUP` and `AZURE_CONTAINER_APP_NAME` to match your Azure resources before the next run.
