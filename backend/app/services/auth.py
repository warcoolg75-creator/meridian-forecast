"""Passwords, JWTs and refresh-token rotation.

Access tokens (15 min) travel in the Authorization header and live only in client
memory. Refresh tokens (7 days) live in an httpOnly cookie; each one is single use.
Callers own the transaction (commit/rollback).
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, get_settings
from app.models import RefreshToken, User

ALGORITHM = "HS256"
ACCESS = "access"
REFRESH = "refresh"

_hasher = PasswordHash((Argon2Hasher(),))
# Checked against when the email is unknown, so that path costs one full argon2
# verification, exactly like a wrong password: response time does not reveal which
# emails have accounts.
DUMMY_PASSWORD_HASH = _hasher.hash(secrets.token_urlsafe(32))


class RefreshError(Exception):
    """The refresh token is missing, malformed, expired, used, revoked or orphaned."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


def authenticate(session: Session, email: str, password: str) -> User | None:
    """The user if the email and password match an active account, else None.

    Unknown email, wrong password and inactive account all return None after the same
    work (one argon2 verification), so neither the result nor the timing tells them apart.
    """
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user.password_hash) or not user.is_active:
        return None
    return user


# ------------------------------------------------------------------------------ JWTs


@lru_cache
def signing_key() -> str:
    configured = get_settings().jwt_secret
    if configured:
        return configured
    dev_key = BACKEND_DIR / ".jwt-secret"
    if not dev_key.exists():
        dev_key.write_text(secrets.token_urlsafe(64), encoding="utf-8")
    return dev_key.read_text(encoding="utf-8").strip()


def create_access_token(user: User, now: datetime) -> str:
    expires = now + timedelta(minutes=get_settings().access_token_minutes)
    claims = {"sub": str(user.id), "role": user.role.value, "type": ACCESS, "iat": now, "exp": expires}
    return jwt.encode(claims, signing_key(), algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Claims of a valid, unexpired token of the expected type; raises jwt.InvalidTokenError."""
    claims = jwt.decode(token, signing_key(), algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
    if claims.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected a {expected_type} token")
    return claims


# ------------------------------------------------------------------------------ refresh tokens


@dataclass(frozen=True)
class IssuedRefresh:
    token: str
    expires_at: datetime
    persistent: bool


def issue_refresh_token(
    session: Session, user: User, *, persistent: bool, now: datetime, family_id: str | None = None
) -> IssuedRefresh:
    """Record and sign a new refresh token; a new family unless one is passed (rotation)."""
    jti = secrets.token_urlsafe(32)
    family = family_id or secrets.token_urlsafe(16)
    expires = now + timedelta(days=get_settings().refresh_token_days)
    session.add(RefreshToken(jti=jti, user_id=user.id, family_id=family, persistent=persistent,
                             issued_at=now, expires_at=expires))
    claims = {"sub": str(user.id), "jti": jti, "fam": family, "type": REFRESH, "iat": now, "exp": expires}
    return IssuedRefresh(jwt.encode(claims, signing_key(), algorithm=ALGORITHM), expires, persistent)


def _row_for(session: Session, token: str) -> RefreshToken:
    try:
        claims = decode_token(token, REFRESH)
    except jwt.InvalidTokenError as exc:
        raise RefreshError("invalid refresh token") from exc
    row = session.scalar(select(RefreshToken).where(RefreshToken.jti == claims.get("jti")))
    if row is None:
        raise RefreshError("unknown refresh token")
    return row


def revoke_family(session: Session, family_id: str, now: datetime) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def revoke_all_for_user(session: Session, user_id: int, now: datetime) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def rotate_refresh_token(session: Session, token: str, now: datetime) -> tuple[User, IssuedRefresh]:
    """Spend `token` and issue its successor in the same family.

    A used or revoked token presented again means it was copied: the whole family is
    revoked before RefreshError is raised, so the caller must commit even on failure.
    """
    row = _row_for(session, token)
    if row.used_at is not None or row.revoked_at is not None:
        revoke_family(session, row.family_id, now)
        raise RefreshError("refresh token reused")
    if row.expires_at <= now:
        raise RefreshError("refresh token expired")
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        revoke_family(session, row.family_id, now)
        raise RefreshError("account unavailable")
    row.used_at = now
    return user, issue_refresh_token(session, user, persistent=row.persistent, now=now, family_id=row.family_id)


def revoke_refresh_token(session: Session, token: str, now: datetime) -> None:
    """Sign-out: end the token's family. Unknown or invalid tokens are ignored."""
    try:
        row = _row_for(session, token)
    except RefreshError:
        return
    revoke_family(session, row.family_id, now)


def persistent_flag(session: Session, token: str | None) -> bool:
    """Whether the session behind a refresh cookie used "remember me" (False if unknown)."""
    if not token:
        return False
    try:
        return _row_for(session, token).persistent
    except RefreshError:
        return False
