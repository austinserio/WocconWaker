# Woccon Control Panel

Monorepo admin UI for reviewing extracted lexicon and grammar rules, uploading scholarship (PDF, txt, docx, Google Drive links), and committing approved data to `dictionary_unified.json` / `rules_unified.json` with an in-process RAG reload.

## Quick start (local)

**Panel only** (backend + Vite dev server):

```bash
cp .env.example .env        # set JWT_SECRET, PANEL_ADMIN_PASSWORD, etc.
alembic upgrade head        # optional; startup also runs create_all + bootstrap
./run-panel-dev.sh          # starts backend + Vite; Ctrl+C stops both
# Open http://localhost:5173/panel/login
```

**Panel + Messenger** (tunnel + backend + Vite — one command):

```bash
./run-local-full.sh
# Panel UI: http://localhost:5173/panel/login
# Webhook:  https://<CLOUDFLARE_TUNNEL_HOSTNAME>/webhook
# Stop stale processes: ./run-local-full.sh --stop
```

See [LOCAL_DEV.md](../LOCAL_DEV.md) for Cloudflare tunnel setup.

Or run backend and frontend in **separate terminals** (stopping one does not stop the other):

```bash
# Terminal 1 — backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
WOCCON_MODE=server python app.py

# Terminal 2 — frontend
cd panel && npm install && npm run dev
```

To stop stale dev processes left on ports 5173/8000: `./run-panel-dev.sh --stop` (panel only) or `./run-local-full.sh --stop` (full stack including tunnel).

Default admin (from `.env`): `PANEL_ADMIN_EMAIL` / `PANEL_ADMIN_PASSWORD`.

Production build:

```bash
cd panel && npm run build
# Serves at http://localhost:8000/panel/ when panel/dist exists
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:///./data/woccon.db` | SQLite local; `postgresql://...` on Azure |
| `JWT_SECRET` | (required in prod) | JWT signing |
| `JWT_EXPIRE_MINUTES` | `1440` | Token lifetime |
| `PANEL_ADMIN_EMAIL` | `admin@woccon.local` | Bootstrap admin |
| `PANEL_ADMIN_PASSWORD` | `changeme` | Bootstrap password |
| `PANEL_CORS_ORIGINS` | `http://localhost:5173,...` | Vite dev CORS |
| `WOCCON_UPLOAD_DIR` | `data/uploads` | Stored uploads |
| `DUPLICATE_THRESHOLD` | `0.85` | Pending duplicate flag |
| `WOCCON_DICTIONARY_PATH` | unified JSON path | Commit + reload target |
| `WOCCON_RULES_PATH` | unified rules path | Commit + reload target |
| `PDF_OCR_ENABLED` | `true` | Auto vision OCR for scanned PDF pages |
| `PDF_OCR_MIN_CHARS_PER_PAGE` | `50` | Trigger OCR when pdfplumber yields fewer chars |
| `PDF_OCR_DPI` | `200` | Render resolution for vision OCR |
| `PDF_OCR_MODEL` | (uses `ANTHROPIC_MODEL`) | Claude model for page transcription |
| `PANEL_PUBLIC_BASE_URL` | `http://localhost:5173` | Base URL for invite/reset email links |
| `EMAIL_MODE` | `log` | `log` = print links to server log; `smtp` = send mail |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | — | SMTP relay (SendGrid, M365, etc.) |
| `SMTP_USE_TLS` | `true` | STARTTLS on SMTP |
| `INVITE_EXPIRE_HOURS` | `168` | Invitation link lifetime |
| `PASSWORD_RESET_EXPIRE_HOURS` | `24` | Password reset link lifetime |

Scanned PDF OCR requires `ANTHROPIC_API_KEY` (Anthropic-only for vision). Library shows **Vision OCR** / **Hybrid OCR** on documents when OCR was used.

Machine admin endpoints (`/admin/reload-language`, `/admin/ingest-drive`) still use `INGEST_DRIVE_SECRET`.

### Messenger / assistant data source

With default `WOCCON_LANGUAGE_SOURCE=panel_db`, the Woccon assistant (Messenger and `POST /message`) loads lexicon and community rules **from the same SQLite/Postgres DB** as the control panel (`DATABASE_URL`), not from `dictionary_unified.json` / `rules_unified.json`. Those unified files are **backup exports** written when you **Commit**; treat old unified JSON as archival.

After editing canonical dictionary or rules in the panel, restart the app or call `POST /admin/reload-language` so the assistant picks up changes without a Commit. Set `WOCCON_LANGUAGE_SOURCE=json` only if you intentionally want file-based loading.

## Team access and roles

| Role slug | Label | Access |
|-----------|-------|--------|
| `admin` | Admin | Full access, commit, audit, team management, re-extract |
| `worker` | Community language worker | Pending review, upload, edit dictionary/rules |
| `member` | Community member | Read-only: dictionary, grammar rules, library |

Bootstrap admin is created from `PANEL_ADMIN_EMAIL` / `PANEL_ADMIN_PASSWORD` on first startup. Additional users are **invited** by an admin (Team page); they complete signup with first name, last name, and password.

### Email (invites and password reset)

- **Local dev:** leave `SMTP_HOST` unset (or `EMAIL_MODE=log`). Invite and reset links are printed to the API server log.
- **Production:** set `EMAIL_MODE=smtp` and SMTP credentials. Run `./scripts/setup-panel-email-azure-cli.sh` for SendGrid/M365 env templates and Azure Container App secret commands.
- Set `PANEL_PUBLIC_BASE_URL` to the URL users open in the browser (e.g. `https://your-app.azurecontainerapps.io` — panel is at `/panel/`).

Public routes (no login): `/panel/accept-invite?token=…`, `/panel/forgot-password`, `/panel/reset-password?token=…`

## API overview

All panel routes are under `/api` with `Authorization: Bearer <token>` except login and public auth routes.

- `POST /api/auth/login/json` — `{ email, password }`
- `GET /api/auth/me` — current user (name, role, display_name)
- `PATCH /api/auth/me` — update first/last name
- `GET /api/auth/invite?token=` — preview invitation (public)
- `POST /api/auth/accept-invite` — complete signup (public)
- `POST /api/auth/forgot-password` — request reset email (public)
- `POST /api/auth/reset-password` — set new password (public)
- `GET /api/users` — list users + pending invitations (admin)
- `POST /api/users/invite` — `{ email, role }` (admin)
- `POST /api/users/invitations/{id}/resend` — resend invite (admin)
- `DELETE /api/users/invitations/{id}` — revoke invite (admin)
- `PATCH /api/users/{id}` — `{ role }` (admin)
- `DELETE /api/users/{id}` — deactivate user (admin)
- `POST /api/documents` — multipart file upload
- `POST /api/documents/link` — `{ drive_url, title? }`
- `PATCH /api/documents/{id}` — edit bibliographic citation fields
- `POST /api/admin/documents/{id}/reextract` — admin; page-aware re-extract + locator merge (Library uploads)
- `POST /api/admin/backfill-citations` — admin; re-parse Drive sources cited on canonical rows (`?dry_run=true`, `?export=true`)
- `GET /api/admin/backfill-citations/status` — last citation backfill run status
- `GET /api/pending/rules`, `PATCH /api/pending/rules/{id}`, `POST /api/pending/rules`, bulk approve
- `GET /api/pending/lexicon`, `PATCH /api/pending/lexicon/{id}`, `POST /api/pending/lexicon`, bulk approve
- `GET /api/rules?category=grammar`, `PATCH /api/rules/{id}`, `PATCH /api/rules/reorder`, `DELETE /api/rules/{id}`
- `GET /api/lexicon?q=...` — paginated list with `teaching_unit`, `word_class`, `lesson_band` filters
- `PATCH /api/lexicon/{id}`, `DELETE /api/lexicon/{id}`
- `GET /api/lexicon/taxonomy`, `/grouped`, `/stats`, `POST /api/lexicon/reclassify`
- `POST /api/admin/commit` — admin only; exports JSON + reloads assistant

## Azure Container Apps

`Dockerfile.azure` builds the panel SPA and copies `panel/dist` into the image. Set at minimum:

- `DATABASE_URL` — Azure Database for PostgreSQL connection string
- `JWT_SECRET` — strong random secret
- `PANEL_ADMIN_PASSWORD` — change from default (bootstrap admin only)
- `PANEL_PUBLIC_BASE_URL` — Container App HTTPS URL
- `EMAIL_MODE=smtp` + `SMTP_*` — for team invites (see `./scripts/setup-panel-email-azure-cli.sh`)
- `WOCCON_DICTIONARY_PATH` / `WOCCON_RULES_PATH` — unified file paths (writable volume if committing in-container)

Mount a persistent volume on `/app/data` for SQLite uploads **or** use Postgres + Azure Files for `WOCCON_UPLOAD_DIR`.

Run `alembic upgrade head` after deploy (migration `009_users_auth` adds names, invitations, role renames).

### Sync env from local `.env` to Azure

After editing `.env` locally:

```bash
./scripts/sync-azure-container-env.sh          # apply secrets + env to Container App
./scripts/sync-azure-container-env.sh --dry-run
```

Sets `PANEL_PUBLIC_BASE_URL` to `https://<container-app-fqdn>` automatically. The **control panel** (not a separate process) is served at `/panel/` by the same `uvicorn` process when `panel/dist` is in the Docker image (`Dockerfile.azure` builds it).

Production URL example: `https://wocconwaker-app.<region>.azurecontainerapps.io/panel/login`

## Grammar rule organization

Each **grammar** rule is tagged with three dimensions (auto-classified on ingest; editable via **Edit tags**):

| Dimension | Examples |
|-----------|----------|
| **Grammar area** | Phonology, Morphology, Syntax, Morphosyntax, Lexicon & word classes, Semantics, Discourse, Historical / comparative |
| **Part of speech** | Noun, verb, pronoun, affix, clause, … |
| **Construction** | Word order (SOV), relative clause, possession, reduplication, agreement, … |

The Rules page groups grammar notes by **grammar area** in the left sidebar, with filters for POS and construction. Re-run classification on all rules: `POST /api/rules/reclassify` (admin).

Committed rules export these fields in `rules_unified.json` under `community_grammar_notes` as `{ text, source_url, citation_short, citation_full, source_page, source_excerpt, provenance_status, grammar_domain, pos_tag, construction_type }`.

## Dictionary / vocabulary organization

Each lexicon entry is tagged for teaching (auto-classified on ingest; editable via **Edit tags**):

| Dimension | Examples |
|-----------|----------|
| **Teaching unit** | Lawson core (1709), kinship, animals, plants & food, numbers, motion, function words, … |
| **Word class** | Noun, verb, pronoun, particle, affix, numeral, … (normalized from extractor POS) |
| **Lesson band** | Lawson core, beginner, intermediate, advanced, reference |

The Dictionary page has three views: **Base vocabulary** (definitive ~209-word list), **All entries** (paginated flat browse), and **By teaching unit** (sidebar groups). Expand a base word to see linked variant attestations from other sources. Re-run classification on all entries: `POST /api/lexicon/reclassify` (admin).

### Definitive base vocabulary

The Google Doc **Documentation of Woccon Words** (`WOCCON_BASE_VOCAB_DRIVE_ID`) is the authoritative word list. It appears pinned at the top of **Library** with inline browse and **Sync from Google Doc** (`POST /api/admin/vocab-base/sync`).

- Base entries: `is_base_entry=true`, `source=vocab_base`
- Other attestations link via fuzzy match (`base_entry_id`, `base_match_method`, `base_match_score`)
- Unmatched pending rows appear in Pending with **Link to existing word** or **Add to vocabulary**
- Scripts: `python scripts/import_base_vocab.py`, `python scripts/link_lexicon_to_base.py`

Pronunciations from **English-Woccon** (`WOCCON_PRONUNCIATION_DRIVE_ID`) are merged onto base entries when you sync base vocabulary (exact or fuzzy woccon/english match). The pronunciation doc appears in Library as a pronunciation guide.

API: `GET /api/lexicon/base`, `GET /api/lexicon/{id}/variants`, `GET /api/pending/lexicon?unmatched_only=true`, `POST /api/pending/lexicon/{id}/link-base`, `POST /api/pending/lexicon/{id}/promote-base`.

Committed lexicon exports these fields in `dictionary_unified.json` as `{ woccon, english, pos, teaching_unit, word_class, lesson_band, is_base_entry, base_entry_id, citation_short, citation_full, source_page, source_excerpt, provenance_status, ... }`.

## Bibliographic provenance

Each **source document** in the Library can have Chicago author-date bibliography metadata:

| Field | Purpose |
|-------|---------|
| `short_title` | Shorthand label (e.g. `Koontz 2019`) |
| `authors` | JSON array string, e.g. `["Koontz, Robert L."]` |
| `year`, `pub_title`, `container_title`, `publisher`, `place` | Structured bib fields |
| `citation_text` | Full citation override |

Each **lexicon entry** and **rule note** carries locators when extracted from page-marked PDFs:

| Field | Meaning |
|-------|---------|
| `source_page` / `source_page_end` | Printed page (or range) |
| `source_excerpt` | Surrounding text for verification |
| `provenance_status` | `verified` (excerpt matched), `inferred` (chunk/page only), `missing`, `manual` |

UI shows a collapsed shorthand citation (e.g. `Koontz 2019, p. 42`) with expandable full citation and excerpt on Dictionary, Rules, and Pending pages.

Lawson (1709) entries use a seed bibliography (`Lawson 1709`) linked at bootstrap.

### Re-extract and citation backfill

**Library uploads** (`--db`):

1. **Library → Edit citation** — set author, year, full title before or after ingest.
2. **Re-extract with provenance** (Library button or `POST /api/admin/documents/{id}/reextract`) — re-runs page-aware LLM extraction, merges locators into canonical rows, replaces pending rows for that document.
3. `python scripts/backfill_provenance.py --db` — re-extract all non-seed rows in `source_documents` (usually uploaded PDFs only).

**Existing Drive citations** (`--from-citations`) — use when lexicon/rules already have `source_url` from drive_staging / unified JSON but no Library document:

```bash
python3 scripts/backfill_provenance.py --from-citations --dry-run   # list ~16 sources
python3 scripts/backfill_provenance.py --from-citations --text-only --export  # fast: PDF text search only
python3 scripts/backfill_provenance.py --from-citations --export    # LLM re-extract + PDF text search
```

Or `POST /api/admin/backfill-citations?export=true` (runs in background; poll `GET /api/admin/backfill-citations/status`).

Citation backfill **does not create Pending rows** — it updates canonical lexicon/rules in place (`merge_only`). Matches rows by **same Drive file ID + woccon/content**. Canonical notes are often LLM paraphrases, so after LLM merge a **PDF text search pass** fills remaining locators (longest distinctive phrase match). Use `--text-only` to skip LLM and run only that search pass.

Extraction uses the same LLM stack as Drive ingest (`ANTHROPIC_API_KEY` → Claude, else `LOCAL_LLM` → Ollama, else Foundry). Set `REEXTRACT_MODEL` to override. **Scanned PDF OCR** always uses Anthropic vision (`PDF_OCR_*` env vars). Requires `GOOGLE_APPLICATION_CREDENTIALS` for Drive fetch.

### Clean rebuild (Library-first)

When re-ingesting community data with page-level provenance, use the Library pipeline one document at a time — not bulk `drive_ingest.py` → `merge_staging.py`.

**List URLs to reprocess** (16 Drive sources with prior extracted content):

```bash
python scripts/list_reprocess_urls.py
```

Writes `data/reprocess_urls.txt` and `data/reprocess_urls.md`.

**Backup and wipe panel DB** (preserves admin login in `users`):

```bash
python scripts/reset_panel_db.py --backup --wipe
```

Backups go to `data/backups/`. After wipe, set `PANEL_IMPORT_COMMUNITY=false` in `.env` (default) and restart the app. Bootstrap imports Lawson-only lexicon from `dictionary.json` (~141 words) — not community rows from `dictionary_unified.json`.

**Per-document ingest:** Upload → Library shows extraction **progress %** while processing → Pending review → Commit.

## Workflow

1. **Upload** PDF/txt/docx or paste a Drive or Google Docs link (file shared with service account).
2. **Library** — watch extraction progress (%); **Vision OCR** badge appears when a scanned PDF was transcribed via Claude; edit bibliographic citation; optionally re-extract for page-level provenance.
3. Background job reads the document (pdfplumber for PDFs; Claude vision OCR when pages are sparse) → page-aware `drive_extract.extract_one_file` → pending lexicon + rules with locators.
4. **Pending** — add manual entries, edit extracted rows, approve, reject, review citations and duplicate hints.
5. **Dictionary** — browse by teaching unit; edit or delete committed entries (Lawson seed entries cannot be deleted).
6. **Rules** — drag-reorder committed community rules by category; edit or delete rule content and tags.
7. **Commit** (admin) — merge into canonical DB → export unified JSON with citations → `reload_language_data`.

### Manual entry CRUD (hybrid)

| Action | Where | Result |
|--------|-------|--------|
| **Add** lexicon or rule | Pending → Add entry | Row in pending queue (`provenance_status: manual`); approve then Commit |
| **Edit** before commit | Pending → Edit | Content/tags/locators; status becomes `modified` when content changes |
| **Edit** committed data | Dictionary or Rules → Edit | PATCH canonical row; reflected in JSON on next Commit |
| **Delete** committed data | Dictionary or Rules → Delete | Removed from canonical DB (Lawson lexicon entries return 409); export on Commit |

Legacy structured phonology/morphology in `rules.json` remain read-only via `GET /api/rules/legacy`.
