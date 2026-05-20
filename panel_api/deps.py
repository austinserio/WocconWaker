"""FastAPI dependencies."""
from typing import Annotated, Callable, List

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from panel_api.auth import decode_token
from panel_api.db import User, get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

ROLE_ORDER = {"viewer": 0, "reviewer": 1, "admin": 2}


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
    return user


def require_role(min_role: str) -> Callable:
    def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if ROLE_ORDER.get(user.role, -1) < ROLE_ORDER.get(min_role, 99):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _dep


RequireReviewer = Annotated[User, Depends(require_role("reviewer"))]
RequireAdmin = Annotated[User, Depends(require_role("admin"))]
CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
