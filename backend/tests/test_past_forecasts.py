"""make backtest-forecasts: stores a backtest's held-out champion forecasts (h 1-4) only when
the recomputation reproduces the run's stored per-SKU scores at h1 and h4 exactly.

The backtest itself is replaced by a stub here (the real one takes minutes); the stub
returns what run_backtest returns, so this checks the comparison and the write."""

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app.forecasting import past_forecasts
from app.models import BacktestForecast, BacktestMetric, ForecastRun, ForecastRunKind, MetricWindow, ShockScope
from app.models.base import utcnow

ORIGIN = date(2026, 7, 13)


@dataclass
class FakeResult:
    champions: dict
    metrics: list
    pairs: pd.DataFrame
    extra: dict = field(default_factory=dict)


def _metric(sku, shocks, horizon, wape=0.1):
    return {"model": "champion", "sku": sku, "window": "held_out", "shocks": shocks, "horizon": horizon,
            "n_weeks": 4, "wape": wape, "bias": -0.02, "mase": 0.5, "coverage_80": 0.75, "coverage_95": 1.0}


@pytest.fixture
def backtest_run(db, ids):
    run = ForecastRun(kind=ForecastRunKind.BACKTEST, model="all", data_end_date=date(2026, 10, 8),
                      training_cutoff=date(2026, 9, 28), trained_at=utcnow(),
                      params={"champions": {"FDS-GFB-1KG": "prophet_lightgbm"}}, library_versions={},
                      random_seed=42, duration_seconds=1.0)
    db.add(run)
    db.flush()
    for shocks in ("included", "excluded"):
        for h in (1, 4):
            m = _metric("FDS-GFB-1KG", shocks, h)
            db.add(BacktestMetric(run_id=run.id, model="champion", product_id=ids["product"]["FDS-GFB-1KG"],
                                  window=MetricWindow.HELD_OUT, shocks=ShockScope(shocks), horizon=h,
                                  **{k: m[k] for k in past_forecasts.FIELDS}))
    db.commit()
    return run


def _result(wape=0.1, champions=None):
    pairs = pd.DataFrame([
        {"model": "champion", "source": "prophet_lightgbm", "sku": "FDS-GFB-1KG", "origin": ORIGIN, "horizon": h,
         "target": ORIGIN + timedelta(weeks=h - 1), "window": "held_out", "actual": 100.0 + h, "p50": 99.5 + h,
         "lo80": 90.25, "hi80": 110.5, "lo95": 80.0, "hi95": 120.0}
        for h in range(1, 7)
    ] + [{"model": "lightgbm", "source": "lightgbm", "sku": "FDS-GFB-1KG", "origin": ORIGIN, "horizon": 1,
          "target": ORIGIN, "window": "held_out", "actual": 101.0, "p50": 1.0, "lo80": 0.0, "hi80": 2.0,
          "lo95": 0.0, "hi95": 3.0}])
    metrics = [_metric("FDS-GFB-1KG", s, h, wape) for s in ("included", "excluded") for h in (1, 4)]
    metrics.append(_metric(None, "included", 1, 0.5))  # pooled rows are not part of the check
    return FakeResult(champions=champions or {"FDS-GFB-1KG": "prophet_lightgbm"}, metrics=metrics, pairs=pairs)


def test_reproduced_scores_store_the_champions_held_out_weeks_h1_to_4(db, backtest_run, monkeypatch):
    monkeypatch.setattr(past_forecasts, "run_backtest", lambda *a, **k: _result())
    rows, mismatches, checked = past_forecasts.recompute(db, None, backtest_run, 42)
    assert mismatches == [] and checked == 4
    assert [r["horizon"] for r in rows] == [1, 2, 3, 4]  # h 5-6 and other models left out
    assert rows[0] == {"sku": "FDS-GFB-1KG", "origin": ORIGIN, "horizon": 1, "week": ORIGIN,
                       "model": "prophet_lightgbm", "actual": 101, "p50": 100.5, "lo80": 90.25, "hi80": 110.5,
                       "lo95": 80.0, "hi95": 120.0}
    assert past_forecasts.save(db, backtest_run.id, rows) == 4
    assert past_forecasts.save(db, backtest_run.id, rows) == 4  # replaces, never duplicates
    db.commit()
    stored = db.scalars(sa.select(BacktestForecast).order_by(BacktestForecast.horizon)).all()
    assert [(f.horizon, f.p50) for f in stored] == [(1, 100.5), (2, 101.5), (3, 102.5), (4, 103.5)]


def test_any_difference_in_a_score_refuses(db, backtest_run, monkeypatch):
    monkeypatch.setattr(past_forecasts, "run_backtest", lambda *a, **k: _result(wape=0.1 + 1e-15))
    _, mismatches, checked = past_forecasts.recompute(db, None, backtest_run, 42)
    assert checked == 4 and len(mismatches) == 4
    assert "wape" in mismatches[0]


def test_different_champions_refuse(db, backtest_run, monkeypatch):
    monkeypatch.setattr(past_forecasts, "run_backtest",
                        lambda *a, **k: _result(champions={"FDS-GFB-1KG": "lightgbm"}))
    _, mismatches, _ = past_forecasts.recompute(db, None, backtest_run, 42)
    assert any("champions differ" in m for m in mismatches)


def test_the_cli_writes_nothing_when_scores_differ(db, backtest_run, monkeypatch, capsys):
    from app import cli

    monkeypatch.setattr(past_forecasts, "run_backtest", lambda *a, **k: _result(wape=0.2))
    monkeypatch.setattr("app.forecasting.data.load_history", lambda session: None)
    # The test database, never the dev one get_sessionmaker() would open.
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    assert cli.main(["backtest-forecasts"]) == 1
    err = capsys.readouterr().err
    assert f"stored scores of backtest run {backtest_run.id}" in err and "Refusing to write" in err
    assert db.scalar(sa.select(sa.func.count()).select_from(BacktestForecast)) == 0
