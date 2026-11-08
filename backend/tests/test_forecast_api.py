"""GET /api/v1/forecasts, /forecasts/{sku}, /backtest/metrics, /backtest/leaderboard."""

from datetime import date, timedelta

import pytest

from app.models import BacktestMetric, Forecast, ForecastRun, ForecastRunKind, MetricWindow, ShockScope
from app.models.base import utcnow
from tests.conftest import add_daily

CUTOFF = date(2026, 9, 28)  # Monday of the last training week


@pytest.fixture
def runs(db, ids):
    pid = ids["product"]
    backtest = ForecastRun(
        kind=ForecastRunKind.BACKTEST, model="all", data_end_date=date(2026, 10, 8), training_cutoff=CUTOFF,
        trained_at=utcnow(), params={"champions": {"FDS-GFB-1KG": "prophet", "IND-BRG-6205": "lightgbm",
                                                   "KIT-AFR-45": "lightgbm"},
                                     "headline_skus": ["FDS-GFB-1KG", "IND-BRG-6205"],
                                     "short_history_skus": ["KIT-AFR-45"]},
        library_versions={"lightgbm": "4.7.0"}, random_seed=42, duration_seconds=1.0)
    production = ForecastRun(
        kind=ForecastRunKind.PRODUCTION, model="champion", data_end_date=date(2026, 10, 8), training_cutoff=CUTOFF,
        trained_at=utcnow(), params={"short_history_skus": ["KIT-AFR-45"],
                                     "assumptions": {"promotions": "none planned after the data end",
                                                     "supply_shocks": "never forecast"}},
        library_versions={"lightgbm": "4.7.0"}, random_seed=42, duration_seconds=1.0)
    db.add_all([backtest, production])
    db.flush()
    for sku, model, base in (("FDS-GFB-1KG", "prophet", 101), ("IND-BRG-6205", "lightgbm", 5000),
                             ("KIT-AFR-45", "lightgbm", 37)):
        for h in (1, 2, 3):
            db.add(Forecast(run_id=production.id, product_id=pid[sku], week=CUTOFF + timedelta(weeks=h), horizon=h,
                            model=model, p50=base + h, lo80=base, hi80=base + 10, lo95=base - 5, hi95=base + 20))
    metrics = [
        # model, sku, window, shocks, horizon, wape, coverage_80
        ("seasonal_naive", None, "held_out", "included", None, 0.30, 0.70),
        ("prophet", None, "held_out", "included", None, 0.15, 0.80),
        ("champion", None, "held_out", "included", None, 0.18, 0.78),
        ("seasonal_naive", "FDS-GFB-1KG", "held_out", "included", None, 0.40, 0.60),
        ("seasonal_naive", "IND-BRG-6205", "held_out", "included", None, 0.20, 0.75),
        ("prophet", "FDS-GFB-1KG", "held_out", "included", None, 0.20, 0.90),
        ("prophet", "IND-BRG-6205", "held_out", "included", None, 0.19, 0.80),
        ("champion", "FDS-GFB-1KG", "held_out", "included", None, 0.20, 0.90),
        ("champion", "IND-BRG-6205", "held_out", "included", None, 0.22, 0.70),
        ("champion", "KIT-AFR-45", "held_out", "included", None, 0.30, 0.40),
        ("champion", None, "held_out", "included", 4, 0.25, 0.75),
        ("champion", None, "selection", "included", None, 0.12, None),
    ]
    db.add_all(BacktestMetric(run_id=backtest.id, model=m, product_id=pid[s] if s else None, window=MetricWindow(w),
                              shocks=ShockScope(sh), horizon=h, n_weeks=84, wape=wp, bias=-0.01, mase=0.7,
                              coverage_80=c, coverage_95=None if c is None else 0.95)
               for m, s, w, sh, h, wp, c in metrics)
    # 13 weeks of sales for the allocation shares: Mumbai and Pune are in Maharashtra.
    rows = []
    for k in range(13):
        day = CUTOFF - timedelta(weeks=k)
        rows += [(day, "FDS-GFB-1KG", "IN-MH-MUM", "retail", 30, 0), (day, "FDS-GFB-1KG", "IN-MH-PUN", "direct", 10, 0),
                 (day, "FDS-GFB-1KG", "IN-DL-NDL", "retail", 60, 0)]
    rows.append((CUTOFF - timedelta(weeks=13), "FDS-GFB-1KG", "IN-DL-NDL", "retail", 999, 0))  # before the window
    add_daily(db, ids, rows)
    db.commit()
    return backtest, production


def test_latest_forecast_for_every_sku(signed_in, runs):
    body = signed_in.get("/api/v1/forecasts").json()
    assert body["run"]["kind"] == "production" and body["run"]["training_cutoff"] == "2026-09-28"
    assert body["assumptions"]["supply_shocks"] == "never forecast"
    assert [i["sku"] for i in body["items"]] == ["FDS-GFB-1KG", "IND-BRG-6205", "KIT-AFR-45"]
    gift = body["items"][0]
    assert gift["model"] == "prophet" and gift["short_history"] is False
    assert gift["weeks"][0] == {"week": "2026-10-05", "horizon": 1, "p50": 102, "lo80": 101, "hi80": 111,
                                "lo95": 96, "hi95": 121}
    assert body["items"][2]["short_history"] is True
    only = signed_in.get("/api/v1/forecasts", params={"skus": ["IND-BRG-6205"]}).json()["items"]
    assert [i["sku"] for i in only] == ["IND-BRG-6205"]


def test_one_sku_allocated_by_state_and_channel(signed_in, runs):
    body = signed_in.get("/api/v1/forecasts/FDS-GFB-1KG", params={"view": "state"}).json()
    allocation = body["allocation"]
    assert allocation["allocated"] is True and allocation["view"] == "state"
    assert (allocation["share_from"], allocation["share_to"]) == ("2026-07-06", "2026-10-04")
    shares = {g["code"]: g["share"] for g in allocation["groups"]}
    assert shares == {"IN-DL": pytest.approx(0.6), "IN-MH": pytest.approx(0.4)}  # the week before the window is out
    for i, week in enumerate(body["forecast"]["weeks"]):
        assert sum(g["weeks"][i]["p50"] for g in allocation["groups"]) == week["p50"]  # adds up exactly
    channels = signed_in.get("/api/v1/forecasts/FDS-GFB-1KG", params={"view": "channel"}).json()["allocation"]
    assert {g["code"]: g["share"] for g in channels["groups"]} == {"direct": pytest.approx(0.1),
                                                                   "retail": pytest.approx(0.9)}
    plain = signed_in.get("/api/v1/forecasts/FDS-GFB-1KG").json()
    assert plain["allocation"] is None


def test_forecast_errors(signed_in, client, runs):
    assert signed_in.get("/api/v1/forecasts/NOPE").status_code == 404
    assert signed_in.get("/api/v1/forecasts/FDS-GFB-1KG", params={"view": "city"}).status_code == 422
    client.headers.pop("Authorization", None)
    for path in ("/api/v1/forecasts", "/api/v1/forecasts/FDS-GFB-1KG", "/api/v1/backtest/metrics",
                 "/api/v1/backtest/leaderboard"):
        assert client.get(path).status_code == 401


def test_no_runs_yet_is_a_404_that_says_what_to_run(signed_in):
    response = signed_in.get("/api/v1/forecasts")
    assert response.status_code == 404 and "make backtest" in response.json()["detail"]
    assert signed_in.get("/api/v1/backtest/leaderboard").status_code == 404


def test_backtest_metrics_filter(signed_in, runs):
    body = signed_in.get("/api/v1/backtest/metrics", params={"model": "champion", "window": "held_out"}).json()
    assert body["run"]["kind"] == "backtest"
    assert len(body["items"]) == 5
    assert body["items"][0]["sku"] is None and body["items"][0]["horizon"] is None  # pooled rows first
    by_sku = signed_in.get("/api/v1/backtest/metrics", params={"sku": "KIT-AFR-45"}).json()["items"]
    assert [r["coverage_80"] for r in by_sku] == [0.4]
    h4 = signed_in.get("/api/v1/backtest/metrics", params={"horizon": 4}).json()["items"]
    assert [(r["model"], r["wape"]) for r in h4] == [("champion", 0.25)]


def test_leaderboard_has_pooled_and_median_per_sku_skill(signed_in, runs):
    body = signed_in.get("/api/v1/backtest/leaderboard").json()
    assert body["target_skill"] == 0.15 and body["headline_skus"] == ["FDS-GFB-1KG", "IND-BRG-6205"]
    models = {m["model"]: m for m in body["models"]}
    assert [m["model"] for m in body["models"]] == ["prophet", "champion", "seasonal_naive"]  # by WAPE
    assert models["prophet"]["skill"] == pytest.approx(0.5)
    # Per SKU: gift box 1 - 0.20/0.40 = 0.5, bearing 1 - 0.19/0.20 = 0.05; median 0.275.
    assert models["prophet"]["median_sku_skill"] == pytest.approx(0.275)
    assert models["seasonal_naive"]["skill"] is None
    champions = {c["sku"]: c for c in body["champions"]}
    assert champions["IND-BRG-6205"]["skill"] == pytest.approx(-0.1)
    assert champions["KIT-AFR-45"]["short_history"] is True and champions["KIT-AFR-45"]["skill"] is None
    selection = signed_in.get("/api/v1/backtest/leaderboard", params={"window": "selection"}).json()
    assert [m["model"] for m in selection["models"]] == ["champion"]
