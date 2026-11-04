"""GET /api/v1/analytics/*: figures, comparison windows, filters, ABC-XYZ, events, auth.

The dataset: four weeks (Mon 3 Mar - Sun 30 Mar 2025) and the same days 52 weeks earlier
(Mon 4 Mar - Sun 31 Mar 2024), three cells a day. Expected values are recomputed in the
tests from the same per-day figures, not copied from the API.
"""

import statistics
from datetime import date, timedelta

import pytest

from app.models import CalendarEvent, LineCapability, Plant, Product, ProductionLine
from tests.conftest import add_daily, add_order

PERIOD = (date(2025, 3, 3), date(2025, 3, 30))
LAST_YEAR = (date(2024, 3, 4), date(2024, 3, 31))
COST = 100  # unit_cost_minor of every test product (conftest)

# cell -> (units, revenue) per day, this year and last year
CELLS = {
    ("FDS-GFB-1KG", "IN-MH-MUM", "retail"): ((2, 2000), (1, 1000)),
    ("FDS-GFB-1KG", "IN-MH-PUN", "distributor"): ((1, 900), (1, 900)),
    ("IND-BRG-6205", "IN-DL-NDL", "direct"): ((10, 1850), (10, 1850)),
}
DAYS = 28


def days(first: date, n: int = DAYS) -> list[date]:
    return [first + timedelta(days=k) for k in range(n)]


@pytest.fixture
def data(db, ids):
    rows = []
    for (sku, region, channel), (now, before) in CELLS.items():
        rows += [(d, sku, region, channel, *now) for d in days(PERIOD[0])]
        rows += [(d, sku, region, channel, *before) for d in days(LAST_YEAR[0])]
    add_daily(db, ids, rows)
    # Orders: 2 this period (one with two lines), 1 last year.
    add_order(db, ids, date(2025, 3, 5), "C09", "IN-DL-NDL", "retail",
              [("FDS-GFB-1KG", 1, 1000, 0), ("IND-BRG-6205", 2, 185, 0)])
    add_order(db, ids, date(2025, 3, 6), "C01", "IN-MH-MUM", "distributor", [("FDS-GFB-1KG", 1, 900, 0)])
    add_order(db, ids, date(2024, 3, 6), "C01", "IN-MH-MUM", "distributor", [("FDS-GFB-1KG", 1, 900, 0)])
    return ids


def get(client, path, **params):
    params.setdefault("date_from", PERIOD[0].isoformat())
    params.setdefault("date_to", PERIOD[1].isoformat())
    response = client.get(f"/api/v1/analytics/{path}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def expected(cells=CELLS, year: int = 0):
    units = sum(c[year][0] for c in cells.values()) * DAYS
    revenue = sum(c[year][1] for c in cells.values()) * DAYS
    return units, revenue, revenue - units * COST


# --------------------------------------------------------------------------- summary


def test_summary_against_same_period_last_year(signed_in, data):
    body = get(signed_in, "summary")
    units, revenue, margin = expected()
    b_units, b_revenue, b_margin = expected(year=1)
    assert body["period"] == {"date_from": "2025-03-03", "date_to": "2025-03-30", "days": 28, "days_with_data": 28}
    assert body["comparison"] == {"date_from": "2024-03-04", "date_to": "2024-03-31", "days": 28,
                                  "days_with_data": 28, "mode": "same_period_last_year", "shift_days": 364,
                                  "complete": True}
    assert body["current"] == {"revenue_minor": revenue, "units": units, "orders": 2, "gross_margin_minor": margin,
                               "average_selling_price_minor": round(revenue / units),
                               "margin_rate": pytest.approx(margin / revenue)}
    assert (body["baseline"]["revenue_minor"], body["baseline"]["units"], body["baseline"]["orders"]) == (
        b_revenue, b_units, 1)
    assert body["change"]["revenue"] == pytest.approx(revenue / b_revenue - 1)
    assert body["change"]["gross_margin"] == pytest.approx(margin / b_margin - 1)
    assert body["change"]["orders"] == pytest.approx(1.0)


def test_orders_are_distinct_orders_not_lines(signed_in, data):
    # The first order has two product lines; filtering on one of its products still counts it once.
    assert get(signed_in, "summary")["current"]["orders"] == 2
    assert get(signed_in, "summary", skus="IND-BRG-6205")["current"]["orders"] == 1


def test_previous_period_and_incomplete_comparisons(signed_in, data):
    body = get(signed_in, "summary", comparison="previous_period")
    assert (body["comparison"]["date_from"], body["comparison"]["date_to"]) == ("2025-02-03", "2025-03-02")
    assert body["comparison"]["complete"] and body["baseline"]["revenue_minor"] == 0
    assert body["change"]["revenue"] is None  # nothing to compare with

    early = get(signed_in, "summary", date_from="2024-03-04", date_to="2024-03-31")
    assert early["comparison"]["complete"] is False  # a year before the history starts
    assert all(value is None for value in early["change"].values())


def test_state_filter_includes_its_cities_and_channel_filter(signed_in, data):
    mh = {k: v for k, v in CELLS.items() if k[1].startswith("IN-MH")}
    units, revenue, _ = expected(mh)
    state = get(signed_in, "summary", regions="IN-MH")["current"]
    assert (state["units"], state["revenue_minor"]) == (units, revenue)

    retail = {k: v for k, v in CELLS.items() if k[2] == "retail"}
    units, revenue, _ = expected(retail)
    body = get(signed_in, "summary", channels="retail")["current"]
    assert (body["units"], body["revenue_minor"]) == (units, revenue)


def test_a_range_past_the_history_is_clipped(signed_in, data):
    body = get(signed_in, "summary", date_from="2025-03-03", date_to="2025-12-31")
    assert body["period"]["date_to"] == "2025-03-30"
    assert body["current"]["revenue_minor"] == expected()[1]


# --------------------------------------------------------------------------- timeseries


def test_weekly_series_with_aligned_comparison(signed_in, data):
    body = get(signed_in, "timeseries")
    week_units = sum(c[0][0] for c in CELLS.values()) * 7
    base_units = sum(c[1][0] for c in CELLS.values()) * 7
    assert [p["period_start"] for p in body["points"]] == ["2025-03-03", "2025-03-10", "2025-03-17", "2025-03-24"]
    assert all(p["units"] == week_units and p["baseline_units"] == base_units and not p["is_partial"]
               for p in body["points"])


def test_partial_edge_buckets(signed_in, data):
    body = get(signed_in, "timeseries", date_from="2025-03-05", date_to="2025-03-18")  # Wed .. Tue
    per_day = sum(c[0][0] for c in CELLS.values())
    assert [(p["period_start"], p["days_covered"], p["is_partial"], p["units"]) for p in body["points"]] == [
        ("2025-03-03", 5, True, 5 * per_day),
        ("2025-03-10", 7, False, 7 * per_day),
        ("2025-03-17", 2, True, 2 * per_day),
    ]
    assert body["points"][0]["baseline_units"] == 5 * sum(c[1][0] for c in CELLS.values())


def test_comparison_coverage_per_bucket_follows_history_and_launch(signed_in, data, db, ids):
    # All products: history starts with the data (4 Mar 2024), so every week compares whole.
    body = get(signed_in, "timeseries")
    assert body["baseline_history"] == {"first_date": "2024-03-04", "starts_with": "data"}
    assert [p["baseline_days_covered"] for p in body["points"]] == [7, 7, 7, 7]

    # Filtered to a product that launched on Wed 20 Mar 2024, inside last year's window:
    # the weeks compared with days before its launch have no comparison, or a partial one.
    db.get(Product, ids["product"]["IND-BRG-6205"]).launched_on = date(2024, 3, 20)
    db.commit()
    body = get(signed_in, "timeseries", skus="IND-BRG-6205")
    assert body["baseline_history"] == {"first_date": "2024-03-20", "starts_with": "launch"}
    assert [(p["period_start"], p["days_covered"], p["baseline_days_covered"]) for p in body["points"]] == [
        ("2025-03-03", 7, 0),  # 4-10 Mar 2024: before the launch
        ("2025-03-10", 7, 0),
        ("2025-03-17", 7, 5),  # 18-24 Mar 2024: from the 20th, 5 of 7 days
        ("2025-03-24", 7, 7),
    ]
    # A product launched before the data starts changes nothing: history starts with the data.
    body = get(signed_in, "timeseries", skus="FDS-GFB-1KG")
    assert body["baseline_history"] == {"first_date": "2024-03-04", "starts_with": "data"}

    # The previous period of the first two weeks of data (19 Feb - 3 Mar 2024) lies before it.
    body = get(signed_in, "timeseries", date_from="2024-03-04", date_to="2024-03-17", comparison="previous_period")
    assert [p["baseline_days_covered"] for p in body["points"]] == [0, 0]


@pytest.mark.parametrize("granularity", ["day", "month"])
def test_day_and_month_series_sum_to_the_summary(signed_in, data, granularity):
    body = get(signed_in, "timeseries", granularity=granularity)
    summary = get(signed_in, "summary")
    assert sum(p["revenue_minor"] for p in body["points"]) == summary["current"]["revenue_minor"]
    assert sum(p["baseline_revenue_minor"] for p in body["points"]) == summary["baseline"]["revenue_minor"]
    assert len(body["points"]) == (28 if granularity == "day" else 1)


def test_moving_festivals_are_named(signed_in, data, db, ids):
    db.add_all([
        CalendarEvent(date=date(2025, 3, 14), end_date=date(2025, 3, 14), name="Holi", event_type="public_holiday"),
        CalendarEvent(date=date(2024, 3, 25), end_date=date(2024, 3, 25), name="Holi", event_type="public_holiday"),
        # Fixed date: 20 Mar both years is one day apart once shifted 364 days: not "moved".
        CalendarEvent(date=date(2025, 3, 20), end_date=date(2025, 3, 20), name="Fixed", event_type="public_holiday"),
        CalendarEvent(date=date(2024, 3, 20), end_date=date(2024, 3, 20), name="Fixed", event_type="public_holiday"),
        CalendarEvent(date=date(2025, 3, 10), end_date=date(2025, 3, 10), name="Delhi Fest", event_type="festival",
                      region_id=ids["region"]["IN-DL"]),
        CalendarEvent(date=date(2025, 3, 11), end_date=date(2025, 3, 11), name="Mumbai Fest", event_type="festival",
                      region_id=ids["region"]["IN-MH"]),
    ])
    db.commit()
    moved = get(signed_in, "timeseries")["moving_events"]
    assert {(e["name"], e["current_date"], e["comparison_date"], e["days_apart"]) for e in moved} == {
        ("Holi", "2025-03-14", "2024-03-25", -10),
        ("Delhi Fest", "2025-03-10", None, None),
        ("Mumbai Fest", "2025-03-11", None, None),
    }
    # A Mumbai view: the Maharashtra festival applies, the Delhi one does not.
    mumbai = get(signed_in, "timeseries", regions="IN-MH-MUM")["moving_events"]
    assert {e["name"] for e in mumbai} == {"Holi", "Mumbai Fest"}
    assert get(signed_in, "timeseries", comparison="previous_period")["moving_events"] == []


# --------------------------------------------------------------------------- products


def test_products_rank_share_growth_and_abc(signed_in, data):
    body = get(signed_in, "products")
    rows = {r["sku"]: r for r in body["rows"]}
    assert [r["sku"] for r in body["rows"]] == ["FDS-GFB-1KG", "IND-BRG-6205", "KIT-AFR-45"]  # inactive one omitted
    gfb_revenue = (2000 + 900) * DAYS
    total = expected()[1]
    assert rows["FDS-GFB-1KG"]["revenue_minor"] == gfb_revenue
    assert rows["FDS-GFB-1KG"]["share"] == pytest.approx(gfb_revenue / total)
    assert rows["FDS-GFB-1KG"]["growth"] == pytest.approx(gfb_revenue / ((1000 + 900) * DAYS) - 1)
    assert rows["FDS-GFB-1KG"]["gross_margin_minor"] == gfb_revenue - 3 * DAYS * COST
    assert [(r["rank"], r["abc"]) for r in body["rows"]] == [(1, "A"), (2, "A"), (3, "C")]
    assert body["classification"]["abc_a_share"] == 0.8 and body["classification"]["xyz_y_up_to"] == 1.0


def test_products_xyz_and_sparkline(signed_in, data):
    body = get(signed_in, "products")
    rows = {r["sku"]: r for r in body["rows"]}
    # XYZ window: full weeks inside the history (it starts Mon 4 Mar 2024) up to Sun 30 Mar 2025, at most 52.
    window = body["classification"]["xyz_window"]
    assert (window["date_from"], window["date_to"]) == ("2024-04-01", "2025-03-30")
    gfb = rows["FDS-GFB-1KG"]
    assert gfb["xyz_weeks"] == 52
    weekly = [0] * 48 + [21] * 4  # 52 weeks: last year's March falls before the window
    assert gfb["xyz_cv"] == pytest.approx(statistics.stdev(weekly) / statistics.fmean(weekly), abs=1e-4)
    assert gfb["xyz"] == "Z"
    assert gfb["sparkline"] == [0] * 9 + [21] * 4
    assert rows["KIT-AFR-45"]["xyz"] is None and rows["KIT-AFR-45"]["xyz_weeks"] == 0  # launches in 2026


def test_products_sort_on_the_server(signed_in, data):
    by_name = get(signed_in, "products", sort="name", order="asc")["rows"]
    assert [r["name"] for r in by_name] == sorted(r["name"] for r in by_name)
    by_growth = get(signed_in, "products", sort="growth", order="desc")["rows"]
    assert by_growth[-1]["growth"] is None  # no comparison revenue: always last


# --------------------------------------------------------------------------- regions and channels


def test_regions_by_state_and_city_drill_down(signed_in, data):
    states = get(signed_in, "regions")["rows"]
    mh_revenue, dl_revenue = (2000 + 900) * DAYS, 1850 * DAYS
    assert [(r["code"], r["revenue_minor"]) for r in states] == [("IN-MH", mh_revenue), ("IN-DL", dl_revenue)]
    assert states[0]["share"] == pytest.approx(mh_revenue / (mh_revenue + dl_revenue))

    cities = get(signed_in, "regions", level="city", parent="IN-MH")["rows"]
    assert [(r["code"], r["parent_code"], r["revenue_minor"]) for r in cities] == [
        ("IN-MH-MUM", "IN-MH", 2000 * DAYS), ("IN-MH-PUN", "IN-MH", 900 * DAYS)]
    assert sum(r["share"] for r in cities) == pytest.approx(1.0)


def test_channels_with_comparison_share(signed_in, data):
    rows = {r["channel"]: r for r in get(signed_in, "channels")["rows"]}
    assert rows["retail"]["revenue_minor"] == 2000 * DAYS
    assert rows["retail"]["baseline_share"] == pytest.approx(1000 / (1000 + 900 + 1850))
    assert sum(r["share"] for r in rows.values()) == pytest.approx(1.0)


# --------------------------------------------------------------------------- errors and auth


@pytest.mark.parametrize(("path", "params", "status"), [
    ("summary", {"skus": "NOPE"}, 404),
    ("summary", {"regions": "IN-XX"}, 404),
    ("summary", {"date_from": "2025-03-30", "date_to": "2025-03-01"}, 422),
    ("summary", {"comparison": "last_week"}, 422),
    ("timeseries", {"granularity": "year"}, 422),
    ("regions", {"level": "state", "parent": "IN-MH"}, 422),
    ("regions", {"level": "country"}, 422),
    ("regions", {"level": "city", "parent": "IN-XX"}, 404),
    ("products", {"sort": "price"}, 422),
])
def test_bad_parameters(signed_in, data, path, params, status):
    assert signed_in.get(f"/api/v1/analytics/{path}", params=params).status_code == status


@pytest.mark.parametrize("path", ["coverage", "summary", "timeseries", "products", "regions", "channels"])
def test_sales_analytics_need_a_signed_in_user(client, path):
    assert client.get(f"/api/v1/analytics/{path}").status_code == 401


def test_coverage_and_empty_database(signed_in, ids):
    assert signed_in.get("/api/v1/analytics/coverage").json() == {"first_date": None, "last_date": None}
    body = get(signed_in, "summary")
    assert body["current"]["revenue_minor"] == 0 and body["change"]["revenue"] is None


# --------------------------------------------------------------------------- product detail


def test_product_detail_lists_the_events_that_touch_it(signed_in, data, db, ids):
    plant = Plant(code="PUN", name="Pune Works", city="Pune", state="Maharashtra", country="IN", latitude=18.5,
                  longitude=73.8, timezone="Asia/Kolkata")
    other = Plant(code="CHN", name="Chennai Works", city="Chennai", state="Tamil Nadu", country="IN", latitude=13.0,
                  longitude=80.2, timezone="Asia/Kolkata")
    db.add_all([plant, other])
    db.flush()
    line = ProductionLine(code="PUN-L1", name="Line", plant_id=plant.id, units_per_hour=10, changeover_minutes=0,
                          operating_hours_per_day=8)
    db.add(line)
    db.flush()
    db.add(LineCapability(production_line_id=line.id, product_id=ids["product"]["FDS-GFB-1KG"]))
    gfb, brg = ids["product"]["FDS-GFB-1KG"], ids["product"]["IND-BRG-6205"]
    db.add_all([
        CalendarEvent(date=date(2025, 3, 10), end_date=date(2025, 3, 16), name="Gift box promo", event_type="promotion",
                      product_id=gfb),
        CalendarEvent(date=date(2025, 3, 10), end_date=date(2025, 3, 16), name="Bearing promo", event_type="promotion",
                      product_id=brg),
        CalendarEvent(date=date(2025, 3, 14), end_date=date(2025, 3, 14), name="Holi", event_type="public_holiday"),
        CalendarEvent(date=date(2025, 3, 11), end_date=date(2025, 3, 11), name="Mumbai Fest", event_type="festival",
                      region_id=ids["region"]["IN-MH"]),
        CalendarEvent(date=date(2025, 3, 20), end_date=date(2025, 3, 22), name="PUN shutdown",
                      event_type="plant_shutdown", plant_id=plant.id),
        CalendarEvent(date=date(2025, 3, 20), end_date=date(2025, 3, 22), name="CHN shutdown",
                      event_type="plant_shutdown", plant_id=other.id),
        CalendarEvent(date=date(2025, 6, 1), end_date=date(2025, 6, 1), name="Out of range", event_type="festival"),
    ])
    db.commit()
    response = signed_in.get("/api/v1/products/FDS-GFB-1KG", params={"date_from": "2025-03-01",
                                                                     "date_to": "2025-03-31"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Dry Fruit Gift Box 1kg" and body["unit_cost_minor"] == COST
    assert [(e["name"], e["scope"], e["region_code"], e["plant_code"]) for e in body["events"]] == [
        ("Gift box promo", "product", None, None),
        ("Mumbai Fest", "regional", "IN-MH", None),
        ("Holi", "national", None, None),
        ("PUN shutdown", "plant", None, "PUN"),
    ]


def test_product_detail_errors_and_auth(signed_in, client, data):
    assert signed_in.get("/api/v1/products/NOPE").status_code == 404
    assert signed_in.get("/api/v1/products/FDS-GFB-1KG",
                         params={"date_from": "2025-03-30", "date_to": "2025-03-01"}).status_code == 422
    signed_in.headers.pop("Authorization")
    assert client.get("/api/v1/products/FDS-GFB-1KG").status_code == 401
