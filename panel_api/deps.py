"""FastAPI dependencies."""
from typing import Annotated, Callable, List

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from panel_api.auth import decode_token
from panel_api.db import User, get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

ROLE_ORDER = {"member": 0, "worker": 1, "admin": 2}
# Legacy slugs from before migration 009
_ROLE_ALIASES = {"viewer": "member", "reviewer": "worker"}


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(User, payload["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account deactivated")
    return user


def _role_level(role: str) -> int:
    slug = _ROLE_ALIASES.get(role, role)
    return ROLE_ORDER.get(slug, -1)


def require_role(min_role: str) -> Callable:
    def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if _role_level(user.role) < _role_level(min_role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _dep


def get_optional_user(
    token: Annotated[str | None, Depends(oauth2_scheme_optional)],
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    if not token:
        return None
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        return None
    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        return None
    return user


RequireWorker = Annotated[User, Depends(require_role("worker"))]
RequireAdmin = Annotated[User, Depends(require_role("admin"))]
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
DbSession = Annotated[Session, Depends(get_db)]
