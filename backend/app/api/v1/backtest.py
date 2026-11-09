from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import ForecastRunKind, MetricWindow, ShockScope
from app.schemas import ErrorResponse
from app.schemas.forecasting import LeaderboardResponse, MetricsResponse
from app.config import REPO_ROOT
from app.services import forecast_read
from app.services.errors import NotFoundError

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


# The one file /report serves (app.forecasting.report writes it; not imported: it needs the ml extra).
REPORT_PATH = REPO_ROOT / "docs" / "backtest-report.md"


@router.get("/report", summary="docs/backtest-report.md", response_class=Response,
            responses={200: {"content": {"text/markdown": {}}, "description": "The generated backtest report"}})
def report() -> Response:
    """The one generated report, docs/backtest-report.md, as written by make backtest and
    make forecast. A fixed file: there is no path parameter. A file download, so not a
    Pydantic model (documented exception)."""
    if not REPORT_PATH.is_file():
        raise NotFoundError("No backtest report yet: run make backtest")
    return Response(REPORT_PATH.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")
