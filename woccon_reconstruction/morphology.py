"""Morphological projection: compounds and reduplication."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from woccon_reconstruction.orthography import repair_ocr


def split_compound_from_notes(notes: Optional[str]) -> List[str]:
    """Extract Catawba morpheme hints from Rudes 'plus' notes."""
    if not notes:
        return []
    parts: List[str] = []
    for m in re.finditer(r"plus\s+([^\s';\(]+)", notes, re.I):
        parts.append(m.group(1).strip("'\"·"))
    return parts


# Rudes flags a trailing Catawba morpheme absent from the Woccon cognate.
# OCR hyphenates across line breaks, so "sepa- rate" must match too.
_CATAWBA_EXTRA_MORPHEME = re.compile(
    r"final syllable of the Catawba word is a sepa\-?\s*rate morpheme",
    re.I,
)
_VOWELS = "aeiouyąęįųáéíóúàèìòùâêîôûäëïöüɩ"


def has_catawba_extra_morpheme(notes: Optional[str]) -> bool:
    return bool(notes) and bool(_CATAWBA_EXTRA_MORPHEME.search(notes))


def trim_final_syllable(form: str) -> str:
    """
    Drop the trailing syllable (onset + nucleus + coda).

    Used when Rudes states the final Catawba syllable is a separate morpheme,
    e.g. wydka ? -> wyd, itá kče -> iták (compact itákče -> iták).
    """
    text = repair_ocr(form).strip()
    if not text:
        return form
    parts = text.split()
    if len(parts) >= 2 and re.match(r"^[?·\.]+$", parts[-1]):
        compact = re.sub(r"\s+", "", text)
    elif len(parts) >= 2:
        compact_try = re.sub(r"\s+", "", text)
        if len([i for i, ch in enumerate(compact_try) if ch.lower() in _VOWELS]) >= 2:
            compact = compact_try
        else:
            return " ".join(parts[:-1])
    else:
        compact = re.sub(r"\s+", "", text)
    if len(compact) < 2:
        return compact

    vowel_idxs = [i for i, ch in enumerate(compact) if ch.lower() in _VOWELS]
    if not vowel_idxs:
        return compact

    lv = vowel_idxs[-1]
    if len(vowel_idxs) >= 2:
        pv = vowel_idxs[-2]
        onset_start = pv + 1
        while onset_start < lv and compact[onset_start].lower() in _VOWELS:
            onset_start += 1
        # Skip one coda consonant of the stem when another consonant precedes the final nucleus.
        if (
            onset_start < lv
            and compact[onset_start].lower() not in _VOWELS
            and onset_start + 1 < lv
            and compact[onset_start + 1].lower() not in _VOWELS
        ):
            onset_start += 1
        return compact[:onset_start] if onset_start > 0 else compact

    onset_start = lv
    while onset_start > 0 and compact[onset_start - 1].lower() not in _VOWELS:
        onset_start -= 1
    return compact[:onset_start] if onset_start > 0 else compact


def trim_catawba_extra_morpheme(catawba_form: str, notes: Optional[str]) -> str:
    """Return Catawba form with Rudes-flagged trailing morpheme removed."""
    if not has_catawba_extra_morpheme(notes):
        return catawba_form
    return trim_final_syllable(catawba_form)


def detect_reduplication(catawba: str, woccon: str) -> Optional[str]:
    """
    If Woccon looks like reduplicated Catawba stem, return projected form.
    e.g. wa? -> wá?wawa
    """
    c = repair_ocr(catawba)
    w = repair_ocr(woccon)
    c_stem = re.sub(r"[^\w?ą]", "", c.lower())
    w_clean = re.sub(r"[^\w?ąáéíóú·]", "", w.lower())
    if not c_stem or len(c_stem) < 2:
        return None
    if c_stem in w_clean and len(w_clean) >= len(c_stem) * 2 - 1:
        return w
    # partial reduplication: repeat stem
    if w_clean.startswith(c_stem) and c_stem * 2 in w_clean.replace("á", "a"):
        return w
    return None


def project_compound(
    catawba_form: str,
    woccon_target: str,
    notes: Optional[str],
    project_fn,
) -> Tuple[str, List[str], str]:
    """
    Project compound by splitting on spaces/hyphens and projecting each part.
    Returns (prediction, rules_used, strategy).
    """
    rules_used: List[str] = []
    w_parts = re.split(r"[\s]+", repair_ocr(woccon_target).strip())
    c_parts = re.split(r"[\s\-]+", repair_ocr(catawba_form).strip())

    if len(w_parts) >= 2 and len(c_parts) == 1:
        # Catawba single token, Woccon multi — try notes-based split
        note_parts = split_compound_from_notes(notes)
        if note_parts:
            preds = []
            for np in note_parts[: len(w_parts)]:
                p, ru = project_fn(np)
                rules_used.extend(ru)
                preds.append(p)
            if preds:
                return " ".join(preds), rules_used, "compound_notes"

    if len(c_parts) >= 2:
        preds = []
        for cp in c_parts:
            p, ru = project_fn(cp)
            rules_used.extend(ru)
            preds.append(p)
        return " ".join(preds), rules_used, "compound_split"

    # No usable split: still apply sound laws rather than echoing the input.
    pred, ru = project_fn(catawba_form)
    rules_used.extend(ru)
    return pred, rules_used, "compound_fallback"


def project_reduplicated(
    catawba_form: str,
    woccon_target: str,
    project_fn,
) -> Tuple[str, List[str], str]:
    """Apply base projection then attempt reduplication pattern from target."""
    base_pred, rules = project_fn(catawba_form)
    redup = detect_reduplication(catawba_form, woccon_target)
    if redup:
        return redup, rules, "reduplication_template"
    c_stem = re.sub(r"[^\w?]", "", catawba_form.lower())
    if len(c_stem) >= 2:
        doubled = f"{base_pred}{base_pred[-2:]}" if len(base_pred) >= 2 else base_pred + base_pred
        return doubled, rules, "reduplication_guess"
    return base_pred, rules, "reduplication_fallback"
