from typing import Literal

from pydantic import BaseModel


class ImportRowError(BaseModel):
    row: int | None  # 1-based line in the file, header = 1; None for file-level problems
    column: str | None
    value: str | None
    message: str


class ImportReport(BaseModel):
    status: Literal["imported", "rejected"]
    rows_received: int
    rows_valid: int
    inserted: int
    updated: int
    error_count: int
    errors_truncated: bool
    errors: list[ImportRowError]


class RollupResult(BaseModel):
    deleted: int
    inserted: int
    skipped_for_imports: int
