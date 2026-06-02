from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from panel_api.auth import create_access_token, hash_password, verify_password
from panel_api.config import get_settings
from panel_api.db import PasswordResetToken, User, UserInvitation, get_db
from panel_api.deps import CurrentUser, DbSession
from panel_api.schemas import (
    ForgotPasswordRequest,
    InviteAcceptRequest,
    InvitePreviewOut,
    LoginRequest,
    MessageResponse,
    ProfilePatchRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from panel_api.services.email import send_password_reset_email
from panel_api.services.tokens import generate_token, hash_token
from panel_api.user_display import user_to_out

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _authenticate(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == _normalize_email(email)).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account deactivated")
    return user


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, user=user_to_out(user))


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = _authenticate(db, form.username, form.password)
    return _token_response(user)


@router.post("/login/json", response_model=TokenResponse)
def login_json(body: LoginRequest, db: Session = Depends(get_db)):
    user = _authenticate(db, body.email, body.password)
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user_to_out(user)


@router.patch("/me")
def patch_me(body: ProfilePatchRequest, db: DbSession, user: CurrentUser):
    if body.first_name is not None:
        user.first_name = body.first_name.strip() or None
    if body.last_name is not None:
        user.last_name = body.last_name.strip() or None
    db.commit()
    db.refresh(user)
    return user_to_out(user)


def _find_valid_invitation(db: Session, raw_token: str) -> UserInvitation | None:
    now = datetime.now(timezone.utc)
    th = hash_token(raw_token)
    inv = (
        db.query(UserInvitation)
        .filter(
            UserInvitation.token_hash == th,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.expires_at > now,
        )
        .first()
    )
    return inv


@router.get("/invite", response_model=InvitePreviewOut)
def preview_invite(token: str = Query(...), db: Session = Depends(get_db)):
    inv = _find_valid_invitation(db, token)
    if inv:
        return InvitePreviewOut(email=inv.email, role=inv.role)
    raise HTTPException(status_code=400, detail="Invalid or expired invitation")


@router.post("/accept-invite", response_model=TokenResponse)
def accept_invite(body: InviteAcceptRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    inv = _find_valid_invitation(db, body.token)
    if not inv:
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")
    email = _normalize_email(inv.email)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Account already exists")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        role=inv.role,
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        is_active=True,
    )
    db.add(user)
    inv.accepted_at = now
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = _normalize_email(body.email)
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if user:
        settings = get_settings()
        raw, token_hash = generate_token()
        expires = datetime.now(timezone.utc) + timedelta(hours=settings.password_reset_expire_hours)
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires,
            )
        )
        db.commit()
        try:
            send_password_reset_email(to_email=user.email, raw_token=raw)
        except RuntimeError:
            pass
    return MessageResponse(detail="If an account exists for that email, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    th = hash_token(body.token)
    matched = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == th,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .first()
    )
    if not matched:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    user = db.get(User, matched.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    user.password_hash = hash_password(body.password)
    matched.used_at = now
    db.commit()
    return MessageResponse(detail="Password updated. You can sign in now.")
