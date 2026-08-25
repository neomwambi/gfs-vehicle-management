from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.config import SESSION_HEADER
from app.database import get_db
from app.schemas.schemas import LoginRequest, LoginResponse, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return auth_service.list_demo_users(db)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    token, user = auth_service.login(db, payload.Username)
    return LoginResponse(session_token=token, user=UserOut.model_validate(user))


@router.post("/logout")
def logout(x_session_token: str | None = Header(default=None, alias=SESSION_HEADER)):
    auth_service.destroy_session(x_session_token)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(user: auth_service.AuthUser = Depends(auth_service.get_current_user)):
    return UserOut(
        UserID=user.UserID,
        Username=user.Username,
        DisplayName=user.DisplayName,
        Role=user.Role,
    )
