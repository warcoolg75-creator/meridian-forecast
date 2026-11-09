from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import ForecastRunKind
from app.schemas import ErrorResponse
from app.schemas.forecasting import (
    ForecastOverviewResponse,
    ForecastsResponse,
    OracleTestResponse,
    SkuForecast,
    SkuForecastContext,
    SkuForecastResponse,
)
from app.services import forecast_read
from app.services.errors import NotFoundError

router = APIRouter(
    prefix="/forecasts",
    tags=["forecasts"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)

HORIZONS = (4, 13, 26)


def horizon_weeks(horizon: Annotated[int, Query(description="Weeks ahead to return: 4, 13 or 26")] = 26) -> int:
    # A query string is never a Literal[4, 13, 26] (it arrives as "4"), so checked here.
    if horizon not in HORIZONS:
        raise HTTPException(422, f"horizon must be one of {', '.join(map(str, HORIZONS))}")
    return horizon


Horizon = Annotated[int, Depends(horizon_weeks)]


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


# Fixed paths are declared before /{sku}, which would otherwise match them as a SKU.
@router.get("/overview", response_model=ForecastOverviewResponse, summary="Every SKU's forecast at a glance")
def overview(db: Annotated[Session, Depends(get_db)]) -> ForecastOverviewResponse:
    """Next 4 and 13 weeks against the same weeks last year (364 days earlier), held-out
    skill against seasonal naive, ABC and forecastability (XYZ on forecast errors)."""
    return forecast_read.overview(db, forecast_read.latest(db, ForecastRunKind.PRODUCTION))


@router.get("/oracle-test", response_model=OracleTestResponse, summary="The stored forward oracle test")
def oracle_test(db: Annotated[Session, Depends(get_db)]) -> OracleTestResponse:
    return forecast_read.oracle_test(forecast_read.latest(db, ForecastRunKind.PRODUCTION))


def _one(db: Session, sku: str) -> tuple:
    run = forecast_read.latest(db, ForecastRunKind.PRODUCTION)
    found = forecast_read.sku_forecasts(db, run, [sku])
    if not found:
        raise NotFoundError(f"No forecast for sku: {sku}")
    return run, found[0]


@router.get("/{sku}", response_model=SkuForecastResponse, summary="One SKU's forecast, optionally allocated")
def sku_forecast(
    sku: str,
    db: Annotated[Session, Depends(get_db)],
    horizon: Horizon,
    view: Annotated[Literal["sku", "state", "channel"], Query(
        description="sku: the modelled forecast only. state / channel: also split by the trailing 13-week "
                    "shares (allocated, not modelled; medians only)")] = "sku",
) -> SkuForecastResponse:
    run, found = _one(db, sku)
    found = forecast_read.limit_horizon(found, horizon)
    allocation = None if view == "sku" else forecast_read.allocation(db, run, found, view)
    return SkuForecastResponse(run=forecast_read.run_info(run), assumptions=forecast_read.assumptions(run),
                               forecast=found, allocation=allocation)


@router.get("/{sku}/csv", summary="One SKU's forecast as CSV", response_class=Response,
            responses={200: {"content": {"text/csv": {}}, "description": "sku, week, horizon, model, p50 and "
                                                                         "the 80% / 95% bounds"}})
def sku_forecast_csv(sku: str, db: Annotated[Session, Depends(get_db)], horizon: Horizon) -> Response:
    """The same weeks and numbers as GET /forecasts/{sku} with the same horizon. A file
    download, so not a Pydantic model (documented exception)."""
    _, found = _one(db, sku)
    found: SkuForecast = forecast_read.limit_horizon(found, horizon)
    return Response(forecast_read.forecast_csv(found), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="forecast-{found.sku}-{horizon}w.csv"'})


@router.get("/{sku}/context", response_model=SkuForecastContext, summary="What the forecast page draws around it")
def sku_context(sku: str, db: Annotated[Session, Depends(get_db)]) -> SkuForecastContext:
    run, found = _one(db, sku)
    return forecast_read.context(db, run, found)
