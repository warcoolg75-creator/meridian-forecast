"""A backtest run's held-out champion forecasts, horizons 1-4, for the forecast page.

The backtest stored only scores. This recomputes the run (same models, same seed: the
backtest is deterministic) and keeps the champion's held-out forecast-weeks at horizons 1-4:
with origins every 4 weeks, each held-out week has exactly one forecast made 1-4 weeks
before it. Nothing is written unless the recomputation reproduces every stored per-SKU
held-out champion score at horizons 1 and 4 (WAPE, bias, MASE, 80% / 95% coverage, n weeks;
with and without shock weeks) exactly, which proves these are the forecasts the run scored.

This views the held-out window a third time. It chooses nothing and scores nothing new:
the scores it computes are only compared with the stored ones.
"""

from collections.abc import Callable

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.forecasting.backtest import CHAMPION, run_backtest
from app.forecasting.data import SalesHistory
from app.forecasting.models import all_models
from app.models import BacktestForecast, BacktestMetric, ForecastRun, Product

MAX_HORIZON = 4
CHECKED_HORIZONS = (1, 4)
FIELDS = ("n_weeks", "wape", "bias", "mase", "coverage_80", "coverage_95")


def recompute(session: Session, history: SalesHistory, run: ForecastRun, seed: int,
              progress: Callable[[str], None] = lambda _: None) -> tuple[list[dict], list[str], int]:
    """(rows to store, mismatches, number of scores checked)."""
    result = run_backtest(history, seed=seed, models=all_models(), progress=progress)
    mismatches = []
    if result.champions != run.params.get("champions"):
        mismatches.append(f"champions differ: {result.champions} vs {run.params.get('champions')}")
    recomputed = {(m["sku"], m["shocks"], m["horizon"]): m for m in result.metrics
                  if m["model"] == CHAMPION and m["window"] == "held_out" and m["sku"] is not None
                  and m["horizon"] in CHECKED_HORIZONS}
    stored = session.execute(
        sa.select(BacktestMetric, Product.sku).join(Product, Product.id == BacktestMetric.product_id)
        .where(BacktestMetric.run_id == run.id, BacktestMetric.model == CHAMPION,
               BacktestMetric.window == "held_out", BacktestMetric.horizon.in_(CHECKED_HORIZONS))).all()
    if len(stored) != len(recomputed) or not stored:
        mismatches.append(f"{len(stored)} stored scores against {len(recomputed)} recomputed")
    for metric, sku in stored:
        key = (sku, metric.shocks.value, metric.horizon)
        mine = recomputed.get(key)
        if mine is None:
            mismatches.append(f"{key}: not recomputed")
            continue
        for field in FIELDS:
            if getattr(metric, field) != mine[field]:
                mismatches.append(f"{key} {field}: stored {getattr(metric, field)!r}, recomputed {mine[field]!r}")
    pairs = result.pairs
    held = pairs[(pairs["model"] == CHAMPION) & (pairs["window"] == "held_out") & (pairs["horizon"] <= MAX_HORIZON)]
    rows = [{"sku": r.sku, "origin": r.origin, "horizon": int(r.horizon), "week": r.target, "model": r.source,
             "actual": int(r.actual), "p50": float(r.p50), "lo80": float(r.lo80), "hi80": float(r.hi80),
             "lo95": float(r.lo95), "hi95": float(r.hi95)}
            for r in held.sort_values(["sku", "target"]).itertuples()]
    return rows, mismatches, len(stored)


def save(session: Session, run_id: int, rows: list[dict]) -> int:
    """Replaces the run's stored rows (idempotent)."""
    product_id = dict(session.execute(sa.select(Product.sku, Product.id)).all())
    session.execute(sa.delete(BacktestForecast).where(BacktestForecast.run_id == run_id))
    session.add_all(BacktestForecast(run_id=run_id, product_id=product_id[r["sku"]],
                                     **{k: v for k, v in r.items() if k != "sku"}) for r in rows)
    return len(rows)
