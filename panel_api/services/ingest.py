"""Document upload, text extraction, LLM extract, pending rows."""
import hashlib
import io
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from panel_api.config import get_settings
from panel_api.db import CanonicalLexicon, CanonicalRule, PendingLexicon, PendingRule, SourceDocument
from panel_api.services.citation import guess_bibliography_from_title
from panel_api.services.duplicates import find_lexicon_duplicate, find_rule_duplicate, normalize_text
from panel_api.services.vocab_match import apply_base_link_to_pending
from panel_api.services.lexicon_classifier import apply_lexicon_classification
from panel_api.services.provenance import (
    resolve_canonical_provenance,
    resolve_lexicon_provenance,
    resolve_note_provenance,
)
from panel_api.services.rule_classifier import apply_classification_to_rule

log = logging.getLogger("panel_ingest")

DRIVE_D_ID_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)")
DRIVE_OPEN_RE = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")
PAGE_MARKER = "[[PAGE {n}]]"


def parse_drive_file_id(url: str) -> Optional[str]:
    """Extract Drive file ID from file, Docs, Sheets, or open?id= URLs."""
    if not url:
        return None
    m = DRIVE_D_ID_RE.search(url.strip())
    if m:
        return m.group(1)
    m = DRIVE_OPEN_RE.search(url)
    if m:
        return m.group(1)
    return None


def mark_text_with_pages(parts: list[str]) -> str:
    """Join page texts with [[PAGE n]] markers."""
    marked = []
    for i, text in enumerate(parts, start=1):
        if text and text.strip():
            marked.append(f"{PAGE_MARKER.format(n=i)}\n{text.strip()}")
    return "\n\n".join(marked) if marked else ""


def extract_text_from_pdf_bytes(
    data: bytes,
    *,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> Tuple[str, str]:
    from panel_api.services.pdf_text import extract_pdf_text

    return extract_pdf_text(data, on_progress=on_progress)


def extract_text_from_docx_bytes(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return mark_text_with_pages([text]) if text.strip() else ""


def fetch_drive_meta(file_id: str) -> Tuple[str, str]:
    """Return (name, mime_type) for a Drive file."""
    import drive_ingest

    creds = drive_ingest._get_credentials()
    service = drive_ingest._build_drive_service(creds)
    meta = service.files().get(fileId=file_id, fields="mimeType,name").execute()
    return meta.get("name", "drive_document"), meta.get("mimeType", "")


def fetch_drive_bytes(file_id: str) -> Tuple[bytes, str, str]:
    """Download Drive file bytes. Returns (data, name, mime_type)."""
    import drive_ingest

    creds = drive_ingest._get_credentials()
    service = drive_ingest._build_drive_service(creds)
    meta = service.files().get(fileId=file_id, fields="mimeType,name").execute()
    mime = meta.get("mimeType", "")
    name = meta.get("name", "drive_document")
    if mime == drive_ingest.GOOGLE_DOCS_MIME:
        text = drive_ingest.fetch_doc_text(service, file_id)
        data = text.encode("utf-8")
    else:
        data = service.files().get_media(fileId=file_id).execute()
        if not isinstance(data, bytes):
            data = bytes(data) if data else b""
    return data, name, mime


def fetch_drive_text(
    file_id: str,
    *,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> Tuple[str, str, Optional[str]]:
    """Fetch marked text from Drive. Returns (text, name, extraction_method)."""
    import drive_ingest

    data, name, mime = fetch_drive_bytes(file_id)
    method: Optional[str] = None
    if mime == drive_ingest.GOOGLE_DOCS_MIME:
        text = data.decode("utf-8", errors="replace")
        text = mark_text_with_pages([text]) if text.strip() else ""
    elif mime == drive_ingest.PDF_MIME:
        text, method = extract_text_from_pdf_bytes(data, on_progress=on_progress)
    else:
        raise ValueError(f"Unsupported Drive mime type: {mime}")
    return text, name, method


def extract_text_from_upload(
    filename: str,
    data: bytes,
    *,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> Tuple[str, Optional[str]]:
    """Extract marked text from upload bytes. Returns (text, extraction_method)."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        text, method = extract_text_from_pdf_bytes(data, on_progress=on_progress)
        return text, method
    if lower.endswith(".txt"):
        raw = data.decode("utf-8", errors="replace")
        return (mark_text_with_pages([raw]) if raw.strip() else ""), None
    if lower.endswith(".docx"):
        return extract_text_from_docx_bytes(data), None
    raise ValueError(f"Unsupported file type: {filename}")


def extract_text_from_document(
    doc: SourceDocument,
    db: Session,
    *,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> Tuple[str, Optional[str]]:
    """Load marked source text from stored upload or Drive link."""
    if on_progress:
        on_progress(1, "Reading document…")
    if doc.local_path and os.path.isfile(doc.local_path):
        path = Path(doc.local_path)
        return extract_text_from_upload(path.name, path.read_bytes(), on_progress=on_progress)
    if doc.drive_file_id:
        text, _, method = fetch_drive_text(doc.drive_file_id, on_progress=on_progress)
        return text, method
    raise ValueError("No local file or Drive ID available for re-extract")


def save_upload_file(data: bytes, filename: str) -> str:
    settings = get_settings()
    os.makedirs(settings.woccon_upload_dir, exist_ok=True)
    safe = re.sub(r'[<>:"|?*\r\n\\/]', "_", filename)[:200]
    dest = os.path.join(settings.woccon_upload_dir, f"{uuid.uuid4().hex}_{safe}")
    with open(dest, "wb") as f:
        f.write(data)
    return dest


def file_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_existing_document(
    db: Session,
    *,
    drive_file_id: Optional[str] = None,
    content_hash: Optional[str] = None,
) -> Optional[SourceDocument]:
    """Return the newest matching library document (excluding seed/vocab-base rows)."""
    q = db.query(SourceDocument).filter(
        SourceDocument.is_vocab_base.is_(False),
        SourceDocument.is_seed.is_(False),
    )
    if drive_file_id:
        q = q.filter(SourceDocument.drive_file_id == drive_file_id)
    elif content_hash:
        q = q.filter(SourceDocument.content_hash == content_hash)
    else:
        return None
    return q.order_by(SourceDocument.created_at.desc()).first()


def restart_document_for_reingest(
    db: Session,
    doc: SourceDocument,
    *,
    user_id: Optional[str],
    extraction_focus: str,
    grammar_lineage: Optional[str],
    title: Optional[str] = None,
) -> SourceDocument:
    if title:
        doc.title = title
    doc.extraction_focus = extraction_focus
    doc.grammar_lineage = grammar_lineage
    doc.status = "processing"
    doc.progress_pct = 0
    doc.progress_message = "Reading document…"
    doc.error_message = None
    if user_id:
        doc.uploaded_by = user_id
    db.commit()
    db.refresh(doc)
    return doc


def _clear_pending_for_focus(db: Session, doc_id: str, focus: str) -> None:
    """Remove pending rows for categories being re-extracted (keeps other categories)."""
    focus = (focus or "general").strip().lower()
    if focus in ("general", ""):
        db.query(PendingLexicon).filter(
            PendingLexicon.source_document_id == doc_id,
            PendingLexicon.status == "pending",
        ).delete(synchronize_session=False)
        db.query(PendingRule).filter(
            PendingRule.source_document_id == doc_id,
            PendingRule.status == "pending",
        ).delete(synchronize_session=False)
        return
    if focus == "vocabulary":
        db.query(PendingLexicon).filter(
            PendingLexicon.source_document_id == doc_id,
            PendingLexicon.status == "pending",
        ).delete(synchronize_session=False)
        return
    category_map = {
        "grammar": "grammar",
        "pronunciation": "pronunciation",
        "culture": "cultural",
    }
    category = category_map.get(focus)
    if category:
        db.query(PendingRule).filter(
            PendingRule.source_document_id == doc_id,
            PendingRule.status == "pending",
            PendingRule.category == category,
        ).delete(synchronize_session=False)


def apply_bibliography_defaults(doc: SourceDocument) -> None:
    """Fill empty bibliography fields from upload title."""
    guessed = guess_bibliography_from_title(doc.title or "")
    if not doc.short_title:
        doc.short_title = guessed.get("short_title")
    if not doc.year:
        doc.year = guessed.get("year")
    if not doc.pub_title:
        doc.pub_title = guessed.get("pub_title") or doc.title


def _note_text(note: Any) -> str:
    if isinstance(note, dict):
        return (note.get("text") or note.get("content") or "").strip()
    return str(note).strip()


def urls_match(a: Optional[str], b: Optional[str]) -> bool:
    """True when two citation URLs refer to the same Drive file (or identical URL)."""
    if not a or not b:
        return False
    a, b = a.strip(), b.strip()
    if a == b:
        return True
    fa, fb = parse_drive_file_id(a), parse_drive_file_id(b)
    if fa and fb:
        return fa == fb
    return a.rstrip("/") == b.rstrip("/")


def _canonical_lexicon_for_merge(db: Session, doc: SourceDocument, woccon_key: str):
    rows = db.query(CanonicalLexicon).filter(CanonicalLexicon.woccon_normalized == woccon_key).all()
    return [r for r in rows if urls_match(r.source_url, doc.source_url)]


def _canonical_rules_for_merge(db: Session, doc: SourceDocument, category: str, content_norm: str):
    rows = (
        db.query(CanonicalRule)
        .filter(CanonicalRule.category == category, CanonicalRule.content_normalized == content_norm)
        .all()
    )
    return [r for r in rows if urls_match(r.source_url, doc.source_url)]


def _needs_locator(row) -> bool:
    if row.source_page is None:
        return True
    return row.provenance_status in (None, "missing")


def merge_locators_from_text(db: Session, doc: SourceDocument, marked_text: str) -> Dict[str, int]:
    """Search source text for canonical rows still missing page-level locators."""
    counts = {"lexicon": 0, "rules": 0}
    file_id = doc.drive_file_id or parse_drive_file_id(doc.source_url or "")
    if not file_id or not (marked_text or "").strip():
        return counts

    rule_candidates = (
        db.query(CanonicalRule)
        .filter(CanonicalRule.source_url.isnot(None), CanonicalRule.source_url.contains(file_id))
        .all()
    )
    for row in rule_candidates:
        if not urls_match(row.source_url, doc.source_url) or not _needs_locator(row):
            continue
        prov = resolve_canonical_provenance(row.content, marked_text)
        if prov["source_page"] is None:
            continue
        row.source_document_id = doc.id
        row.source_page = prov["source_page"]
        row.source_page_end = prov["source_page_end"]
        row.source_excerpt = prov["source_excerpt"]
        row.source_chunk_index = prov["source_chunk_index"]
        row.provenance_status = prov["provenance_status"]
        counts["rules"] += 1

    lex_candidates = (
        db.query(CanonicalLexicon)
        .filter(CanonicalLexicon.source_url.isnot(None), CanonicalLexicon.source_url.contains(file_id))
        .all()
    )
    for row in lex_candidates:
        if not urls_match(row.source_url, doc.source_url) or not _needs_locator(row):
            continue
        prov = resolve_canonical_provenance(
            row.english or "",
            marked_text,
            woccon=row.woccon,
        )
        if prov["source_page"] is None and row.woccon:
            prov = resolve_canonical_provenance(row.woccon, marked_text)
        if prov["source_page"] is None:
            continue
        row.source_document_id = doc.id
        row.source_page = prov["source_page"]
        row.source_page_end = prov["source_page_end"]
        row.source_excerpt = prov["source_excerpt"]
        row.source_chunk_index = prov["source_chunk_index"]
        row.provenance_status = prov["provenance_status"]
        counts["lexicon"] += 1

    if counts["lexicon"] or counts["rules"]:
        db.commit()
    return counts


def _set_document_progress(db: Session, doc: SourceDocument, pct: int, message: str) -> None:
    doc.progress_pct = max(0, min(100, pct))
    doc.progress_message = message
    db.commit()


def process_document(
    db: Session,
    doc: SourceDocument,
    text: str,
    *,
    skip_llm: bool = False,
    merge_locators: bool = False,
    merge_only: bool = False,
    replace_pending: bool = False,
    progress_range: Tuple[int, int] = (0, 100),
) -> Dict[str, Any]:
    """Run extraction and insert pending rows (unless merge_only)."""
    import drive_extract

    counts = {"lexicon": 0, "rules": 0}
    locators_merged = {"lexicon": 0, "rules": 0}
    extracted_counts = {"lexicon": 0, "rules": 0}

    if not (text or "").strip():
        doc.status = "failed"
        doc.error_message = "No text extracted from document"
        doc.progress_pct = None
        doc.progress_message = None
        db.commit()
        return {"document_id": doc.id, "status": "failed", "counts": counts, "locators_merged": locators_merged}

    apply_bibliography_defaults(doc)
    _set_document_progress(db, doc, 0, "Starting extraction")

    if skip_llm:
        doc.status = "ready"
        doc.progress_pct = 100
        doc.progress_message = None
        db.commit()
        return {"document_id": doc.id, "status": "ready", "counts": counts, "locators_merged": locators_merged}

    if replace_pending:
        focus = getattr(doc, "extraction_focus", None) or "general"
        _clear_pending_for_focus(db, doc.id, focus)

    short_title = doc.short_title or doc.title
    prog_lo, prog_hi = progress_range

    def on_progress(pct: int, message: str) -> None:
        mapped = prog_lo + int((prog_hi - prog_lo) * max(0, min(100, pct)) / 100)
        _set_document_progress(db, doc, mapped, message)

    result = drive_extract.extract_one_file(
        text,
        doc.title,
        source_url=doc.source_url,
        file_id=doc.drive_file_id,
        short_title=short_title,
        marked_source_text=text,
        on_progress=on_progress,
        extraction_focus=getattr(doc, "extraction_focus", None) or "general",
        grammar_lineage=getattr(doc, "grammar_lineage", None),
    )

    _set_document_progress(db, doc, 92, "Resolving provenance")

    extracted_lexicon = []
    for e in result.get("lexicon_entries") or []:
        prov = resolve_lexicon_provenance(
            e,
            text,
            chunk_index=e.get("source_chunk_index"),
            chunk_page_start=e.get("_chunk_page_start"),
            chunk_page_end=e.get("_chunk_page_end"),
        )
        e = {**e, **prov}
        extracted_lexicon.append(e)

    extracted_counts["lexicon"] = len(extracted_lexicon)

    if merge_locators:
        for e in extracted_lexicon:
            key = (e.get("woccon") or "").strip().lower()
            if not key:
                continue
            for row in _canonical_lexicon_for_merge(db, doc, key):
                row.source_document_id = doc.id
                row.source_page = e.get("source_page")
                row.source_page_end = e.get("source_page_end")
                row.source_excerpt = e.get("source_excerpt")
                row.source_chunk_index = e.get("source_chunk_index")
                row.provenance_status = e.get("provenance_status")
                locators_merged["lexicon"] += 1
            if not merge_only:
                for row in db.query(PendingLexicon).filter(
                    PendingLexicon.source_document_id == doc.id,
                    PendingLexicon.woccon.ilike(key),
                ).all():
                    if row.status not in ("pending", "approved", "modified"):
                        continue
                    row.source_page = e.get("source_page")
                    row.source_page_end = e.get("source_page_end")
                    row.source_excerpt = e.get("source_excerpt")
                    row.source_chunk_index = e.get("source_chunk_index")
                    row.provenance_status = e.get("provenance_status")

    if not merge_only:
        for e in extracted_lexicon:
            w = (e.get("woccon") or "").strip()
            eng = (e.get("english") or "").strip()
            if not w or not eng:
                continue
            dup_id, dup_score, _ = find_lexicon_duplicate(db, w, eng)
            row = PendingLexicon(
                source_document_id=doc.id,
                woccon=w,
                english=eng,
                pos=(e.get("pos") or "unknown").strip(),
                pronunciation=(e.get("pronunciation") or None),
                source_url=result.get("source_url") or doc.source_url,
                status="pending",
                duplicate_of_id=dup_id,
                duplicate_score=dup_score,
                source_page=e.get("source_page"),
                source_page_end=e.get("source_page_end"),
                source_excerpt=e.get("source_excerpt"),
                source_chunk_index=e.get("source_chunk_index"),
                provenance_status=e.get("provenance_status"),
            )
            apply_lexicon_classification(row, w, eng, row.pos, "community_drive")
            if not getattr(doc, "is_vocab_base", False):
                apply_base_link_to_pending(row, db)
            db.add(row)
            counts["lexicon"] += 1

    category_lists = [
        ("grammar", result.get("grammar_notes") or []),
        ("pronunciation", result.get("pronunciation_notes") or []),
        ("cultural", result.get("cultural_notes") or []),
    ]
    for category, notes in category_lists:
        extracted_counts["rules"] += len(notes)
        for note in notes:
            content = _note_text(note)
            if not content:
                continue
            prov = resolve_note_provenance(
                note,
                text,
                chunk_index=note.get("source_chunk_index") if isinstance(note, dict) else None,
                chunk_page_start=note.get("_chunk_page_start") if isinstance(note, dict) else None,
                chunk_page_end=note.get("_chunk_page_end") if isinstance(note, dict) else None,
            )
            if merge_locators:
                norm = normalize_text(content)
                for row in _canonical_rules_for_merge(db, doc, category, norm):
                    row.source_document_id = doc.id
                    row.source_page = prov.get("source_page")
                    row.source_page_end = prov.get("source_page_end")
                    row.source_excerpt = prov.get("source_excerpt")
                    row.source_chunk_index = prov.get("source_chunk_index")
                    row.provenance_status = prov.get("provenance_status")
                    locators_merged["rules"] += 1

            if merge_only:
                continue

            dup_id, dup_score, _ = find_rule_duplicate(db, category, content)
            row = PendingRule(
                source_document_id=doc.id,
                category=category,
                content=content,
                source_url=result.get("source_url") or doc.source_url,
                status="pending",
                duplicate_of_id=dup_id,
                duplicate_score=dup_score,
                source_page=prov.get("source_page"),
                source_page_end=prov.get("source_page_end"),
                source_excerpt=prov.get("source_excerpt"),
                source_chunk_index=prov.get("source_chunk_index"),
                provenance_status=prov.get("provenance_status"),
            )
            apply_classification_to_rule(
                row,
                category,
                content,
                grammar_lineage=note.get("grammar_lineage") if isinstance(note, dict) else None,
            )
            db.add(row)
            counts["rules"] += 1

    doc.status = "ready"
    doc.error_message = None
    doc.progress_pct = 100
    doc.progress_message = None
    locators_from_text = {"lexicon": 0, "rules": 0}
    if merge_locators:
        locators_from_text = merge_locators_from_text(db, doc, text)
    db.commit()
    return {
        "document_id": doc.id,
        "status": "ready",
        "counts": counts,
        "locators_merged": locators_merged,
        "locators_from_text": locators_from_text,
        "extracted": extracted_counts,
    }


def reload_document_text(
    doc: SourceDocument,
    *,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> Tuple[str, Optional[str]]:
    """Re-read marked text from stored file or Drive."""
    if doc.local_path and os.path.isfile(doc.local_path):
        path = Path(doc.local_path)
        return extract_text_from_upload(path.name, path.read_bytes(), on_progress=on_progress)
    if doc.drive_file_id:
        text, _, method = fetch_drive_text(doc.drive_file_id, on_progress=on_progress)
        return text, method
    raise ValueError("No local file or Drive ID available for re-extract")


def run_ingest_background(
    doc_id: str,
    *,
    merge_locators: bool = False,
    replace_pending: bool = False,
) -> None:
    """Background worker: extract text (with OCR if needed) then run LLM extraction."""
    from panel_api.db import get_session_factory

    session = get_session_factory()()
    try:
        doc = session.get(SourceDocument, doc_id)
        if not doc:
            return

        def read_progress(pct: int, message: str) -> None:
            mapped = int(20 * max(0, min(100, pct)) / 100)
            _set_document_progress(session, doc, mapped, message)

        text, method = extract_text_from_document(doc, session, on_progress=read_progress)
        if method:
            doc.text_extraction_method = method
            session.commit()

        result = process_document(
            session,
            doc,
            text,
            merge_locators=merge_locators,
            replace_pending=replace_pending,
            progress_range=(20, 100),
        )
        return result
    except Exception as e:
        log.exception("Ingest failed for %s", doc_id)
        doc = session.get(SourceDocument, doc_id)
        if doc:
            doc.status = "failed"
            doc.error_message = str(e)
            doc.progress_pct = None
            doc.progress_message = None
            session.commit()
    finally:
        session.close()


def run_reextract_background(doc_id: str, user_id: str) -> None:
    """Background worker for admin re-extract."""
    from panel_api.db import AuditLog, get_session_factory

    session = get_session_factory()()
    try:
        doc = session.get(SourceDocument, doc_id)
        if not doc:
            return

        def read_progress(pct: int, message: str) -> None:
            mapped = int(20 * max(0, min(100, pct)) / 100)
            _set_document_progress(session, doc, mapped, message)

        text, method = reload_document_text(doc, on_progress=read_progress)
        if method:
            doc.text_extraction_method = method
            session.commit()

        result = process_document(
            session,
            doc,
            text,
            merge_locators=True,
            replace_pending=True,
            progress_range=(20, 100),
        )
        session.add(
            AuditLog(
                entity_type="source_document",
                entity_id=doc.id,
                action="reextract",
                user_id=user_id,
                payload_json=str(result),
            )
        )
        session.commit()
    except Exception as e:
        log.exception("Re-extract failed for %s", doc_id)
        doc = session.get(SourceDocument, doc_id)
        if doc:
            doc.status = "failed"
            doc.error_message = str(e)
            doc.progress_pct = None
            doc.progress_message = None
            session.commit()
    finally:
        session.close()
