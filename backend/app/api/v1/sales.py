from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Channel
from app.schemas import Page, SalesPeriod
from app.services.bucketing import Granularity
from app.services.sales_query import GroupBy, SalesQuery, query_sales

router = APIRouter(prefix="/sales", tags=["sales"])


@router.get("/daily", response_model=Page[SalesPeriod])
def daily_sales(
    db: Annotated[Session, Depends(get_db)],
    sku: Annotated[list[str] | None, Query(description="Repeat to filter on several SKUs")] = None,
    region: Annotated[list[str] | None, Query(description="Region code; includes all regions below it")] = None,
    channel: Annotated[list[Channel] | None, Query()] = None,
    date_from: Annotated[date | None, Query(description="Inclusive")] = None,
    date_to: Annotated[date | None, Query(description="Inclusive")] = None,
    granularity: Granularity = Granularity.DAY,
    group_by: Annotated[list[GroupBy] | None, Query(description="Dimensions to keep; others are summed")] = None,
    limit: Annotated[int, Query(ge=1, le=10000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SalesPeriod]:
    """Sales from daily_sales, bucketed by day, ISO week (Monday start) or calendar month.

    Without group_by every matching row is summed into one series. Periods with no
    recorded sales are omitted, not zero-filled.
    """
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")

    query = SalesQuery(
        skus=sku or [],
        region_codes=region or [],
        channels=channel or [],
        date_from=date_from,
        date_to=date_to,
        granularity=granularity,
        group_by=list(dict.fromkeys(group_by or [])),
    )
    items, total = query_sales(db, query, limit=limit, offset=offset)
    return Page[SalesPeriod](items=items, total=total, limit=limit, offset=offset)
