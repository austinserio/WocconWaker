"""Build in-memory dictionary/rules snapshots from the panel canonical DB."""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from panel_api.config import get_settings
from panel_api.db import CanonicalLexicon, CanonicalRule
from panel_api.services.citation import citation_for_entry


def provenance_export(db: Session, row) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if row.source_page is not None:
        out["source_page"] = row.source_page
    if row.source_page_end is not None:
        out["source_page_end"] = row.source_page_end
    if row.source_excerpt:
        out["source_excerpt"] = row.source_excerpt
    if row.provenance_status:
        out["provenance_status"] = row.provenance_status
    citation = citation_for_entry(
        db,
        source_document_id=getattr(row, "source_document_id", None),
        source=getattr(row, "source", None),
        source_url=getattr(row, "source_url", None),
        source_page=getattr(row, "source_page", None),
        source_page_end=getattr(row, "source_page_end", None),
        source_excerpt=getattr(row, "source_excerpt", None),
        provenance_status=getattr(row, "provenance_status", None),
    )
    if citation:
        out["citation_short"] = citation.short
        out["citation_full"] = citation.full
    return out


def language_source() -> str:
    """panel_db (default) or json — where WocconAssistant loads language data."""
    return os.environ.get("WOCCON_LANGUAGE_SOURCE", "panel_db").strip().lower()


def use_panel_db_source() -> bool:
    return language_source() in ("panel_db", "db", "database")


def build_language_snapshot(db: Session) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Same merge logic as commit export, without writing unified JSON files.
    Lawson legacy + canonical lexicon/rules from the control panel DB.
    """
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
        if row.is_base_entry:
            entry["is_base_entry"] = True
        if row.base_entry_id:
            entry["base_entry_id"] = row.base_entry_id
        entry.update(provenance_export(db, row))
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
        "Live snapshot from control panel DB: community + Lawson."
    )

    if not rules_legacy_path.is_file():
        return unified_dictionary, {"language": "Woccon"}

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
            note.update(provenance_export(db, row))
            if cat == "grammar":
                if row.grammar_domain:
                    note["grammar_domain"] = row.grammar_domain
                if row.pos_tag:
                    note["pos_tag"] = row.pos_tag
                if row.construction_type:
                    note["construction_type"] = row.construction_type
                if row.grammar_lineage:
                    note["grammar_lineage"] = row.grammar_lineage
                if getattr(row, "rule_kind", None):
                    note["rule_kind"] = row.rule_kind
                if getattr(row, "correspondence_status", None):
                    note["correspondence_status"] = row.correspondence_status
            notes.append(note)
        unified_rules[key] = notes
    unified_rules["source_note"] = (
        "Live snapshot: legacy rules plus community notes from control panel DB."
    )
    return unified_dictionary, unified_rules


def sync_assistant_from_panel_db(assistant: Any, db: Optional[Session] = None) -> Dict[str, Any]:
    """Reload assistant in-memory data from the panel canonical DB."""
    from panel_api.db import get_session_factory

    own_session = db is None
    if own_session:
        db = get_session_factory()()
    try:
        dictionary, rules = build_language_snapshot(db)
        return assistant.reload_language_data(
            dictionary=dictionary,
            rules=rules,
            source="panel_db",
        )
    finally:
        if own_session:
            db.close()
