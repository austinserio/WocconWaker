# Reconstruction agent handoff (Aug 2026)

Single onboarding doc for Cursor agents joining Woccon reconstruction work. Read this first, then drill into linked docs.

| Doc | Role |
|-----|------|
| [RECONSTRUCTION_METHODOLOGY.md](RECONSTRUCTION_METHODOLOGY.md) | Scholarly method, phases 1–5, holdout program, calibration gate |
| [RECONSTRUCTION_ROADMAP.md](RECONSTRUCTION_ROADMAP.md) | Engineering R0–R6 tracks, model stack, DoD |
| [CONTROL_PANEL.md](CONTROL_PANEL.md) | Panel workflow, API, citations, commit |
| [CLAUDE.md](../CLAUDE.md) | Dev commands, Catawba separation, ingest, LLM env |

---

## 1. North star — calibrated regeneration

**Goal:** Expand usable Woccon vocabulary and grammar *without* inventing unattested forms or leaking Catawba into the teaching lexicon — and without teaching kids coin-flip reconstructions.

### Core shift: from accuracy to calibration

With ~90–140 evaluable pairs max, a single blended accuracy number (e.g. “70% holdout”) averages clean cases with murky ones and hides which predictions are safe to act on. Wrong words taught in a language with few fluent-ish learners are hard-to-undo harm. What the system must do is **know the difference between what it is sure of and what it is guessing** (*selective prediction* / *calibration*):

| Metric | Question |
|--------|----------|
| **Coverage** | What fraction of proposals land in the high-confidence bucket at all? |
| **Precision @ tier** | Of the words claimed high-confidence, how many are actually right? |

A system with low coverage (confident on 20%) but **~90%+ precision** in that bucket is more useful than “70% accurate” overall: you can act on the confident slice, and you know to scrutinize the rest hard. Growth is measured as **more words graduating into the high-confidence tier** as evidence accumulates — not as blended accuracy creeping upward.

This is not lowering the reliability bar. It is being precise about which part of the system is reliable and admitting, structurally, that part is not yet (and may never be for every word). A reviewer can inspect *why* a form is high-confidence (which rules, which cognate, independent corroboration) rather than trusting a black-box percentage.

### Teaching tiers (provenance) × confidence bands (calibration)

| Provenance tier | Meaning | Default use |
|-----------------|---------|-------------|
| **Tier 1** | Attested Woccon (Lawson 1709 + confirmed community spellings in English-Woccon) | Lessons, Messenger, drills — exact community `woccon` field |
| **Tier 2** | Not attested in Woccon but supported by Catawba sister cognates + tagged sound laws (+ optional PS backup) | Labeled reconstruction; classroom use gated by **confidence band** (Lane 6) |
| **Tier 3** | Speculative / low coverage / typology-only | Reference panel only; never default teaching |

| Confidence band | Typical evidence | Policy (committee-tunable) |
|-----------------|------------------|----------------------------|
| **High** | `established` sister rules with 2+ independent carriers; unambiguous Lawson/Rudes reading; direct cognate; no scholar disagreement on input | Classroom with disclaimer once precision @ high clears bar (~85–90%) |
| **Medium** | Mix of `tentative` / thin carriers; partial cognate; minor input ambiguity | Reference / explore mode; committee review required |
| **Low** | Singleton rules, disputed reading, morpheme-inferred or PS-only path | Reference-only indefinitely |

**Pipeline (Option A):** attested → use as-is; else Catawba cognate → project via sister rules → emit form **+ structured confidence signal** → evaluate **precision per confidence band** on holdout; else PS/PSC cautiously; else **do not auto-coin**. Do not train phonetic→Lawson exact-match mappers (failed on gold).

PSC is backup and morphology, not the default coinage crank. Woccon is Catawba’s **sister**, not its descendant.

---

## 2. Current state snapshot (Aug 2026)

### Data

| Asset | Count / status |
|-------|----------------|
| Lawson seed | ~141 words in `woccon_language/dictionary.json` |
| Cognate seed | 81 sets in `rudes_carter_seed.json` (App. 1 **certain ×58**, partial 7, possible 6, ps_only 10) |
| Correspondence registry | ~73 rules (`registry.json`); sister / diachronic / orthographic tagged |
| Alignments | 50 App. 1 certain pairs in `alignments.json` |
| Catawba staging | ~2,850 entries across 13 PDF/JSON sources in `catawba_staging/` |
| Catawba grammar store | `woccon_language/catawba_grammar/` (senses, morphemes, compounds — bootstrap in progress) |
| Carter sets | 34 parsed; 26 linked to seed; re-OCR recovered diacritics on Carter PDF |

### Built (phases 1–5)

- JSON cognate seed + correspondence registry v2 + alignments + gap report
- Deterministic proposer, holdout split, tiered scoring (baseline + value-added + ablation gate)
- Panel: Pending (lexicon, rules, Catawba, Comparative Links, Comparative linguistics), Dictionary, Rules, Library, Commit
- Comparative DB import (`import_cognates_to_panel.py`, `import_correspondences_to_panel.py`)
- `link_catawba_lexicon.py`, comparative link review API, Catawba grammar extraction services
- UIC deploy + Phase 3 Qwen validation queue scripts

### Not built / partial

- Committee publication states (`official_teaching`) — ~5% in roadmap; band-specific classroom policy open
- `reconstruction_candidates` end-to-end queue → approved lexicon (R3–R4; reuse `confidence.py` when wired)
- Full Catawba lexicon linked into cognate gaps at scale (linking pass started)
- Tier-aware lesson gating in Messenger (R6)
- ByT5 fine-tune on approved pairs only (deferred until registry stable)
- Rudes NAA dictionary drafts (external archive)

---

## 3. Main blocker

**Evidence scarcity + uneven noise, not rule tuning.**

- Only **~58 certain** Woccon↔Catawba cognate pairs anchor projection; many environments have **1–2 carriers** (cannot both train and validate the same law).
- Noise is **not uniform**: some items have clean, multiply attested correspondences; others are single-attestation / disputed / tentative. Blending them into one accuracy number throws away trust information the pipeline already has.
- **Legacy holdout gate:** combined **56.7%** vs **70%** threshold — documented historical FAIL (`data/holdout_report.json`). That single number is **no longer the success criterion**; keep it as a diagnostic only.
- Post-correction: **value-added segment** over copy-Catawba baseline is ~**+1–2%** on train/dev; test ~0%; oracle ceiling shows unconstrained rules hurt train — further proof that chasing blended accuracy is the wrong lever.
- Secondary literature re-OCR adds **one** evaluable pool item — corpus growth requires **Catawba lexical sources** + Comparative Links review, which also graduates more proposals into the high-confidence band.

**Do not chase 95% whole-word exact or “pass 70% overall.”** Ship calibrated confidence; grow cognates so high-confidence **coverage** rises while **precision @ high** stays above the committee bar.

---

## 4. Seven work lanes (ordered steps)

### Lane 1 — Tier 1 corpus (Woccon attested)

1. Keep English-Woccon + Documentation of Woccon Words as authoritative; hybrid parser + LLM for list docs (`HYBRID_LIST_EXTRACT`).
2. Review Pending **Woccon lexicon**; link unmatched rows to base vocabulary (`link-base`, `import_base_vocab.py`).
3. Commit approved rows → canonical DB → export `dictionary_unified.json`; reload assistant (`POST /admin/reload-language` or restart).
4. Fix Documentation gap list (~70 flagged; **~15–20** are real missing attestations after dedupe/parser noise).

### Lane 2 — Catawba comparative (never Woccon lexicon)

1. Ingest / re-OCR diacritic-stripped Catawba PDFs (`reocr_lossy_pdf.py`, `pages_with_lossy_text_layer`).
2. Sync staging → panel Pending **Catawba lexicon** (`POST /api/admin/staging/sync`).
3. Human review Catawba pending; **do not Commit into Woccon dictionary**.
4. Run `link_catawba_lexicon.py` → seed gaps; review **Comparative Links** tab.
5. Bootstrap / extend `catawba_grammar` (`extract_catawba_grammar.py`, `bootstrap_catawba_grammar.py`).

### Lane 3 — Correspondences & alignments

1. Regenerate registry: `tag_rule_kinds.py` → `upgrade_correspondence_registry.py` → `align_cognate_pairs.py`.
2. Validate: `validate_correspondence_registry.py`, `discover_correspondence_gaps.py`.
3. Import to panel; linguists confirm sister vs orthographic vs diachronic in Comparative browse.
4. Merge segment rules: `merge_segment_rules.py`; hand-edit `corrections.json` for broken cognate pairs.

### Lane 4 — Holdout & calibration

1. `build_holdout_split.py` (environment-stratified).
2. `run_lawson_holdout.py --eval-split dev|test` — report **v6** includes `metrics_by_confidence_band`.
3. `validate_holdout_report.py`; keep reading `value_added_segment`, ablation table, `broken` bucket as **diagnostics**.
4. **Primary report:** `metrics_by_confidence_band` in `data/holdout_report.json` — per-band `coverage` and `precision_exact` (legacy blended accuracy is diagnostic only). Scoring formula: [`woccon_reconstruction/confidence.py`](../woccon_reconstruction/confidence.py). Example dev decomposition: high 38% coverage @ 100% precision; low 46% @ 33%.
5. Phase 3 on UIC: `queue_phase3_qwen_validation_uic.sh` → Qwen re-extract Carter/Rudes slices for grammar validation (`run_phase3_validation_sequence.sh`).

### Lane 5 — Candidate queue (Tier 2 + confidence)

1. Proposer: `woccon_reconstruction/proposer.py` (sister rules + morphology + projectability buckets).
2. Every proposal emits a **structured confidence signal**, not just a form: applied rule IDs + `established`/`tentative`/`singleton`; cognate link type (direct / morpheme-level / inferred); scholar disagreement / input ambiguity flags; projectability bucket.
3. Wire outputs to `reconstruction_candidates` + panel review (roadmap R3–R4; partially stubbed) including confidence band + explanation.
4. Only **established/tentative** `sister_wc` rules for projection; never orthographic rules on PSC input.
5. Label all outputs `provenance_status: reconstructed`, `grammar_tier: 2`, plus `confidence_band`.

### Lane 6 — Committee policy (tier-specific)

1. Policy is **per confidence band**, not a blunt Tier 2 yes/no: e.g. high-confidence Tier 2 allowed in classrooms with disclaimer once precision @ high clears ~85–90%; medium/low stays reference-only / “explore reconstructed forms” indefinitely.
2. Implement publication states on canonical lexicon (`draft` → `committee_approved` → `official_teaching`) — roadmap R5; map states to confidence bands.
3. Gate Messenger / lessons to Tier 1 + **committee-approved high-confidence** Tier 2 only.

### Lane 7 — Learner products

1. Dictionary teaching units, pronunciation audio — see [PRONUNCIATION_AUDIO.md](PRONUNCIATION_AUDIO.md) (`generate_pronunciation_audio.py`, Kokoro batch, panel Listen).
2. Tier-aware `lesson_manager` / grammar lessons (R6).
3. Tutor guardrails: cite chunk IDs; refuse unlabeled coinages.

---

## 5. Panel surfaces map

| Surface | Purpose |
|---------|---------|
| **Library** | Upload PDF/txt/docx/Drive; extraction progress; re-extract; citation edit |
| **Pending → Rules** | Community grammar notes from Woccon sources |
| **Pending → Woccon lexicon** | Extracted/manual Woccon entries; approve → Commit path |
| **Pending → Catawba lexicon** | Comparative vocabulary only; patch/reject; **never Woccon Commit** |
| **Pending → Comparative Links** | Machine-suggested Woccon↔Catawba links; accept/reject/defer |
| **Pending → Comparative linguistics** | Catawba grammar drafts (`data/catawba_grammar_pending.json`); `--clear-pending` keeps approved/rejected + backups under `data/backups/` |
| **Dictionary / Rules** | Edit committed canonical rows |
| **Comparative** (page) | Read-only browse of imported cognate sets + correspondence rules |
| **Commit** (admin) | Merge approved pending → canonical DB → export unified JSON → RAG reload |

**Commit path:** Pending approve → **Commit** → `dictionary_unified.json` / `rules_unified.json` backups in `data/backups/`. Assistant loads from panel DB by default (`WOCCON_LANGUAGE_SOURCE=panel_db`).

---

## 6. Catawba / Woccon separation guards

Catawba is a **distinct language**. Its forms are evidence for reconstruction, not Woccon vocabulary.

| Layer | Guard |
|-------|--------|
| Folder routing | `content_language.py`: `Catawba Language/` → `catawba`; `Catawba Nation - Context/` → `context` (no vocab) |
| Extraction | Catawba prompt → `catawba_entries`; strip `lexicon_entries` from non-Woccon extracts |
| Staging | `woccon_language/catawba_staging/` separate from `drive_staging*` |
| Merge | `merge_staging.load_staging_files` refuses non-Woccon |
| Panel DB | `SourceDocument.content_language` blocks Woccon `PendingLexicon` from Catawba docs |
| Human process | Catawba pending tab + Comparative Links only; no Catawba rows in Woccon Commit |

Test: `python scripts/test_content_language_guard.py`

---

## 7. Key files & scripts

| Area | Path |
|------|------|
| Cognate seed | `woccon_language/cognate_sets/rudes_carter_seed.json` |
| Correspondences | `woccon_language/correspondences/registry.json`, `rudes_segment_rules.json` |
| Proposer / scoring | `woccon_reconstruction/proposer.py`, `scoring.py`, `confidence.py`, `recurrence.py`, `morphology.py`, `lawson_speller.py` |
| Catawba link | `scripts/link_catawba_lexicon.py`, `panel_api/services/comparative_links.py` |
| Holdout | `scripts/build_holdout_split.py`, `run_lawson_holdout.py`, `validate_holdout_report.py`, `data/holdout_report.json` |
| UIC Phase 3 queue | `scripts/queue_phase3_qwen_validation_uic.sh`, `wait_for_uic_llm_idle.sh`, `run_phase3_validation_sequence.sh`, `deploy_uic_ingest.sh` |
| Catawba grammar | `woccon_language/catawba_grammar/`, `scripts/extract_catawba_grammar.py`, `panel_api/services/catawba_grammar*.py` |
| Content language | `content_language.py`, `drive_extract.py` |
| Panel import | `scripts/import_cognates_to_panel.py`, `import_correspondences_to_panel.py` |
| Apply link decisions | `scripts/apply_link_decisions.py`, `panel_api/services/apply_link_decisions.py` |
| **Pronunciation audio** | [docs/PRONUNCIATION_AUDIO.md](PRONUNCIATION_AUDIO.md), `scripts/generate_pronunciation_audio.py`, `scripts/pull_uic_pronunciation_audio.sh`, `panel_api/services/pronunciation_audio.py`, `panel_api/services/kokoro_phonemes.py`, `requirements-tts.txt`, `.venv-tts` on **UIC** (CPU Kokoro batch; not Qwen) |

---

## 8. Known gaps & bugs

| Issue | Notes |
|-------|--------|
| **Grammar pending drop (Aug 2026)** | `--clear-pending` + stricter filters replaced ~53 weak drafts with ~15–16 rich-excerpt cards; approved `kuni`/`peeah`/`icaa` kept (now in `morphemes.json`, 42 total). Old weak queue not in git (`data/` gitignored); future clears snapshot to `data/backups/`. |
| **Panel upload routing** | Some uploads may not land in the intended `content_language` / document type; verify Library card and folder metadata after upload. |
| **Documentation “70 missing”** | Completeness checker flags ~70; after hybrid parser + dedupe, **~15–20** are genuine gaps worth linguist review. |
| **Stale panel backend** | New API routes or pronunciation-audio filter changes require **restart** `./run-panel-dev.sh` or `app.py`. If port 8000 is occupied, use `PORT=8003 ./run-panel-dev.sh`. |
| **Local background jobs** | Ingest, re-extract, and backfill started from the panel die if the dev process exits; use `nohup`, UIC queue, or keep server running. |
| **Phase 3 GPU wait** | Always queue via `queue_phase3_qwen_validation_uic.sh` (SSH heredoc + `UIC_LLM_WAIT_REMOTE=0`). Mac-side waiters die on sleep; SSH probe failures no longer count as GPU-busy. |
| **Lossy PDF OCR** | Many Catawba scans need `reocr_lossy_pdf.py` before lexicon is usable for cognate work. |
| **Blended holdout “fail”** | Legacy 56.7% vs 70% is diagnostic only. Gate on **precision @ high** + coverage; see `metrics_by_confidence_band` in holdout report. |

---

## 9. Immediate next steps by role

### Coordinator

- Prioritize Lane 2 human review (Catawba pending + Comparative Links) — primary lever for high-confidence **coverage**.
- Schedule UIC long jobs when GPU idle (`wait_for_uic_llm_idle.sh`).
- Track **per-band** holdout precision/coverage + Phase 3 Qwen validation logs on UIC (not the blended 70% gate).

### Linguist

- Review Comparative Links and App. 1 spot-check table in methodology doc.
- Resolve Lawson vs Carter spelling disagreements (e.g. dog, wind) — disagreement flags demote confidence.
- Set band-specific Tier 2 policy: precision bar for high → classroom; medium/low → reference.

### Developer

- Extend proposer + holdout report for structured confidence + per-band metrics (Lanes 4–5).
- Fix panel upload → `content_language` routing if misclassified.
- Restart backend after pulling comparative grammar API changes.
- Import cognates/correspondences after JSON regen; run content-language tests before merge.

---

## 10. Commands cheat sheet

```bash
# Local panel dev
./run-panel-dev.sh
# Port 8000 busy? PORT=8003 LOCAL_LLM=false ./run-panel-dev.sh

# Pronunciation audio (Kokoro CPU batch on UIC) — see docs/PRONUNCIATION_AUDIO.md
# On UIC (/root/WocconWaker): .venv-tts + generate_pronunciation_audio.py --staging ...
# Pull to Mac: ./scripts/pull_uic_pronunciation_audio.sh
python3 scripts/test_pronunciation_audio.py

# Reconstruction validators
python3 scripts/validate_cognate_seed.py
python3 scripts/validate_correspondence_registry.py
python3 scripts/validate_holdout_report.py
python scripts/test_content_language_guard.py
python3 scripts/test_confidence_bands.py

# Holdout pipeline
python3 scripts/build_holdout_split.py
python3 scripts/run_lawson_holdout.py --eval-split dev
python3 scripts/run_lawson_holdout.py --eval-split test --final

# Catawba linking (review before --write-seed)
python3 scripts/link_catawba_lexicon.py --write-seed

# Panel DB import (needs DATABASE_URL)
python3 scripts/import_cognates_to_panel.py
python3 scripts/import_correspondences_to_panel.py

# Re-OCR lossy Catawba/Woccon PDF
python scripts/reocr_lossy_pdf.py --pdf data/ingest_sources/<file>.pdf --dpi 300 --write

# UIC Phase 3 validation queue
bash scripts/queue_phase3_qwen_validation_uic.sh
# Monitor (on UIC via WSL):
# tail -f /root/WocconWaker/data/backups/phase3_qwen_validation.log

# Reload language after Commit or JSON edit
curl -X POST "http://localhost:8000/admin/reload-language?secret=$INGEST_DRIVE_SECRET"

# Drive ingest (Woccon only paths)
python drive_ingest.py
python merge_staging.py   # Woccon staging only
```

**UIC SSH:** `info@urbanindigenouscollective.org@100.71.124.8`, key `~/.ssh/uic-learning-deploy`, remote root `/root/WocconWaker` (or `INGEST_REMOTE_ROOT`).

---

*Maintainers: update this file when phases, gates, or panel tabs change. Last aligned with RECONSTRUCTION_METHODOLOGY.md through Phase 5 + calibration reframe (Aug 2026).*
