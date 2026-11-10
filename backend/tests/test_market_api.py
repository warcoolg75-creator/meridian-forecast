"""The market endpoints: /market/overview, /sources, /series, /headlines, /products/{sku}/market.

Data comes from a backfill replayed from the recorded fixtures (tests/signals_fixture.py).
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update

from app.models import (FetchStatus, NewsItem, NewsItemCategory, Product, SignalObservation, SignalSeries,
                        SignalSource, UserRole)
from app.schemas.market import CONTEXT_NOTE, SHAPES_NOTE
from tests.conftest import add_reference_data
from tests.signals_fixture import recording, runner

ENDPOINTS = ["/api/v1/market/overview", "/api/v1/market/sources",
             "/api/v1/market/series?keys=weather.tmax.IN-DL-NDL", "/api/v1/market/headlines?category=Kitchen%20Appliances",
             "/api/v1/products/COL-ACL-70/market"]


@pytest.fixture
def loaded(engine, db, tmp_path):
    add_reference_data(db)
    db.add(Product(sku="COL-ACL-70", name="Desert Air Cooler 70L", category="Cooling", subcategory="Air Coolers",
                   unit_cost_minor=1, unit_price_minor=2, unit_of_measure="each", shelf_life_days=None,
                   is_active=True, launched_on=date(2015, 1, 1)))
    db.commit()
    runner(engine, tmp_path).run()
    # The fixtures were recorded at a fixed time; judge freshness as of then.
    now, _ = recording()
    db.execute(update(SignalSource).values(last_success_at=datetime.now(UTC), last_attempt_at=datetime.now(UTC)))
    db.execute(update(SignalSeries).where(SignalSeries.last_success_at == now)
               .values(last_success_at=datetime.now(UTC)))
    db.commit()
    return db


@pytest.mark.parametrize("path", ENDPOINTS)
def test_market_endpoints_need_sign_in(client, path):
    assert client.get(path).status_code == 401


def test_overview_maps_series_to_categories_with_status_and_reasons(client, auth_headers, loaded):
    response = client.get("/api/v1/market/overview", headers=auth_headers(UserRole.VIEWER))
    assert response.status_code == 200
    body = response.json()
    assert body["note"] == CONTEXT_NOTE
    assert body["sales_first_date"] is None  # no sales rows in this test database
    cooling = next(c for c in body["categories"] if c["category"] == "Cooling")
    demand = {m["series"]["key"]: m for m in cooling["demand_context"]}
    cost = {m["series"]["key"]: m for m in cooling["input_cost"]}
    tmax = demand["weather.tmax.IN-DL-NDL"]["series"]
    assert tmax["forecast_key"] == "weather.tmax_forecast.IN-DL-NDL"
    assert tmax["unit"] == "°C" and tmax["source"] == "open_meteo" and tmax["status"] == "fresh"
    assert tmax["first_observed_on"] == recording()[1].isoformat()
    assert "Open-Meteo" in tmax["attribution"]
    assert "weather.tmax_forecast.IN-DL-NDL" not in demand  # forecasts ride along, never mapped themselves
    assert demand["wiki.Evaporative_cooler"]["reason"].endswith("not Indian search.")
    assert set(cost) == {"fred.PCOPPUSDM", "fred.DCOILBRENTEU"}
    assert all(m["series"]["role"] == "input_cost" for m in cost.values())
    assert cost["fred.PCOPPUSDM"]["series"]["citation"].startswith("Source: International Monetary Fund")
    assert {s["code"] for s in body["sources"]} == {"open_meteo", "fred", "wikimedia", "gdelt"}


def test_a_series_not_refreshed_in_time_is_stale_and_a_missing_key_is_not_configured(client, auth_headers, loaded):
    old = datetime.now(UTC) - timedelta(days=5)
    loaded.execute(update(SignalSeries).where(SignalSeries.key == "weather.tmax.IN-DL-NDL")
                   .values(last_success_at=old))
    loaded.execute(update(SignalSource).where(SignalSource.code == "fred")
                   .values(last_status=FetchStatus.NOT_CONFIGURED))
    loaded.execute(update(SignalSeries).where(SignalSeries.key.like("fred.%")).values(last_success_at=None))
    loaded.commit()
    body = client.get("/api/v1/market/overview", headers=auth_headers(UserRole.VIEWER)).json()
    series = {m["series"]["key"]: m["series"] for c in body["categories"] for m in c["demand_context"] + c["input_cost"]}
    assert series["weather.tmax.IN-DL-NDL"]["status"] == "stale"
    assert series["weather.tmax.IN-DL-NDL"]["status_reason"] == "Not refreshed for 5 days."
    assert series["weather.tmax.IN-TN-CHE"]["status"] == "fresh"
    assert series["fred.PCOPPUSDM"]["status"] == "not_configured"
    assert {s["code"]: s["status"] for s in body["sources"]}["fred"] == "not_configured"


def test_series_values_are_aggregated_in_the_database(client, auth_headers, loaded):
    keys = ["weather.tmax.IN-DL-NDL", "weather.rain.IN-DL-NDL", "fred.PCOPPUSDM", "weather.tmax_forecast.IN-DL-NDL"]
    headers = auth_headers(UserRole.VIEWER)
    response = client.get("/api/v1/market/series", params={"keys": keys, "granularity": "week"}, headers=headers)
    assert response.status_code == 200
    items = {i["key"]: i for i in response.json()["items"]}
    assert list(items) == keys
    tmax, rain = items["weather.tmax.IN-DL-NDL"], items["weather.rain.IN-DL-NDL"]
    assert tmax["granularity"] == "week" and tmax["aggregation"] == "mean" and rain["aggregation"] == "sum"
    assert all(date.fromisoformat(p["period_start"]).weekday() == 0 for p in tmax["points"])
    assert items["fred.PCOPPUSDM"]["granularity"] == "month"  # never finer than its own frequency
    assert items["weather.tmax_forecast.IN-DL-NDL"]["is_forecast"] is True

    def daily(key):
        series = loaded.scalars(select(SignalSeries).where(SignalSeries.key == key)).one()
        return dict(loaded.execute(select(SignalObservation.observed_on, SignalObservation.value)
                                   .where(SignalObservation.series_id == series.id)).all())

    full_week = next(p for p in tmax["points"] if p["days"] == 7)
    start = date.fromisoformat(full_week["period_start"])
    days = [start + timedelta(days=i) for i in range(7)]
    assert full_week["value"] == pytest.approx(sum(daily("weather.tmax.IN-DL-NDL")[d] for d in days) / 7, abs=1e-3)
    week_rain = next(p for p in rain["points"] if p["period_start"] == full_week["period_start"])
    assert week_rain["value"] == pytest.approx(sum(daily("weather.rain.IN-DL-NDL")[d] for d in days), abs=1e-3)

    day = client.get("/api/v1/market/series", params={"keys": keys[0], "granularity": "day",
                                                      "date_from": days[0].isoformat(), "date_to": days[2].isoformat()},
                     headers=headers).json()["items"][0]
    assert [p["period_start"] for p in day["points"]] == [d.isoformat() for d in days[:3]]


def test_series_requests_are_checked(client, auth_headers, loaded):
    headers = auth_headers(UserRole.VIEWER)
    assert client.get("/api/v1/market/series", params={"keys": "nope"}, headers=headers).status_code == 404
    assert client.get("/api/v1/market/series", headers=headers).status_code == 422
    assert client.get("/api/v1/market/series", params={"keys": ["weather.tmax.IN-DL-NDL"] * 41},
                      headers=headers).status_code == 422
    assert client.get("/api/v1/market/series", params={"keys": "weather.tmax.IN-DL-NDL", "granularity": "year"},
                      headers=headers).status_code == 422
    assert client.get("/api/v1/market/series", params={"keys": "weather.tmax.IN-DL-NDL", "date_from": "2026-10-02",
                                                       "date_to": "2026-10-01"}, headers=headers).status_code == 422


def test_headlines_newest_first_with_publisher_and_link(client, auth_headers, loaded):
    headers = auth_headers(UserRole.VIEWER)
    body = client.get("/api/v1/market/headlines", params={"category": "Kitchen Appliances", "limit": 3},
                      headers=headers).json()
    assert body["category"] == "Kitchen Appliances" and body["total"] >= len(body["items"]) > 0
    assert len(body["items"]) <= 3
    stamps = [i["published_at"] for i in body["items"]]
    assert stamps == sorted(stamps, reverse=True)
    for item in body["items"]:
        assert item["url"].startswith(("http://", "https://")) and item["title"] and item["publisher"]
    assert body["source"]["code"] == "gdelt" and "GDELT" in body["source"]["attribution"]
    assert client.get("/api/v1/market/headlines", params={"category": "Toys"}, headers=headers).status_code == 404
    assert client.get("/api/v1/market/headlines", params={"category": "Kitchen Appliances", "limit": 51},
                      headers=headers).status_code == 422


def test_product_market_lists_its_mapped_signals_with_both_notes(client, auth_headers, loaded):
    headers = auth_headers(UserRole.VIEWER)
    body = client.get("/api/v1/products/COL-ACL-70/market", headers=headers).json()
    assert body["note"] == CONTEXT_NOTE and body["shapes_note"] == SHAPES_NOTE
    assert body["category"] == "Cooling"
    demand = [m["series"]["key"] for m in body["demand_context"]]
    assert demand[:1] == ["weather.tmax.IN-DL-NDL"]  # the trimmed catalog keeps New Delhi of its three cities
    assert "wiki.Evaporative_cooler" in demand
    assert [m["series"]["key"] for m in body["input_cost"]] == ["fred.PCOPPUSDM"]
    assert client.get("/api/v1/products/NOPE-1/market", headers=headers).status_code == 404


def test_a_product_with_no_mapping_gets_empty_lists(client, auth_headers, loaded):
    body = client.get("/api/v1/products/COL-OLD-300/market", headers=auth_headers(UserRole.VIEWER)).json()
    assert body["demand_context"] == [] and body["input_cost"] == []


def test_news_whose_last_run_stopped_early_is_partial_while_headlines_are_stored(client, auth_headers, loaded):
    headers = auth_headers(UserRole.VIEWER)
    gdelt = update(SignalSource).where(SignalSource.code == "gdelt")
    error = ("Kitchen Appliances 20231009000000-20240101000000: HTTP 429: Please limit requests ... from "
             "https://api.gdeltproject.org/api/v2/doc/doc?query=x; Stopped: GDELT is rate-limiting this address.")
    for status in (FetchStatus.PARTIAL, FetchStatus.FAILED):
        loaded.execute(gdelt.values(last_status=status, last_error=error))
        loaded.commit()
        body = client.get("/api/v1/market/headlines", params={"category": "Cooling"}, headers=headers).json()
        assert body["total"] == 0  # this category has none, but the news source as a whole has some
        assert body["source"]["status"] == "partial"
        assert "stopped at GDELT's rate limit (HTTP 429)" in body["source"]["status_reason"]
        assert "gdeltproject" not in body["source"]["status_reason"]  # written for the page, not GDELT's text
        sources = client.get("/api/v1/market/overview", headers=headers).json()["sources"]
        assert {s["code"]: s["status"] for s in sources}["gdelt"] == "partial"
    # Nothing stored at all: there is nothing partial to show, so it is stale.
    loaded.execute(delete(NewsItemCategory))
    loaded.execute(delete(NewsItem))
    loaded.commit()
    body = client.get("/api/v1/market/headlines", params={"category": "Cooling"}, headers=headers).json()
    assert body["source"]["status"] == "stale"


def test_other_sources_whose_last_run_was_incomplete_are_stale(client, auth_headers, loaded):
    loaded.execute(update(SignalSource).where(SignalSource.code == "wikimedia").values(
        last_status=FetchStatus.PARTIAL, last_error="wiki.Diwali: HTTP 503"))
    loaded.commit()
    sources = client.get("/api/v1/market/overview", headers=auth_headers(UserRole.VIEWER)).json()["sources"]
    wikimedia = next(s for s in sources if s["code"] == "wikimedia")
    assert wikimedia["status"] == "stale" and "was incomplete: wiki.Diwali: HTTP 503" in wikimedia["status_reason"]


def test_status_reasons_show_hosts_not_long_urls(client, auth_headers, loaded):
    url = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/" + "x" * 400
    loaded.execute(update(SignalSource).where(SignalSource.code == "wikimedia").values(
        last_status=FetchStatus.FAILED, last_error=f"wiki.Diwali: HTTP 404: Not found from {url}"))
    loaded.commit()
    body = client.get("/api/v1/market/overview", headers=auth_headers(UserRole.VIEWER)).json()
    wikimedia = next(s for s in body["sources"] if s["code"] == "wikimedia")
    assert wikimedia["status"] == "stale" and "from wikimedia.org" in wikimedia["status_reason"]
    assert "x" * 50 not in wikimedia["status_reason"] and "x" * 50 not in wikimedia["last_error"]
