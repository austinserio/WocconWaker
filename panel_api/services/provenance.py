"""Validate and resolve page-level provenance from marked source text."""
import re
from typing import Any, Dict, List, Optional, Tuple

PAGE_MARKER_RE = re.compile(r"\[\[PAGE\s+(\d+)\]\]", re.IGNORECASE)
WORD_TOKEN_RE = re.compile(r"[a-z0-9']+|[-/][a-z0-9]+", re.IGNORECASE)
MAX_EXCERPT_LEN = 200
MAX_RULE_EXCERPT_LEN = 800


def strip_page_markers(text: str) -> str:
    return PAGE_MARKER_RE.sub("", text or "")


def page_at_offset(marked_text: str, offset: int) -> Optional[int]:
    if offset < 0:
        return None
    page = None
    for m in PAGE_MARKER_RE.finditer(marked_text):
        if m.start() <= offset:
            page = int(m.group(1))
        else:
            break
    return page


def find_text_offset(marked_text: str, needle: str) -> Optional[int]:
    if not needle or not marked_text:
        return None
    idx = marked_text.find(needle)
    if idx >= 0:
        return idx
    clean_needle = needle.strip()
    clean_text = strip_page_markers(marked_text)
    idx2 = clean_text.find(clean_needle)
    if idx2 < 0:
        idx2 = clean_text.lower().find(clean_needle.lower())
    if idx2 >= 0:
        # Map clean offset back to marked text (approximate)
        stripped = 0
        pos = 0
        while pos < len(marked_text) and stripped < idx2:
            m = PAGE_MARKER_RE.match(marked_text, pos)
            if m:
                pos = m.end()
                continue
            stripped += 1
            pos += 1
        return pos
    return None


def _content_search_phrases(content: str, *, min_words: int = 4, min_chars: int = 18) -> List[str]:
    """Longest-first phrases to locate paraphrased notes in source text."""
    content = (content or "").strip()
    if not content:
        return []
    phrases: List[str] = []
    seen: set[str] = set()

    def add(phrase: str) -> None:
        phrase = phrase.strip()
        if phrase and phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)

    add(content)
    if len(content) > 120:
        add(content[:120])
    add(content[:80])

    tokens = WORD_TOKEN_RE.findall(content)
    if len(tokens) < min_words:
        return phrases

    n = len(tokens)
    sizes = sorted({n, n - 1, n - 2, 10, 8, 6, 5, min_words}, reverse=True)
    sizes = [s for s in sizes if min_words <= s <= n]
    for size in sizes:
        step = 1 if size >= 8 else 2
        for i in range(0, n - size + 1, step):
            phrase = " ".join(tokens[i : i + size])
            if len(phrase) >= min_chars:
                add(phrase)
    return phrases


def find_best_text_offset(marked_text: str, content: str) -> Optional[int]:
    """Find source offset using full text, then longest distinctive sub-phrases."""
    for phrase in _content_search_phrases(content):
        offset = find_text_offset(marked_text, phrase)
        if offset is not None:
            return offset
    return None


def resolve_canonical_provenance(
    content: str,
    marked_text: str,
    *,
    woccon: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve page/excerpt for an existing canonical row by searching source text."""
    search = (content or "").strip()
    offset = find_best_text_offset(marked_text, search) if search else None
    if offset is None and woccon:
        offset = find_text_offset(marked_text, woccon.strip())
    if offset is None:
        return {
            "source_page": None,
            "source_page_end": None,
            "source_excerpt": None,
            "source_chunk_index": None,
            "provenance_status": "missing",
        }

    page = page_at_offset(marked_text, offset)
    anchor_len = len(search) if search else len((woccon or "").strip())
    start = max(0, offset - 40)
    end = min(len(marked_text), offset + anchor_len + 80)
    excerpt = cap_excerpt(strip_page_markers(marked_text[start:end]))
    status = "verified" if page is not None else "missing"
    return {
        "source_page": page,
        "source_page_end": None,
        "source_excerpt": excerpt,
        "source_chunk_index": None,
        "provenance_status": status,
    }


def cap_excerpt(text: Optional[str], max_len: int = MAX_EXCERPT_LEN) -> Optional[str]:
    if not text:
        return None
    s = " ".join(str(text).split())
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def resolve_lexicon_provenance(
    entry: Dict[str, Any],
    marked_text: str,
    chunk_index: Optional[int] = None,
    chunk_page_start: Optional[int] = None,
    chunk_page_end: Optional[int] = None,
) -> Dict[str, Any]:
    excerpt = cap_excerpt(entry.get("source_excerpt"))
    page = _coerce_int(entry.get("source_page"))
    page_end = None
    woccon = (entry.get("woccon") or "").strip()

    search = excerpt or woccon
    offset = find_text_offset(marked_text, search) if search else None
    if offset is not None:
        resolved_page = page_at_offset(marked_text, offset)
        if resolved_page is not None:
            page = resolved_page
            status = "verified"
            if not excerpt and woccon:
                start = max(0, offset - 40)
                end = min(len(marked_text), offset + len(woccon) + 80)
                excerpt = cap_excerpt(strip_page_markers(marked_text[start:end]))
        elif page is not None:
            status = "inferred"
        else:
            status = "missing"
    elif page is not None:
        status = "inferred"
    elif chunk_page_start is not None:
        page = chunk_page_start
        page_end = chunk_page_end if chunk_page_end != chunk_page_start else None
        status = "inferred"
    else:
        status = "missing"

    return {
        "source_page": page,
        "source_page_end": page_end,
        "source_excerpt": excerpt,
        "source_chunk_index": chunk_index,
        "provenance_status": status,
    }


def resolve_note_provenance(
    note: Any,
    marked_text: str,
    chunk_index: Optional[int] = None,
    chunk_page_start: Optional[int] = None,
    chunk_page_end: Optional[int] = None,
) -> Dict[str, Any]:
    if isinstance(note, dict):
        content = (note.get("text") or note.get("content") or "").strip()
        excerpt = cap_excerpt(
            note.get("source_excerpt") or content[:400],
            MAX_RULE_EXCERPT_LEN,
        )
        page = _coerce_int(note.get("source_page"))
        page_end = _coerce_int(note.get("source_page_end"))
    else:
        content = str(note).strip()
        excerpt = cap_excerpt(content[:400], MAX_RULE_EXCERPT_LEN)
        page = None
        page_end = None

    search = excerpt or content[:200]
    offset = find_text_offset(marked_text, search) if search else None
    if offset is not None:
        resolved_page = page_at_offset(marked_text, offset)
        if resolved_page is not None:
            page = resolved_page
            status = "verified"
        elif page is not None:
            status = "inferred"
        else:
            status = "missing"
    elif page is not None:
        status = "inferred"
    elif chunk_page_start is not None:
        page = chunk_page_start
        page_end = chunk_page_end if chunk_page_end and chunk_page_end != chunk_page_start else page_end
        status = "inferred"
    else:
        status = "missing"

    return {
        "source_page": page,
        "source_page_end": page_end,
        "source_excerpt": excerpt,
        "source_chunk_index": chunk_index,
        "provenance_status": status,
    }


def _coerce_int(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def chunk_page_range(chunk_text: str) -> Tuple[Optional[int], Optional[int]]:
    pages = [int(m.group(1)) for m in PAGE_MARKER_RE.finditer(chunk_text)]
    if not pages:
        return None, None
    return min(pages), max(pages)
