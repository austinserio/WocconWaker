from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from panel_api.db import AuditLog, PendingLexicon, PendingRule, SourceDocument, get_session_factory, init_db
from panel_api.deps import DbSession, RequireAdmin
from panel_api.schemas import AuditLogOut, BackfillCitationsResponse, CommitResponse, ReextractRequest, ReextractResponse, VocabBaseSyncResponse
from panel_api.extraction_config import validate_extraction_config
from panel_api.services.base_vocab import import_base_vocab
from panel_api.services.citation_backfill import backfill_from_citations
from panel_api.services.commit import commit_pending, export_unified_json, reload_assistant
from panel_api.services.ingest import reload_document_text, run_reextract_background

router = APIRouter(prefix="/admin", tags=["admin"])

_backfill_status: dict = {"running": False, "last_result": None}


def _run_backfill_citations(export: bool, user_id: str):
    global _backfill_status
    _backfill_status = {"running": True, "last_result": None}
    init_db()
    db = get_session_factory()()
    try:
        result = backfill_from_citations(db, dry_run=False)
        if export:
            result["export_paths"] = export_unified_json(db)
        db.add(
            AuditLog(
                entity_type="citation_backfill",
                entity_id="batch",
                action="backfill_citations",
                user_id=user_id,
                payload_json=str(result.get("sources_found")),
            )
        )
        db.commit()
        _backfill_status = {"running": False, "last_result": result}
    except Exception as e:
        _backfill_status = {"running": False, "last_result": {"error": str(e)}}
    finally:
        db.close()


@router.post("/vocab-base/sync", response_model=VocabBaseSyncResponse)
def sync_vocab_base(db: DbSession, admin: RequireAdmin):
    result = import_base_vocab(db)
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    db.add(
        AuditLog(
            entity_type="vocab_base",
            entity_id=result.get("document_id", "sync"),
            action="sync",
            user_id=admin.id,
            payload_json=str(result),
        )
    )
    db.commit()
    return VocabBaseSyncResponse(
        imported=result.get("imported", 0),
        updated=result.get("updated", 0),
        total=result.get("total", 0),
        document_id=result.get("document_id", ""),
        pronunciation=result.get("pronunciation"),
    )


@router.get("/commit/preview")
def commit_preview(db: DbSession, admin: RequireAdmin):
    lex = (
        db.query(PendingLexicon)
        .filter(PendingLexicon.status.in_(["approved", "modified"]))
        .count()
    )
    rules = (
        db.query(PendingRule).filter(PendingRule.status.in_(["approved", "modified"])).count()
    )
    return {"pending_lexicon": lex, "pending_rules": rules}


@router.post("/commit", response_model=CommitResponse)
def run_commit(request: Request, db: DbSession, admin: RequireAdmin):
    result = commit_pending(db)
    assistant = getattr(request.app.state, "assistant", None)
    if assistant:
        result["reload_summary"] = reload_assistant(assistant, db=db)
    db.add(
        AuditLog(
            entity_type="commit",
            entity_id="batch",
            action="commit",
            user_id=admin.id,
            payload_json=str(result.get("export_paths")),
        )
    )
    db.commit()
    return CommitResponse(**result)


@router.post("/documents/{doc_id}/reextract", response_model=ReextractResponse)
def reextract_document(
    doc_id: str,
    body: ReextractRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    admin: RequireAdmin,
):
    doc = db.get(SourceDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        reload_document_text(doc)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        focus, lineage = validate_extraction_config(
            body.extraction_focus or getattr(doc, "extraction_focus", None) or "general",
            body.grammar_lineage if body.grammar_lineage is not None else getattr(doc, "grammar_lineage", None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    doc.extraction_focus = focus
    doc.grammar_lineage = lineage
    doc.status = "processing"
    doc.progress_pct = 0
    doc.progress_message = "Starting re-extract"
    doc.error_message = None
    db.commit()
    background_tasks.add_task(run_reextract_background, doc.id, admin.id)
    return ReextractResponse(
        document_id=doc.id,
        status="processing",
        counts={},
        locators_merged={},
    )


@router.post("/backfill-citations", response_model=BackfillCitationsResponse)
def backfill_citations(
    background_tasks: BackgroundTasks,
    db: DbSession,
    admin: RequireAdmin,
    dry_run: bool = False,
    export: bool = False,
):
    if dry_run:
        result = backfill_from_citations(db, dry_run=True)
        return BackfillCitationsResponse(**result)
    if _backfill_status.get("running"):
        raise HTTPException(status_code=409, detail="Citation backfill already running")
    background_tasks.add_task(_run_backfill_citations, export, admin.id)
    sources = backfill_from_citations(db, dry_run=True)
    return BackfillCitationsResponse(
        sources_found=sources["sources_found"],
        dry_run=False,
        results=[{"status": "started", "sources_found": sources["sources_found"]}],
    )


@router.get("/backfill-citations/status")
def backfill_citations_status(admin: RequireAdmin):
    return _backfill_status


@router.get("/audit", response_model=list[AuditLogOut])
def list_audit(db: DbSession, admin: RequireAdmin, limit: int = 100):
    from panel_api.db import User
    from panel_api.user_display import user_display_name

    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    user_ids = {r.user_id for r in rows if r.user_id}
    users_by_id = {}
    if user_ids:
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            users_by_id[u.id] = u
    out = []
    for r in rows:
        data = AuditLogOut.model_validate(r).model_dump()
        u = users_by_id.get(r.user_id) if r.user_id else None
        data["user_display"] = user_display_name(u) if u else None
        out.append(AuditLogOut(**data))
    return out
