# Woccon Control Panel

Monorepo admin UI for reviewing extracted lexicon and grammar rules, uploading scholarship (PDF, txt, docx, Google Drive links), and committing approved data to `dictionary_unified.json` / `rules_unified.json` with an in-process RAG reload.

## Quick start (local)

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # set JWT_SECRET, PANEL_ADMIN_PASSWORD, etc.
alembic upgrade head        # optional; startup also runs create_all + bootstrap
WOCCON_MODE=server python app.py

# Frontend (separate terminal)
cd panel && npm install && npm run dev
# Open http://localhost:5173/panel/login
```

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

Machine admin endpoints (`/admin/reload-language`, `/admin/ingest-drive`) still use `INGEST_DRIVE_SECRET`.

## API overview

All panel routes are under `/api` with `Authorization: Bearer <token>` except login.

- `POST /api/auth/login/json` — `{ email, password }`
- `GET /api/auth/me`
- `POST /api/documents` — multipart file upload
- `POST /api/documents/link` — `{ drive_url, title? }`
- `GET /api/pending/rules`, `PATCH /api/pending/rules/{id}`, bulk approve
- `GET /api/rules?category=grammar`, `PATCH /api/rules/reorder`
- `GET /api/lexicon?q=...` — paginated list with `teaching_unit`, `word_class`, `lesson_band` filters
- `GET /api/lexicon/taxonomy`, `/grouped`, `/stats`, `POST /api/lexicon/reclassify`
- `POST /api/admin/commit` — admin only; exports JSON + reloads assistant

## Azure Container Apps

`Dockerfile.azure` builds the panel SPA and copies `panel/dist` into the image. Set at minimum:

- `DATABASE_URL` — Azure Database for PostgreSQL connection string
- `JWT_SECRET` — strong random secret
- `PANEL_ADMIN_PASSWORD` — change from default
- `WOCCON_DICTIONARY_PATH` / `WOCCON_RULES_PATH` — unified file paths (writable volume if committing in-container)

Mount a persistent volume on `/app/data` for SQLite uploads **or** use Postgres + Azure Files for `WOCCON_UPLOAD_DIR`.

## Grammar rule organization

Each **grammar** rule is tagged with three dimensions (auto-classified on ingest; editable via **Edit tags**):

| Dimension | Examples |
|-----------|----------|
| **Grammar area** | Phonology, Morphology, Syntax, Morphosyntax, Lexicon & word classes, Semantics, Discourse, Historical / comparative |
| **Part of speech** | Noun, verb, pronoun, affix, clause, … |
| **Construction** | Word order (SOV), relative clause, possession, reduplication, agreement, … |

The Rules page groups grammar notes by **grammar area** in the left sidebar, with filters for POS and construction. Re-run classification on all rules: `POST /api/rules/reclassify` (admin).

Committed rules export these fields in `rules_unified.json` under `community_grammar_notes` as `{ text, source_url, grammar_domain, pos_tag, construction_type }`.

## Dictionary / vocabulary organization

Each lexicon entry is tagged for teaching (auto-classified on ingest; editable via **Edit tags**):

| Dimension | Examples |
|-----------|----------|
| **Teaching unit** | Lawson core (1709), kinship, animals, plants & food, numbers, motion, function words, … |
| **Word class** | Noun, verb, pronoun, particle, affix, numeral, … (normalized from extractor POS) |
| **Lesson band** | Lawson core, beginner, intermediate, advanced, reference |

The Dictionary page groups words by **teaching unit** in the left sidebar, with filters for word class and lesson band. Re-run classification on all entries: `POST /api/lexicon/reclassify` (admin).

Committed lexicon exports these fields in `dictionary_unified.json` as `{ woccon, english, pos, teaching_unit, word_class, lesson_band, ... }`.

## Workflow

1. **Upload** PDF/txt/docx or paste a Drive link (file shared with service account).
2. Background job runs `drive_extract.extract_one_file` → pending lexicon + rules.
3. **Pending** — approve, reject, or review duplicate hints.
4. **Dictionary** — browse by teaching unit; adjust tags before lessons use the data.
5. **Rules** — drag-reorder committed community rules by category.
6. **Commit** (admin) — merge into canonical DB → export unified JSON → `reload_language_data`.

Legacy structured phonology/morphology in `rules.json` remain read-only via `GET /api/rules/legacy`.
