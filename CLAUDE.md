# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Start main FastAPI server (primary entry point)
python app.py

# CLI interface only
python woccon_cli.py

# Core language engine
python main.py

# Environment-specific modes
WOCCON_MODE=server python app.py     # Server only
WOCCON_MODE=cli python app.py        # CLI only  
WOCCON_MODE=hybrid python app.py     # Both CLI and server
```

### Testing
```bash
# Run morphological analyzer tests
python woccon_analyzer_test.py

# Start webhook test server for Messenger integration
python webhook_test_server.py
```

### Dependencies
```bash
pip install -r requirements.txt
```

### Docker Deployment
```bash
docker build -t wocconwaker .
docker run -p 8000:8000 wocconwaker
```

### System Service
```bash
# Deploy as systemd service
sudo cp woccon.service /etc/systemd/system/
sudo systemctl enable woccon
sudo systemctl start woccon

# Or use startup script
./start_woccon.sh
```

## Architecture Overview

### Core Components
- **app.py**: FastAPI web server and main application entry point with Messenger bot integration
- **main.py**: Core WocconT5 class - the linguistic processing engine using T5 transformers
- **woccon_llama_integration.py**: LLaMA model integration via Ollama for conversational AI
- **messenger_integration.py**: Facebook Messenger webhook handling and rich messaging features

### Key Classes
- **WocconT5**: Primary language engine with morphological analysis, translation, and T5 model integration
- **WocconAssistant**: Ollama-powered conversational interface combining linguistics with chat capabilities  
- **WocconMorphologicalAnalyzer**: Advanced morphological decomposition and linguistic analysis
- **MessengerIntegration**: Facebook platform integration with webhooks and rich messaging

### Language Data Structure
- **woccon_language/dictionary.json**: 143 attested Woccon words from John Lawson's 1709 documentation
- **woccon_language/rules.json**: Phonological rules, morphological patterns, and suffix ordering constraints

### AI Stack Integration
- **PyTorch + Transformers**: T5 models for sequence-to-sequence language tasks
- **Ollama**: Local LLM inference (llama3:8b model) for conversational features
- **FastAPI**: Async web framework for API endpoints and webhook handling

### Application Modes
The system supports three operational modes via WOCCON_MODE environment variable:
1. **server**: Web API and Messenger bot only
2. **cli**: Command-line interface only  
3. **hybrid**: Both CLI and server functionality

### Educational Features
- **lesson_manager.py**: Vocabulary lesson system with progress tracking
- **grammar_lesson_manager.py**: Grammar instruction modules
- Interactive learning via chat interface with scoring and adaptive content

## Environment Variables

Required for full functionality:
```bash
VERIFY_TOKEN="facebook_webhook_verify_token"
PAGE_ACCESS_TOKEN="facebook_page_access_token" 
WOCCON_MODE="server|cli|hybrid"
PORT="8000"
LLAMA_MODEL_PATH="/workspace/models/llama3-8b"
T5_MODEL_PATH="/workspace/models/t5-base"
ENABLE_TYPING_INDICATORS="true|false"  # Optional: Enable Facebook typing indicators (default: false)
```

### LLM mode: local vs Microsoft Foundry
- **Anthropic (optional)**: If `ANTHROPIC_API_KEY` is set, all LLM calls (including Drive extraction) use **Claude** via the Anthropic API. Set `ANTHROPIC_MODEL` (e.g. `claude-3-5-sonnet-20241022`) or the code defaults to Sonnet. Useful when Azure quota isn’t available or for better extraction accuracy.
- **LOCAL_LLM**: When `true`, `1`, or `yes` (case-insensitive), the app uses **local Ollama** (e.g. RunPod/CUDA or CPU). When unset or false and no Anthropic key, the app uses **Microsoft Foundry** (Llama/equivalent via Azure API). No OpenAI models are used; Foundry serves Llama (or HF-equivalent) via an OpenAI-compatible API.
- **Local (OLLAMA_URL, OLLAMA_MODEL)**: Used only when `LOCAL_LLM` is true.
- **Foundry (when LOCAL_LLM is false)**:
  - `FOUNDRY_ENDPOINT` or `AZURE_AI_ENDPOINT`: Foundry/Azure OpenAI base URL (e.g. `https://<resource>.openai.azure.com`).
  - `FOUNDRY_API_KEY` or `AZURE_INFERENCE_CREDENTIAL`: API key from the Foundry resource.
  - `FOUNDRY_DEPLOYMENT`: Deployment name (e.g. `Llama-3-8B-Instruct`). Defaults to `OLLAMA_MODEL` if unset.
  - `FOUNDRY_API_VERSION`: Optional; default `2024-10-21`.
  - Use `./setup-foundry-azure-cli.sh` to create the resource and print these values.

### Drive ingest (Phase 1+)
- **GOOGLE_APPLICATION_CREDENTIALS**: Path to service account JSON key file. Required for listing/reading a shared Drive folder (share the folder with the service account email). Do not commit the JSON.
- **DRIVE_FOLDER_ID**: Optional. Defaults to the Woccon community folder ID.
- **INGEST_DRIVE_SECRET**: Optional. If set, `POST /admin/ingest-drive` and `GET /admin/ingest-drive/status` require this value in header `X-Ingest-Secret` or query `secret=`.

```bash
# Phase 1 verify: list folder and fetch text from Docs/PDFs
python drive_ingest.py
# Phase 2: schedule with cron (every 12h). See DRIVE_INGEST.md.
```

## API Endpoints

- `GET /webhook` - Facebook webhook verification
- `POST /webhook` - Handle incoming Facebook messages  
- `POST /message` - Direct API message endpoint
- `GET /health` - Health check
- `GET /info` - Assistant information
- `POST /admin/ingest-drive` - Run Drive ingest on demand (optional: X-Ingest-Secret or ?secret=)
- `GET /admin/ingest-drive/status` - Last ingest result

## Notes

- Project focuses on the extinct Woccon language (Eastern Siouan, documented 1709)
- No formal testing framework configured - uses manual test scripts
- No linting/formatting tools configured
- Ollama model (llama3:8b) automatically pulled on startup
- Uses Docker with CUDA PyTorch runtime for deployment