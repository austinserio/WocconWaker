"""
Phase 3: Structured extraction from raw Drive text.
Chunks text, calls LLM to extract lexicon entries and notes, validates, writes staging JSON.
"""
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("drive_extract")

# Per-file staging directory; one JSON per source file for review-before-merge
DEFAULT_STAGING_DIR = "woccon_language/drive_staging"
# When using Haiku model, write here so Sonnet output in drive_staging is not overwritten (compare accuracy).
STAGING_DIR_HAIKU = "woccon_language/drive_staging_haiku"
DRIVE_FILE_URL_TEMPLATE = "https://drive.google.com/file/d/{file_id}/view"


def _staging_dir_for_model(model: Optional[str]) -> str:
    """Use separate staging dir for Haiku so Sonnet files are not overwritten; DRIVE_STAGING_DIR overrides."""
    if os.environ.get("DRIVE_STAGING_DIR"):
        return os.environ.get("DRIVE_STAGING_DIR", DEFAULT_STAGING_DIR)
    resolved = (model or os.getenv("ANTHROPIC_MODEL") or "").strip().lower()
    if resolved and "haiku" in resolved:
        return STAGING_DIR_HAIKU
    return DEFAULT_STAGING_DIR
# Legacy single-file path (used only if write_per_file_staging is False)
DEFAULT_STAGING_PATH = "woccon_language/drive_lexicon_staging.json"
MAX_CHUNK_CHARS = 2400
# When a file is under this size, send the whole file in one LLM call (no input chunking).
# Anthropic requires streaming for long requests, so when using Anthropic we always chunk (effective 0).
MAX_WHOLE_FILE_CHARS_DEFAULT = int(os.environ.get("DRIVE_EXTRACT_WHOLE_FILE_MAX_CHARS", "14000"))
EXTRACTION_SOURCE = "community_drive"
PAGE_MARKER_RE = re.compile(r"\[\[PAGE\s+(\d+)\]\]", re.IGNORECASE)


@dataclass
class ChunkMeta:
    text: str
    chunk_index: int
    page_start: Optional[int] = None
    page_end: Optional[int] = None


def _max_whole_file_chars() -> int:
    """Whole-file threshold; disable for local Ollama (context/output limits). Anthropic streaming supports long single-pass."""
    if os.getenv("LOCAL_LLM", "").strip().lower() in ("true", "1", "yes"):
        return 0
    return MAX_WHOLE_FILE_CHARS_DEFAULT


def _extract_parallel_workers() -> int:
    raw = os.environ.get("EXTRACT_PARALLEL_WORKERS")
    if raw is not None and str(raw).strip():
        try:
            return max(1, int(str(raw).strip()))
        except ValueError:
            pass
    if os.getenv("LOCAL_LLM", "").strip().lower() in ("true", "1", "yes"):
        return 2
    return 1


def _extract_num_predict() -> int:
    try:
        return max(512, int(os.environ.get("EXTRACT_NUM_PREDICT", "4096")))
    except ValueError:
        return 4096


def _report_progress(
    *,
    path: str,
    file_index: int,
    total_files: int,
    chunk_index: Optional[int],
    chunk_total: Optional[int],
    overall_chunk: Optional[int],
    overall_chunks: Optional[int],
    percent: int,
    message: str,
    on_progress: Optional[Callable[[int, str], None]],
) -> None:
    if on_progress:
        on_progress(percent, message)
    try:
        import ingest_progress

        ingest_progress.write(
            phase="extract",
            document=path,
            document_index=file_index,
            document_total=total_files,
            chunk_index=chunk_index,
            chunk_total=chunk_total,
            overall_chunk=overall_chunk,
            overall_chunks=overall_chunks,
            percent=percent,
            message=message,
            workers=_extract_parallel_workers(),
        )
    except Exception:
        pass


def _normalize_lexicon_key(woccon: str, english: str) -> Tuple[str, str]:
    from list_doc_parser import normalize_english_for_key, normalize_woccon_for_key

    return (normalize_woccon_for_key(woccon), normalize_english_for_key(english))


def _normalize_lexicon_woccon(value: Any) -> str:
    from list_doc_parser import normalize_unicode_text

    return normalize_unicode_text(str(value or "")).strip()


def _repair_lexicon_fields(woccon: str, english: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Normalize and repair malformed woccon (e.g. 'Ten=soone noponne' with english 'Theirs').
    Returns (woccon, english, repair_reason) or (None, None, drop_reason).
    """
    w = _normalize_lexicon_woccon(woccon)
    e = _normalize_lexicon_woccon(english)
    if not w or not e:
        return None, None, "missing_woccon_or_english"
    if "=" in w:
        parts = w.split("=", 1)
        if len(parts) == 2:
            left, right = parts[0].strip(), parts[1].strip()
            if left and right and not re.search(r"[=:]", right):
                return right, left, "repaired_malformed_woccon"
        return None, None, "woccon_contains_equals"
    return w, e, None


def _lexicon_dedup_key(woccon: str, english: str) -> str:
    w, e = _normalize_lexicon_key(woccon, english)
    return f"{w}\x00{e}"


def _empty_extraction_audit() -> Dict[str, Any]:
    return {
        "raw_lexicon_count": 0,
        "kept_lexicon_count": 0,
        "dropped_missing_fields": [],
        "dropped_duplicates": [],
        "dropped_non_dict": 0,
    }


def _source_url(file_id: str) -> str:
    """Build a stable Drive URL for citing the document later (e.g. in Frappe)."""
    return DRIVE_FILE_URL_TEMPLATE.format(file_id=file_id)


def _safe_filename(path: str, max_len: int = 120) -> str:
    """Turn a path like 'Articles/Woccon Doc.pdf' into a safe filename for one JSON per file."""
    # Replace path separators and problematic chars
    safe = re.sub(r'[<>:"|?*\r\n]', "_", path)
    safe = safe.replace("/", "_").replace("\\", "_")
    safe = re.sub(r"_+", "_", safe).strip("_")
    if not safe:
        safe = "unnamed"
    # Add .json if missing
    if not safe.lower().endswith(".json"):
        safe = safe + ".json"
    return safe[:max_len]


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    """Split text into chunks without breaking a line. Prefer paragraph boundaries, then line boundaries."""
    if not (text or text.strip()):
        return []
    chunks = []
    # Prefer splitting on double newline (paragraphs)
    parts = re.split(r"\n\s*\n", text)
    current = []
    current_len = 0
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if current_len + len(p) + 2 <= max_chars:
            current.append(p)
            current_len += len(p) + 2
        else:
            if current:
                chunks.append("\n\n".join(current))
            if len(p) > max_chars:
                # Long paragraph: split by single newline so we never cut a line in the middle
                lines = p.split("\n")
                current = []
                current_len = 0
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if current_len + len(line) + 1 <= max_chars:
                        current.append(line)
                        current_len += len(line) + 1
                    else:
                        if current:
                            chunks.append("\n".join(current))
                        # Keep whole line even if over max_chars so we never break "English= woccon"
                        current = [line]
                        current_len = len(line) + 1
                if current:
                    chunks.append("\n".join(current))
                current = []
                current_len = 0
            else:
                current = [p]
                current_len = len(p) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_page_range(chunk: str) -> Tuple[Optional[int], Optional[int]]:
    pages = [int(m.group(1)) for m in PAGE_MARKER_RE.finditer(chunk)]
    if not pages:
        return None, None
    return min(pages), max(pages)


def chunk_text_with_meta(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[ChunkMeta]:
    raw_chunks = chunk_text(text, max_chars)
    return [
        ChunkMeta(
            text=c,
            chunk_index=i,
            page_start=chunk_page_range(c)[0],
            page_end=chunk_page_range(c)[1],
        )
        for i, c in enumerate(raw_chunks)
    ]


MAX_LEXICON_EXCERPT = 200
MAX_NOTE_EXCERPT = 200
MAX_GRAMMAR_EXCERPT = 800
MAX_GRAMMAR_EXCERPT_FALLBACK = 400

# Legacy alias — prompts built dynamically via panel_api.extraction_config.build_extraction_prompt
EXTRACTION_PROMPT = None


def _parse_json_from_response(content: str) -> Optional[Dict[str, Any]]:
    """Extract JSON object from LLM response (strip markdown code blocks if present)."""
    content = (content or "").strip()
    # Remove optional markdown code block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if m:
        content = m.group(1).strip()
    start = content.find("{")
    end = content.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(content[start:end])
    except json.JSONDecodeError:
        return None


def _validate_extraction(raw: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    """Validate and normalize extraction. Returns (ok, normalized_dict, audit_dict)."""
    lexicon = raw.get("lexicon_entries")
    grammar = raw.get("grammar_notes")
    pronunciation = raw.get("pronunciation_notes")
    cultural = raw.get("cultural_notes")
    if not isinstance(lexicon, list):
        lexicon = []
    if not isinstance(grammar, list):
        grammar = []
    if not isinstance(pronunciation, list):
        pronunciation = []
    if not isinstance(cultural, list):
        cultural = []
    audit: Dict[str, Any] = {
        "raw_lexicon_count": len(lexicon),
        "dropped_missing_fields": [],
        "dropped_non_dict": 0,
        "repaired_malformed_woccon": [],
        "dropped_malformed_woccon": [],
        "suspicious_woccon": [],
    }
    normalized_lexicon = []
    for e in lexicon:
        if not isinstance(e, dict):
            audit["dropped_non_dict"] = int(audit.get("dropped_non_dict") or 0) + 1
            continue
        w_raw = e.get("woccon") or e.get("woccon_word")
        eng_raw = e.get("english") or e.get("meaning")
        w, eng, repair = _repair_lexicon_fields(str(w_raw or ""), str(eng_raw or ""))
        if repair == "repaired_malformed_woccon":
            audit["repaired_malformed_woccon"].append({
                "original_woccon": str(w_raw).strip() if w_raw else None,
                "original_english": str(eng_raw).strip() if eng_raw else None,
                "woccon": w,
                "english": eng,
            })
        elif not w or not eng:
            audit["dropped_missing_fields"].append({
                "reason": repair or "missing_woccon_or_english",
                "woccon": str(w_raw).strip() if w_raw else None,
                "english": str(eng_raw).strip() if eng_raw else None,
            })
            if repair == "woccon_contains_equals":
                audit["dropped_malformed_woccon"].append({
                    "woccon": str(w_raw).strip() if w_raw else None,
                    "english": str(eng_raw).strip() if eng_raw else None,
                })
            continue
        if len(w.split()) > 3 and not re.search(r"[\u0105\u0107\u0119\u0127\u0129\u0142\u0144\u00f3\u00f4\u015b\u0161\u017a\u017c\u0294'-]", w, re.I):
            audit["suspicious_woccon"].append({"woccon": w, "english": eng})
        normalized_lexicon.append({
            "woccon": w,
            "english": eng,
            "pos": str(e.get("pos") or e.get("part_of_speech") or "").strip() or "unknown",
            "pronunciation": str(e.get("pronunciation") or "").strip() or None,
            "source_page": _coerce_int(e.get("source_page")),
            "source_excerpt": _cap_excerpt(e.get("source_excerpt"), MAX_LEXICON_EXCERPT),
        })
    normalized_grammar = [_normalize_note(g, excerpt_max=MAX_GRAMMAR_EXCERPT, excerpt_fallback=MAX_GRAMMAR_EXCERPT_FALLBACK) for g in grammar if g]
    normalized_pronunciation = [_normalize_note(p) for p in pronunciation if p]
    normalized_cultural = [_normalize_note(c) for c in cultural if c]
    normalized_grammar = [n for n in normalized_grammar if n]
    normalized_pronunciation = [n for n in normalized_pronunciation if n]
    normalized_cultural = [n for n in normalized_cultural if n]
    return True, {
        "lexicon_entries": normalized_lexicon,
        "grammar_notes": normalized_grammar,
        "pronunciation_notes": normalized_pronunciation,
        "cultural_notes": normalized_cultural,
    }, audit


def _coerce_int(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _cap_excerpt(val: Any, max_len: int = MAX_NOTE_EXCERPT) -> Optional[str]:
    if not val:
        return None
    s = " ".join(str(val).split())
    return s[:max_len] if len(s) > max_len else s


def _normalize_note(
    note: Any,
    *,
    excerpt_max: int = MAX_NOTE_EXCERPT,
    excerpt_fallback: int = 120,
) -> Optional[Dict[str, Any]]:
    if not note:
        return None
    if isinstance(note, dict):
        text = (note.get("text") or note.get("content") or "").strip()
        if not text:
            return None
        out = {
            "text": text,
            "source_page": _coerce_int(note.get("source_page")),
            "source_page_end": _coerce_int(note.get("source_page_end")),
            "source_excerpt": _cap_excerpt(
                note.get("source_excerpt") or text[:excerpt_fallback],
                excerpt_max,
            ),
        }
        gl = (note.get("grammar_lineage") or "").strip()
        if gl:
            out["grammar_lineage"] = gl
        return out
    s = str(note).strip()
    m = re.match(r"^\s*\{['\"]text['\"]\s*:\s*['\"](.+)['\"]\s*\}\s*$", s, re.DOTALL)
    if m:
        s = m.group(1).replace("\\'", "'").strip()
    if not s:
        return None
    return {"text": s, "source_excerpt": _cap_excerpt(s[:excerpt_fallback], excerpt_max)}


def _apply_extraction_focus(data: Dict[str, Any], focus: str) -> Dict[str, Any]:
    """Drop buckets not requested by the extraction focus."""
    from panel_api.extraction_config import EXTRACTION_FOCUS_IDS

    f = focus if focus in EXTRACTION_FOCUS_IDS else "general"
    out = dict(data)
    if f == "vocabulary":
        out["grammar_notes"] = []
        out["pronunciation_notes"] = []
        out["cultural_notes"] = []
    elif f == "grammar":
        out["lexicon_entries"] = []
        out["pronunciation_notes"] = []
        out["cultural_notes"] = []
    elif f == "pronunciation":
        out["lexicon_entries"] = []
        out["grammar_notes"] = []
        out["cultural_notes"] = []
    elif f == "culture":
        out["lexicon_entries"] = []
        out["grammar_notes"] = []
        out["pronunciation_notes"] = []
    return out


def extract_from_chunk(
    chunk: str,
    file_path: str,
    model: Optional[str] = None,
    retry: bool = True,
    max_text_chars: int = 2200,
    num_predict: int = 4096,
    *,
    context_header: str = "",
    chunk_index: Optional[int] = None,
    chunk_page_start: Optional[int] = None,
    chunk_page_end: Optional[int] = None,
    extraction_focus: str = "general",
    grammar_lineage: Optional[str] = None,
) -> Dict[str, Any]:
    """Call LLM on one chunk (or full file text); return normalized extraction or empty dict on failure."""
    from llm_client import llm_chat
    from panel_api.extraction_config import build_extraction_prompt

    if model:
        resolved_model = model
    elif os.getenv("REEXTRACT_MODEL"):
        resolved_model = os.getenv("REEXTRACT_MODEL", "").strip()
    elif os.getenv("LOCAL_LLM", "").strip().lower() in ("true", "1", "yes"):
        resolved_model = os.getenv("OLLAMA_MODEL", "llama3:8b").strip()
    else:
        resolved_model = (
            os.getenv("ANTHROPIC_MODEL")
            or os.getenv("FOUNDRY_DEPLOYMENT")
            or os.getenv("OLLAMA_MODEL", "llama3:8b")
        ).strip()
    model = resolved_model
    text_slice = chunk[:max_text_chars] if max_text_chars else chunk
    header = context_header or "Extract from the following source text."
    prompt = build_extraction_prompt(
        context_header=header,
        text=text_slice,
        focus=extraction_focus,
        grammar_lineage=grammar_lineage,
    )
    messages = [
        {"role": "user", "content": prompt},
    ]
    try:
        out = llm_chat(model, messages, options={"temperature": 0.2, "num_predict": num_predict})
        content = (out.get("message") or {}).get("content") or ""
        data = _parse_json_from_response(content)
        if not data:
            if len(content) > 500:
                log.warning("Extraction returned no valid JSON (response length=%d). Increase num_predict if truncated.", len(content))
            if retry:
                return extract_from_chunk(
                    chunk,
                    file_path,
                    model=model,
                    retry=False,
                    max_text_chars=max_text_chars,
                    num_predict=num_predict,
                    context_header=context_header,
                    chunk_index=chunk_index,
                    chunk_page_start=chunk_page_start,
                    chunk_page_end=chunk_page_end,
                    extraction_focus=extraction_focus,
                    grammar_lineage=grammar_lineage,
                )
            return {"lexicon_entries": [], "grammar_notes": [], "pronunciation_notes": [], "cultural_notes": []}
        ok, normalized, validation_audit = _validate_extraction(data)
        normalized = _apply_extraction_focus(normalized, extraction_focus)
        normalized["_validation_audit"] = validation_audit
        for e in normalized.get("lexicon_entries", []):
            e["source_chunk_index"] = chunk_index
            e["_chunk_page_start"] = chunk_page_start
            e["_chunk_page_end"] = chunk_page_end
        for key in ("grammar_notes", "pronunciation_notes", "cultural_notes"):
            for n in normalized.get(key, []):
                if isinstance(n, dict):
                    n["source_chunk_index"] = chunk_index
                    n["_chunk_page_start"] = chunk_page_start
                    n["_chunk_page_end"] = chunk_page_end
        return normalized
    except Exception as e:
        log.warning("Extraction failed for chunk from %s: %s", file_path, e)
        if retry:
            return extract_from_chunk(
                chunk,
                file_path,
                model=model,
                retry=False,
                max_text_chars=max_text_chars,
                num_predict=num_predict,
                context_header=context_header,
                chunk_index=chunk_index,
                chunk_page_start=chunk_page_start,
                chunk_page_end=chunk_page_end,
                extraction_focus=extraction_focus,
                grammar_lineage=grammar_lineage,
            )
        return {"lexicon_entries": [], "grammar_notes": [], "pronunciation_notes": [], "cultural_notes": []}


def extract_one_file(
    text: str,
    path: str,
    model: Optional[str] = None,
    *,
    file_id: Optional[str] = None,
    source_url: Optional[str] = None,
    file_index: int = 0,
    total_files: int = 0,
    chunk_start: int = 0,
    total_chunks: int = 0,
    short_title: Optional[str] = None,
    marked_source_text: Optional[str] = None,
    on_progress: Optional[Callable[[int, str], None]] = None,
    extraction_focus: str = "general",
    grammar_lineage: Optional[str] = None,
    previous_lexicon: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Run extraction on a single file's text. When the file fits in MAX_WHOLE_FILE_CHARS,
    send the whole file in one LLM call (no input chunking). Otherwise chunk and merge.
    Dedupe within this file only. Returns dict with lexicon_entries, grammar_notes, etc.
    """
    file_lexicon: List[Dict[str, Any]] = []
    file_grammar: List[Dict[str, Any]] = []
    file_pronunciation: List[Dict[str, Any]] = []
    file_cultural: List[Dict[str, Any]] = []
    seen_lexicon: set = set()
    seen_notes: set = set()
    file_audit = _empty_extraction_audit()

    def _note_key(n: Dict[str, Any]) -> str:
        return (n.get("text") or "").strip().lower()

    def _accumulate_validation_audit(extracted: Dict[str, Any]) -> None:
        chunk_audit = extracted.pop("_validation_audit", None)
        if not chunk_audit:
            return
        file_audit["raw_lexicon_count"] += int(chunk_audit.get("raw_lexicon_count") or 0)
        file_audit["dropped_missing_fields"].extend(chunk_audit.get("dropped_missing_fields") or [])
        file_audit["dropped_non_dict"] = int(file_audit.get("dropped_non_dict") or 0) + int(
            chunk_audit.get("dropped_non_dict") or 0
        )

    def merge_extraction(extracted: Dict[str, Any]) -> None:
        _accumulate_validation_audit(extracted)
        for e in extracted.get("lexicon_entries", []):
            woccon = (e.get("woccon") or "").strip()
            english = (e.get("english") or "").strip()
            key = _lexicon_dedup_key(woccon, english)
            if not woccon or not english:
                continue
            if key in seen_lexicon:
                file_audit["dropped_duplicates"].append({
                    "woccon": woccon,
                    "english": english,
                    "reason": "duplicate_woccon_and_english",
                })
                continue
            seen_lexicon.add(key)
            e = dict(e)
            e["source"] = EXTRACTION_SOURCE
            file_lexicon.append(e)
        for bucket, target in (
            ("grammar_notes", file_grammar),
            ("pronunciation_notes", file_pronunciation),
            ("cultural_notes", file_cultural),
        ):
            for note in extracted.get(bucket) or []:
                if isinstance(note, str):
                    note = _normalize_note(note)
                if not note:
                    continue
                nk = _note_key(note)
                if not nk or nk in seen_notes:
                    continue
                seen_notes.add(nk)
                target.append(dict(note))

    def _context_header(meta: ChunkMeta) -> str:
        label = short_title or path
        if meta.page_start is not None:
            if meta.page_end is not None and meta.page_end != meta.page_start:
                return f'Text from pages {meta.page_start}–{meta.page_end} of "{label}".'
            return f'Text from page {meta.page_start} of "{label}".'
        return f'Text from "{label}".'

    # Whole-file path: beam the entire file in one call when it fits (no input chunking).
    max_whole = _max_whole_file_chars()
    if max_whole and len(text) <= max_whole:
        log.info(
            "Document %d/%d (%s) | whole file (%d chars, no chunking)",
            file_index, total_files, path, len(text),
        )
        if on_progress:
            on_progress(5, "Extracting document (single pass)")
        _report_progress(
            path=path, file_index=file_index, total_files=total_files,
            chunk_index=1, chunk_total=1, overall_chunk=chunk_start + 1, overall_chunks=total_chunks,
            percent=5, message="Extracting document (single pass)", on_progress=None,
        )
        meta = ChunkMeta(text=text, chunk_index=0, page_start=chunk_page_range(text)[0], page_end=chunk_page_range(text)[1])
        extracted = extract_from_chunk(
            text,
            path,
            model=model,
            max_text_chars=max_whole,
            num_predict=32768,
            context_header=_context_header(meta),
            chunk_index=0,
            chunk_page_start=meta.page_start,
            chunk_page_end=meta.page_end,
            extraction_focus=extraction_focus,
            grammar_lineage=grammar_lineage,
        )
        merge_extraction(extracted)
        if on_progress:
            on_progress(90, "Extraction complete")
    else:
        chunks = chunk_text_with_meta(text)
        total = len(chunks) or 1
        workers = _extract_parallel_workers()
        if workers > 1 and len(chunks) > 1:
            log.info(
                "Document %d/%d (%s) | %d chunks with %d parallel workers",
                file_index, total_files, path, len(chunks), workers,
            )

            def _run_chunk(i: int, meta: ChunkMeta) -> Tuple[int, Dict[str, Any]]:
                current_chunk = chunk_start + i + 1
                pct_log = int(100 * current_chunk / total_chunks) if total_chunks else 0
                log.info(
                    "Document %d/%d (%s) | chunk %d/%d of file | overall %d/%d (%d%%)",
                    file_index, total_files, path, i + 1, len(chunks), current_chunk, total_chunks, pct_log,
                )
                extracted = extract_from_chunk(
                    meta.text,
                    path,
                    model=model,
                    max_text_chars=MAX_CHUNK_CHARS,
                    num_predict=_extract_num_predict(),
                    context_header=_context_header(meta),
                    chunk_index=meta.chunk_index,
                    chunk_page_start=meta.page_start,
                    chunk_page_end=meta.page_end,
                    extraction_focus=extraction_focus,
                    grammar_lineage=grammar_lineage,
                )
                return i, extracted

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_run_chunk, i, meta) for i, meta in enumerate(chunks)]
                completed = 0
                for fut in as_completed(futures):
                    i, extracted = fut.result()
                    merge_extraction(extracted)
                    completed += 1
                    pct = int(100 * completed / total)
                    msg = f"Extracting chunk {completed}/{total}"
                    _report_progress(
                        path=path, file_index=file_index, total_files=total_files,
                        chunk_index=completed, chunk_total=total,
                        overall_chunk=chunk_start + completed, overall_chunks=total_chunks,
                        percent=min(pct, 90), message=msg, on_progress=on_progress,
                    )
        else:
            for i, meta in enumerate(chunks):
                current_chunk = chunk_start + i + 1
                pct = int(100 * (i + 1) / total)
                msg = f"Extracting chunk {i + 1}/{total}"
                _report_progress(
                    path=path, file_index=file_index, total_files=total_files,
                    chunk_index=i + 1, chunk_total=total,
                    overall_chunk=current_chunk, overall_chunks=total_chunks,
                    percent=min(pct, 90), message=msg, on_progress=on_progress,
                )
                pct_log = int(100 * current_chunk / total_chunks) if total_chunks else 0
                log.info(
                    "Document %d/%d (%s) | chunk %d/%d of file | overall %d/%d (%d%%)",
                    file_index, total_files, path, i + 1, len(chunks), current_chunk, total_chunks, pct_log,
                )
                extracted = extract_from_chunk(
                    meta.text,
                    path,
                    model=model,
                    max_text_chars=MAX_CHUNK_CHARS,
                    num_predict=_extract_num_predict(),
                    context_header=_context_header(meta),
                    chunk_index=meta.chunk_index,
                    chunk_page_start=meta.page_start,
                    chunk_page_end=meta.page_end,
                    extraction_focus=extraction_focus,
                    grammar_lineage=grammar_lineage,
                )
                merge_extraction(extracted)

    file_grammar = list({n["text"]: n for n in file_grammar if n.get("text")}.values())
    file_pronunciation = list({n["text"]: n for n in file_pronunciation if n.get("text")}.values())
    file_cultural = list({n["text"]: n for n in file_cultural if n.get("text")}.values())

    # Hybrid list-doc merge: parser recall + LLM enrichment
    try:
        from list_doc_parser import (
            audit_dropped_vs_previous,
            check_lexicon_completeness,
            collect_parser_candidate_keys,
            hybrid_enabled_for_path,
            list_doc_profile,
            merge_carry_forward,
            merge_parser_and_llm_lexicon,
            parse_list_document,
        )

        if hybrid_enabled_for_path(path):
            profile = list_doc_profile(path)
            section = "english_woccon" if profile == "english_woccon" else "lawson"
            parser_entries = parse_list_document(text, section=section)
            llm_lexicon = file_lexicon
            if os.environ.get("HYBRID_LLM_LEXICON", "1").strip().lower() in ("0", "false", "no"):
                llm_lexicon = []
            merged_lexicon, hybrid_audit = merge_parser_and_llm_lexicon(parser_entries, llm_lexicon)
            parser_keys = collect_parser_candidate_keys(text, section=section)
            if previous_lexicon:
                merged_lexicon, carry_audit = merge_carry_forward(merged_lexicon, previous_lexicon, parser_keys)
                hybrid_audit["carry_forward"] = carry_audit
                hybrid_audit["dropped_vs_previous"] = audit_dropped_vs_previous(merged_lexicon, previous_lexicon)
                hybrid_audit["merged_count"] = len(merged_lexicon)
            for row in merged_lexicon:
                row["source"] = EXTRACTION_SOURCE
            file_lexicon = merged_lexicon
            completeness = check_lexicon_completeness(text, file_lexicon)
            file_audit["completeness"] = completeness
            file_audit["hybrid"] = {
                "profile": profile,
                "section": section,
                **hybrid_audit,
            }
            log.info(
                "Hybrid extract %s: parser=%d llm=%d merged=%d completeness=%s%%",
                path,
                hybrid_audit.get("parser_count", 0),
                hybrid_audit.get("llm_count", 0),
                hybrid_audit.get("merged_count", 0),
                completeness.get("completeness_pct", "?"),
            )
            if completeness.get("missing_count", 0) > 0:
                log.warning(
                    "Completeness gap for %s: %d parser candidates missing from staging",
                    path,
                    completeness["missing_count"],
                )
                for item in (completeness.get("missing") or [])[:8]:
                    log.warning("  missing: %s = %s (%s)", item.get("english"), item.get("woccon"), item.get("section"))
                if os.environ.get("EXTRACT_COMPLETENESS_FAIL", "").strip().lower() in ("1", "true", "yes"):
                    raise RuntimeError(
                        f"Completeness check failed for {path}: {completeness['missing_count']} missing parser rows"
                    )
    except Exception as exc:
        log.warning("Hybrid list extract failed for %s: %s", path, exc)

    file_audit["kept_lexicon_count"] = len(file_lexicon)

    return {
        "source_path": path,
        "source_url": source_url or (_source_url(file_id) if file_id else None),
        "lexicon_entries": file_lexicon,
        "grammar_notes": file_grammar,
        "pronunciation_notes": file_pronunciation,
        "cultural_notes": file_cultural,
        "meta": {"source": EXTRACTION_SOURCE},
        "audit": file_audit,
    }


def _load_existing_staging(staging_dir: str, staging_file: str, file_id: str, modified_time: str, path: str) -> Optional[Dict[str, Any]]:
    """Load existing staging JSON and add file_id/modified_time for sync_state."""
    p = os.path.join(staging_dir, staging_file)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["file_id"] = file_id
        data["modified_time"] = modified_time
        return data
    except Exception as e:
        log.warning("Could not load existing staging %s: %s", p, e)
        return None


def extract_per_file(
    results: List[Dict[str, Any]],
    model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Run extraction per source file. Returns list of per-file staging dicts, each with
    source_path, source_url (for citing in Frappe), lexicon_entries, grammar_notes, pronunciation_notes, cultural_notes.
    If result has use_existing_staging and staging_file, reuses existing staging JSON (no LLM). Otherwise extracts.
    Logs progress as: Document N/M | chunk ... | overall chunk X/Y (Z%).
    """
    staging_dir = _staging_dir_for_model(model)
    os.makedirs(staging_dir, exist_ok=True)
    log.info("Staging dir: %s", staging_dir)
    files_to_extract = [
        {"path": r.get("path") or r.get("name") or "unknown", "text": (r.get("text") or "").strip(), "file_id": r.get("file_id"), "modified_time": r.get("modified_time"), "result": r}
        for r in results
        if (r.get("text") or "").strip()
    ]
    total_extract = len(files_to_extract)
    total_chunks = sum(len(chunk_text(f["text"])) for f in files_to_extract)
    if total_extract or any(r.get("use_existing_staging") for r in results):
        log.info("Extraction: %d to (re)extract (%d chunks), %d to reuse from sync_state",
                 total_extract, total_chunks, sum(1 for r in results if r.get("use_existing_staging")))
    out: List[Dict[str, Any]] = []
    chunk_so_far = 0
    extract_index = 0
    for r in results:
        if r.get("use_existing_staging") and r.get("staging_file"):
            path = r.get("path") or r.get("name") or "unknown"
            existing = _load_existing_staging(
                staging_dir, r["staging_file"], r.get("file_id") or "", r.get("modified_time") or "", path
            )
            if existing:
                out.append(existing)
                log.info("Reused staging: %s", path)
                _write_sync_state(out, staging_dir)
            else:
                log.warning("Sync state said reuse %s but file missing or invalid; skipping", path)
        elif (r.get("text") or "").strip():
            extract_index += 1
            path = r.get("path") or r.get("name") or "unknown"
            text = (r.get("text") or "").strip()
            file_id = r.get("file_id")
            modified_time = r.get("modified_time")
            num_chunks = len(chunk_text(text))
            previous_lexicon: Optional[List[Dict[str, Any]]] = None
            safe = _safe_filename(path)
            existing_path = os.path.join(staging_dir, safe)
            if os.path.isfile(existing_path):
                try:
                    with open(existing_path, "r", encoding="utf-8") as f:
                        previous_lexicon = json.load(f).get("lexicon_entries") or []
                except Exception as exc:
                    log.warning("Could not load previous staging for carry-forward %s: %s", path, exc)
            file_data = extract_one_file(
                text, path, model=model,
                file_id=file_id,
                file_index=extract_index,
                total_files=total_extract,
                chunk_start=chunk_so_far,
                total_chunks=total_chunks,
                previous_lexicon=previous_lexicon,
            )
            chunk_so_far += num_chunks
            file_data["file_id"] = file_id
            file_data["modified_time"] = modified_time
            _write_one_file_staging(file_data, staging_dir)
            out.append(file_data)
            _write_sync_state(out, staging_dir)
    manifest_path = _write_manifest_only(out, staging_dir)
    return out, staging_dir, manifest_path


def _write_one_file_staging(file_data: Dict[str, Any], staging_dir: str) -> str:
    """Write one file's staging JSON. Returns the staging filename (for manifest/sync_state)."""
    path = file_data.get("source_path") or "unknown"
    safe = _safe_filename(path)
    file_path = os.path.join(staging_dir, safe)
    payload = {
        "source_path": path,
        "source_url": file_data.get("source_url"),
        "lexicon_entries": file_data.get("lexicon_entries") or [],
        "grammar_notes": file_data.get("grammar_notes") or [],
        "pronunciation_notes": file_data.get("pronunciation_notes") or [],
        "cultural_notes": file_data.get("cultural_notes") or [],
    }
    if file_data.get("audit"):
        payload["audit"] = file_data["audit"]
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    log.info("Wrote %s", file_path)
    return safe


def _write_manifest_only(per_file_data: List[Dict[str, Any]], staging_dir: str) -> str:
    """Write manifest.json from current per_file_data list. Returns manifest path."""
    manifest_entries = []
    for data in per_file_data:
        path = data.get("source_path") or "unknown"
        safe = _safe_filename(path)
        manifest_entries.append({
            "file": safe,
            "source_path": path,
            "source_url": data.get("source_url"),
            "lexicon_count": len(data.get("lexicon_entries") or []),
            "grammar_count": len(data.get("grammar_notes") or []),
            "pronunciation_count": len(data.get("pronunciation_notes") or []),
            "cultural_count": len(data.get("cultural_notes") or []),
        })
    manifest_path = os.path.join(staging_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"files": manifest_entries}, f, indent=2)
    log.info("Wrote manifest %s", manifest_path)
    return manifest_path


def write_per_file_staging(
    per_file_data: List[Dict[str, Any]],
    staging_dir: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Write one JSON per file into staging_dir; add manifest.json listing all files.
    Returns (staging_dir, manifest_path). Use extract_per_file (writes incrementally) for resumable runs.
    """
    staging_dir = staging_dir or _staging_dir_for_model(None)
    os.makedirs(staging_dir, exist_ok=True)
    for data in per_file_data:
        _write_one_file_staging(data, staging_dir)
    manifest_path = _write_manifest_only(per_file_data, staging_dir)
    return staging_dir, manifest_path


SYNC_STATE_FILENAME = "sync_state.json"


def _write_sync_state(per_file_data: List[Dict[str, Any]], staging_dir: str) -> None:
    """Write sync_state.json so next ingest can skip unchanged Drive files and resume after cut-off."""
    state: Dict[str, Any] = {}
    for data in per_file_data:
        fid = data.get("file_id")
        if not fid:
            continue
        path = data.get("source_path") or "unknown"
        state[fid] = {
            "modified_time": data.get("modified_time") or "",
            "staging_file": _safe_filename(path),
        }
    path = os.path.join(staging_dir, SYNC_STATE_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    log.debug("Wrote sync state (%d entries) to %s", len(state), path)


def extract_from_ingest_results(
    results: List[Dict[str, Any]],
    model: Optional[str] = None,
    per_file: bool = True,
) -> Dict[str, Any]:
    """
    Run extraction. If per_file=True (default), extract per source file and return
    summary + paths. If per_file=False, merge all into one dict (legacy).
    """
    if per_file:
        per_file_data, staging_dir, manifest_path = extract_per_file(results, model=model)
        total_lexicon = sum(len(d.get("lexicon_entries") or []) for d in per_file_data)
        total_grammar = sum(len(d.get("grammar_notes") or []) for d in per_file_data)
        total_pronunciation = sum(len(d.get("pronunciation_notes") or []) for d in per_file_data)
        total_cultural = sum(len(d.get("cultural_notes") or []) for d in per_file_data)
        return {
            "staging_dir": staging_dir,
            "manifest_path": manifest_path,
            "files_written": len(per_file_data),
            "extraction_lexicon_count": total_lexicon,
            "extraction_grammar_count": total_grammar,
            "extraction_pronunciation_count": total_pronunciation,
            "extraction_cultural_count": total_cultural,
            "per_file": True,
        }
    # Legacy: single merged file
    all_lexicon: List[Dict[str, Any]] = []
    all_grammar: List[str] = []
    all_pronunciation: List[str] = []
    seen_lexicon: set = set()
    merge_audit = _empty_extraction_audit()
    total_chunks = sum(max(1, len(chunk_text((r.get("text") or "").strip()))) for r in results if (r.get("text") or "").strip())
    chunk_num = 0
    for r in results:
        text = (r.get("text") or "").strip()
        path = r.get("path") or r.get("name") or "unknown"
        if not text:
            continue
        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            chunk_num += 1
            log.info("Extraction %d/%d: %s (chunk %d)", chunk_num, total_chunks, path, i + 1)
            extracted = extract_from_chunk(chunk, path, model=model)
            chunk_audit = extracted.pop("_validation_audit", None)
            if chunk_audit:
                merge_audit["raw_lexicon_count"] += int(chunk_audit.get("raw_lexicon_count") or 0)
                merge_audit["dropped_missing_fields"].extend(chunk_audit.get("dropped_missing_fields") or [])
                merge_audit["dropped_non_dict"] = int(merge_audit.get("dropped_non_dict") or 0) + int(
                    chunk_audit.get("dropped_non_dict") or 0
                )
            for e in extracted.get("lexicon_entries", []):
                woccon = (e.get("woccon") or "").strip()
                english = (e.get("english") or "").strip()
                key = _lexicon_dedup_key(woccon, english)
                if not woccon or not english:
                    continue
                if key in seen_lexicon:
                    merge_audit["dropped_duplicates"].append({
                        "woccon": woccon,
                        "english": english,
                        "reason": "duplicate_woccon_and_english",
                    })
                    continue
                seen_lexicon.add(key)
                e = dict(e)
                e["source"] = EXTRACTION_SOURCE
                all_lexicon.append(e)
            all_grammar.extend(extracted.get("grammar_notes") or [])
            all_pronunciation.extend(extracted.get("pronunciation_notes") or [])

    all_grammar = list(dict.fromkeys(g.strip() for g in all_grammar if g and g.strip()))
    all_pronunciation = list(dict.fromkeys(p.strip() for p in all_pronunciation if p and p.strip()))
    merge_audit["kept_lexicon_count"] = len(all_lexicon)

    return {
        "lexicon_entries": all_lexicon,
        "grammar_notes": all_grammar,
        "pronunciation_notes": all_pronunciation,
        "meta": {"source": EXTRACTION_SOURCE},
        "audit": merge_audit,
    }


def write_staging(data: Dict[str, Any], path: Optional[str] = None) -> str:
    """Write staging JSON to path. Returns path written."""
    path = path or os.environ.get("DRIVE_STAGING_PATH") or DEFAULT_STAGING_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("Wrote staging to %s", path)
    return path
