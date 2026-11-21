from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import get_password_hash, validate_password_policy, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LogoutRequest,
    Message,
    PasswordChange,
    RefreshRequest,
    Token,
    UserCreate,
    UserLogin,
    UserProfileUpdate,
    UserRead,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, enabled=settings.rate_limit_enabled)
except Exception:  # pragma: no cover
    limiter = None


def _client_ip(request: Request) -> str | None:
    try:
        return request.client.host if request.client else None
    except Exception:
        return None


def _to_user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        organization_id=user.organization_id,
        role=user.role.name if user.role else "member",
        created_at=user.created_at,
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)) -> UserRead:
    try:
        user = auth_service.create_user_with_org(db, payload, ip_address=_client_ip(request))
    except ValueError as e:
        msg = str(e)
        code = status.HTTP_409_CONFLICT if "already" in msg.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail={"code": "validation_error" if code == 400 else "conflict", "message": msg})
    return _to_user_read(user)


@router.post("/login", response_model=Token)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)) -> Token:
    user = auth_service.authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Incorrect email or password"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token, refresh_token = auth_service.issue_token_pair(db, user, ip_address=_client_ip(request))
    return Token(access_token=access_token, token_type="bearer", refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> Token:
    try:
        access_token, refresh_token, _user = auth_service.refresh_tokens(db, payload.refresh_token, ip_address=_client_ip(request))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_refresh_token", "message": str(e)})
    return Token(access_token=access_token, token_type="bearer", refresh_token=refresh_token)


@router.post("/logout", response_model=Message)
def logout(
    payload: LogoutRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Message:
    if payload.all_sessions:
        auth_service.revoke_all_refresh_tokens(db, current_user, ip_address=_client_ip(request))
        return Message(message="All sessions logged out")
    if payload.refresh_token:
        auth_service.revoke_refresh_token(db, payload.refresh_token, user=current_user, ip_address=_client_ip(request))
    return Message(message="Logged out")


@router.get("/me", response_model=UserRead)
def read_me(current_user: User = Depends(get_current_user)) -> UserRead:
    return _to_user_read(current_user)


@router.patch("/me", response_model=UserRead)
def update_me(
    payload: UserProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    if payload.email is not None:
        normalized = payload.email.lower()
        if normalized != current_user.email:
            existing = auth_service.get_user_by_email(db, normalized)
            if existing and existing.id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "conflict", "message": "Email already registered"},
                )
            current_user.email = normalized
    if payload.full_name is not None:
        current_user.full_name = payload.full_name.strip() or None
    auth_service.create_audit_log(
        db,
        "auth.profile_updated",
        user=current_user,
        resource_type="user",
        resource_id=current_user.id,
        ip_address=_client_ip(request),
    )
    db.commit()
    db.refresh(current_user)
    return _to_user_read(current_user)


@router.post("/change-password", response_model=Message)
def change_password(
    payload: PasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Message:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_password", "message": "Current password is incorrect"},
        )
    try:
        validate_password_policy(payload.new_password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "weak_password", "message": str(exc)},
        ) from exc
    current_user.hashed_password = get_password_hash(payload.new_password)
    auth_service.revoke_all_refresh_tokens(db, current_user, ip_address=_client_ip(request))
    auth_service.create_audit_log(
        db,
        "auth.password_changed",
        user=current_user,
        resource_type="user",
        resource_id=current_user.id,
        ip_address=_client_ip(request),
    )
    db.commit()
    return Message(message="Password updated")
