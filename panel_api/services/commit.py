"""Commit approved pending rows to canonical DB and export unified JSON."""
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from panel_api.config import get_settings
from panel_api.db import CanonicalLexicon, CanonicalRule, PendingLexicon, PendingRule
from panel_api.services.duplicates import normalize_text

log = logging.getLogger("panel_commit")


def _normalize_woccon(w: str) -> str:
    return (w or "").strip().lower()


def commit_pending(db: Session) -> Dict[str, Any]:
    settings = get_settings()
    lexicon_committed = 0
    rules_committed = 0

    for pending in (
        db.query(PendingLexicon)
        .filter(PendingLexicon.status.in_(["approved", "modified"]))
        .all()
    ):
        key = _normalize_woccon(pending.woccon)
        existing = (
            db.query(CanonicalLexicon).filter(CanonicalLexicon.woccon_normalized == key).first()
        )
        if existing:
            existing.english = pending.english
            existing.pos = pending.pos
            existing.pronunciation = pending.pronunciation
            existing.source_url = pending.source_url or existing.source_url
            existing.source = "community_drive"
            existing.teaching_unit = pending.teaching_unit or existing.teaching_unit
            existing.word_class = pending.word_class or existing.word_class
            existing.lesson_band = pending.lesson_band or existing.lesson_band
        else:
            db.add(
                CanonicalLexicon(
                    woccon=pending.woccon,
                    english=pending.english,
                    pos=pending.pos,
                    pronunciation=pending.pronunciation,
                    source="community_drive",
                    source_url=pending.source_url,
                    woccon_normalized=key,
                    teaching_unit=pending.teaching_unit,
                    word_class=pending.word_class,
                    lesson_band=pending.lesson_band,
                )
            )
        pending.status = "committed"
        lexicon_committed += 1

    max_order = {}
    for cat in ("grammar", "pronunciation", "cultural"):
        row = (
            db.query(CanonicalRule)
            .filter(CanonicalRule.category == cat)
            .order_by(CanonicalRule.sort_order.desc())
            .first()
        )
        max_order[cat] = (row.sort_order + 1) if row else 0

    for pending in (
        db.query(PendingRule).filter(PendingRule.status.in_(["approved", "modified"])).all()
    ):
        cat = pending.category
        order = max_order.get(cat, 0)
        db.add(
            CanonicalRule(
                category=cat,
                content=pending.content,
                source_url=pending.source_url,
                source_document_id=pending.source_document_id,
                sort_order=order,
                content_normalized=normalize_text(pending.content),
                grammar_domain=pending.grammar_domain,
                pos_tag=pending.pos_tag,
                construction_type=pending.construction_type,
            )
        )
        max_order[cat] = order + 1
        pending.status = "committed"
        rules_committed += 1

    db.commit()

    export_paths = export_unified_json(db)
    reload_summary = {}
    return {
        "lexicon_committed": lexicon_committed,
        "rules_committed": rules_committed,
        "export_paths": export_paths,
        "reload_summary": reload_summary,
    }


def export_unified_json(db: Session) -> Dict[str, str]:
    settings = get_settings()
    dict_legacy_path = Path(settings.dictionary_legacy_path)
    rules_legacy_path = Path(settings.rules_legacy_path)

    if dict_legacy_path.is_file():
        with open(dict_legacy_path, encoding="utf-8") as f:
            legacy_dict = json.load(f)
    else:
        legacy_dict = {"language": "Woccon", "lexicon": []}

    community_lexicon = []
    for row in db.query(CanonicalLexicon).all():
        entry = {
            "woccon": row.woccon,
            "english": row.english,
            "pos": row.pos,
            "pronunciation": row.pronunciation,
            "source": row.source or "community_drive",
            "source_url": row.source_url,
        }
        if row.teaching_unit:
            entry["teaching_unit"] = row.teaching_unit
        if row.word_class:
            entry["word_class"] = row.word_class
        if row.lesson_band:
            entry["lesson_band"] = row.lesson_band
        community_lexicon.append(entry)

    import merge_staging

    legacy_lexicon = legacy_dict.get("lexicon") or []
    old_only, new_only, overlap, old_by_key, new_by_key = merge_staging.compare_lexicons(
        community_lexicon, legacy_lexicon
    )
    unified_lexicon = merge_staging.build_unified_lexicon(
        community_lexicon,
        legacy_lexicon,
        old_only,
        overlap,
        old_by_key,
        new_by_key,
    )
    unified_dictionary = dict(legacy_dict)
    unified_dictionary["lexicon"] = unified_lexicon
    unified_dictionary["source_note"] = (
        "Merged via control panel commit: community + Lawson."
    )

    dict_out = Path(settings.dictionary_unified_path)
    dict_out.parent.mkdir(parents=True, exist_ok=True)
    if dict_out.is_file():
        backup = dict_out.with_suffix(
            f".backup_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
        )
        shutil.copy2(dict_out, backup)
    with open(dict_out, "w", encoding="utf-8") as f:
        json.dump(unified_dictionary, f, indent=2, ensure_ascii=False)

    rules_out_path = Path(settings.rules_unified_path)
    unified_rules = None
    if rules_legacy_path.is_file():
        with open(rules_legacy_path, encoding="utf-8") as f:
            legacy_rules = json.load(f)
        unified_rules = dict(legacy_rules)
        for cat, key in [
            ("grammar", "community_grammar_notes"),
            ("pronunciation", "community_pronunciation_notes"),
            ("cultural", "community_cultural_notes"),
        ]:
            notes = []
            for row in (
                db.query(CanonicalRule)
                .filter(CanonicalRule.category == cat)
                .order_by(CanonicalRule.sort_order)
                .all()
            ):
                note = {"text": row.content, "source_url": row.source_url}
                if cat == "grammar":
                    if row.grammar_domain:
                        note["grammar_domain"] = row.grammar_domain
                    if row.pos_tag:
                        note["pos_tag"] = row.pos_tag
                    if row.construction_type:
                        note["construction_type"] = row.construction_type
                notes.append(note)
            unified_rules[key] = notes
        unified_rules["source_note"] = "Legacy rules plus community notes from control panel."
        if rules_out_path.is_file():
            backup = rules_out_path.with_suffix(
                f".backup_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
            )
            shutil.copy2(rules_out_path, backup)
        with open(rules_out_path, "w", encoding="utf-8") as f:
            json.dump(unified_rules, f, indent=2, ensure_ascii=False)

    return {
        "dictionary_unified": str(dict_out),
        "rules_unified": str(rules_out_path) if unified_rules else "",
    }


def reload_assistant(assistant: Any, dict_path: Optional[str] = None, rules_path: Optional[str] = None) -> Dict:
    settings = get_settings()
    return assistant.reload_language_data(
        dict_path=dict_path or settings.dictionary_unified_path,
        rules_path=rules_path or settings.rules_unified_path,
    )
