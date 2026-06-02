"""Fuzzy matching of lexicon entries to definitive base vocabulary."""
import re
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from panel_api.config import get_settings
from panel_api.db import CanonicalLexicon
from panel_api.services.duplicates import normalize_text, similarity


def base_woccon_match(
    woccon_a: str, woccon_b: str, *, threshold: Optional[float] = None
) -> Tuple[float, Optional[str]]:
    """Compare two Woccon forms for base-vocabulary dedupe. Returns (score, method)."""
    settings = get_settings()
    cut = threshold if threshold is not None else settings.base_vocab_dedupe_threshold
    key_a = normalize_woccon(woccon_a)
    key_b = normalize_woccon(woccon_b)
    if key_a == key_b:
        return 1.0, "woccon_exact"
    fa, fb = fuzzy_woccon_key(woccon_a), fuzzy_woccon_key(woccon_b)
    if fa == fb:
        return 1.0, "woccon_exact"
    score = similarity(fa, fb)
    if score >= cut:
        return score, "woccon_fuzzy"
    return 0.0, None


def find_duplicate_base(
    db: Session, woccon: str, english: str, *, threshold: Optional[float] = None
) -> Optional[CanonicalLexicon]:
    """Find an existing base row for the same lexeme (english + similar woccon)."""
    eng = normalize_text(english)
    if not eng:
        return None
    key = normalize_woccon(woccon)
    exact = (
        db.query(CanonicalLexicon)
        .filter(CanonicalLexicon.is_base_entry.is_(True), CanonicalLexicon.woccon_normalized == key)
        .first()
    )
    if exact:
        return exact

    for row in db.query(CanonicalLexicon).filter(CanonicalLexicon.is_base_entry.is_(True)).all():
        if normalize_text(row.english) != eng:
            continue
        score, _ = base_woccon_match(woccon, row.woccon, threshold=threshold)
        if score > 0:
            return row
    return None


def normalize_woccon(w: str) -> str:
    return (w or "").strip().lower()


def fuzzy_woccon_key(w: str) -> str:
    return re.sub(r"[^a-z]", "", normalize_woccon(w))


def find_base_match(
    db: Session, woccon: str, english: str
) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Match woccon/english against is_base_entry rows. Returns (base_id, score, method)."""
    settings = get_settings()
    key = normalize_woccon(woccon)
    fuzzy_key = fuzzy_woccon_key(woccon)
    eng_norm = normalize_text(english)

    base_rows = db.query(CanonicalLexicon).filter(CanonicalLexicon.is_base_entry.is_(True)).all()
    if not base_rows:
        return None, None, None

    for row in base_rows:
        if row.woccon_normalized == key:
            return row.id, 1.0, "woccon_exact"

    if eng_norm:
        for row in base_rows:
            if eng_norm != normalize_text(row.english):
                continue
            score, method = base_woccon_match(woccon, row.woccon, threshold=settings.base_vocab_dedupe_threshold)
            if score > 0:
                return row.id, score, method

    if fuzzy_key:
        best_id, best_score = None, 0.0
        for row in base_rows:
            score = similarity(fuzzy_key, fuzzy_woccon_key(row.woccon))
            if score > best_score:
                best_score, best_id = score, row.id
        if best_score >= settings.woccon_fuzzy_threshold:
            return best_id, best_score, "woccon_fuzzy"

    for row in base_rows:
        if eng_norm and eng_norm == normalize_text(row.english):
            return row.id, 1.0, "english_exact"

    best_id, best_score = None, 0.0
    for row in base_rows:
        score = similarity(eng_norm, normalize_text(row.english))
        if score > best_score:
            best_score, best_id = score, row.id
    if best_score >= settings.duplicate_threshold:
        return best_id, best_score, "english_fuzzy"

    return None, None, None


def apply_base_link_to_pending(row, db: Session) -> None:
    """Set base_entry_id and match_status on a pending row."""
    if getattr(row, "match_status", None) == "manual" and row.base_entry_id:
        return
    base_id, score, method = find_base_match(db, row.woccon, row.english)
    row.base_entry_id = base_id
    row.base_match_score = score
    row.base_match_method = method
    row.match_status = "matched" if base_id else "unmatched"


def manual_link_canonical_to_base(
    db: Session,
    row: CanonicalLexicon,
    base: CanonicalLexicon,
    *,
    score: float = 1.0,
) -> None:
    """Link a non-base canonical row to a base entry (curator override)."""
    if not base.is_base_entry:
        raise ValueError("Target is not a base entry")
    if row.is_base_entry:
        raise ValueError("Cannot link a base entry as a variant")
    if row.id == base.id:
        raise ValueError("Cannot link entry to itself")
    row.base_entry_id = base.id
    row.base_match_score = score
    row.base_match_method = "manual"
    if base.teaching_unit and base.teaching_unit != "other":
        row.teaching_unit = base.teaching_unit
        row.lesson_band = base.lesson_band


def apply_base_link_to_canonical(row, db: Session, *, skip_if_base: bool = True) -> None:
    """Set base_entry_id on a non-base canonical row."""
    if skip_if_base and getattr(row, "is_base_entry", False):
        return
    if row.base_entry_id and getattr(row, "base_match_method", None) == "manual":
        return
    base_id, score, method = find_base_match(db, row.woccon, row.english)
    if base_id and base_id != row.id:
        row.base_entry_id = base_id
        row.base_match_score = score
        row.base_match_method = method


def base_entry_preview(db: Session, base_entry_id: Optional[str]) -> Optional[dict]:
    if not base_entry_id:
        return None
    row = db.get(CanonicalLexicon, base_entry_id)
    if not row:
        return None
    return {"id": row.id, "woccon": row.woccon, "english": row.english}


def _citation_key(row: CanonicalLexicon) -> str:
    excerpt = (row.source_excerpt or "")[:80]
    return "|".join(
        [
            str(row.source or ""),
            str(row.source_page or ""),
            str(row.source_page_end or ""),
            str(row.source_url or ""),
            excerpt,
            str(row.id),
        ]
    )


def variant_count(db: Session, base_entry_id: str) -> int:
    return (
        db.query(CanonicalLexicon)
        .filter(
            CanonicalLexicon.base_entry_id == base_entry_id,
            CanonicalLexicon.is_base_entry.is_(False),
        )
        .count()
    )


def attestation_citation_count(db: Session, base_row: CanonicalLexicon) -> int:
    """Unique citations across the base row and its linked variants."""
    variants = (
        db.query(CanonicalLexicon)
        .filter(
            CanonicalLexicon.base_entry_id == base_row.id,
            CanonicalLexicon.is_base_entry.is_(False),
        )
        .all()
    )
    seen: set[str] = set()
    count = 0
    for row in [base_row, *variants]:
        key = _citation_key(row)
        if key in seen:
            continue
        seen.add(key)
        count += 1
    return count
