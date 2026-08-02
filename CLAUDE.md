# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Start main FastAPI server (primary entry point)
python app.py

# Full local dev: Messenger tunnel + backend + control panel Vite
./run-local-full.sh

# Messenger + tunnel only (no panel Vite dev server)
./run-local-messenger.sh

# Control panel only (backend + Vite dev server)
./run-panel-dev.sh

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

Copy [.env.example](.env.example) to `.env` and fill in values for your environment. `.env` is gitignored.

**Phase 4 – language reload and unified data:**
- `WOCCON_DICTIONARY_PATH`: Path to dictionary JSON (default `woccon_language/dictionary.json`). Set to `woccon_language/dictionary_unified.json` to use merged community + Lawson lexicon.
- `WOCCON_RULES_PATH`: Path to rules JSON (default `woccon_language/rules.json`). Set to `woccon_language/rules_unified.json` to use merged rules.
- After running `merge_staging.py`, call `POST /admin/reload-language` (same auth as ingest: `X-Ingest-Secret` or `?secret=`) to reload and rebuild RAG without restart.

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
- **LOCAL_LLM**: When `true`, `1`, or `yes` (case-insensitive), the app uses a **local LLM** backend. When unset or false and no Anthropic key, the app uses **Microsoft Foundry** (Llama/equivalent via Azure API).
- **Local backends (when LOCAL_LLM=true)**:
  - **llama-server (recommended on UIC)**: `OLLAMA_URL=http://100.71.124.8:8080/v1` — Qwen3.6-27B Q8 multimodal via OpenAI-compatible `/v1` (same setup as Policy Tracker `deploy/qwen36-llama-server.service`). Set **the same** model for `OLLAMA_MODEL` and `OLLAMA_VISION_MODEL` (`Qwen3.6-27B-Q8_0.gguf`). Optional: `LLM_REASONING=off`.
  - **Native Ollama (legacy)**: `OLLAMA_URL=http://127.0.0.1:11434` — uses Ollama `/api/chat`. For single-GPU ingest, set the same model for text and vision (e.g. `qwen2.5vl:32b`). Set `OLLAMA_NUM_PARALLEL=3` in Ollama systemd to match `EXTRACT_PARALLEL_WORKERS`.
- **Foundry (when LOCAL_LLM is false)**:
  - `FOUNDRY_ENDPOINT` or `AZURE_AI_ENDPOINT`: Base URL from the Azure account — either `https://<resource>.services.ai.azure.com` (Model Inference API) or `https://<resource>.openai.azure.com` (Azure OpenAI SDK path).
  - `FOUNDRY_API_KEY` or `AZURE_INFERENCE_CREDENTIAL`: API key from the Foundry resource.
  - `FOUNDRY_DEPLOYMENT`: Deployment name (e.g. `Llama-3-8B-Instruct`). Defaults to `OLLAMA_MODEL` if unset.
  - `FOUNDRY_INFERENCE_API_VERSION`: Used only when the endpoint host is `*.services.ai.azure.com` (REST `/models/chat/completions`). Default `2024-05-01-preview`. Do not use `FOUNDRY_API_VERSION` for that host — wrong versions return 404.
  - `FOUNDRY_API_VERSION`: Used only for `*.openai.azure.com` with the Azure OpenAI SDK. Default `2024-10-21`.
  - Use `./setup-foundry-azure-cli.sh` to create the resource and print these values.

### Drive ingest (Phase 1+)
- **GOOGLE_APPLICATION_CREDENTIALS**: Path to service account JSON key file. Required for listing/reading a shared Drive folder (share the folder with the service account email). Do not commit the JSON.
- **DRIVE_FOLDER_ID**: **Required** for `drive_ingest.py` and `/admin/ingest-drive`. Set the Google Drive folder ID in `.env`.
- **INGEST_DRIVE_SECRET**: Optional. If set, `POST /admin/ingest-drive` and `GET /admin/ingest-drive/status` require this value in header `X-Ingest-Secret` or query `secret=`.

```bash
# Phase 1 verify: list folder and fetch text from Docs/PDFs
python drive_ingest.py
# Phase 2: schedule with cron (every 12h). See DRIVE_INGEST.md.
```

**Hybrid list-doc extract** (`list_doc_parser.py` + `drive_extract.py`):
- **English-Woccon**: deterministic parser (main list + **Possible Words** subsection + note lines) merged with LLM output (enrichment). Staging JSON includes `audit.hybrid`, `audit.completeness`, and per-entry `extraction_method` (`parser` | `llm` | `merged` | `carry_forward`).
- **Documentation of Woccon Words**: parser runs on the Lawson list block only; LLM still handles citations and comparative notes.
- Env: `HYBRID_LIST_EXTRACT=1` (default), `HYBRID_LIST_DOCS=...` (optional allowlist), `HYBRID_LLM_LEXICON=1` (set `0` for parser-only lexicon), `EXTRACT_COMPLETENESS_FAIL=1` (abort when parser rows missing).
- On re-ingest, parser-backed rows from previous staging are carried forward if the LLM drops them; see `audit.hybrid.dropped_vs_previous`.
- Completeness check: `python scripts/check_extraction_completeness.py --staging woccon_language/drive_staging/English-Woccon.json --source-text data/ingest_text_cache/<file>.json`
- Unit tests: `python scripts/test_list_doc_parser.py`

### Catawba vs Woccon separation

The Drive corpus holds Catawba comparative sources next to Woccon primary sources. **Catawba is
a distinct language**: its vocabulary is evidence for reconstruction and must never become
Woccon vocabulary. [`content_language.py`](content_language.py) classifies each document by its
Drive folder — matched on whole path segments, since `Articles/Resurrecting Coastal Catawban …
Woccon Language` is a *Woccon* source whose title contains "Catawba".

| Folder | `content_language` | Effect |
| --- | --- | --- |
| `Catawba Language/` | `catawba` | Extracted with the Catawba prompt into `catawba_entries`; staged in `woccon_language/catawba_staging/`; never merged into the Woccon lexicon |
| `Catawba Nation - Context/` | `context` | Non-linguistic; no vocabulary extracted |
| everything else | `woccon` | Unchanged behaviour |

Guards are layered so no single failure leaks Catawba into the lexicon: the extraction prompt
asks for a different JSON key (`catawba_entries`), `extract_one_file` drops `lexicon_entries`
from non-Woccon sources even if the model returns them, staging is a separate directory,
`merge_staging.load_staging_files` refuses non-Woccon files, and `SourceDocument.content_language`
blocks `PendingLexicon` inserts in the panel. Override folder names with `CATAWBA_FOLDER_NAMES`
/ `CONTEXT_FOLDER_NAMES` (pipe-separated).

```bash
python scripts/test_content_language_guard.py   # verifies every layer, incl. a rogue-model case
```

**Diacritic-stripped scans:** scanned journal PDFs embed an OCR text layer that reads as dense
clean English while having dropped every phonetic character, so a character-count check scores
them as good text. `pages_with_lossy_text_layer()` also routes image-backed pages with no
phonetic characters to vision OCR (`PDF_OCR_RECHECK_ASCII_SCANS`, `PDF_OCR_SCAN_IMAGE_COVERAGE`).
Every Catawba source acquired so far (Speck 1934, Lieber 1858, Gatschet 1900) is diacritic-
stripped and needs this pass before it is usable for cognate work.

```bash
python scripts/reocr_lossy_pdf.py --pdf data/ingest_sources/<file>.pdf --dry-run   # list pages
python scripts/reocr_lossy_pdf.py --pdf data/ingest_sources/<file>.pdf --dpi 300 --out data/<name>.json --write
python scripts/parse_carter_sets.py --write    # link Carter 1980 sets into the cognate seed
```

## API Endpoints

- `GET /webhook` - Facebook webhook verification
- `POST /webhook` - Handle incoming Facebook messages  
- `POST /message` - Direct API message endpoint
- `GET /health` - Health check
- `GET /info` - Assistant information
- `POST /admin/ingest-drive` - Run Drive ingest on demand (optional: X-Ingest-Secret or ?secret=)
- `GET /admin/ingest-drive/status` - Last ingest result
- `POST /admin/reload-language` - Reload dictionary/rules and rebuild RAG (same auth as ingest; optional body: `dict_path`, `rules_path`)
- `POST /admin/extract-document` - Extract one document (same auth as ingest). JSON or multipart `.txt`.
- **Control panel** (`panel_api`, JWT): `POST /api/auth/login/json`, `POST /api/documents`, `GET /api/pending/*`, `GET /api/rules`, `PATCH /api/rules/reorder`, `GET /api/lexicon`, `POST /api/admin/commit`. See [docs/CONTROL_PANEL.md](docs/CONTROL_PANEL.md). Env: `DATABASE_URL`, `JWT_SECRET`, `PANEL_ADMIN_EMAIL`, `PANEL_ADMIN_PASSWORD`, `PANEL_CORS_ORIGINS`, `WOCCON_UPLOAD_DIR`, `DUPLICATE_THRESHOLD`.
- **Reconstruction methodology:** [docs/RECONSTRUCTION_METHODOLOGY.md](docs/RECONSTRUCTION_METHODOLOGY.md) — Rudes/Carter method, Catawba vs PSC roles, rule kinds, next steps.
- **Reconstruction engineering roadmap:** [docs/RECONSTRUCTION_ROADMAP.md](docs/RECONSTRUCTION_ROADMAP.md) — comparative pipeline, hybrid model stack, grammar tiers, phased DoD.

## Notes

- Project focuses on the extinct Woccon language (Eastern Siouan, documented 1709)
- No formal testing framework configured - uses manual test scripts
- No linting/formatting tools configured
- Ollama model (llama3:8b) automatically pulled on startup
- Uses Docker with CUDA PyTorch runtime for deployment