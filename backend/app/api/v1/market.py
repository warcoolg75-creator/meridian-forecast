from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.schemas import ErrorResponse
from app.schemas.market import HeadlinesResponse, MarketOverview, SeriesDataResponse, SourceStatus
from app.services import market
from app.services.bucketing import Granularity

router = APIRouter(
    prefix="/market",
    tags=["market"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.get("/overview", response_model=MarketOverview, summary="Signals mapped to each category, with status")
def overview(db: Annotated[Session, Depends(get_db)]) -> MarketOverview:
    """Per category, the demand-context and input-cost series mapped to it (and why), each
    with its source, unit, latest value date, last successful fetch and a stale flag.
    Context only: the sales data is synthetic, so no signal is used in the forecast."""
    return market.overview(db)


@router.get("/sources", response_model=list[SourceStatus], summary="Each signal source's last run")
def sources(db: Annotated[Session, Depends(get_db)]) -> list[SourceStatus]:
    return market.overview(db).sources


@router.get("/series", response_model=SeriesDataResponse, summary="Values of one or more signal series")
def series(
    db: Annotated[Session, Depends(get_db)],
    keys: Annotated[list[str], Query(description="Series keys, e.g. weather.tmax.IN-DL-NDL")],
    granularity: Annotated[Literal["day", "week", "month"], Query(
        description="Bucket for daily series (mean or sum per the series); monthly series stay monthly")] = "week",
    date_from: date | None = None,
    date_to: date | None = None,
) -> SeriesDataResponse:
    if not keys or len(keys) > market.MAX_SERIES_PER_REQUEST:
        raise HTTPException(422, f"Ask for 1 to {market.MAX_SERIES_PER_REQUEST} series")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from is after date_to")
    return SeriesDataResponse(items=market.series_data(db, keys, Granularity(granularity), date_from, date_to))


@router.get("/headlines", response_model=HeadlinesResponse, summary="Recent headlines for a category")
def headlines(
    db: Annotated[Session, Depends(get_db)],
    category: Annotated[str, Query(min_length=1, max_length=60)],
    limit: Annotated[int, Query(ge=1, le=50)] = 8,
) -> HeadlinesResponse:
    """Headlines and links only (never article bodies), newest first, from GDELT."""
    return market.headlines(db, category, limit)
