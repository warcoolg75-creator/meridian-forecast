from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import UserRole
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    remember: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class UserRead(ORMModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    last_login_at: datetime | None


class SessionResponse(BaseModel):
    """A signed-in session. The refresh token is not here: it is set as an httpOnly cookie."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserRead


class SignedOutResponse(BaseModel):
    status: Literal["signed_out"] = "signed_out"
