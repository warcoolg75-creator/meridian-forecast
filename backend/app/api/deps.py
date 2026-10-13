"""Authentication dependencies: who is calling, and may their role do this."""

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserRole
from app.services.auth import ACCESS, decode_token

_bearer = HTTPBearer(auto_error=False)
_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """The active user behind a valid access token; 401 otherwise.

    The user is re-read on every request, so a deactivation or role change applies
    immediately rather than when the token expires.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not signed in.", headers=_CHALLENGE)
    try:
        claims = decode_token(credentials.credentials, ACCESS)
        user = db.get(User, int(claims["sub"]))
    except (jwt.InvalidTokenError, ValueError):
        user = None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.",
                            headers=_CHALLENGE)
    return user


def require_role(*roles: UserRole) -> Callable[..., User]:
    """Dependency factory: 401 when signed out, 403 unless the user has one of `roles`."""
    allowed = frozenset(roles)

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Your role does not allow this action.")
        return user

    return dependency
