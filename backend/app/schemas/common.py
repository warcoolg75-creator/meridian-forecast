from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Offset pagination envelope used by every list endpoint."""

    items: list[T]
    total: int
    limit: int
    offset: int


class CursorPage(BaseModel, Generic[T]):
    """Keyset pagination envelope: pass next_cursor back as `cursor` for the next page.

    next_cursor is null on the last page. There is no total: counting would cost as much
    as reading every page.
    """

    items: list[T]
    next_cursor: str | None
    limit: int


class ErrorResponse(BaseModel):
    detail: str
