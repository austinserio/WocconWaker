import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from panel_api.db import SourceDocument
from panel_api.deps import CurrentUser, DbSession, RequireReviewer
from panel_api.schemas import DriveLinkRequest, SourceDocumentOut
from panel_api.services.ingest import (
    extract_text_from_upload,
    fetch_drive_text,
    parse_drive_file_id,
    process_document,
    save_upload_file,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _doc_out(doc: SourceDocument, counts: Optional[dict] = None) -> SourceDocumentOut:
    out = SourceDocumentOut.model_validate(doc)
    out.counts = counts
    return out


def _run_ingest(doc_id: str, text: str):
    from panel_api.db import get_session_factory

    session = get_session_factory()()
    try:
        doc = session.get(SourceDocument, doc_id)
        if doc:
            process_document(session, doc, text)
    finally:
        session.close()


@router.post("", response_model=SourceDocumentOut)
async def create_document(
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: RequireReviewer,
    file: Optional[UploadFile] = File(None),
    drive_url: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
):
    if file:
        data = await file.read()
        filename = file.filename or "upload"
        try:
            text = extract_text_from_upload(filename, data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        local_path = save_upload_file(data, filename)
        doc = SourceDocument(
            title=title or filename,
            source_type="upload",
            mime_type=file.content_type,
            local_path=local_path,
            status="processing",
            uploaded_by=user.id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        background_tasks.add_task(_run_ingest, doc.id, text)
        return _doc_out(doc)

    if drive_url:
        file_id = parse_drive_file_id(drive_url)
        if not file_id:
            raise HTTPException(status_code=400, detail="Could not parse Drive file ID from URL")
        try:
            text, name = fetch_drive_text(file_id)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Drive fetch failed: {e}")
        from drive_extract import _source_url

        doc = SourceDocument(
            title=title or name,
            source_type="drive_link",
            source_url=_source_url(file_id),
            drive_file_id=file_id,
            status="processing",
            uploaded_by=user.id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        background_tasks.add_task(_run_ingest, doc.id, text)
        return _doc_out(doc)

    raise HTTPException(status_code=400, detail="Provide file upload or drive_url")


@router.post("/link", response_model=SourceDocumentOut)
async def create_from_link(
    body: DriveLinkRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: RequireReviewer,
):
    file_id = parse_drive_file_id(body.drive_url)
    if not file_id:
        raise HTTPException(status_code=400, detail="Could not parse Drive file ID")
    try:
        text, name = fetch_drive_text(file_id)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Drive fetch failed: {e}")
    from drive_extract import _source_url

    doc = SourceDocument(
        title=body.title or name,
        source_type="drive_link",
        source_url=_source_url(file_id),
        drive_file_id=file_id,
        status="processing",
        uploaded_by=user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    background_tasks.add_task(_run_ingest, doc.id, text)
    return _doc_out(doc)


@router.get("", response_model=list[SourceDocumentOut])
def list_documents(db: DbSession, user: CurrentUser):
    docs = db.query(SourceDocument).order_by(SourceDocument.created_at.desc()).all()
    return [_doc_out(d) for d in docs]


@router.get("/{doc_id}", response_model=SourceDocumentOut)
def get_document(doc_id: str, db: DbSession, user: CurrentUser):
    doc = db.get(SourceDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_out(doc)


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
