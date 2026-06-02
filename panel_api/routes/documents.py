import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from panel_api.db import CanonicalLexicon, CanonicalRule, PendingLexicon, PendingRule, SourceDocument
from panel_api.deps import CurrentUser, DbSession, RequireWorker
from panel_api.extraction_config import validate_extraction_config
from panel_api.schemas import DriveLinkRequest, MergedSourceOut, SourceDocumentOut, SourceDocumentPatch
from panel_api.services.document_groups import (
    WORK_GROUPS,
    merge_extraction_counts,
    pick_primary_document,
    work_group_for_document,
)
from panel_api.services.ingest import (
    apply_bibliography_defaults,
    fetch_drive_meta,
    file_content_hash,
    find_existing_document,
    parse_drive_file_id,
    restart_document_for_reingest,
    run_ingest_background,
    save_upload_file,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _extraction_counts(db: Session, doc_id: str) -> dict:
    """Pending + committed items per extraction category for library badges."""
    pending_statuses = ("pending", "modified")
    vocabulary = (
        db.query(PendingLexicon)
        .filter(
            PendingLexicon.source_document_id == doc_id,
            PendingLexicon.status.in_(pending_statuses),
        )
        .count()
        + db.query(CanonicalLexicon)
        .filter(CanonicalLexicon.source_document_id == doc_id)
        .count()
    )
    counts = {"vocabulary": vocabulary}
    for category in ("grammar", "pronunciation", "cultural"):
        key = "cultural" if category == "cultural" else category
        counts[key] = (
            db.query(PendingRule)
            .filter(
                PendingRule.source_document_id == doc_id,
                PendingRule.category == category,
                PendingRule.status.in_(pending_statuses),
            )
            .count()
            + db.query(CanonicalRule)
            .filter(
                CanonicalRule.source_document_id == doc_id,
                CanonicalRule.category == category,
            )
            .count()
        )
    return counts


def _doc_counts(db: Session, doc: SourceDocument) -> Optional[dict]:
    if doc.is_vocab_base:
        base_entries = (
            db.query(CanonicalLexicon).filter(CanonicalLexicon.is_base_entry.is_(True)).count()
        )
        variants = (
            db.query(CanonicalLexicon)
            .filter(
                CanonicalLexicon.is_base_entry.is_(False),
                CanonicalLexicon.base_entry_id.isnot(None),
            )
            .count()
        )
        unmatched = (
            db.query(PendingLexicon)
            .filter(
                PendingLexicon.status.in_(["pending", "modified"]),
                PendingLexicon.match_status == "unmatched",
            )
            .count()
        )
        return {
            "base_entries": base_entries,
            "variants_from_other_sources": variants,
            "unmatched_pending": unmatched,
            "extracted": _extraction_counts(db, doc.id),
        }
    counts: dict = {"extracted": _extraction_counts(db, doc.id)}
    if doc.drive_file_id or doc.source_url:
        variants = (
            db.query(CanonicalLexicon)
            .filter(
                CanonicalLexicon.source_document_id == doc.id,
                CanonicalLexicon.is_base_entry.is_(False),
            )
            .count()
        )
        if variants:
            counts["variants_linked"] = variants
    return counts if counts.get("extracted") or counts.get("variants_linked") else None


def _doc_out(doc: SourceDocument, db: Session, counts: Optional[dict] = None) -> SourceDocumentOut:
    out = SourceDocumentOut.model_validate(doc)
    out.counts = counts if counts is not None else _doc_counts(db, doc)
    return out


def _validate_extraction_config(focus: Optional[str], lineage: Optional[str]) -> tuple[str, Optional[str]]:
    try:
        return validate_extraction_config(focus, lineage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _run_ingest(doc_id: str, *, merge_locators: bool = False, replace_pending: bool = False):
    run_ingest_background(doc_id, merge_locators=merge_locators, replace_pending=replace_pending)


def _dedupe_library_documents(docs: list[SourceDocument]) -> list[SourceDocument]:
    """Hide duplicate rows when the same Drive file or upload was ingested more than once."""
    pinned: list[SourceDocument] = []
    by_key: dict[str, SourceDocument] = {}
    no_key: list[SourceDocument] = []

    for doc in docs:
        if doc.is_vocab_base or doc.is_seed:
            pinned.append(doc)
            continue
        key = None
        if doc.drive_file_id:
            key = f"drive:{doc.drive_file_id}"
        elif getattr(doc, "content_hash", None):
            key = f"hash:{doc.content_hash}"
        if key:
            prev = by_key.get(key)
            if prev is None or (doc.created_at and prev.created_at and doc.created_at > prev.created_at):
                by_key[key] = doc
        else:
            no_key.append(doc)

    return pinned + list(by_key.values()) + no_key


def _to_merged_source(out: SourceDocumentOut) -> MergedSourceOut:
    return MergedSourceOut.model_validate(out.model_dump())


def _group_library_outputs(docs: list[SourceDocument], db: Session) -> list[SourceDocumentOut]:
    """Fold alternate scans of the same work under one primary library card."""
    from collections import defaultdict

    buckets: dict[str, list[SourceDocument]] = defaultdict(list)
    ungrouped: list[SourceDocument] = []

    for doc in docs:
        if doc.is_vocab_base or doc.is_seed:
            ungrouped.append(doc)
            continue
        group = work_group_for_document(doc)
        if group:
            buckets[group.key].append(doc)
        else:
            ungrouped.append(doc)

    group_by_key = {g.key: g for g in WORK_GROUPS}
    group_labels = {g.key: g.label for g in WORK_GROUPS}

    results: list[SourceDocumentOut] = []
    for key, members in buckets.items():
        group = group_by_key[key]
        primary_doc = pick_primary_document(members, group)
        primary_out = _doc_out(primary_doc, db)
        alternates = sorted(
            (d for d in members if d.id != primary_doc.id),
            key=lambda d: (d.title or "").lower(),
        )
        alt_outs = [_doc_out(d, db) for d in alternates]
        primary_out.counts = merge_extraction_counts([primary_out.counts] + [a.counts for a in alt_outs]) or primary_out.counts
        primary_out.work_group_key = key
        primary_out.work_group_label = group_labels.get(key)
        primary_out.merged_sources = [_to_merged_source(a) for a in alt_outs]
        results.append(primary_out)

    for doc in ungrouped:
        results.append(_doc_out(doc, db))

    return results


def _library_sort_key(out: SourceDocumentOut) -> tuple:
    tier = (
        0
        if out.is_vocab_base
        else 1
        if out.source_type == "pronunciation_guide"
        else 2
        if out.is_seed
        else 3
    )
    group_rank = 0
    for g in WORK_GROUPS:
        if g.key == out.work_group_key:
            group_rank = -g.sort_priority
            break
    created = -(out.created_at.timestamp() if out.created_at else 0)
    return (tier, group_rank, created)


def _is_no_text_failure(doc: SourceDocument) -> bool:
    if doc.status != "failed":
        return False
    msg = (doc.error_message or "").lower()
    return "no text extracted" in msg


def _delete_source_document(db: Session, doc: SourceDocument) -> None:
    """Remove a failed document and its pending rows; detach canonical citations."""
    if doc.is_vocab_base or doc.is_seed:
        raise HTTPException(status_code=403, detail="Protected documents cannot be deleted")
    if not _is_no_text_failure(doc):
        raise HTTPException(
            status_code=400,
            detail="Only failed documents with no extractable text can be deleted",
        )

    db.query(PendingLexicon).filter(PendingLexicon.source_document_id == doc.id).delete(
        synchronize_session=False
    )
    db.query(PendingRule).filter(PendingRule.source_document_id == doc.id).delete(
        synchronize_session=False
    )
    for row in db.query(CanonicalLexicon).filter(CanonicalLexicon.source_document_id == doc.id):
        row.source_document_id = None
    for row in db.query(CanonicalRule).filter(CanonicalRule.source_document_id == doc.id):
        row.source_document_id = None

    local_path = doc.local_path
    db.delete(doc)
    db.commit()

    if local_path and os.path.isfile(local_path):
        try:
            os.remove(local_path)
        except OSError:
            pass


@router.post("", response_model=SourceDocumentOut)
async def create_document(
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: RequireWorker,
    file: Optional[UploadFile] = File(None),
    drive_url: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    extraction_focus: Optional[str] = Form("general"),
    grammar_lineage: Optional[str] = Form(None),
):
    focus, lineage = _validate_extraction_config(extraction_focus, grammar_lineage)
    if file:
        data = await file.read()
        filename = file.filename or "upload"
        if not filename.lower().endswith((".pdf", ".txt", ".docx")):
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")
        content_hash = file_content_hash(data)
        existing = find_existing_document(db, content_hash=content_hash)
        if existing:
            restart_document_for_reingest(
                db,
                existing,
                user_id=user.id,
                extraction_focus=focus,
                grammar_lineage=lineage,
                title=title or filename,
            )
            local_path = save_upload_file(data, filename)
            existing.local_path = local_path
            db.commit()
            background_tasks.add_task(_run_ingest, existing.id, replace_pending=True)
            return _doc_out(existing, db)

        local_path = save_upload_file(data, filename)
        doc = SourceDocument(
            title=title or filename,
            source_type="upload",
            mime_type=file.content_type,
            local_path=local_path,
            content_hash=content_hash,
            status="processing",
            progress_pct=0,
            progress_message="Reading document…",
            uploaded_by=user.id,
            extraction_focus=focus,
            grammar_lineage=lineage,
        )
        apply_bibliography_defaults(doc)
        db.add(doc)
        db.commit()
        db.refresh(doc)
        background_tasks.add_task(_run_ingest, doc.id)
        return _doc_out(doc, db)

    if drive_url:
        file_id = parse_drive_file_id(drive_url)
        if not file_id:
            raise HTTPException(status_code=400, detail="Could not parse Drive file ID from URL")
        try:
            name, mime = fetch_drive_meta(file_id)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Drive fetch failed: {e}")
        import drive_ingest

        if mime not in (drive_ingest.GOOGLE_DOCS_MIME, drive_ingest.PDF_MIME):
            raise HTTPException(status_code=400, detail=f"Unsupported Drive mime type: {mime}")
        from drive_extract import _source_url

        existing = find_existing_document(db, drive_file_id=file_id)
        if existing:
            restart_document_for_reingest(
                db,
                existing,
                user_id=user.id,
                extraction_focus=focus,
                grammar_lineage=lineage,
                title=title or name,
            )
            background_tasks.add_task(_run_ingest, existing.id, replace_pending=True)
            return _doc_out(existing, db)

        doc = SourceDocument(
            title=title or name,
            source_type="drive_link",
            source_url=_source_url(file_id),
            drive_file_id=file_id,
            mime_type=mime,
            status="processing",
            progress_pct=0,
            progress_message="Reading document…",
            uploaded_by=user.id,
            extraction_focus=focus,
            grammar_lineage=lineage,
        )
        apply_bibliography_defaults(doc)
        db.add(doc)
        db.commit()
        db.refresh(doc)
        background_tasks.add_task(_run_ingest, doc.id)
        return _doc_out(doc, db)

    raise HTTPException(status_code=400, detail="Provide file upload or drive_url")


@router.post("/link", response_model=SourceDocumentOut)
async def create_from_link(
    body: DriveLinkRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: RequireWorker,
):
    focus, lineage = _validate_extraction_config(body.extraction_focus, body.grammar_lineage)
    file_id = parse_drive_file_id(body.drive_url)
    if not file_id:
        raise HTTPException(status_code=400, detail="Could not parse Drive file ID")
    try:
        name, mime = fetch_drive_meta(file_id)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Drive fetch failed: {e}")
    import drive_ingest

    if mime not in (drive_ingest.GOOGLE_DOCS_MIME, drive_ingest.PDF_MIME):
        raise HTTPException(status_code=400, detail=f"Unsupported Drive mime type: {mime}")
    from drive_extract import _source_url

    existing = find_existing_document(db, drive_file_id=file_id)
    if existing:
        restart_document_for_reingest(
            db,
            existing,
            user_id=user.id,
            extraction_focus=focus,
            grammar_lineage=lineage,
            title=body.title or name,
        )
        background_tasks.add_task(_run_ingest, existing.id, replace_pending=True)
        return _doc_out(existing, db)

    doc = SourceDocument(
        title=body.title or name,
        source_type="drive_link",
        source_url=_source_url(file_id),
        drive_file_id=file_id,
        mime_type=mime,
        status="processing",
        progress_pct=0,
        progress_message="Reading document…",
        uploaded_by=user.id,
        extraction_focus=focus,
        grammar_lineage=lineage,
    )
    apply_bibliography_defaults(doc)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    background_tasks.add_task(_run_ingest, doc.id)
    return _doc_out(doc, db)


@router.get("", response_model=list[SourceDocumentOut])
def list_documents(db: DbSession, user: CurrentUser):
    docs = _dedupe_library_documents(db.query(SourceDocument).all())
    out = _group_library_outputs(docs, db)
    out.sort(key=_library_sort_key)
    return out


@router.get("/{doc_id}", response_model=SourceDocumentOut)
def get_document(doc_id: str, db: DbSession, user: CurrentUser):
    doc = db.get(SourceDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_out(doc, db)


@router.patch("/{doc_id}", response_model=SourceDocumentOut)
def patch_document(doc_id: str, body: SourceDocumentPatch, db: DbSession, user: RequireWorker):
    doc = db.get(SourceDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(doc, k, v)
    db.commit()
    db.refresh(doc)
    return _doc_out(doc, db)


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, db: DbSession, user: RequireWorker):
    doc = db.get(SourceDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    _delete_source_document(db, doc)


@router.get("/{doc_id}/file")
def get_document_file(doc_id: str, db: DbSession, user: CurrentUser):
    doc = db.get(SourceDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.source_url and not doc.local_path:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url=doc.source_url)
    if not doc.local_path or not os.path.isfile(doc.local_path):
        raise HTTPException(status_code=404, detail="File not available locally")
    return FileResponse(doc.local_path, filename=doc.title)
