from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db import get_db
from app.models import UserRole
from app.schemas import ErrorResponse, ImportReport
from app.services.csv_import import MAX_UPLOAD_BYTES, TEMPLATE_CSV, file_too_large_report, import_sales_csv

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post(
    "/sales",
    response_model=ImportReport,
    # Importing overwrites sales data, so only admins and planners may do it.
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.PLANNER))],
    responses={
        401: {"model": ErrorResponse, "description": "Not signed in"},
        403: {"model": ErrorResponse, "description": "Role is not admin or planner"},
        413: {"model": ImportReport, "description": "File too large"},
        422: {"model": ImportReport, "description": "Validation failed; nothing was imported"},
    },
)
def import_sales(file: UploadFile, db: Annotated[Session, Depends(get_db)]) -> ImportReport | JSONResponse:
    """Validate every row, then upsert all of them into daily_sales in one transaction.

    If any row is invalid nothing is written and the response lists every problem
    by row number (header = row 1). Download the expected format from
    GET /api/v1/imports/sales/template.
    """
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=413, content=file_too_large_report().model_dump(mode="json"))
    report = import_sales_csv(db, raw)
    if report.status == "rejected":
        return JSONResponse(status_code=422, content=report.model_dump(mode="json"))
    return report


@router.get(
    "/sales/template",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV template with one example row"}},
)
def sales_import_template() -> Response:
    """Documented exception to the Pydantic-response rule: this is a file download."""
    return Response(
        content=TEMPLATE_CSV,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sales_import_template.csv"'},
    )
