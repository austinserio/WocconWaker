"""Document upload, text extraction, LLM extract, pending rows."""
import io
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from panel_api.config import get_settings
from panel_api.db import PendingLexicon, PendingRule, SourceDocument
from panel_api.services.duplicates import find_lexicon_duplicate, find_rule_duplicate, normalize_text
from panel_api.services.lexicon_classifier import apply_lexicon_classification
from panel_api.services.rule_classifier import apply_classification_to_rule

log = logging.getLogger("panel_ingest")

DRIVE_FILE_ID_RE = re.compile(r"/file/d/([a-zA-Z0-9_-]+)")
DRIVE_OPEN_RE = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")


def parse_drive_file_id(url: str) -> Optional[str]:
    if not url:
        return None
    m = DRIVE_FILE_ID_RE.search(url)
    if m:
        return m.group(1)
    m = DRIVE_OPEN_RE.search(url)
    if m:
        return m.group(1)
    return None


def extract_text_from_pdf_bytes(data: bytes) -> str:
    import pdfplumber

    buf = io.BytesIO(data)
    parts = []
    with pdfplumber.open(buf) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n\n".join(parts)


def extract_text_from_docx_bytes(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def fetch_drive_text(file_id: str) -> Tuple[str, str]:
    import drive_ingest

    creds = drive_ingest._get_credentials()
    service = drive_ingest._build_drive_service(creds)
    meta = service.files().get(fileId=file_id, fields="mimeType,name").execute()
    mime = meta.get("mimeType", "")
    name = meta.get("name", "drive_document")
    if mime == drive_ingest.GOOGLE_DOCS_MIME:
        text = drive_ingest.fetch_doc_text(service, file_id)
    elif mime == drive_ingest.PDF_MIME:
        text = drive_ingest.fetch_pdf_text(service, file_id)
    else:
        raise ValueError(f"Unsupported Drive mime type: {mime}")
    url = drive_ingest.DRIVE_FILE_URL_TEMPLATE.format(file_id=file_id) if hasattr(
        drive_ingest, "DRIVE_FILE_URL_TEMPLATE"
    ) else f"https://drive.google.com/file/d/{file_id}/view"
    try:
        from drive_extract import _source_url

        url = _source_url(file_id)
    except ImportError:
        pass
    return text, name


def save_upload_file(data: bytes, filename: str) -> str:
    settings = get_settings()
    os.makedirs(settings.woccon_upload_dir, exist_ok=True)
    safe = re.sub(r'[<>:"|?*\r\n\\/]', "_", filename)[:200]
    dest = os.path.join(settings.woccon_upload_dir, f"{uuid.uuid4().hex}_{safe}")
    with open(dest, "wb") as f:
        f.write(data)
    return dest


def process_document(
    db: Session,
    doc: SourceDocument,
    text: str,
    *,
    skip_llm: bool = False,
) -> Dict[str, Any]:
    """Run extraction and insert pending rows."""
    import drive_extract

    counts = {"lexicon": 0, "rules": 0}
    if not (text or "").strip():
        doc.status = "failed"
        doc.error_message = "No text extracted from document"
        db.commit()
        return {"document_id": doc.id, "status": "failed", "counts": counts}

    if skip_llm:
        doc.status = "ready"
        db.commit()
        return {"document_id": doc.id, "status": "ready", "counts": counts}

    result = drive_extract.extract_one_file(
        text,
        doc.title,
        source_url=doc.source_url,
        file_id=doc.drive_file_id,
    )

    for e in result.get("lexicon_entries") or []:
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
        )
        apply_lexicon_classification(row, w, eng, row.pos, "community_drive")
        db.add(row)
        counts["lexicon"] += 1

    category_lists = [
        ("grammar", result.get("grammar_notes") or []),
        ("pronunciation", result.get("pronunciation_notes") or []),
        ("cultural", result.get("cultural_notes") or []),
    ]
    for category, notes in category_lists:
        for note in notes:
            content = (note if isinstance(note, str) else str(note)).strip()
            if not content:
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
            )
            apply_classification_to_rule(row, category, content)
            db.add(row)
            counts["rules"] += 1

    doc.status = "ready"
    doc.error_message = None
    db.commit()
    return {"document_id": doc.id, "status": "ready", "counts": counts}


def extract_text_from_upload(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return extract_text_from_pdf_bytes(data)
    if lower.endswith(".txt"):
        return data.decode("utf-8", errors="replace")
    if lower.endswith(".docx"):
        return extract_text_from_docx_bytes(data)
    raise ValueError(f"Unsupported file type: {filename}")
