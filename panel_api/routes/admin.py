from fastapi import APIRouter, Request

from panel_api.db import AuditLog, PendingLexicon, PendingRule
from panel_api.deps import DbSession, RequireAdmin
from panel_api.schemas import AuditLogOut, CommitResponse
from panel_api.services.commit import commit_pending, reload_assistant

router = APIRouter(prefix="/admin", tags=["admin"])


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
        result["reload_summary"] = reload_assistant(assistant)
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


@router.get("/audit", response_model=list[AuditLogOut])
def list_audit(db: DbSession, admin: RequireAdmin, limit: int = 100):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [AuditLogOut.model_validate(r) for r in rows]
