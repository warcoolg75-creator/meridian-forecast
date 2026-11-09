"""Forecast runs, forecasts and backtest metrics in the database."""

import importlib.metadata
import platform

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.forecasting.backtest import BacktestResult
from app.forecasting.data import SalesHistory
from app.forecasting.models import VERSION
from app.models import BacktestMetric, Forecast, ForecastRun, ForecastRunKind, MetricWindow, Product, ShockScope

LIBRARIES = ("prophet", "cmdstanpy", "lightgbm", "statsmodels", "scikit-learn", "numpy", "pandas", "scipy")


def library_versions() -> dict[str, str]:
    return {"python": platform.python_version(), **{n: importlib.metadata.version(n) for n in LIBRARIES}}


def latest_run(session: Session, kind: ForecastRunKind) -> ForecastRun | None:
    return session.scalars(
        sa.select(ForecastRun).where(ForecastRun.kind == kind).order_by(ForecastRun.id.desc()).limit(1)
    ).first()


def run_version(run: ForecastRun) -> str:
    """Runs made before v2 store no version: they are v1."""
    return (run.params or {}).get("version", "v1")


def latest_of_version(session: Session, kind: ForecastRunKind, version: str,
                      backtest_run_id: int | None = None) -> ForecastRun | None:
    """The newest run of a kind and version (for production runs, optionally made from a
    given backtest run)."""
    runs = session.scalars(sa.select(ForecastRun).where(ForecastRun.kind == kind).order_by(ForecastRun.id.desc()))
    for run in runs:
        if run_version(run) == version and (backtest_run_id is None
                                            or run.params.get("backtest_run_id") == backtest_run_id):
            return run
    return None


def save_backtest(session: Session, history: SalesHistory, result: BacktestResult, seed: int,
                  duration: float, warnings: list[str]) -> ForecastRun:
    run = ForecastRun(
        kind=ForecastRunKind.BACKTEST, model="all", data_end_date=history.data_end,
        training_cutoff=history.weeks[-1], params={
            "version": VERSION,
            "origins": [str(o) for o in result.origins],
            "held_out_start": str(result.held_out_start),
            "champions": result.champions,
            "headline_skus": result.headline_skus,
            "short_history_skus": result.short_history_skus,
            "interval_quantiles": result.quantiles_all,
            "xyz": result.xyz,
            "notes": result.notes,
            "warnings": warnings,
        },
        library_versions=library_versions(), random_seed=seed, duration_seconds=round(duration, 1),
    )
    session.add(run)
    session.flush()
    product_id = dict(session.execute(sa.select(Product.sku, Product.id)).all())
    session.add_all(
        BacktestMetric(
            run_id=run.id, model=m["model"], product_id=product_id[m["sku"]] if m["sku"] else None,
            window=MetricWindow(m["window"]), shocks=ShockScope(m["shocks"]), horizon=m["horizon"],
            n_weeks=m["n_weeks"], wape=m["wape"], bias=m["bias"], mase=m["mase"],
            coverage_80=m["coverage_80"], coverage_95=m["coverage_95"],
        )
        for m in result.metrics
    )
    return run


def save_production(session: Session, history: SalesHistory, rows: list[dict], params: dict, seed: int,
                    duration: float) -> ForecastRun:
    run = ForecastRun(
        kind=ForecastRunKind.PRODUCTION, model="champion", data_end_date=history.data_end,
        training_cutoff=history.weeks[-1], params=params, library_versions=library_versions(),
        random_seed=seed, duration_seconds=round(duration, 1),
    )
    session.add(run)
    session.flush()
    product_id = {s.sku: s.product_id for s in history.skus}
    session.add_all(
        Forecast(run_id=run.id, product_id=product_id[r["sku"]], week=r["week"], horizon=r["horizon"],
                 model=r["model"], p50=r["p50"], lo80=r["lo80"], hi80=r["hi80"], lo95=r["lo95"], hi95=r["hi95"])
        for r in rows
    )
    return run
