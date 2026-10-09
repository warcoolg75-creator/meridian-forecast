from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.db import get_db
from app.models import Region, RegionLevel
from app.schemas import Page, RegionRead
from app.services.errors import NotFoundError

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("", response_model=Page[RegionRead])
def list_regions(
    db: Annotated[Session, Depends(get_db)],
    level: RegionLevel | None = None,
    parent_code: Annotated[str | None, Query(description="Only direct children of this region")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RegionRead]:
    parent = aliased(Region)
    stmt = select(Region, parent.code.label("parent_code")).outerjoin(parent, Region.parent_region_id == parent.id)
    if level is not None:
        stmt = stmt.where(Region.level == level)
    if parent_code is not None:
        if db.scalar(select(Region.id).where(Region.code == parent_code)) is None:
            raise NotFoundError(f"Unknown region code: {parent_code}")
        stmt = stmt.where(parent.code == parent_code)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Region.code).limit(limit).offset(offset)).all()
    items = [
        RegionRead.model_validate(region).model_copy(update={"parent_code": code}) for region, code in rows
    ]
    return Page[RegionRead](items=items, total=total, limit=limit, offset=offset)
