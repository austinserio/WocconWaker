# Woccon Waker: Lesson & Content Generation — Plan (updated)

## Current status summary

| Phase | Status | Notes |
|-------|--------|--------|
| 1. Drive ingest & auth | **Done** | Sync state, resumable, Haiku/Sonnet split, force-full option |
| 2. Schedule & on-demand | **Superseded** | See revised approach below (upload-first, no scheduled Drive scrape) |
| 3. Structured extraction | **Done** | LLM + merge + verification; Sonnet/Haiku; source_url in output |
| 4. RAG & dictionary | **Done** | Reload endpoint + [Community] RAG tagging and precedence |
| 5. Frappe UI | **Revised** | Control-panel vision below; upload → review → commit flow |

---

## Phase 4: What’s left (before revision)

- **Reload endpoint**  
  After ingest/merge, the app (e.g. `woccon_llama_integration`) loads `dictionary.json` and `rules.json` at startup. There is no HTTP endpoint or in-process hook to “reload” after new merge output. Options: add e.g. `POST /admin/reload-language` that re-reads unified files (or swapped paths) and rebuilds RAG chunks, or document “restart app after merge.”

- **RAG chunk tagging and precedence**  
  RAG in `woccon_llama_integration.py` builds `self.chunks` from the lexicon and rules; it does not tag community-sourced items or give them higher precedence. If you switch the app to `dictionary_unified.json` / `rules_unified.json`, you could add a `[Community]` (or source) tag in the chunk text and boost community chunks in retrieval (e.g. when scoring).

---

## Revised direction: Frappe as control panel, upload-first (no scheduled Drive scrape)

### Design principles

- **Single place for language work:** Encourage doing language work **in Frappe**, not in Google Docs.
- **Drive as archive + library:** Use Drive to store **copies** of uploaded files and as part of the “library,” not as the primary source that we poll on a schedule.
- **Upload → extract → review → commit:** Users upload a file (or submit a Drive link); we parse once (Sonnet), store structured data for review in Frappe; community approves/modifies/rejects; then they “commit” into the main rule/lexicon DB.
- **Quality gate:** Optionally verify extraction (e.g. compare structured output to original with a model) so we don’t silently drop content.
- **Control panel:** Frappe = Woccon Waker “control panel” for the language: tabs (Grammar, Lexicon, etc.) → sections/categories (morphemes, phonemes, etc.) → line-by-line review with source links; library of source documents.

### High-level flow

1. **Ingest (current, optional)**  
   Existing Drive ingest (list folder, export Docs/PDFs) remains available for one-off or manual “pull from Drive” when needed — but **no regular 12-hour scheduled scrape**. Primary path is upload/link.

2. **Upload / link**  
   User uploads a **PDF or Doc** or submits a **Drive link** in WocconWaker (or Frappe).
   - Store **raw file** in:
     - Community Google Drive (archive).
     - A **separate DB on Azure** that Frappe uses for the “library” (so anyone can see files and academia behind the logic and read them).
   - Trigger **one-time extraction** (Sonnet) for that document.

3. **Verification (optional)**  
   Compare structured extraction to the original (e.g. with a model) to flag possible dropped or mis-parsed content before it goes to review.

4. **Structured data for review**  
   Extracted lexicon entries and rules are stored **separately** (e.g. “staging” or “pending” in Frappe/DB), not merged into the main lexicon/rules yet.

5. **Frappe control panel**  
   - **Language tabs:** e.g. Grammar, Lexicon, Pronunciation, etc.
   - **Subdivisions:** e.g. Morphemes, Phonemes, Suffixes, Roots, etc., so each rule/entry can be reviewed line by line.
   - **Source link:** Each line cites the document it was pulled from (link from existing `source_url` in processed data).
   - **Actions:** Community can **approve**, **modify**, or **reject** an imported rule or word.
   - When ready, they **commit** the approved set into the larger (canonical) lexicon/rules DB.

6. **Library**  
   Frappe shows a “library” of source documents (metadata + link to read); data comes from the Azure DB (and optionally Drive links). Raw files live in Drive + Azure so people can read the originals.

### Long-term goal

Rebuild the **logic behind Woccon** (rules, lexicon, morphology, phonology) in a structured, reviewable form so that:
- AI can **interpolate and extrapolate** from the rule base.
- As the community learns more about proto-Catawban, proto-Siouan-Catawban, and Woccon, the rule base grows and stays citable.
- The system can **answer questions** against this rule base and **accelerate (re)generation** of lessons and content.

---

## Phase 2 (revised): Upload and on-demand ingest

- **Remove:** Regular 12-hour scheduled Drive fetch as the main path.
- **Keep:** Optional on-demand “pull from Drive” (e.g. `POST /admin/ingest-drive` or script) for one-off syncs.
- **Add:**
  - **Upload endpoint:** Accept PDF/Doc upload; store in Community Drive + Azure DB; trigger Sonnet extraction; write structured output to staging/pending for Frappe.
  - **Drive link:** Accept a Drive link; fetch file (with auth), store same as upload; same extraction and staging flow.
  - **No schedule** for Drive by default; encourage “add via upload or link” instead.

---

## Phase 4 (revised): RAG, dictionary, reload

- **Dictionary/merge:** Already done (unified lexicon + rules, community over Lawson, source_url).
- **Reload:** Add an explicit **reload endpoint** (or startup hook) so that after merge or after a Frappe “commit,” the app can reload lexicon/rules and rebuild RAG without restart.
- **RAG (optional):** When using unified data, tag chunks with source (e.g. `[Community]`) and give community-sourced chunks higher precedence in retrieval.

---

## Phase 5 (revised): Frappe UI — control panel and workflow

- **Scope:** Frappe as the main “control panel” for the language.
- **Structure:**
  - **Woccon Waker plugin** (or app) in Frappe.
  - **Tabs / top-level pages:** Grammar, Lexicon, Pronunciation, etc.
  - **Sections / categories:** e.g. Morphemes, Phonemes, Affixes, Roots, Inflection, etc., under each tab.
  - **Line-by-line review:** Each rule or lexicon entry is one row/card; show **source link** (from `source_url` in processed data); allow **edit**, **approve**, **reject**.
- **Library:** List of source documents (from Azure DB); link to read file; shows “academia behind the logic.”
- **Workflow:**
  - Upload/link → file stored (Drive + Azure) → Sonnet extraction → structured data in “pending” / staging.
  - Review in Frappe (by tab/section) → approve / modify / reject.
  - **Commit** approved set into canonical lexicon/rules (DB or exported JSON that WocconWaker uses).
- **Source of truth:** To be decided when implementing: e.g. Frappe DB as source of truth with WocconWaker reading via API or export; or filesystem JSON with Frappe as editor and sync job. Plan favors “Frappe as editor, canonical data in DB or export” so lesson generation can pull from one place.

---

## Verification step (new)

- After Sonnet extraction, **optional check:** Use a model to compare structured output (lexicon + rules snippets) to the original document text and flag:
  - Possible dropped lines or entries.
  - Possible mis-parsed fields.
- Output: report or UI in Frappe for reviewers before they approve/commit.

---

## Implementation order (suggested)

1. **Phase 4 (minimal):** Reload endpoint; optionally point app at unified files + RAG tagging.
2. **Upload + storage:** Upload endpoint; store file in Drive + Azure DB; trigger extraction (reuse existing Sonnet pipeline); write to “pending” storage (DB or JSON Frappe can read).
3. **Frappe plugin shell:** Tabs (Grammar, Lexicon, etc.), sections, list views for “pending” items with source link; approve/reject/modify; no commit yet.
4. **Commit flow:** “Commit” approved set into canonical lexicon/rules; reload endpoint so WocconWaker sees new data.
5. **Drive link:** Accept Drive link, fetch, same as upload.
6. **Verification:** Optional model-based check of extraction vs original.
7. **Library UI:** Frappe library view over Azure DB (and links to Drive if desired).

This keeps the existing ingest and merge useful for one-off or legacy Drive pulls while shifting the main workflow to upload → review in Frappe → commit.
