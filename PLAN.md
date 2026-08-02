# Woccon Waker — Project plan

**Reconstruction:**
- **Method & next steps:** [docs/RECONSTRUCTION_METHODOLOGY.md](docs/RECONSTRUCTION_METHODOLOGY.md) — Lawson↔Catawba first, selective PSC, rule kinds, cognate/correspondence shapes.
- **Engineering roadmap:** [docs/RECONSTRUCTION_ROADMAP.md](docs/RECONSTRUCTION_ROADMAP.md) — digitize → correspondences → candidates → committee publish → learner products (R0–R6).

This file tracks **platform / ingest / panel** history.

---

## Current status summary

| Phase | Status | Notes |
|-------|--------|--------|
| 1. Drive ingest & auth | **Done** | Sync state, resumable, Haiku/Sonnet split, force-full option |
| 2. Schedule & on-demand | **Superseded** | Upload-first; optional `POST /admin/ingest-drive` |
| 3. Structured extraction | **Done** | LLM + merge + verification; source_url in output |
| 4. RAG & dictionary | **Done** | `POST /admin/reload-language`; `[Community]` RAG precedence; `panel_db` default |
| 5. Control panel UI | **Done** | `panel/` + `panel_api/` — [docs/CONTROL_PANEL.md](docs/CONTROL_PANEL.md) |
| 6. Reconstruction engine | **Not started** | Method: [RECONSTRUCTION_METHODOLOGY.md](docs/RECONSTRUCTION_METHODOLOGY.md); eng: roadmap R0–R6 |
| 7. Committee publish gate | **Not started** | See roadmap R5 |
| 8. Learner products | **Partial** | Messenger + lessons; tier-gated curriculum TBD |

---

## Design principles (unchanged)

- **Single place for language work:** Control panel, not scattered Google Docs.
- **Drive as archive + library:** Upload/link is primary; Drive poll is optional.
- **Upload → extract → review → commit:** Community approves pending rows; admin commits to canonical DB.
- **Citations everywhere:** `source_url`, page, excerpt on lexicon and grammar notes.
- **Long-term:** Structured rule base so AI can assist reconstruction **with traces and review**, not replace linguists.

---

## What's next (platform)

Maintenance and near-term platform work:

| Item | Priority | Notes |
|------|----------|--------|
| Extraction verification UI | Medium | Compare structured output vs source before bulk approve (roadmap R4-b) |
| Postgres / prod sync | Ongoing | `scripts/pull_panel_db_from_postgres.sh`, migrate scripts |
| Panel polish | Low | Per user feedback; see CONTROL_PANEL.md |

Linguistic method and ordered next steps: **RECONSTRUCTION_METHODOLOGY.md**. Engineering phases: **RECONSTRUCTION_ROADMAP.md** (cognate schema → correspondences → candidates → committee gate → tier-aware lessons).

---

## Archived detail

Older Frappe-oriented paragraphs and step-by-step implementation order from 2025 planning are superseded by the control panel implementation. Historical notes:

- Frappe approach archived in [docs/FRAPPE_WOCCON_APP.md](docs/FRAPPE_WOCCON_APP.md).
- `merge_staging.py` remains useful for one-off Drive staging → unified JSON merges.
- Reload endpoint and community RAG tagging are **shipped** (`app.py`, `woccon_llama_integration.py`).

For commands and env vars, use [CLAUDE.md](CLAUDE.md).
