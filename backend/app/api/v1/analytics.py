from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import Channel, RegionLevel
from app.schemas import ErrorResponse
from app.schemas.analytics import (
    ChannelsResponse,
    ComparisonMode,
    Coverage,
    ProductSort,
    ProductsResponse,
    RegionsResponse,
    SortOrder,
    SummaryResponse,
    TimeseriesResponse,
)
from app.services.analytics import queries
from app.services.analytics.scope import AnalyticsParams, InvalidRangeError, Scope, resolve_scope
from app.services.bucketing import Granularity
from app.services.sales_source import data_bounds

# Sales data is not public: any signed-in role may read it.
router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_user)],
    responses={
        401: {"model": ErrorResponse, "description": "Not signed in"},
        404: {"model": ErrorResponse, "description": "Unknown sku or region code"},
    },
)


def analytics_params(
    date_from: Annotated[date | None, Query(description="Inclusive; default 13 weeks before date_to")] = None,
    date_to: Annotated[date | None, Query(description="Inclusive; default the last day with data")] = None,
    skus: Annotated[list[str] | None, Query(description="Repeat for several SKUs")] = None,
    regions: Annotated[list[str] | None, Query(description="Region codes at any level; a state includes "
                                                           "its cities")] = None,
    channels: Annotated[list[Channel] | None, Query()] = None,
    granularity: Granularity = Granularity.WEEK,
    comparison: ComparisonMode = ComparisonMode.SAME_PERIOD_LAST_YEAR,
) -> AnalyticsParams:
    return AnalyticsParams(
        date_from=date_from, date_to=date_to, skus=tuple(dict.fromkeys(skus or [])),
        regions=tuple(dict.fromkeys(regions or [])), channels=tuple(dict.fromkeys(channels or [])),
        granularity=granularity, comparison=comparison,
    )


def scope(params: Annotated[AnalyticsParams, Depends(analytics_params)],
          db: Annotated[Session, Depends(get_db)]) -> Scope:
    try:
        return resolve_scope(db, params)
    except InvalidRangeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


ScopeDep = Annotated[Scope, Depends(scope)]
DbDep = Annotated[Session, Depends(get_db)]


@router.get("/coverage", response_model=Coverage)
def coverage(db: DbDep) -> Coverage:
    """The first and last day with sales: date presets count back from last_date."""
    bounds = data_bounds(db)
    return Coverage(first_date=bounds[0] if bounds else None, last_date=bounds[1] if bounds else None)


@router.get("/summary", response_model=SummaryResponse)
def summary(db: DbDep, s: ScopeDep) -> SummaryResponse:
    """Revenue, units, distinct orders, average selling price and gross margin for the
    period and the comparison period, and the change between them."""
    return queries.summary(db, s)


@router.get("/timeseries", response_model=TimeseriesResponse)
def timeseries(db: DbDep, s: ScopeDep) -> TimeseriesResponse:
    """Units and revenue per bucket, each with the same days of the comparison period."""
    return queries.timeseries(db, s)


@router.get("/products", response_model=ProductsResponse)
def products(db: DbDep, s: ScopeDep, sort: ProductSort = ProductSort.RANK,
             order: SortOrder = SortOrder.ASC) -> ProductsResponse:
    """One row per SKU: revenue, units, margin, share, growth, ABC-XYZ class and a
    13-week sparkline, sorted on the server."""
    return queries.products(db, s, sort, order)


@router.get("/regions", response_model=RegionsResponse)
def regions(db: DbDep, s: ScopeDep, level: RegionLevel = RegionLevel.STATE,
            parent: Annotated[str | None, Query(description="With level=city: only this state's cities")] = None,
            ) -> RegionsResponse:
    """Totals and share per state or per city."""
    try:
        return queries.regions(db, s, level, parent)
    except queries.InvalidParameterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/channels", response_model=ChannelsResponse)
def channels(db: DbDep, s: ScopeDep) -> ChannelsResponse:
    """Totals and share per sales channel, in the period and the comparison period."""
    return queries.channels(db, s)
