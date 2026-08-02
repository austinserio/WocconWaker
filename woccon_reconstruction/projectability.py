"""Classify cognate pairs by reconstructability bucket."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from woccon_reconstruction.orthography import is_corrupt, normalize_for_scoring

_FRAGMENT = re.compile(r"^\|[\-|\w]+\|$|^\([^\)]*\)$|^\[[^\]]*\]$|^\|[\-|\w]+\-?\|$")
_COMPOUND_MARKER = re.compile(r"\bplus\b", re.I)
_REDUPLICATION = re.compile(r"(.)\1|(.{2,})\2", re.I)

# Rudes prose signalling that the two compared forms differ in morpheme count.
# "contams" is a recurring OCR spelling of "contains".
_COMPOUND_PROSE = re.compile(
    r"construction cont(?:a|am)[in]*s the words|"
    r"construction shows|"
    r"contains the words|"
    r"\bmeans '[^']+', while \w+ means\b",
    re.I,
)
# Woccon side carries an affix the Catawba cognate lacks.
_AFFIXED_PROSE = re.compile(
    r"contains the independent \w+ suffix|"
    r"is apparently a participle|"
    r"contains the \w+ modal suffix",
    re.I,
)

# Length ratio outside this band => structurally broken pair (not a fair test).
_PLAUSIBLE_RATIO_MIN = 0.55
_PLAUSIBLE_RATIO_MAX = 1.8


def pair_plausibility_ratio(row: Dict[str, Any]) -> Optional[float]:
    """Return len(C)/len(W) on normalized forms, or None if either side empty."""
    c = normalize_for_scoring(row.get("catawba_form"))
    w = normalize_for_scoring(row.get("woccon_reconstituted"))
    if not c or not w:
        return None
    return len(c) / max(len(w), 1)


def is_plausible_pair(row: Dict[str, Any]) -> bool:
    ratio = pair_plausibility_ratio(row)
    if ratio is None:
        return False
    return _PLAUSIBLE_RATIO_MIN <= ratio <= _PLAUSIBLE_RATIO_MAX


def classify_pair(
    row: Dict[str, Any],
    raw_chunk: Optional[str] = None,
) -> str:
    """
    Return projectability bucket:
    simple | compound | reduplicated | fragment | corrupt | broken
    """
    w = (row.get("woccon_reconstituted") or "").strip()
    c = (row.get("catawba_form") or "").strip()
    gloss = (row.get("gloss") or "").strip()

    if is_corrupt(w) or is_corrupt(c):
        return "corrupt"

    if not w or not c:
        return "broken"

    if _FRAGMENT.match(w) or _FRAGMENT.match(c) or w.startswith("(") or "|-" in w:
        return "fragment"

    chunk = raw_chunk or row.get("_raw_chunk") or row.get("notes") or ""
    notes = row.get("notes") or ""
    if _COMPOUND_MARKER.search(chunk):
        return "compound"
    if " plus " in notes.lower():
        return "compound"
    if _COMPOUND_PROSE.search(notes) or _COMPOUND_PROSE.search(chunk):
        return "compound"

    # Woccon carries an affix absent from the Catawba cognate
    if _AFFIXED_PROSE.search(notes) or _AFFIXED_PROSE.search(chunk):
        return "affixed"

    # Rudes often writes spaces inside single reconstructed words (tá si, kú wate·).
    # If normalized lengths match, spaces are orthographic — not a compound.
    plausible = is_plausible_pair(row)

    # multi-word Woccon vs single-token Catawba suggests compound (unless orthographic spacing)
    if " " in w.replace("·", " ") and len(w.split()) >= 2:
        if (not c or " " not in c) and not plausible:
            return "compound"

    # both sides multi-token: phrase pair unless lengths still match as one word each
    if len(c.split()) >= 2 and len(w.split()) >= 2 and not plausible:
        return "compound"

    # reduplication: snow wa? -> wá?wawa; short Catawba vs long Woccon with repeated syllable
    w_norm = re.sub(r"[^\w?]", "", w.lower())
    c_norm = re.sub(r"[^\w?]", "", c.lower())
    if c_norm and w_norm and len(w_norm) > len(c_norm) + 2:
        if c_norm in w_norm and w_norm.count(c_norm[:2]) >= 2:
            return "reduplicated"
        if _REDUPLICATION.search(w_norm):
            return "reduplicated"

    # morpheme-only gloss rows
    if gloss in ("eat", "give it to me") and (len(c) <= 3 or len(w) <= 5):
        return "fragment"

    if not is_plausible_pair(row):
        return "broken"

    return "simple"


def annotate_pool(items: List[Dict[str, Any]], raw_by_id: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    raw_by_id = raw_by_id or {}
    for row in items:
        enriched = dict(row)
        chunk = raw_by_id.get(row.get("cognate_id", ""), "")
        enriched["projectability"] = classify_pair(enriched, chunk)
        out.append(enriched)
    return out
