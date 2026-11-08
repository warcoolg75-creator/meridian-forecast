from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import ForecastRunKind, MetricWindow, ShockScope
from app.schemas import ErrorResponse
from app.schemas.forecasting import LeaderboardResponse, MetricsResponse
from app.services import forecast_read

router = APIRouter(
    prefix="/backtest",
    tags=["backtest"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


@router.get("/metrics", response_model=MetricsResponse, summary="Backtest scores of the latest backtest run")
def metrics(
    db: Annotated[Session, Depends(get_db)],
    model: Annotated[str | None, Query(description="A model, 'champion' or 'oracle'")] = None,
    sku: Annotated[str | None, Query(description="One SKU; rows with sku null pool the headline SKUs")] = None,
    window: MetricWindow | None = None,
    shocks: ShockScope | None = None,
    horizon: Annotated[int | None, Query(description="1, 4, 13 or 26; rows with horizon null pool 1-26")] = None,
) -> MetricsResponse:
    run = forecast_read.latest(db, ForecastRunKind.BACKTEST)
    return MetricsResponse(run=forecast_read.run_info(run),
                           items=forecast_read.metric_rows(db, run, model, sku, window, shocks, horizon))


@router.get("/leaderboard", response_model=LeaderboardResponse, summary="Models ranked against seasonal naive")
def leaderboard(
    db: Annotated[Session, Depends(get_db)],
    window: MetricWindow = MetricWindow.HELD_OUT,
    shocks: ShockScope = ShockScope.INCLUDED,
) -> LeaderboardResponse:
    """Pooled WAPE (volume-weighted) and the median per-SKU skill (every SKU counts once),
    horizons 1-26, plus each SKU's champion against seasonal naive."""
    run = forecast_read.latest(db, ForecastRunKind.BACKTEST)
    models, champions = forecast_read.leaderboard(db, run, window, shocks)
    return LeaderboardResponse(run=forecast_read.run_info(run), window=window, shocks=shocks,
                               target_skill=forecast_read.TARGET_SKILL,
                               headline_skus=run.params.get("headline_skus", []), models=models, champions=champions)
