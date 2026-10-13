from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, enum_type, utcnow
from app.models.enums import UserRole


class User(Base):
    """A person who signs in. Emails are stored lower-cased, so uniqueness is
    case-insensitive on every dialect."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(sa.String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(sa.String(255))
    full_name: Mapped[str] = mapped_column(sa.String(120))
    role: Mapped[UserRole] = mapped_column(enum_type(UserRole, "user_role"))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class RefreshToken(Base):
    """One issued refresh token, identified by its JWT id (the token itself is never stored).

    Every sign-in starts a family; each refresh marks the presented token used and
    issues the next one in the same family. Presenting a used or revoked token again
    means it leaked, so the whole family is revoked.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(sa.String(64), unique=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[str] = mapped_column(sa.String(64), index=True)
    # "Remember me": a persistent cookie (Max-Age) rather than a browser-session cookie.
    persistent: Mapped[bool] = mapped_column(sa.Boolean)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
