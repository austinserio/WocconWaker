# WocconWaker

FastAPI app and language tooling for the Woccon language (Eastern Siouan, documented 1709), with optional Facebook Messenger integration, Google Drive ingest, and LLM backends (local Ollama, Microsoft Foundry, or Anthropic).

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env: at minimum set WOCCON_MODE, and LLM/Messenger vars as needed.
python app.py
```

- **[CLAUDE.md](CLAUDE.md)** – commands, architecture, and environment variables.
- **[LOCAL_DEV.md](LOCAL_DEV.md)** – Messenger webhooks and local tunnels.
- **[DRIVE_INGEST.md](DRIVE_INGEST.md)** – Google Drive → staging ingest (`DRIVE_FOLDER_ID` and service account required).
- **[FOUNDRY_SETUP.md](FOUNDRY_SETUP.md)** – Azure Foundry setup via CLI.
- **[SECURITY.md](SECURITY.md)** – reporting issues; pre-publication checks.

Shell scripts that talk to Azure load `.env` via [scripts/load_repo_env.sh](scripts/load_repo_env.sh). Set `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, and other keys there before running deploy helpers.

## License

See [LICENSE](LICENSE).
