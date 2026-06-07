# WocconWaker

WocconWaker is a FastAPI application and language toolkit for **Woccon**, an Eastern Siouan language documented by John Lawson in 1709. It combines attested lexicon and phonological rules with LLM-assisted conversation, Facebook Messenger integration, Google Drive document ingest, and an admin control panel for curating reconstructed language data.

**Production** runs on **Azure Container Apps** with **Microsoft Foundry** (Llama) for inference. Push to `main` triggers CI to build `Dockerfile.azure` and roll out the container image.

## Features

- **Messenger bot** – Webhook-based chat with vocabulary and grammar lessons, typing indicators, and rich postbacks.
- **Language engine** – Morphological analysis, translation, and T5-backed processing (`main.py`, `woccon_language/`).
- **LLM backends** – Microsoft Foundry (default in production), local Ollama (`LOCAL_LLM=true`), or Anthropic Claude when `ANTHROPIC_API_KEY` is set.
- **Drive ingest** – Extract vocabulary and rules from shared Google Drive folders into staging for review.
- **Control panel** – JWT-protected React UI (`panel/`) to upload documents, review pending entries, and commit to the canonical lexicon.

## Quick start (local)

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env: WOCCON_MODE, LLM vars, Messenger tokens as needed.
python app.py
```

For Messenger webhooks against a local server, use a Cloudflare tunnel:

```bash
./run-local-full.sh    # backend + panel Vite + optional tunnel helpers
# or Messenger only:
./run-local-messenger.sh
```

Health check: `GET http://localhost:8000/health`

## LLM configuration

| Mode | When | Key variables |
|------|------|---------------|
| **Foundry** (production) | `LOCAL_LLM` unset or false | `FOUNDRY_ENDPOINT`, `FOUNDRY_API_KEY`, `FOUNDRY_DEPLOYMENT` |
| **Local Ollama** | `LOCAL_LLM=true` | `OLLAMA_URL`, `OLLAMA_MODEL` |
| **Anthropic** | `ANTHROPIC_API_KEY` set | `ANTHROPIC_MODEL` (optional) |

One-time Foundry setup on Azure:

```bash
az login
./setup-foundry-azure-cli.sh
```

See **[FOUNDRY_SETUP.md](FOUNDRY_SETUP.md)** for deployment names, endpoint formats, and `.env` examples.

## Azure deployment

Production infrastructure lives in Azure (Central US): Container Apps, ACR, Postgres, and Foundry. Environment variables and secrets are configured in the Container App — CI only builds and deploys the image.

**GitHub Actions** (`.github/workflows/deploy-azure-foundry.yml`) runs on push to `main`:

1. Builds and pushes `Dockerfile.azure` to ACR.
2. Updates the Container App with the new image tag (`github.sha`).

Required GitHub configuration:

| Type | Name | Purpose |
|------|------|---------|
| Secret | `AZURE_CREDENTIALS` | Service principal JSON from `az ad sp create-for-rbac --sdk-auth` |
| Variable | `AZURE_RESOURCE_GROUP` | Resource group containing the Container App |
| Variable | `AZURE_CONTAINER_APP_NAME` | e.g. `wocconwaker-app-central` |
| Variable | `ACR_IMAGE_NAME` | Optional; default `wocconwaker` |

Set matching values in `.env` for local Azure CLI scripts (`scripts/load_repo_env.sh` loads `.env` automatically):

```bash
AZURE_SUBSCRIPTION_ID=
AZURE_RESOURCE_GROUP=
AZURE_CONTAINER_APP_NAME=wocconwaker-app-central
```

Helper scripts: `deploy-container-app-gpu.sh`, `scripts/sync-azure-container-env.sh`, `scripts/setup-azure-postgres.sh`.

## Branches

| Branch | Purpose |
|--------|---------|
| **`main`** | Production line; Azure Foundry + Container Apps deploy |
| `azure-foundry` | Legacy deploy branch (kept in sync with `main`) |
| `ollama` | Local Ollama / GPU experimentation |
| `huggingface` | Hugging Face mirror experiments |

## Documentation

| Doc | Contents |
|-----|----------|
| **[CLAUDE.md](CLAUDE.md)** | Commands, architecture, environment variables |
| **[LOCAL_DEV.md](LOCAL_DEV.md)** | Messenger webhooks, Cloudflare tunnel, local scripts |
| **[FOUNDRY_SETUP.md](FOUNDRY_SETUP.md)** | Azure Foundry setup via CLI |
| **[DRIVE_INGEST.md](DRIVE_INGEST.md)** | Google Drive → staging ingest |
| **[docs/CONTROL_PANEL.md](docs/CONTROL_PANEL.md)** | Panel API, auth, upload/review/commit |
| **[docs/RECONSTRUCTION_ROADMAP.md](docs/RECONSTRUCTION_ROADMAP.md)** | Reconstruction pipeline and phased DoD |
| **[PLAN.md](PLAN.md)** | Platform phase status |
| **[SECURITY.md](SECURITY.md)** | Reporting issues; pre-publication checks |

## API endpoints (summary)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/info` | Assistant metadata |
| `GET` / `POST` | `/webhook` | Facebook Messenger webhook |
| `POST` | `/message` | Direct message API |
| `POST` | `/admin/ingest-drive` | Run Drive ingest (optional secret) |
| `POST` | `/admin/reload-language` | Reload dictionary/rules and rebuild RAG |
| `POST` | `/api/auth/login/json` | Control panel login (JWT) |

Full panel routes: see [docs/CONTROL_PANEL.md](docs/CONTROL_PANEL.md).

## License

See [LICENSE](LICENSE).
