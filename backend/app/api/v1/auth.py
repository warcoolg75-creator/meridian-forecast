"""Sign-in, token refresh, sign-out, the current user and password change.

The access token is returned in the body; the client keeps it in memory only. The
refresh token is set as an httpOnly, Secure, SameSite=Lax cookie scoped to /api/v1/auth,
so scripts can never read it and no other endpoint ever receives it.
"""

import math
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.models.base import utcnow
from app.schemas import (
    ChangePasswordRequest,
    ErrorResponse,
    LoginRequest,
    SessionResponse,
    SignedOutResponse,
    UserRead,
)
from app.services import auth
from app.services.rate_limit import LoginRateLimiter, login_limiter

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "meridian_refresh"
COOKIE_PATH = "/api/v1/auth"
INVALID_CREDENTIALS = "Email or password is incorrect."
SESSION_EXPIRED = "Your session has expired. Sign in again."

DbSession = Annotated[Session, Depends(get_db)]
RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def get_login_limiter() -> LoginRateLimiter:
    return login_limiter


def _set_refresh_cookie(response: Response, issued: auth.IssuedRefresh, now: datetime) -> None:
    # Without "remember me" this is a browser-session cookie: no Max-Age, gone when the
    # browser closes. The token inside still expires after refresh_token_days either way.
    max_age = int((issued.expires_at - now).total_seconds()) if issued.persistent else None
    response.set_cookie(REFRESH_COOKIE, issued.token, max_age=max_age, path=COOKIE_PATH,
                        secure=True, httponly=True, samesite="lax")


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH, secure=True, httponly=True, samesite="lax")


def _error(status_code: int, detail: str, *, headers: dict[str, str] | None = None,
           clear_cookie: bool = False) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content=ErrorResponse(detail=detail).model_dump(),
                            headers=headers)
    if clear_cookie:
        _clear_refresh_cookie(response)
    return response


def _session(user: User, now: datetime) -> SessionResponse:
    return SessionResponse(access_token=auth.create_access_token(user, now),
                           expires_in=get_settings().access_token_minutes * 60,
                           user=UserRead.model_validate(user))


@router.post(
    "/login",
    response_model=SessionResponse,
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse, "description": "Too many attempts"}},
)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    limiter: Annotated[LoginRateLimiter, Depends(get_login_limiter)],
) -> SessionResponse | JSONResponse:
    """Sign in with email and password.

    Every failure gets the same 401 message, whether or not the email has an account.
    Five failures for one client IP and email within 15 minutes block further attempts
    with 429 and Retry-After; a successful sign-in clears the count.
    """
    key = (request.client.host if request.client else "unknown", auth.normalize_email(body.email))
    wait = limiter.retry_after(key)
    if wait is not None:
        minutes = math.ceil(wait / 60)
        return _error(429, f"Too many sign-in attempts. Try again in {minutes} minute{'' if minutes == 1 else 's'}.",
                      headers={"Retry-After": str(wait)})
    user = auth.authenticate(db, body.email, body.password)
    if user is None:
        limiter.record_failure(key)
        return _error(401, INVALID_CREDENTIALS)
    limiter.reset(key)
    now = utcnow()
    user.last_login_at = now
    issued = auth.issue_refresh_token(db, user, persistent=body.remember, now=now)
    db.commit()
    _set_refresh_cookie(response, issued, now)
    return _session(user, now)


@router.post("/refresh", response_model=SessionResponse, responses={401: {"model": ErrorResponse}})
def refresh(response: Response, db: DbSession, refresh_token: RefreshCookie = None) -> SessionResponse | JSONResponse:
    """Exchange the refresh cookie for a new access token and a new refresh cookie.

    Each refresh token works once. Replaying a used one revokes that whole sign-in.
    """
    if not refresh_token:
        return _error(401, "Not signed in.")
    now = utcnow()
    try:
        user, issued = auth.rotate_refresh_token(db, refresh_token, now)
    except auth.RefreshError:
        db.commit()  # keep the family revocation a replayed token triggers
        return _error(401, SESSION_EXPIRED, clear_cookie=True)
    db.commit()
    _set_refresh_cookie(response, issued, now)
    return _session(user, now)


@router.post("/logout", response_model=SignedOutResponse)
def logout(response: Response, db: DbSession, refresh_token: RefreshCookie = None) -> SignedOutResponse:
    """Sign out: revoke this sign-in's refresh tokens and clear the cookie. Always succeeds."""
    if refresh_token:
        auth.revoke_refresh_token(db, refresh_token, utcnow())
        db.commit()
    _clear_refresh_cookie(response)
    return SignedOutResponse()


@router.get("/me", response_model=UserRead, responses={401: {"model": ErrorResponse}})
def me(user: Annotated[User, Depends(get_current_user)]) -> UserRead:
    return UserRead.model_validate(user)


@router.post(
    "/change-password",
    response_model=SessionResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
def change_password(
    body: ChangePasswordRequest,
    response: Response,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    refresh_token: RefreshCookie = None,
) -> SessionResponse | JSONResponse:
    """Change your own password. Every other session is signed out; this one gets new tokens."""
    if not auth.verify_password(body.current_password, user.password_hash):
        return _error(400, "Your current password is incorrect.")
    if body.new_password == body.current_password:
        return _error(400, "Choose a password different from your current one.")
    now = utcnow()
    persistent = auth.persistent_flag(db, refresh_token)
    user.password_hash = auth.hash_password(body.new_password)
    auth.revoke_all_for_user(db, user.id, now)
    issued = auth.issue_refresh_token(db, user, persistent=persistent, now=now)
    db.commit()
    _set_refresh_cookie(response, issued, now)
    return _session(user, now)
