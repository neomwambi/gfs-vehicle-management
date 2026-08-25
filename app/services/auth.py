"""Mock authentication / session service.

Replace this module with Standard Bank employee SSO / Azure Entra ID later.
The login page already exposes a "Login with SSO" placeholder for that cutover.
Manager and Admin share the same portal permissions.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import SESSION_HEADER
from app.database import get_db
from app.models.models import User

# In-memory sessions for the prototype: token -> UserID
_SESSIONS: dict[str, int] = {}


@dataclass
class AuthUser:
    UserID: int
    Username: str
    DisplayName: str
    Role: str

    @property
    def is_manager_portal(self) -> bool:
        return self.Role in ("Manager", "Admin")


def create_session(user: User) -> str:
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = user.UserID
    return token


def destroy_session(token: str | None) -> None:
    if token:
        _SESSIONS.pop(token, None)


def get_user_by_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    user_id = _SESSIONS.get(token)
    if not user_id:
        return None
    return db.get(User, user_id)


def login(db: Session, username: str) -> tuple[str, User]:
    user = db.query(User).filter(User.Username == username, User.IsActive.is_(True)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown or inactive user")
    token = create_session(user)
    return token, user


def get_current_user(
    db: Session = Depends(get_db),
    x_session_token: str | None = Header(default=None, alias=SESSION_HEADER),
) -> AuthUser:
    user = get_user_by_token(db, x_session_token)
    if not user or not user.IsActive:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return AuthUser(
        UserID=user.UserID,
        Username=user.Username,
        DisplayName=user.DisplayName,
        Role=user.Role,
    )


def require_manager(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if not user.is_manager_portal:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager or Admin role required",
        )
    return user


def optional_user(
    db: Session = Depends(get_db),
    x_session_token: str | None = Header(default=None, alias=SESSION_HEADER),
) -> AuthUser | None:
    user = get_user_by_token(db, x_session_token)
    if not user or not user.IsActive:
        return None
    return AuthUser(
        UserID=user.UserID,
        Username=user.Username,
        DisplayName=user.DisplayName,
        Role=user.Role,
    )


def list_demo_users(db: Session) -> list[User]:
    return db.query(User).filter(User.IsActive.is_(True)).order_by(User.Role.desc(), User.DisplayName).all()
