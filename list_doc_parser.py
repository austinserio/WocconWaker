"""
Deterministic parsers for list-shaped Woccon Drive documents (English-Woccon, Lawson block).

Used by drive_extract hybrid ingest and panel base_vocab pronunciation sync.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

# --- Normalization ---

APOSTROPHE_MAP = str.maketrans({
    "\u2019": "'",
    "\u2018": "'",
    "\u02bc": "'",
    "\u0060": "'",
})


def normalize_unicode_text(value: str) -> str:
    s = unicodedata.normalize("NFKC", value or "")
    return s.translate(APOSTROPHE_MAP)


def normalize_woccon_for_key(woccon: str) -> str:
    s = normalize_unicode_text(woccon).strip().lower()
    return re.sub(r"[^a-z0-9\u0105\u0107\u0119\u0127\u0129\u0142\u0144\u00f3\u00f4\u015b\u0161\u017a\u017c\u0294'-]", "", s)


def normalize_english_for_key(english: str) -> str:
    s = normalize_unicode_text(english).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s.rstrip("?")


def lexicon_merge_key(woccon: str, english: str) -> str:
    return f"{normalize_woccon_for_key(woccon)}\x00{normalize_english_for_key(english)}"


# --- Line parsing ---

PAGE_MARKER_RE = re.compile(r"^\s*--\s*\d+\s+of\s+\d+\s*--\s*$", re.IGNORECASE)
URL_RE = re.compile(r"https?://", re.IGNORECASE)
NUMBER_PREFIX_RE = re.compile(r"^\s*(?:\d+[\.\)]\s*)")

SKIP_ENGLISH = frozenset({"i", "e", "a", "u", "i:", "e:", "a:", "u:"})
SKIP_WOCCON_FRAGMENTS = ("same as above", "living dictionary entry")

ENGLISH_WOCCON_HEADER_SKIP = (
    "english-woccon",
    "highlighted in blue",
    "written in blue",
    "highlighted yellow",
    "where we stopped last",
)

ENGLISH_WOCCON_END_MARKERS = (
    "possible words:",
    "known names:",
    "pronunciations according to",
    "what does ",
    "woccon shows long",
    "woccon village located",
    "people make the house",
    "yauh-he= man path",
)

# Vowel-chart rows from the Waccamaw pronunciation guide (not lexicon).
_VOWEL_CHART = frozenset(
    (e, w)
    for e, w in [
        ("a", "ah"),
        ("c", "ch"),
        ("e", "ay"),
        ("i", "ee"),
        ("o", "oh"),
        ("u", "oo"),
        ("au", "oo"),
    ]
)

# English= woccon (pron) | English: woccon | English - woccon
_LINE_WITH_PRON = re.compile(
    r"^\s*(?:\d+[\.\)]\s*)?"
    r"(?P<english>.+?)\s*[:=—–\-]\s*(?P<woccon>.+?)\s*\((?P<pronunciation>[^\)]+)\)\s*$"
)
_LINE_WITH_PRON_REV = re.compile(
    r"^\s*(?:\d+[\.\)]\s*)?"
    r"(?P<woccon>.+?)\s*[:=—–\-]\s*(?P<english>.+?)\s*\((?P<pronunciation>[^\)]+)\)\s*$"
)
_LINE_EQ = re.compile(r"^\s*(?:\d+[\.\)]\s*)?(?P<english>.+?)\s*=\s*(?P<right>.+?)\s*$")
_LINE_COLON = re.compile(r"^\s*(?:\d+[\.\)]\s*)?(?P<english>.+?)\s*:\s*(?P<right>.+?)\s*$")
_LINE_DASH = re.compile(r"^\s*(?:\d+[\.\)]\s*)?(?P<english>.+?)\s*-\s*(?P<right>.+?)\s*$")
_COULD_WOCCON = re.compile(
    r'^Could\s+["""\u201c\u201d\']?(?P<woccon>[^"""\u201c\u201d\']+)["""\u201c\u201d\']?\s*=\s*(?P<english>.+?)\s*$',
    re.IGNORECASE,
)
_THANK_YOU_INLINE = re.compile(r"thank\s+you\s*=\s*(?P<woccon>\S+)\s*$", re.IGNORECASE)

POSSIBLE_WORDS_END_MARKERS = (
    "known names:",
)

LAWSON_START_MARKERS = (
    "documentation of words",
    "documentation of words/spellings",
    "vocabulary of woccon",
    "lawson, john",
)
LAWSON_END_MARKERS = (
    "adelung",
    "carter, richard",
    "language sources:",
    "rankin, robert",
    "rudes, blair",
    "rudin, catherine",
    "kasak, ryan",
    "campbell, l.",
    "booker, karen",
)


@dataclass
class ParsedEntry:
    woccon: str
    english: str
    pronunciation: Optional[str] = None
    pos: Optional[str] = None
    source_excerpt: Optional[str] = None


def _guess_pos(english: str) -> str:
    e = english.lower()
    if e.startswith("to "):
        return "verb"
    if any(w in e for w in ("the ", "a ", "an ")):
        return "noun"
    return "unknown"


def _looks_like_pronunciation(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low or len(low) > 80:
        return False
    if low.startswith("capital here") or low.startswith("this is just"):
        return False
    if "means that" in low or "tentatively" in low:
        return False
    if re.match(r"^\d+\)", low):
        return False
    return True


def _looks_like_english_woccon_doc(text: str) -> bool:
    head = (text or "")[:500].lower()
    return "english-woccon" in head or "highlighted in blue=" in head


def _is_english_woccon_end_line(line: str, *, in_vocab: bool) -> bool:
    if not in_vocab:
        return False
    raw = (line or "").strip()
    low = raw.lower()
    if not low:
        return False
    if URL_RE.search(raw):
        return True
    if any(low.startswith(m) for m in ENGLISH_WOCCON_END_MARKERS):
        return True
    if re.match(r"^-re\s*=", low):
        return True
    if re.match(r"^p,\s*t,\s*k", low):
        return True
    if re.match(r"^[ieau]:?\s*$", low):
        return True
    return False


def _is_header_line(line: str) -> bool:
    low = (line or "").strip().lower().lstrip("\ufeff")
    if not low:
        return True
    if low in ENGLISH_WOCCON_HEADER_SKIP:
        return True
    if any(low.startswith(h) for h in ENGLISH_WOCCON_HEADER_SKIP):
        return True
    if low == "english-woccon":
        return True
    return False


def _extract_english_woccon_section(text: str) -> str:
    """Main vocabulary block only — stops before suffix notes, Possible Words, names, URLs."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    out: List[str] = []
    in_vocab = False
    for line in lines:
        if _is_english_woccon_end_line(line, in_vocab=in_vocab):
            break
        if _is_header_line(line):
            continue
        if not line.strip():
            if in_vocab:
                out.append(line)
            continue
        if not in_vocab:
            if "=" not in line and ":" not in line:
                continue
            if _is_header_line(line):
                continue
            in_vocab = True
        out.append(line)
    return "\n".join(out)


def _extract_possible_words_section(text: str) -> str:
    """Bounded Possible Words block — stops at Known names, URLs, or trailing prose."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    start: Optional[int] = None
    for i, line in enumerate(lines):
        if (line or "").strip().lower().startswith("possible words:"):
            start = i + 1
            break
    if start is None:
        return ""
    out: List[str] = []
    for line in lines[start:]:
        raw = (line or "").strip()
        low = raw.lower()
        if not raw:
            continue
        if any(low.startswith(m) for m in POSSIBLE_WORDS_END_MARKERS):
            break
        if URL_RE.search(raw) or raw.startswith("http"):
            break
        if low.startswith("eraute is cognated") or low.startswith("possible that it actually"):
            break
        out.append(line)
    return "\n".join(out)


def parse_note_line(line: str) -> Optional[ParsedEntry]:
    """Parse speculative/note lines outside strict English= woccon list format."""
    raw = (line or "").strip()
    if not raw or len(raw) < 5:
        return None
    m = _COULD_WOCCON.match(raw)
    if m:
        woccon = m.group("woccon").strip()
        english = re.split(r"\s{2,}|\s+More=", m.group("english").strip(), maxsplit=1)[0].strip()
        if woccon and english and not should_skip_candidate(english, woccon):
            return ParsedEntry(
                woccon=woccon,
                english=english,
                pos=_guess_pos(english),
                source_excerpt=raw[:200],
            )
    m = _THANK_YOU_INLINE.search(raw)
    if m:
        woccon, _ = _clean_woccon_field(m.group("woccon").strip())
        english = "thank you"
        if woccon and not should_skip_candidate(english, woccon):
            return ParsedEntry(
                woccon=woccon,
                english=english,
                pos="phrase",
                source_excerpt=raw[:200],
            )
    return None


def _clean_woccon_field(woccon: str, pronunciation: Optional[str] = None) -> Tuple[str, Optional[str]]:
    w = normalize_unicode_text(woccon or "").strip()
    w = re.sub(r"\[[^\]]+\]", "", w).strip()
    w = re.split(r"\s*-\s*tentatively\b", w, maxsplit=1)[0].strip()
    pron = pronunciation
    while "(" in w:
        m = re.search(r"\(([^\)]+)\)", w)
        if not m:
            break
        inner = m.group(1).strip()
        if _looks_like_pronunciation(inner):
            if not pron:
                pron = inner
            w = w[: m.start()].strip()
        else:
            w = w[: m.start()].strip()
            break
    w = " ".join(w.split())
    return w, _normalize_pronunciation(pron)


def _entry_to_dict(
    entry: ParsedEntry,
    *,
    source_section: str = "main",
    confidence: Optional[str] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "woccon": entry.woccon,
        "english": entry.english,
        "pos": entry.pos or "unknown",
        "pronunciation": entry.pronunciation,
        "source_excerpt": entry.source_excerpt,
        "extraction_method": "parser",
        "source_section": source_section,
    }
    if confidence:
        row["confidence"] = confidence
    return row


def _parse_body_lines(
    body: str,
    *,
    source_section: str,
    confidence: Optional[str] = None,
    include_notes: bool = False,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw_line in (body or "").splitlines():
        parsed = parse_note_line(raw_line) if include_notes else None
        if not parsed:
            parsed = parse_list_line(raw_line)
        if parsed:
            out.append(_entry_to_dict(parsed, source_section=source_section, confidence=confidence))
    return out


def _english_woccon_sections(text: str) -> List[Tuple[str, str, Optional[str], bool]]:
    """(source_section, body, confidence, include_notes) tuples for English-Woccon."""
    return [
        ("main", _extract_english_woccon_section(text), None, False),
        ("possible_words", _extract_possible_words_section(text), "possible", True),
    ]


def _parse_english_woccon_document(text: str) -> List[Dict[str, Any]]:
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for source_section, body, confidence, include_notes in _english_woccon_sections(text):
        for entry in _parse_body_lines(
            body,
            source_section=source_section,
            confidence=confidence,
            include_notes=include_notes,
        ):
            key = lexicon_merge_key(entry["woccon"], entry["english"])
            if key in seen:
                continue
            seen.add(key)
            out.append(entry)
    return out


def collect_parser_candidate_keys(text: str, *, section: str = "english_woccon") -> set:
    """Merge keys derivable deterministically from source text (for carry-forward)."""
    if section == "english_woccon" and _looks_like_english_woccon_doc(text):
        entries = _parse_english_woccon_document(text)
    elif section == "lawson":
        entries = _parse_body_lines(_extract_lawson_section(text), source_section="lawson")
    else:
        entries = _parse_body_lines(text, source_section="full")
    return {lexicon_merge_key(e["woccon"], e["english"]) for e in entries if e.get("woccon") and e.get("english")}


def iter_lexicon_candidates(text: str) -> Iterable[Tuple[str, str, str]]:
    """Yield (english, woccon, source_line) for completeness checks."""
    if _looks_like_english_woccon_doc(text):
        for source_section, body, _confidence, include_notes in _english_woccon_sections(text):
            for raw_line in body.splitlines():
                parsed = parse_note_line(raw_line) if include_notes else None
                if not parsed:
                    parsed = parse_list_line(raw_line)
                if parsed:
                    yield parsed.english, parsed.woccon, raw_line.strip()
        return
    for raw_line in (text or "").splitlines():
        parsed = parse_list_line(raw_line)
        if parsed:
            yield parsed.english, parsed.woccon, raw_line.strip()


def check_lexicon_completeness(
    source_text: str,
    entries: List[Dict[str, Any]],
    *,
    allowlist_keys: Optional[set] = None,
) -> Dict[str, Any]:
    """Compare parser-derived candidates to staged lexicon rows."""
    allowlist = allowlist_keys or set()
    extracted_keys = {
        lexicon_merge_key((e.get("woccon") or "").strip(), (e.get("english") or "").strip())
        for e in entries or []
        if (e.get("woccon") or "").strip() and (e.get("english") or "").strip()
    }
    missing: List[Dict[str, str]] = []
    matched = 0
    by_section: Dict[str, Dict[str, int]] = {}
    pw_lines = {
        line.strip()
        for line in _extract_possible_words_section(source_text).splitlines()
        if line.strip()
    } if _looks_like_english_woccon_doc(source_text) else set()
    for english, woccon, line in iter_lexicon_candidates(source_text):
        key = lexicon_merge_key(woccon, english)
        section = "possible_words" if line in pw_lines else "main"
        if section not in by_section:
            by_section[section] = {"candidates": 0, "matched": 0, "missing": 0}
        by_section[section]["candidates"] += 1
        if key in allowlist:
            matched += 1
            by_section[section]["matched"] += 1
            continue
        if key in extracted_keys:
            matched += 1
            by_section[section]["matched"] += 1
        else:
            by_section[section]["missing"] += 1
            missing.append({"english": english, "woccon": woccon, "source_line": line, "section": section})
    candidate_count = matched + len(missing)
    pct = round(100.0 * matched / candidate_count, 1) if candidate_count else 100.0
    return {
        "candidate_count": candidate_count,
        "staging_count": len(entries or []),
        "matched_count": matched,
        "missing_count": len(missing),
        "completeness_pct": pct,
        "missing": missing,
        "by_section": by_section,
    }


def audit_dropped_vs_previous(
    merged_entries: List[Dict[str, Any]],
    previous_entries: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    merged_keys = {
        lexicon_merge_key((e.get("woccon") or "").strip(), (e.get("english") or "").strip())
        for e in merged_entries or []
        if (e.get("woccon") or "").strip() and (e.get("english") or "").strip()
    }
    dropped: List[Dict[str, str]] = []
    for entry in previous_entries or []:
        woccon = (entry.get("woccon") or "").strip()
        english = (entry.get("english") or "").strip()
        if not woccon or not english:
            continue
        key = lexicon_merge_key(woccon, english)
        if key not in merged_keys:
            dropped.append(
                {
                    "woccon": woccon,
                    "english": english,
                    "previous_method": entry.get("extraction_method") or "unknown",
                }
            )
    return dropped


def merge_carry_forward(
    merged_entries: List[Dict[str, Any]],
    previous_entries: List[Dict[str, Any]],
    parser_candidate_keys: set,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Restore parser-backed rows lost to LLM variance on re-ingest."""
    out = list(merged_entries or [])
    merged_keys = {
        lexicon_merge_key((e.get("woccon") or "").strip(), (e.get("english") or "").strip())
        for e in out
        if (e.get("woccon") or "").strip() and (e.get("english") or "").strip()
    }
    carried: List[Dict[str, str]] = []
    for entry in previous_entries or []:
        woccon = (entry.get("woccon") or "").strip()
        english = (entry.get("english") or "").strip()
        if not woccon or not english:
            continue
        key = lexicon_merge_key(woccon, english)
        if key in merged_keys:
            continue
        if key not in parser_candidate_keys:
            continue
        row = dict(entry)
        row["extraction_method"] = "carry_forward"
        out.append(row)
        merged_keys.add(key)
        carried.append({"woccon": woccon, "english": english})
    return out, {"carried_forward_count": len(carried), "carried_forward": carried}


def _strip_pronunciation_tail(text: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Return (woccon_part, pronunciation, remainder_excerpt)."""
    excerpt = text.strip() if text else None
    w, pron = _clean_woccon_field(text or "")
    return w, pron, excerpt


def _parse_delimited_line(raw: str, english: str, right: str) -> Optional[ParsedEntry]:
    english = (english or "").strip().strip('"')
    right = (right or "").strip()
    if not english or not right:
        return None
    woccon, pron, _ = _strip_pronunciation_tail(right)
    if not woccon or should_skip_candidate(english, woccon):
        return None
    return ParsedEntry(
        woccon=woccon,
        english=english,
        pronunciation=pron,
        pos=_guess_pos(english),
        source_excerpt=raw[:200],
    )


def should_skip_candidate(english: str, woccon: str) -> bool:
    eng = normalize_english_for_key(english)
    w = normalize_unicode_text(woccon).strip()
    w_low = w.lower()
    if not eng or not w_low:
        return True
    if eng in SKIP_ENGLISH:
        return True
    if any(skip in w_low for skip in SKIP_WOCCON_FRAGMENTS):
        return True
    if any(h in eng for h in ("highlighted in blue", "written in blue", "highlighted yellow")):
        return True
    if "changed on" in w_low or "possible new words" in w_low:
        return True
    if eng == "english" and "woccon" in w_low:
        return True
    if (eng, w_low) in _VOWEL_CHART:
        return True
    if URL_RE.search(w_low) or URL_RE.search(english):
        return True
    if len(english) > 120 or len(woccon) > 120:
        return True
    if english.strip().startswith("http"):
        return True
    if re.match(r"^p\.\s*\d+", eng):
        return True
    if "doi.org" in eng or "doi.org" in w_low:
        return True
    if "questioning mode marker" in w_low:
        return True
    if eng.endswith("(more") or eng.endswith("( more"):
        return True
    if re.search(r"\[[^\]]*\(\d{4}\)", woccon):
        return True
    return False


def parse_list_line(line: str) -> Optional[ParsedEntry]:
    """Parse one vocabulary line. Returns None if not a lexicon candidate."""
    raw = (line or "").strip()
    if not raw or len(raw) < 3:
        return None
    if raw.startswith("#") or raw.startswith("[[PAGE ") or PAGE_MARKER_RE.match(raw):
        return None

    # Prefer '=' lines (English-Woccon primary format) before colon/dash patterns.
    if "=" in raw:
        m = _LINE_EQ.match(raw)
        if m:
            entry = _parse_delimited_line(raw, m.group("english"), m.group("right"))
            if entry:
                return entry

    for pat in (_LINE_WITH_PRON, _LINE_WITH_PRON_REV):
        m = pat.match(raw)
        if m:
            gd = m.groupdict()
            woccon = (gd.get("woccon") or "").strip()
            english = (gd.get("english") or "").strip().strip('"')
            pron = (gd.get("pronunciation") or "").strip()
            woccon, pron = _clean_woccon_field(woccon, pron)
            if woccon and english and not should_skip_candidate(english, woccon):
                return ParsedEntry(
                    woccon=woccon,
                    english=english,
                    pronunciation=pron,
                    pos=_guess_pos(english),
                    source_excerpt=raw[:200],
                )

    for pat in (_LINE_COLON, _LINE_DASH):
        m = pat.match(raw)
        if m:
            entry = _parse_delimited_line(raw, m.group("english"), m.group("right"))
            if entry:
                return entry

    return None


def _normalize_pronunciation(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    s = normalize_unicode_text(value).strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    if s.startswith("/") and s.endswith("/") and len(s) > 2:
        s = s[1:-1].strip()
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _extract_lawson_section(text: str) -> str:
    lines = (text or "").splitlines()
    start_idx = 0
    for i, line in enumerate(lines):
        low = line.strip().lower()
        if any(m in low for m in LAWSON_START_MARKERS):
            start_idx = i
            break
        if re.match(r"^(one|two|three|four|five|six|seven|eight|nine|ten)\s*:", low):
            start_idx = i
            break

    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        low = lines[i].strip().lower()
        if any(low.startswith(m) or m in low[:40] for m in LAWSON_END_MARKERS):
            end_idx = i
            break
    return "\n".join(lines[start_idx:end_idx])


def parse_list_document(text: str, *, section: str = "full") -> List[Dict[str, Any]]:
    """
    Parse list-shaped document text into lexicon dicts.
    section: 'full' | 'english_woccon' | 'lawson'
    Dedupes on (woccon, english) pair only.
    """
    if section == "lawson":
        body = _extract_lawson_section(text)
        seen: set = set()
        out: List[Dict[str, Any]] = []
        for raw_line in body.splitlines():
            parsed = parse_list_line(raw_line)
            if not parsed:
                continue
            key = lexicon_merge_key(parsed.woccon, parsed.english)
            if key in seen:
                continue
            seen.add(key)
            out.append(_entry_to_dict(parsed, source_section="lawson"))
        return out
    if section in ("english_woccon", "full") and _looks_like_english_woccon_doc(text):
        return _parse_english_woccon_document(text)
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for raw_line in (text or "").splitlines():
        parsed = parse_list_line(raw_line)
        if not parsed:
            continue
        key = lexicon_merge_key(parsed.woccon, parsed.english)
        if key in seen:
            continue
        seen.add(key)
        out.append(_entry_to_dict(parsed, source_section="full"))
    return out


def parse_pronunciation_text(text: str) -> List[Dict[str, Any]]:
    """Backward-compatible wrapper: entries with pronunciation only."""
    section = "english_woccon" if _looks_like_english_woccon_doc(text) else "full"
    return [
        {"woccon": e["woccon"], "english": e["english"], "pronunciation": e["pronunciation"]}
        for e in parse_list_document(text, section=section)
        if e.get("pronunciation")
    ]


def parse_vocab_text(text: str) -> List[Dict[str, Any]]:
    """Backward-compatible wrapper for Lawson-style lists (colon/dash, no pron required)."""
    entries = parse_list_document(text, section="lawson")
    if len(entries) < 50:
        entries = parse_list_document(text, section="full")
    return [
        {
            "woccon": e["woccon"],
            "english": e["english"],
            "pos": e.get("pos") or "unknown",
            "pronunciation": e.get("pronunciation"),
        }
        for e in entries
    ]


def list_doc_profile(path: str) -> Optional[str]:
    base = (path or "").split("/")[-1].lower()
    if "english-woccon" in base:
        return "english_woccon"
    if "documentation of woccon words" in base:
        return "doc_woccon_words"
    return None


def hybrid_enabled_for_path(path: str) -> bool:
    import os

    if os.environ.get("HYBRID_LIST_EXTRACT", "1").strip().lower() in ("0", "false", "no"):
        return False
    allowlist = os.environ.get("HYBRID_LIST_DOCS", "").strip()
    if allowlist:
        parts = [p.strip().lower() for p in allowlist.split(",") if p.strip()]
        base = (path or "").split("/")[-1].lower()
        return any(p in base for p in parts)
    return list_doc_profile(path) is not None


def merge_parser_and_llm_lexicon(
    parser_entries: List[Dict[str, Any]],
    llm_entries: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Merge parser (recall) + LLM (enrichment). Parser wins on woccon/english."""
    parser_map: Dict[str, Dict[str, Any]] = {}
    for e in parser_entries or []:
        w = (e.get("woccon") or "").strip()
        eng = (e.get("english") or "").strip()
        if not w or not eng:
            continue
        parser_map[lexicon_merge_key(w, eng)] = dict(e)

    llm_map: Dict[str, Dict[str, Any]] = {}
    for e in llm_entries or []:
        w = (e.get("woccon") or "").strip()
        eng = (e.get("english") or "").strip()
        if not w or not eng:
            continue
        llm_map[lexicon_merge_key(w, eng)] = dict(e)

    merged: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    parser_only = 0
    llm_only = 0

    enrich_fields = ("pronunciation", "pos", "part_of_speech", "source_excerpt", "source_page", "source_chunk_index")

    for key, pe in parser_map.items():
        row = dict(pe)
        row["extraction_method"] = "parser"
        le = llm_map.get(key)
        if le:
            row["extraction_method"] = "merged"
            for f in enrich_fields:
                if f == "part_of_speech":
                    val = le.get("pos") or le.get("part_of_speech")
                    if val and (not row.get("pos") or row.get("pos") == "unknown"):
                        row["pos"] = val
                elif f == "pos":
                    continue
                elif not row.get(f) and le.get(f):
                    row[f] = le[f]
            if (pe.get("pos") or pe.get("part_of_speech")) and le.get("pos") and pe.get("pos") != le.get("pos"):
                conflicts.append({"key": key, "field": "pos", "parser": pe.get("pos"), "llm": le.get("pos")})
        else:
            parser_only += 1
        merged.append(row)

    parser_keys = set(parser_map.keys())
    for key, le in llm_map.items():
        if key in parser_keys:
            continue
        row = dict(le)
        row["extraction_method"] = "llm"
        merged.append(row)
        llm_only += 1

    audit = {
        "parser_count": len(parser_map),
        "llm_count": len(llm_map),
        "merged_count": len(merged),
        "parser_only": parser_only,
        "llm_only": llm_only,
        "conflicts": conflicts,
    }
    return merged, audit
