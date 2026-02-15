"""
Phase 3: Structured extraction from raw Drive text.
Chunks text, calls LLM to extract lexicon entries and notes, validates, writes staging JSON.
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("drive_extract")

# Per-file staging directory; one JSON per source file for review-before-merge
DEFAULT_STAGING_DIR = "woccon_language/drive_staging"
DRIVE_FILE_URL_TEMPLATE = "https://drive.google.com/file/d/{file_id}/view"
# Legacy single-file path (used only if write_per_file_staging is False)
DEFAULT_STAGING_PATH = "woccon_language/drive_lexicon_staging.json"
MAX_CHUNK_CHARS = 2400
# When a file is under this size, send the whole file in one LLM call (no input chunking).
# Anthropic SDK requires streaming for requests that may take >10 min, so we keep default 14k to avoid that:
# English-Woccon (~18k chars) is then chunked and completes reliably. Set to 60000 if you add streaming later.
MAX_WHOLE_FILE_CHARS = int(os.environ.get("DRIVE_EXTRACT_WHOLE_FILE_MAX_CHARS", "14000"))
EXTRACTION_SOURCE = "community_drive"


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


EXTRACTION_PROMPT = """You are extracting structured Woccon language data from community-authored text (Waccamaw people + Siouan linguist). This data is authoritative.

From the following text, extract:
1. lexicon_entries: list of Woccon vocabulary items. Each item has: woccon (the Woccon word), english (meaning), pos (part of speech, e.g. noun, verb), and optionally pronunciation (e.g. "(ay-COOCH-ro-moan)" or phonetic hint). If you see patterns like "Word= woccon (pronunciation)" or "Bag= ekoocromon (ay-COOCH-ro-moan)", extract them.
2. grammar_notes: list of short factual sentences or bullet points about grammar (e.g. "Subject-Object-Verb order", "Reduplication signals emphasis").
3. pronunciation_notes: list of short notes about pronunciation (e.g. "a= ah").
4. cultural_notes: list of short factual sentences that help an agent understand context—e.g. that Woccon is Siouan and how we know, historical names we were called, tribal history, documentation sources, cultural context. Things that are not vocabulary or grammar but are important for answering "how do we know X?" or "what is the context?"

Output ONLY a single JSON object with keys: "lexicon_entries", "grammar_notes", "pronunciation_notes", "cultural_notes". Use empty arrays if nothing relevant. No markdown, no explanation.

Text:
---
{text}
---
JSON:"""


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


def _validate_extraction(raw: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Validate and normalize extraction. Returns (ok, normalized_dict)."""
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
    normalized_lexicon = []
    for e in lexicon:
        if not isinstance(e, dict):
            continue
        w = e.get("woccon") or e.get("woccon_word")
        eng = e.get("english") or e.get("meaning")
        if not w or not eng:
            continue
        normalized_lexicon.append({
            "woccon": str(w).strip(),
            "english": str(eng).strip(),
            "pos": str(e.get("pos") or e.get("part_of_speech") or "").strip() or "unknown",
            "pronunciation": str(e.get("pronunciation") or "").strip() or None,
        })
    normalized_grammar = [str(g).strip() for g in grammar if g]
    normalized_pronunciation = [str(p).strip() for p in pronunciation if p]
    normalized_cultural = []
    for c in cultural:
        if not c:
            continue
        s = str(c).strip()
        # Unwrap LLM artifact: "{'text': '...'}" or similar
        m = re.match(r"^\s*\{['\"]text['\"]\s*:\s*['\"](.+)['\"]\s*\}\s*$", s, re.DOTALL)
        if m:
            s = m.group(1).replace("\\'", "'").strip()
        normalized_cultural.append(s)
    return True, {
        "lexicon_entries": normalized_lexicon,
        "grammar_notes": normalized_grammar,
        "pronunciation_notes": normalized_pronunciation,
        "cultural_notes": normalized_cultural,
    }


def extract_from_chunk(
    chunk: str,
    file_path: str,
    model: Optional[str] = None,
    retry: bool = True,
    max_text_chars: int = 2200,
    num_predict: int = 800,
) -> Dict[str, Any]:
    """Call LLM on one chunk (or full file text); return normalized extraction or empty dict on failure."""
    from llm_client import llm_chat

    model = model or os.getenv("ANTHROPIC_MODEL") or os.getenv("FOUNDRY_DEPLOYMENT") or os.getenv("OLLAMA_MODEL", "llama3:8b")
    text_slice = chunk[:max_text_chars] if max_text_chars else chunk
    prompt = EXTRACTION_PROMPT.format(text=text_slice)
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
                return extract_from_chunk(chunk, file_path, model=model, retry=False, max_text_chars=max_text_chars, num_predict=num_predict)
            return {"lexicon_entries": [], "grammar_notes": [], "pronunciation_notes": [], "cultural_notes": []}
        ok, normalized = _validate_extraction(data)
        return normalized
    except Exception as e:
        log.warning("Extraction failed for chunk from %s: %s", file_path, e)
        if retry:
            return extract_from_chunk(chunk, file_path, model=model, retry=False, max_text_chars=max_text_chars, num_predict=num_predict)
        return {"lexicon_entries": [], "grammar_notes": [], "pronunciation_notes": [], "cultural_notes": []}


def extract_one_file(
    text: str,
    path: str,
    model: Optional[str] = None,
    *,
    file_id: Optional[str] = None,
    file_index: int = 0,
    total_files: int = 0,
    chunk_start: int = 0,
    total_chunks: int = 0,
) -> Dict[str, Any]:
    """
    Run extraction on a single file's text. When the file fits in MAX_WHOLE_FILE_CHARS,
    send the whole file in one LLM call (no input chunking). Otherwise chunk and merge.
    Dedupe within this file only. Returns dict with lexicon_entries, grammar_notes, etc.
    """
    file_lexicon: List[Dict[str, Any]] = []
    file_grammar: List[str] = []
    file_pronunciation: List[str] = []
    file_cultural: List[str] = []
    seen_woccon: set = set()

    def merge_extraction(extracted: Dict[str, Any]) -> None:
        for e in extracted.get("lexicon_entries", []):
            key = (e.get("woccon") or "").lower()
            if not key or key in seen_woccon:
                continue
            seen_woccon.add(key)
            e = dict(e)
            e["source"] = EXTRACTION_SOURCE
            file_lexicon.append(e)
        file_grammar.extend(extracted.get("grammar_notes") or [])
        file_pronunciation.extend(extracted.get("pronunciation_notes") or [])
        file_cultural.extend(extracted.get("cultural_notes") or [])

    # Whole-file path: beam the entire file in one call when it fits (no input chunking).
    if len(text) <= MAX_WHOLE_FILE_CHARS:
        log.info(
            "Document %d/%d (%s) | whole file (%d chars, no chunking)",
            file_index, total_files, path, len(text),
        )
        extracted = extract_from_chunk(
            text,
            path,
            model=model,
            max_text_chars=MAX_WHOLE_FILE_CHARS,
            num_predict=32768,
        )
        merge_extraction(extracted)
    else:
        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            current_chunk = chunk_start + i + 1
            pct = int(100 * current_chunk / total_chunks) if total_chunks else 0
            log.info(
                "Document %d/%d (%s) | chunk %d/%d of file | overall %d/%d (%d%%)",
                file_index, total_files, path, i + 1, len(chunks), current_chunk, total_chunks, pct,
            )
            extracted = extract_from_chunk(
                chunk,
                path,
                model=model,
                max_text_chars=MAX_CHUNK_CHARS,
                num_predict=4096,
            )
            merge_extraction(extracted)

    file_grammar = list(dict.fromkeys(g.strip() for g in file_grammar if g and g.strip()))
    file_pronunciation = list(dict.fromkeys(p.strip() for p in file_pronunciation if p and p.strip()))
    file_cultural = list(dict.fromkeys(c.strip() for c in file_cultural if c and c.strip()))

    return {
        "source_path": path,
        "source_url": _source_url(file_id) if file_id else None,
        "lexicon_entries": file_lexicon,
        "grammar_notes": file_grammar,
        "pronunciation_notes": file_pronunciation,
        "cultural_notes": file_cultural,
        "meta": {"source": EXTRACTION_SOURCE},
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
    staging_dir = os.environ.get("DRIVE_STAGING_DIR") or DEFAULT_STAGING_DIR
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
    os.makedirs(staging_dir, exist_ok=True)
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
            file_data = extract_one_file(
                text, path, model=model,
                file_id=file_id,
                file_index=extract_index,
                total_files=total_extract,
                chunk_start=chunk_so_far,
                total_chunks=total_chunks,
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
    staging_dir = staging_dir or os.environ.get("DRIVE_STAGING_DIR") or DEFAULT_STAGING_DIR
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
    seen_woccon: set = set()
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
            for e in extracted.get("lexicon_entries", []):
                key = (e.get("woccon") or "").lower()
                if not key:
                    continue
                if key not in seen_woccon:
                    seen_woccon.add(key)
                    e = dict(e)
                    e["source"] = EXTRACTION_SOURCE
                    all_lexicon.append(e)
            all_grammar.extend(extracted.get("grammar_notes") or [])
            all_pronunciation.extend(extracted.get("pronunciation_notes") or [])

    all_grammar = list(dict.fromkeys(g.strip() for g in all_grammar if g and g.strip()))
    all_pronunciation = list(dict.fromkeys(p.strip() for p in all_pronunciation if p and p.strip()))

    return {
        "lexicon_entries": all_lexicon,
        "grammar_notes": all_grammar,
        "pronunciation_notes": all_pronunciation,
        "meta": {"source": EXTRACTION_SOURCE},
    }


def write_staging(data: Dict[str, Any], path: Optional[str] = None) -> str:
    """Write staging JSON to path. Returns path written."""
    path = path or os.environ.get("DRIVE_STAGING_PATH") or DEFAULT_STAGING_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("Wrote staging to %s", path)
    return path
