from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token_value,
    get_password_hash,
    get_refresh_expiry,
    hash_token,
    validate_password_policy,
    verify_password,
)
from app.models.user import AuditLog, Organization, RefreshToken, Role, User
from app.schemas.auth import UserCreate


def get_or_create_role(db: Session, name: str, description: str | None = None) -> Role:
    role = db.query(Role).filter(Role.name == name).first()
    if role:
        return role
    role = Role(name=name, description=description)
    db.add(role)
    db.flush()
    return role


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email.lower()).first()


def create_audit_log(
    db: Session,
    action: str,
    user: User | None = None,
    organization_id=None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    try:
        org_id = organization_id or (user.organization_id if user else None)
        log = AuditLog(
            organization_id=org_id,
            user_id=user.id if user else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details=json.dumps(details, ensure_ascii=False) if details else None,
            ip_address=ip_address,
        )
        db.add(log)
        db.flush()
    except Exception:
        # audit logging must not break core flows
        pass


def create_user_with_org(db: Session, payload: UserCreate, ip_address: str | None = None) -> User:
    existing = get_user_by_email(db, payload.email)
    if existing:
        raise ValueError("Email already registered")
    try:
        validate_password_policy(payload.password)
    except ValueError as e:
        raise ValueError(str(e))

    org = Organization(name=payload.organization_name)
    db.add(org)
    db.flush()

    admin_role = get_or_create_role(db, "admin", "Organization administrator")
    get_or_create_role(db, "member", "Organization member")

    user = User(
        email=payload.email.lower(),
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        organization_id=org.id,
        role_id=admin_role.id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    create_audit_log(db, "auth.register", user=user, resource_type="user", resource_id=user.id, ip_address=ip_address)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def issue_token_pair(db: Session, user: User, ip_address: str | None = None) -> tuple[str, str]:
    access = create_access_token(subject=str(user.id), extra_claims={"org": str(user.organization_id)})
    raw_refresh, token_hash, jti = create_refresh_token_value()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        jti=jti,
        expires_at=get_refresh_expiry(),
    )
    db.add(rt)
    create_audit_log(db, "auth.token_issued", user=user, resource_type="refresh_token", resource_id=jti, ip_address=ip_address)
    db.commit()
    return access, raw_refresh


def _get_refresh_record(db: Session, raw_token: str) -> RefreshToken | None:
    th = hash_token(raw_token)
    return db.query(RefreshToken).filter(RefreshToken.token_hash == th).first()


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def refresh_tokens(db: Session, raw_refresh_token: str, ip_address: str | None = None) -> tuple[str, str, User]:
    rec = _get_refresh_record(db, raw_refresh_token)
    now = datetime.now(timezone.utc)
    if rec is None:
        raise ValueError("Invalid refresh token")
    if rec.revoked_at is not None:
        raise ValueError("Refresh token revoked")
    if _as_utc(rec.expires_at) <= now:
        raise ValueError("Refresh token expired")
    user = db.get(User, rec.user_id)
    if user is None or not user.is_active:
        raise ValueError("User not found or inactive")
    # rotate: revoke old, issue new
    rec.revoked_at = now
    access = create_access_token(subject=str(user.id), extra_claims={"org": str(user.organization_id)})
    new_raw, new_hash, new_jti = create_refresh_token_value()
    rec.replaced_by_jti = new_jti
    new_rec = RefreshToken(user_id=user.id, token_hash=new_hash, jti=new_jti, expires_at=get_refresh_expiry())
    db.add(new_rec)
    create_audit_log(db, "auth.token_refreshed", user=user, resource_type="refresh_token", resource_id=new_jti, ip_address=ip_address)
    db.commit()
    return access, new_raw, user


def revoke_refresh_token(db: Session, raw_refresh_token: str, user: User | None = None, ip_address: str | None = None) -> bool:
    rec = _get_refresh_record(db, raw_refresh_token)
    if rec is None:
        return False
    if rec.revoked_at is not None:
        return True
    rec.revoked_at = datetime.now(timezone.utc)
    create_audit_log(db, "auth.token_revoked", user=user or db.get(User, rec.user_id), resource_type="refresh_token", resource_id=rec.jti, ip_address=ip_address)
    db.commit()
    return True


def revoke_all_refresh_tokens(db: Session, user: User, ip_address: str | None = None) -> int:
    now = datetime.now(timezone.utc)
    q = db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
    count = 0
    for rec in q.all():
        rec.revoked_at = now
        count += 1
    create_audit_log(db, "auth.tokens_revoked_all", user=user, details={"count": count}, ip_address=ip_address)
    db.commit()
    return count
