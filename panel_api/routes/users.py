"""Admin user and invitation management."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from panel_api.db import User, UserInvitation
from panel_api.deps import DbSession, RequireAdmin
from panel_api.schemas import (
    UserInviteCreate,
    UserInviteOut,
    UserOut,
    UserRolePatch,
    UsersListResponse,
)
from panel_api.services.audit import write_audit
from panel_api.services.email import email_configured, panel_link, send_invite_email
from panel_api.services.tokens import generate_token
from panel_api.user_display import user_to_out
from panel_api.config import get_settings

router = APIRouter(prefix="/users", tags=["users"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _users_list_meta() -> dict:
    settings = get_settings()
    configured = email_configured()
    return {
        "email_mode": "smtp" if configured else settings.email_mode,
        "email_delivery_configured": configured,
    }


def _invite_out(inv: UserInvitation, raw_token: str | None = None) -> UserInviteOut:
    data = UserInviteOut.model_validate(inv).model_dump()
    if raw_token and not email_configured():
        data["invite_url"] = panel_link(f"/accept-invite?token={raw_token}")
    return UserInviteOut(**data)


@router.get("", response_model=UsersListResponse)
def list_users(db: DbSession, admin: RequireAdmin):
    users = db.query(User).order_by(User.created_at).all()
    invites = (
        db.query(UserInvitation)
        .filter(UserInvitation.accepted_at.is_(None))
        .order_by(UserInvitation.created_at.desc())
        .all()
    )
    return UsersListResponse(
        users=[user_to_out(u) for u in users],
        invitations=[UserInviteOut.model_validate(i) for i in invites],
        **_users_list_meta(),
    )


@router.post("/invite", response_model=UserInviteOut)
def invite_user(body: UserInviteCreate, db: DbSession, admin: RequireAdmin):
    email = _normalize_email(body.email)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="User already exists")
    pending = (
        db.query(UserInvitation)
        .filter(UserInvitation.email == email, UserInvitation.accepted_at.is_(None))
        .first()
    )
    if pending:
        raise HTTPException(status_code=400, detail="Invitation already pending for this email")

    settings = get_settings()
    raw, token_hash = generate_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.invite_expire_hours)
    inv = UserInvitation(
        email=email,
        role=body.role,
        token_hash=token_hash,
        invited_by=admin.id,
        expires_at=expires,
    )
    db.add(inv)
    db.flush()

    try:
        send_invite_email(to_email=email, role=body.role, raw_token=raw)
    except RuntimeError as e:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(e)) from e

    write_audit(
        db,
        entity_type="user_invitation",
        entity_id=inv.id,
        action="invite",
        user_id=admin.id,
        payload={"email": email, "role": body.role},
    )
    db.commit()
    db.refresh(inv)
    return _invite_out(inv, raw)


@router.post("/invitations/{invitation_id}/resend", response_model=UserInviteOut)
def resend_invitation(invitation_id: str, db: DbSession, admin: RequireAdmin):
    inv = db.get(UserInvitation, invitation_id)
    if not inv or inv.accepted_at:
        raise HTTPException(status_code=404, detail="Invitation not found")
    settings = get_settings()
    raw, token_hash = generate_token()
    inv.token_hash = token_hash
    inv.expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.invite_expire_hours)
    try:
        send_invite_email(to_email=inv.email, role=inv.role, raw_token=raw)
    except RuntimeError as e:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(e)) from e
    write_audit(
        db,
        entity_type="user_invitation",
        entity_id=inv.id,
        action="resend_invite",
        user_id=admin.id,
    )
    db.commit()
    db.refresh(inv)
    return _invite_out(inv, raw)


@router.delete("/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: str, db: DbSession, admin: RequireAdmin):
    inv = db.get(UserInvitation, invitation_id)
    if not inv or inv.accepted_at:
        raise HTTPException(status_code=404, detail="Invitation not found")
    write_audit(
        db,
        entity_type="user_invitation",
        entity_id=inv.id,
        action="revoke_invite",
        user_id=admin.id,
        payload={"email": inv.email},
    )
    db.delete(inv)
    db.commit()


@router.patch("/{user_id}", response_model=UserOut)
def patch_user(user_id: str, body: UserRolePatch, db: DbSession, admin: RequireAdmin):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and body.role != "admin":
        raise HTTPException(status_code=400, detail="Cannot change your own admin role")
    if user.role == "admin" and body.role != "admin":
        other_admins = (
            db.query(User)
            .filter(User.role == "admin", User.is_active == True, User.id != user.id)
            .count()
        )
        if other_admins < 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last active admin")
    old_role = user.role
    user.role = body.role
    write_audit(
        db,
        entity_type="user",
        entity_id=user.id,
        action="change_role",
        user_id=admin.id,
        payload={"from": old_role, "to": body.role},
    )
    db.commit()
    db.refresh(user)
    return user_to_out(user)


@router.delete("/{user_id}", status_code=204)
def deactivate_user(user_id: str, db: DbSession, admin: RequireAdmin):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    if user.role == "admin":
        other_admins = (
            db.query(User)
            .filter(User.role == "admin", User.is_active == True, User.id != user.id)
            .count()
        )
        if other_admins < 1:
            raise HTTPException(status_code=400, detail="Cannot deactivate the last active admin")
    user.is_active = False
    write_audit(
        db,
        entity_type="user",
        entity_id=user.id,
        action="deactivate",
        user_id=admin.id,
    )
    db.commit()
