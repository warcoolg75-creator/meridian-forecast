"""Phase 5b reads: /forecasts/overview, /forecasts/oracle-test, /forecasts/{sku}?horizon,
/forecasts/{sku}/csv, /forecasts/{sku}/context and /backtest/report."""

import csv
import io
from datetime import date, timedelta

import pytest

from app.api.v1 import backtest as backtest_api
from app.models import BacktestForecast, CalendarEvent, EventType
from tests.conftest import add_daily
from tests.test_forecast_api import CUTOFF, runs  # noqa: F401 (the fixture)

FORWARD = {
    "weeks": ["2026-10-05", "2027-03-29"],
    "pooled": {"skus": ["FDS-GFB-1KG", "IND-BRG-6205"], "champion_wape": 0.07, "naive_wape": 0.2, "skill": 0.65},
    "festive_pooled": {"skus": ["FDS-GFB-1KG"], "champion_wape": 0.09, "naive_wape": 0.18, "skill": 0.5},
}


@pytest.fixture
def page(db, ids, runs):  # noqa: F811
    backtest, production = runs
    backtest.params = {**backtest.params, "held_out_start": "2026-07-06", "xyz": [
        {"sku": "FDS-GFB-1KG", "volume_xyz": "Z", "error_cv": 0.61, "error_xyz": "Y"},
        {"sku": "IND-BRG-6205", "volume_xyz": "X", "error_cv": 0.2, "error_xyz": "X"}]}
    production.params = {**production.params, "backtest_run_id": backtest.id, "forward_oracle": FORWARD}
    pid = ids["product"]
    # The same weeks last year (364 days before w/c 2026-10-05, 10-12, 10-19), for the Gift Box only.
    add_daily(db, ids, [(date(2025, 10, 6) + timedelta(weeks=k), "FDS-GFB-1KG", "IN-DL-NDL", "retail", 50, 500_00)
                        for k in range(3)])
    db.add_all([
        CalendarEvent(date=date(2026, 10, 20), end_date=date(2026, 10, 20), name="Dussehra",
                      event_type=EventType.PUBLIC_HOLIDAY),
        CalendarEvent(date=date(2026, 10, 14), end_date=date(2026, 10, 14), name="Some promotion",
                      event_type=EventType.PROMOTION, product_id=pid["FDS-GFB-1KG"]),
        CalendarEvent(date=date(2027, 1, 26), end_date=date(2027, 1, 26), name="Outside the horizon",
                      event_type=EventType.PUBLIC_HOLIDAY),
    ])
    db.add_all(BacktestForecast(run_id=backtest.id, product_id=pid["FDS-GFB-1KG"], origin=date(2026, 6, 15),
                                horizon=h, week=date(2026, 6, 15) + timedelta(weeks=h - 1), model="prophet",
                                actual=100 + h, p50=99.5 + h, lo80=80.25, hi80=120.75, lo95=70.0, hi95=130.0)
               for h in range(1, 5))
    db.commit()
    return runs


def test_overview_is_its_own_route_not_a_sku(signed_in, page):
    response = signed_in.get("/api/v1/forecasts/overview")
    assert response.status_code == 200, response.text  # not "No forecast for sku: overview"
    body = response.json()
    assert body["run"]["kind"] == "production" and body["models"] == ["lightgbm", "prophet"]
    assert (body["abc_from"], body["abc_to"]) == ("2025-10-06", "2026-10-04")
    rows = {r["sku"]: r for r in body["items"]}
    gift = rows["FDS-GFB-1KG"]
    # The fixture has horizons 1-3 only: 102 + 103 + 104.
    assert (gift["next_4"], gift["next_13"], gift["last_year_4"]) == (309, 309, 150)
    assert gift["change_4"] == pytest.approx(309 / 150 - 1)
    assert gift["skill"] == pytest.approx(0.5)  # 1 - 0.20 / 0.40, the held-out champion row
    assert (gift["forecastability"], gift["error_cv"]) == ("Y", 0.61)
    assert gift["abc"] == "A"  # the only SKU with revenue in the 52 weeks
    fryer = rows["KIT-AFR-45"]
    assert fryer["short_history"] is True and fryer["change_4"] is None and fryer["last_year_4"] is None
    assert "Launched 8 Feb 2026" in fryer["no_comparison_reason"]
    assert fryer["skill"] is None and fryer["forecastability"] is None


def test_horizon_limits_the_weeks_and_the_csv_equals_the_json(signed_in, page):
    for horizon in (4, 13, 26):
        body = signed_in.get("/api/v1/forecasts/FDS-GFB-1KG", params={"horizon": horizon}).json()
        response = signed_in.get("/api/v1/forecasts/FDS-GFB-1KG/csv", params={"horizon": horizon})
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
        assert f"forecast-FDS-GFB-1KG-{horizon}w.csv" in response.headers["content-disposition"]
        rows = list(csv.DictReader(io.StringIO(response.text)))
        forecast = body["forecast"]
        assert [{"sku": forecast["sku"], "model": forecast["model"], **{k: str(v) for k, v in w.items()}}
                for w in forecast["weeks"]] == rows
    two = signed_in.get("/api/v1/forecasts/IND-BRG-6205", params={"horizon": 4}).json()["forecast"]["weeks"]
    assert [w["horizon"] for w in two] == [1, 2, 3]
    assert signed_in.get("/api/v1/forecasts/IND-BRG-6205", params={"horizon": 5}).status_code == 422
    assert signed_in.get("/api/v1/forecasts/NOPE/csv").status_code == 404


def test_horizon_applies_to_the_allocation_too(signed_in, page):
    body = signed_in.get("/api/v1/forecasts/FDS-GFB-1KG", params={"view": "channel", "horizon": 4}).json()
    assert all(len(g["weeks"]) == len(body["forecast"]["weeks"]) for g in body["allocation"]["groups"])


def test_context(signed_in, page):
    body = signed_in.get("/api/v1/forecasts/FDS-GFB-1KG/context").json()
    assert body["held_out_from"] == "2026-07-06" and body["short_history"] is False
    assert len(body["actuals"]) == 52
    assert body["actuals"][-1] == {"week": "2026-09-28", "units": 100}
    assert body["actuals"][0]["week"] == "2025-10-06" and body["actuals"][0]["units"] == 50
    # Holidays and festivals inside the horizon only; no promotions.
    assert [(e["name"], e["week"]) for e in body["events"]] == [("Dussehra", "2026-10-19")]
    accuracy = body["accuracy"]
    assert accuracy["model"] == "prophet" and accuracy["wape"] == 0.2 and accuracy["baseline_wape"] == 0.4
    assert accuracy["skill"] == pytest.approx(0.5) and accuracy["coverage_80"] == 0.9
    past = body["past_forecasts"]
    assert [p["weeks_before"] for p in past] == [1, 2, 3, 4]
    assert past[0] == {"week": "2026-06-15", "origin": "2026-06-15", "weeks_before": 1, "actual": 101,
                       "p50": 100.5, "lo80": 80.25, "hi80": 120.75}
    fryer = signed_in.get("/api/v1/forecasts/KIT-AFR-45/context").json()
    assert fryer["short_history"] is True and fryer["past_forecasts"] == []
    assert fryer["accuracy"]["baseline_wape"] is None and fryer["accuracy"]["skill"] is None
    launched = [a for a in fryer["actuals"] if a["units"] is not None]
    assert launched[0]["week"] == "2026-02-02"  # the Monday of the launch week; earlier weeks are null


def test_oracle_test(signed_in, page):
    response = signed_in.get("/api/v1/forecasts/oracle-test")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["festive"] == FORWARD["festive_pooled"] and body["pooled"] == FORWARD["pooled"]
    assert (body["weeks_from"], body["weeks_to"]) == ("2026-10-05", "2027-03-29")


def test_report_serves_the_one_file(signed_in, tmp_path, monkeypatch):
    path = tmp_path / "backtest-report.md"
    monkeypatch.setattr(backtest_api, "REPORT_PATH", path)
    assert signed_in.get("/api/v1/backtest/report").status_code == 404
    path.write_text("# Backtest report\n\nWAPE 13.6%\n", encoding="utf-8")
    response = signed_in.get("/api/v1/backtest/report")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/markdown")
    assert response.text == "# Backtest report\n\nWAPE 13.6%\n"
    assert signed_in.get("/api/v1/backtest/report/../../.env").status_code == 404  # no path parameter


def test_the_new_endpoints_need_sign_in(client, page):
    for path in ("/api/v1/forecasts/overview", "/api/v1/forecasts/oracle-test", "/api/v1/forecasts/FDS-GFB-1KG/csv",
                 "/api/v1/forecasts/FDS-GFB-1KG/context", "/api/v1/backtest/report"):
        assert client.get(path).status_code == 401, path
