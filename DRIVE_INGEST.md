# Drive Ingest (Google Drive → RAG / dictionary)

## Phase 1: List folder and fetch text

### Env vars

| Variable | Required | Description |
|----------|----------|-------------|
| **GOOGLE_APPLICATION_CREDENTIALS** | **Yes** | Path to the **service account JSON** key file. The Drive folder must be shared with this service account’s email (e.g. `xxx@project.iam.gserviceaccount.com`). Do not commit the JSON. |
| **DRIVE_FOLDER_ID** | No | Folder ID to ingest. Default: `1s1CgonVWEqj1SBKLKj0FcNotcpAHRYIt`. |
**Note:** The Drive API does not accept API keys for listing/reading (401). Use a service account JSON only.

### Setup (service account)

1. In Google Cloud Console: create a service account, create a key (JSON), download it.
2. Share the Drive folder with the service account email (Editor or Viewer).
3. Set in `.env` or shell: `export GOOGLE_APPLICATION_CREDENTIALS=/path/to/your-key.json`

### Run Phase 1 verify

```bash
pip install -r requirements.txt
python drive_ingest.py
```

This lists all files in the folder and fetches text from every Google Doc and PDF. It prints a JSON summary: `files_listed`, `docs_fetched`, `pdfs_fetched`, and short previews. Any errors are listed in `errors`.

### Supported file types (Phase 1)

- **Google Docs**: exported as plain text.
- **PDFs**: text extracted (no OCR). Scanned PDFs will yield little or no text until OCR is added later.

Other types (e.g. Sheets) are skipped and only listed.

---

## Phase 2: Schedule (cron) and on-demand

### Every 12 hours with cron

Cron does not load your shell `.env`, so the script must load it (or you set vars in the crontab).

**Option A – use the run script (recommended)**  
Ensure `run_drive_ingest.sh` sources `.env` (it does). Then:

```bash
# Edit crontab
crontab -e

# Add line: run ingest every 12 hours (at 00:00 and 12:00 UTC)
# Replace /path/to/WocconWaker with your project root.
0 */12 * * * /path/to/WocconWaker/run_drive_ingest.sh >> /tmp/drive_ingest.log 2>&1
```

Use the **absolute path** to `run_drive_ingest.sh` on your machine (e.g. `$(pwd)/run_drive_ingest.sh` from the project root).

**Option B – call Python with env file**  
If you don’t use the script, set `GOOGLE_APPLICATION_CREDENTIALS` (and optionally `DRIVE_FOLDER_ID`) in the crontab or in a small wrapper that sources `.env` then runs `python3 drive_ingest.py`.

### On-demand via API

With the FastAPI server running:

- **Trigger ingest:**  
  `POST /admin/ingest-drive`  
  Returns the same JSON summary as `drive_ingest.py` (files_listed, docs_fetched, pdfs_fetched, errors, etc.).

- **Optional auth:**  
  If you set `INGEST_DRIVE_SECRET` in `.env`, require it on each request:
  - Header: `X-Ingest-Secret: <your-secret>`
  - Or query: `POST /admin/ingest-drive?secret=<your-secret>`

- **Last run status:**  
  `GET /admin/ingest-drive/status`  
  Returns the result of the most recent ingest (or "no run yet"). Same optional secret as above.

**Example (no secret):**
```bash
curl -X POST http://localhost:8000/admin/ingest-drive
```

**Example (with secret):**
```bash
curl -X POST -H "X-Ingest-Secret: your-secret" http://localhost:8000/admin/ingest-drive
```

---

## Phase 3: Structured extraction (per file)

After fetching text, the ingest runs **structured extraction** (LLM) **per source file**. Each file gets its own JSON so you can review file-by-file and choose what to merge where (lexicon vs grammar vs pronunciation).

- **One JSON per file** in `woccon_language/drive_staging/` (or `DRIVE_STAGING_DIR`). Each file has:
  - `source_path`: original path (e.g. `Articles/Woccon_Waccamaw Documentation.pdf`)
  - `source_url`: stable Google Drive link to the document (e.g. `https://drive.google.com/file/d/{fileId}/view`) for citing in Frappe so people can verify which document a fact came from
  - `lexicon_entries`: list of { woccon, english, pos, pronunciation? }
  - `grammar_notes`: list of strings
  - `pronunciation_notes`: list of strings
  - `cultural_notes`: list of strings (context for the agent: e.g. that Woccon is Siouan and how we know, historical names, tribal history—usable in RAG/answers later)
- **manifest.json** in the same directory lists every file with `source_url` and counts (lexicon_count, grammar_count, pronunciation_count, cultural_count) for quick review.
- **Progress** during extraction: logs show `Document N/M | chunk X/Y of file | overall chunk A/B (Z%)` so you see documents left and overall %.
- Review each file’s JSON and then merge chosen entries into the main dictionary/rules in Phase 4.

The same model as chat is used (Foundry or Ollama per `LOCAL_LLM`).

- **Skip extraction** (fetch only): set `SKIP_EXTRACTION=1` or pass `skip_extraction=True` when calling from code.
- **Staging directory**: optional `DRIVE_STAGING_DIR` (default: `woccon_language/drive_staging`).
- **Limit for testing**: set `DRIVE_INGEST_LIMIT=5` to only fetch and extract the **first 5** Docs/PDFs (skips the rest). Unset or 0 = no limit.
- **Whole-file vs chunking**: If a file’s text is under the limit (default **14,000 characters**), the extractor sends the whole file in one call. Kept low because Anthropic’s SDK requires streaming for requests that may take >10 minutes, so larger docs (e.g. English–Woccon at ~18k chars) are chunked and complete reliably. For Llama 3 8B use `DRIVE_EXTRACT_WHOLE_FILE_MAX_CHARS=12000`. To try whole-file for big docs with Claude, set `DRIVE_EXTRACT_WHOLE_FILE_MAX_CHARS=60000` and add streaming support in `llm_client`.

### Test that ingest works when run twice (cron-style)

Run the ingest twice, 30 seconds apart, to confirm it works when invoked repeatedly (e.g. by cron):

```bash
chmod +x test_drive_ingest_cron.sh
./test_drive_ingest_cron.sh
```

You should see two full JSON summaries about 30 seconds apart. If both succeed, the same script is safe to use in cron.

### Test that cron is actually firing

1. Add a temporary crontab that runs the ingest **every minute**:
   ```bash
   crontab -e
   # Add this line (use your real path to run_drive_ingest.sh):
   * * * * * /path/to/WocconWaker/run_drive_ingest.sh >> /tmp/drive_ingest.log 2>&1
   ```
2. Wait 2–3 minutes, then check the log:
   ```bash
   cat /tmp/drive_ingest.log
   ```
   You should see multiple JSON summaries (one per minute).
3. Remove the every-minute job so it doesn’t run 1,440 times per day:
   ```bash
   crontab -e
   # Delete the * * * * * line, save and exit.
   ```
4. Switch back to the every-12-hours schedule:
   ```bash
   0 */12 * * * /path/to/WocconWaker/run_drive_ingest.sh >> /tmp/drive_ingest.log 2>&1
   ```

---

## Phase 4: Merge staging → unified lexicon and notes

After reviewing files in `woccon_language/drive_staging/`, run the merge to build a **community-only lexicon**, **compare** to the legacy dictionary, and produce **unified** outputs (community over Lawson for overlaps; every entry has `source` and `source_url` for citation).

### Run merge

```bash
python merge_staging.py
```

### Outputs (all under `woccon_language/`)

| File | Description |
|------|-------------|
| **lexicon_from_drive.json** | Community-only lexicon from staging (each entry has `source_url`). |
| **merge_comparison_report.json** | Counts and lists: `old_only_woccon` (Lawson/legacy only), `new_only_woccon` (community only), `overlap_woccon` (community wins). |
| **dictionary_unified.json** | Full dictionary with unified lexicon: community entries (with `source_url`) + Lawson-only entries (`source: "lawson"`, `source_url: null`). Original dictionary is **not** overwritten. |
| **dictionary_backup_YYYYMMDD.json** | Backup of `dictionary.json` from the day you ran the merge. |
| **community_notes.json** | `grammar_notes`, `pronunciation_notes`, `cultural_notes` as lists of `{ "text", "source_url" }` for RAG/Frappe. |
| **rules_unified.json** | Legacy **rules.json** (phonology, morphology, affixes, etc.) plus Drive-sourced rules: `community_grammar_notes`, `community_pronunciation_notes`, `community_cultural_notes` (each list of `{ "text", "source_url" }`). One file for both legacy rules and community rules. |
| **rules_backup_YYYYMMDD.json** | Backup of `rules.json` from the day you ran the merge. |

Rules are scraped from Drive via extraction (grammar_notes, pronunciation_notes); the merge adds them to unified rules so you have one rules file with both legacy structure and community-sourced notes (with source_url).

### Precedence

- **Overlap** (same Woccon in legacy and community): use **community** version (with pronunciation, `source_url`).
- **Old-only**: keep in unified lexicon with `source: "lawson"`, `source_url: null`.
- To adopt the unified lexicon as the app dictionary, replace `dictionary.json` with `dictionary_unified.json` (after review).
