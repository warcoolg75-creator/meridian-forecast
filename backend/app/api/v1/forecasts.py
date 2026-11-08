from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import ForecastRunKind
from app.schemas import ErrorResponse
from app.schemas.forecasting import ForecastsResponse, SkuForecastResponse
from app.services import forecast_read
from app.services.errors import NotFoundError

router = APIRouter(
    prefix="/forecasts",
    tags=["forecasts"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.get("", response_model=ForecastsResponse, summary="The latest forecast for every SKU")
def latest_forecasts(
    db: Annotated[Session, Depends(get_db)],
    skus: Annotated[list[str] | None, Query(description="Only these SKUs")] = None,
) -> ForecastsResponse:
    """Weekly units per SKU, 1-26 weeks ahead, from each SKU's champion: the median and the
    80% / 95% intervals. Modelled at the SKU level only."""
    run = forecast_read.latest(db, ForecastRunKind.PRODUCTION)
    return ForecastsResponse(run=forecast_read.run_info(run), assumptions=forecast_read.assumptions(run),
                             items=forecast_read.sku_forecasts(db, run, skus))


@router.get("/{sku}", response_model=SkuForecastResponse, summary="One SKU's forecast, optionally allocated")
def sku_forecast(
    sku: str,
    db: Annotated[Session, Depends(get_db)],
    view: Annotated[Literal["sku", "state", "channel"], Query(
        description="sku: the modelled forecast only. state / channel: also split by the trailing 13-week "
                    "shares (allocated, not modelled; medians only)")] = "sku",
) -> SkuForecastResponse:
    run = forecast_read.latest(db, ForecastRunKind.PRODUCTION)
    found = forecast_read.sku_forecasts(db, run, [sku])
    if not found:
        raise NotFoundError(f"No forecast for sku: {sku}")
    allocation = None if view == "sku" else forecast_read.allocation(db, run, found[0], view)
    return SkuForecastResponse(run=forecast_read.run_info(run), assumptions=forecast_read.assumptions(run),
                               forecast=found[0], allocation=allocation)
