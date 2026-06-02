"""Audit log helpers for panel mutations."""
import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from panel_api.db import AuditLog


def write_audit(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    user_id: Optional[str] = None,
    payload: Optional[Any] = None,
) -> None:
    db.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            user_id=user_id,
            payload_json=json.dumps(payload, default=str) if payload is not None else None,
        )
    )
