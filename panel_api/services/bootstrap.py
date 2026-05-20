"""Bootstrap admin user and import canonical data from unified JSON files."""
import json
import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from panel_api.auth import hash_password
from panel_api.config import get_settings
from panel_api.db import CanonicalLexicon, CanonicalRule, User
from panel_api.services.duplicates import normalize_text
from panel_api.services.lexicon_classifier import apply_lexicon_classification
from panel_api.services.rule_classifier import apply_classification_to_rule

log = logging.getLogger("panel_bootstrap")


def _normalize_woccon(w: str) -> str:
    return (w or "").strip().lower()


def ensure_admin(db: Session) -> User:
    settings = get_settings()
    user = db.query(User).filter(User.email == settings.panel_admin_email).first()
    if user:
        return user
    user = User(
        email=settings.panel_admin_email,
        password_hash=hash_password(settings.panel_admin_password),
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info("Created bootstrap admin %s", settings.panel_admin_email)
    return user


def import_canonical_if_empty(db: Session) -> dict:
    """Import dictionary_unified and rules_unified when canonical tables are empty."""
    summary = {"lexicon_imported": 0, "rules_imported": 0, "skipped": False}
    if db.query(CanonicalLexicon).count() > 0 or db.query(CanonicalRule).count() > 0:
        summary["skipped"] = True
        return summary

    settings = get_settings()
    dict_path = Path(settings.dictionary_unified_path)
    if dict_path.is_file():
        with open(dict_path, encoding="utf-8") as f:
            data = json.load(f)
        for i, e in enumerate(data.get("lexicon") or []):
            w = (e.get("woccon") or "").strip()
            if not w:
                continue
            row = CanonicalLexicon(
                woccon=w,
                english=(e.get("english") or "").strip(),
                pos=(e.get("pos") or "unknown").strip(),
                pronunciation=(e.get("pronunciation") or None),
                source=e.get("source"),
                source_url=e.get("source_url"),
                sort_order=i,
                woccon_normalized=_normalize_woccon(w),
            )
            apply_lexicon_classification(row, w, row.english, row.pos, row.source)
            db.add(row)
            summary["lexicon_imported"] += 1

    rules_path = Path(settings.rules_unified_path)
    if rules_path.is_file():
        with open(rules_path, encoding="utf-8") as f:
            rules = json.load(f)
        category_map = {
            "grammar": rules.get("community_grammar_notes") or [],
            "pronunciation": rules.get("community_pronunciation_notes") or [],
            "cultural": rules.get("community_cultural_notes") or [],
        }
        for category, notes in category_map.items():
            for i, note in enumerate(notes):
                if isinstance(note, str):
                    text, url = note.strip(), None
                else:
                    text = (note.get("text") or "").strip()
                    url = note.get("source_url")
                if not text:
                    continue
                legacy_key = f"{category}:{i}:{hash(text) & 0xFFFFFFFF:08x}"
                row = CanonicalRule(
                    category=category,
                    content=text,
                    source_url=url,
                    sort_order=i,
                    legacy_key=legacy_key,
                    content_normalized=normalize_text(text),
                )
                apply_classification_to_rule(row, category, text)
                db.add(row)
                summary["rules_imported"] += 1

    db.commit()
    log.info("Bootstrap import: %s", summary)
    return summary


def run_bootstrap(db: Session) -> dict:
    admin = ensure_admin(db)
    imported = import_canonical_if_empty(db)
    return {"admin_id": admin.id, **imported}
