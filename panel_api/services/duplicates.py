"""Duplicate detection for pending lexicon and rules."""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from panel_api.config import get_settings
from panel_api.db import CanonicalLexicon, CanonicalRule, PendingLexicon, PendingRule


def normalize_text(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def similarity(a: str, b: str) -> float:
    """Levenshtein-based ratio (0-1)."""
    if not a and not b:
        return 1.0
    if len(a) > len(b):
        a, b = b, a
    distances = list(range(len(a) + 1))
    for i2, c2 in enumerate(b):
        distances_ = [i2 + 1]
        for i1, c1 in enumerate(a):
            if c1 == c2:
                distances_.append(distances[i1])
            else:
                distances_.append(1 + min(distances[i1], distances[i1 + 1], distances_[-1]))
        distances = distances_
    max_len = max(len(a), len(b))
    return 1.0 - (distances[-1] / max_len) if max_len else 1.0


def _normalize_woccon(w: str) -> str:
    return (w or "").strip().lower()


def find_lexicon_duplicate(
    db: Session, woccon: str, english: str
) -> Tuple[Optional[str], Optional[float], str]:
    """Returns (duplicate_of_id, score, match_type) where match_type is canonical|pending."""
    key = _normalize_woccon(woccon)
    settings = get_settings()
    threshold = settings.duplicate_threshold

    for row in db.query(CanonicalLexicon).filter(CanonicalLexicon.woccon_normalized == key).all():
        if row.woccon_normalized == key:
            return row.id, 1.0, "canonical"

    eng_norm = normalize_text(english)
    best_id, best_score, best_type = None, 0.0, "canonical"
    for row in db.query(CanonicalLexicon).all():
        score = similarity(eng_norm, normalize_text(row.english))
        if score > best_score:
            best_score, best_id, best_type = score, row.id, "canonical"

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.pending_duplicate_days)
    for row in (
        db.query(PendingLexicon)
        .filter(PendingLexicon.status == "pending", PendingLexicon.created_at >= cutoff)
        .all()
    ):
        if _normalize_woccon(row.woccon) == key:
            return row.id, 1.0, "pending"
        score = similarity(eng_norm, normalize_text(row.english))
        if score > best_score:
            best_score, best_id, best_type = score, row.id, "pending"

    if best_score >= threshold:
        return best_id, best_score, best_type
    return None, None, ""


def find_rule_duplicate(db: Session, category: str, content: str) -> Tuple[Optional[str], Optional[float], str]:
    norm = normalize_text(content)
    settings = get_settings()
    threshold = settings.duplicate_threshold

    for row in db.query(CanonicalRule).filter(CanonicalRule.category == category).all():
        if row.content_normalized == norm:
            return row.id, 1.0, "canonical"
        score = similarity(norm, row.content_normalized)
        if score >= threshold:
            return row.id, score, "canonical"

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.pending_duplicate_days)
    for row in (
        db.query(PendingRule)
        .filter(
            PendingRule.category == category,
            PendingRule.status == "pending",
            PendingRule.created_at >= cutoff,
        )
        .all()
    ):
        row_norm = normalize_text(row.content)
        if row_norm == norm:
            return row.id, 1.0, "pending"
        score = similarity(norm, row_norm)
        if score >= threshold:
            return row.id, score, "pending"

    return None, None, ""


def resolve_lexicon_duplicate(db: Session, duplicate_of_id: Optional[str]):
    """Load the canonical or pending row referenced by duplicate_of_id."""
    if not duplicate_of_id:
        return None, ""
    row = db.get(CanonicalLexicon, duplicate_of_id)
    if row:
        return row, "canonical"
    row = db.get(PendingLexicon, duplicate_of_id)
    if row:
        return row, "pending"
    return None, ""


def resolve_rule_duplicate(db: Session, duplicate_of_id: Optional[str]):
    """Load the canonical or pending row referenced by duplicate_of_id."""
    if not duplicate_of_id:
        return None, ""
    row = db.get(CanonicalRule, duplicate_of_id)
    if row:
        return row, "canonical"
    row = db.get(PendingRule, duplicate_of_id)
    if row:
        return row, "pending"
    return None, ""
