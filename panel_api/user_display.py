"""Display names for users in API responses and audit log."""
from panel_api.db import User
from panel_api.schemas import UserOut

_ROLE_ALIASES = {"viewer": "member", "reviewer": "worker"}


def user_display_name(user: User | None) -> str | None:
    if not user:
        return None
    parts = [p for p in (user.first_name, user.last_name) if p]
    name = " ".join(parts).strip()
    return name or user.email


def user_to_out(user: User) -> UserOut:
    role = _ROLE_ALIASES.get(user.role, user.role)
    return UserOut(
        id=user.id,
        email=user.email,
        role=role,
        first_name=user.first_name,
        last_name=user.last_name,
        display_name=user_display_name(user) or user.email,
        is_active=user.is_active,
        created_at=user.created_at,
    )
