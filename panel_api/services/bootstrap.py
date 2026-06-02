"""Bootstrap admin user and import canonical data from unified JSON files."""
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from panel_api.auth import hash_password
from panel_api.config import get_settings
from panel_api.db import CanonicalLexicon, CanonicalRule, SourceDocument, User
from panel_api.services.citation import LAWSON_SEED_ID
from panel_api.services.duplicates import normalize_text
from panel_api.services.lexicon_classifier import apply_lexicon_classification
from panel_api.services.base_vocab import ensure_vocab_base_document, ensure_pronunciation_document, import_base_vocab

log = logging.getLogger("panel_bootstrap")

LAWSON_CITATION = (
    "Lawson, John. 1709. *A New Voyage to Carolina*. London: "
    "Printed for James Knapton, at the Crown in St. Paul's Church-Yard."
)


def _normalize_woccon(w: str) -> str:
    return (w or "").strip().lower()


def ensure_lawson_seed(db: Session) -> SourceDocument:
    doc = db.get(SourceDocument, LAWSON_SEED_ID)
    if doc:
        return doc
    doc = SourceDocument(
        id=LAWSON_SEED_ID,
        title="Lawson (1709) — A New Voyage to Carolina",
        source_type="seed",
        short_title="Lawson 1709",
        authors=json.dumps(["Lawson, John"]),
        year="1709",
        pub_title="A New Voyage to Carolina",
        publisher="James Knapton",
        place="London",
        citation_text=LAWSON_CITATION,
        is_seed=True,
        status="ready",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    log.info("Created Lawson seed source document")
    return doc


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


def _apply_locators(row, e: dict) -> None:
    for field in (
        "source_page",
        "source_page_end",
        "source_excerpt",
        "provenance_status",
    ):
        if e.get(field) is not None:
            setattr(row, field, e.get(field))


def import_canonical_if_empty(db: Session) -> dict:
    """Import canonical data when tables are empty."""
    summary = {"lexicon_imported": 0, "rules_imported": 0, "skipped": False, "import_mode": "none"}
    if db.query(CanonicalLexicon).count() > 0 or db.query(CanonicalRule).count() > 0:
        summary["skipped"] = True
        return summary

    lawson = ensure_lawson_seed(db)
    settings = get_settings()
    import_community = settings.panel_import_community

    if import_community:
        summary["import_mode"] = "unified"
        dict_path = Path(settings.dictionary_unified_path)
    else:
        summary["import_mode"] = "lawson_only"
        dict_path = Path(settings.dictionary_legacy_path)

    if dict_path.is_file():
        with open(dict_path, encoding="utf-8") as f:
            data = json.load(f)
        for i, e in enumerate(data.get("lexicon") or []):
            w = (e.get("woccon") or "").strip()
            if not w:
                continue
            src = e.get("source")
            if not import_community:
                if src and "lawson" not in str(src).lower():
                    continue
                if e.get("source_url"):
                    continue
            row = CanonicalLexicon(
                woccon=w,
                english=(e.get("english") or "").strip(),
                pos=(e.get("pos") or "unknown").strip(),
                pronunciation=(e.get("pronunciation") or None),
                source=src or "lawson",
                source_url=e.get("source_url") if import_community else None,
                sort_order=i,
                woccon_normalized=_normalize_woccon(w),
            )
            if not src or "lawson" in str(src).lower() or not import_community:
                row.source_document_id = lawson.id
            _apply_locators(row, e)
            apply_lexicon_classification(row, w, row.english, row.pos, row.source)
            db.add(row)
            summary["lexicon_imported"] += 1

    if import_community:
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
                        loc = {}
                    else:
                        text = (note.get("text") or "").strip()
                        url = note.get("source_url")
                        loc = note
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
                    _apply_locators(row, loc)
                    apply_classification_to_rule(row, category, text)
                    db.add(row)
                    summary["rules_imported"] += 1

    db.commit()
    log.info("Bootstrap import: %s", summary)
    return summary


def run_bootstrap(db: Session) -> dict:
    lawson = ensure_lawson_seed(db)
    admin = ensure_admin(db)
    vocab_doc = ensure_vocab_base_document(db)
    pron_doc = ensure_pronunciation_document(db)
    for row in db.query(CanonicalLexicon).filter(CanonicalLexicon.source_document_id.is_(None)).all():
        src = (row.source or "").lower()
        if not src or "lawson" in src:
            row.source_document_id = lawson.id
    db.commit()
    imported = import_canonical_if_empty(db)
    vocab_sync = None
    if vocab_doc and db.query(CanonicalLexicon).filter(CanonicalLexicon.is_base_entry.is_(True)).count() == 0:
        try:
            vocab_sync = import_base_vocab(db)
        except Exception as e:
            log.warning("Base vocab import on bootstrap failed: %s", e)
    return {
        "admin_id": admin.id,
        "lawson_seed_id": lawson.id,
        "vocab_base_doc_id": vocab_doc.id if vocab_doc else None,
        "pronunciation_doc_id": pron_doc.id if pron_doc else None,
        "vocab_sync": vocab_sync,
        **imported,
    }
