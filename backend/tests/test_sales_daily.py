"""GET /api/v1/sales/daily: date-range filtering, bucketing, region roll-up, grouping."""

from datetime import date, timedelta

import pytest

from tests.conftest import add_daily

START = date(2024, 12, 26)  # Thursday
END = date(2025, 1, 8)  # Wednesday; the range crosses a year boundary and an ISO week 1


@pytest.fixture
def sales(db, ids):
    """Gift box sells day-of-month units in Mumbai (retail) and 1 unit/day in Pune (distributor)."""
    rows = []
    day = START
    while day <= END:
        rows.append((day, "FDS-GFB-1KG", "IN-MH-MUM", "retail", day.day, day.day * 1000))
        rows.append((day, "FDS-GFB-1KG", "IN-MH-PUN", "distributor", 1, 900))
        rows.append((day, "IND-BRG-6205", "IN-DL-NDL", "direct", 100, 18500))
        day += timedelta(days=1)
    add_daily(db, ids, rows)


def get(client, **params):
    response = client.get("/api/v1/sales/daily", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def gift_units(day: date) -> int:
    return day.day + 1  # Mumbai + Pune


def test_day_range_is_inclusive_on_both_ends(client, sales):
    body = get(client, sku="FDS-GFB-1KG", date_from="2024-12-30", date_to="2025-01-02")
    assert [i["period_start"] for i in body["items"]] == ["2024-12-30", "2024-12-31", "2025-01-01", "2025-01-02"]
    assert [i["units"] for i in body["items"]] == [31, 32, 2, 3]
    assert all(not i["is_partial"] and i["days_covered"] == 1 for i in body["items"])


def test_date_from_alone_and_date_to_alone(client, sales):
    after = get(client, sku="FDS-GFB-1KG", date_from="2025-01-07")
    before = get(client, sku="FDS-GFB-1KG", date_to="2024-12-27")
    assert [i["period_start"] for i in after["items"]] == ["2025-01-07", "2025-01-08"]
    assert [i["period_start"] for i in before["items"]] == ["2024-12-26", "2024-12-27"]


def test_week_buckets_start_monday_and_cross_the_year_boundary(client, sales):
    body = get(client, sku="FDS-GFB-1KG", granularity="week")
    weeks = [(i["period_start"], i["period_end"], i["units"], i["days_covered"], i["is_partial"])
             for i in body["items"]]

    def total(first: date, last: date) -> int:
        return sum(gift_units(first + timedelta(days=k)) for k in range((last - first).days + 1))

    assert weeks == [
        # Data starts Thu 26 Dec, so the first week only has 4 of its 7 days.
        ("2024-12-23", "2024-12-29", total(date(2024, 12, 26), date(2024, 12, 29)), 4, True),
        ("2024-12-30", "2025-01-05", total(date(2024, 12, 30), date(2025, 1, 5)), 7, False),
        # Data ends Wed 8 Jan.
        ("2025-01-06", "2025-01-12", total(date(2025, 1, 6), date(2025, 1, 8)), 3, True),
    ]
    assert body["total"] == 3


def test_week_buckets_respect_the_date_filter(client, sales):
    body = get(client, sku="FDS-GFB-1KG", granularity="week", date_from="2024-12-31", date_to="2025-01-06")
    assert [(i["period_start"], i["units"], i["days_covered"], i["is_partial"]) for i in body["items"]] == [
        ("2024-12-30", sum(gift_units(date(2024, 12, 31) + timedelta(days=k)) for k in range(6)), 6, True),
        ("2025-01-06", gift_units(date(2025, 1, 6)), 1, True),
    ]


def test_month_buckets(client, sales):
    body = get(client, granularity="month", region="IN-MH")
    assert [(i["period_start"], i["period_end"], i["units"]) for i in body["items"]] == [
        ("2024-12-01", "2024-12-31", sum(d + 1 for d in range(26, 32))),
        ("2025-01-01", "2025-01-31", sum(d + 1 for d in range(1, 9))),
    ]


def test_month_bucket_handles_leap_february(client, db, ids):
    add_daily(db, ids, [(date(2024, 2, 28), "IND-BRG-6205", "IN-DL-NDL", "direct", 5, 500),
                        (date(2024, 2, 29), "IND-BRG-6205", "IN-DL-NDL", "direct", 7, 700),
                        (date(2024, 3, 1), "IND-BRG-6205", "IN-DL-NDL", "direct", 11, 1100)])
    body = get(client, granularity="month")
    assert [(i["period_start"], i["period_end"], i["units"]) for i in body["items"]] == [
        ("2024-02-01", "2024-02-29", 12), ("2024-03-01", "2024-03-31", 11)]


def test_region_filter_includes_child_regions(client, sales):
    state = get(client, region="IN-MH", date_from="2025-01-01", date_to="2025-01-01")
    city = get(client, region="IN-MH-PUN", date_from="2025-01-01", date_to="2025-01-01")
    country = get(client, region="IN", date_from="2025-01-01", date_to="2025-01-01")
    assert state["items"][0]["units"] == 1 + 1
    assert city["items"][0]["units"] == 1
    assert country["items"][0]["units"] == 1 + 1 + 100


def test_channel_filter_and_group_by(client, sales):
    retail = get(client, channel="retail", date_from="2025-01-02", date_to="2025-01-02")
    assert retail["items"][0]["units"] == 2

    grouped = get(client, date_from="2025-01-02", date_to="2025-01-02", group_by=["sku", "channel"])
    assert [(i["sku"], i["channel"], i["region_code"], i["units"], i["revenue_minor"]) for i in grouped["items"]] == [
        ("FDS-GFB-1KG", "distributor", None, 1, 900),
        ("FDS-GFB-1KG", "retail", None, 2, 2000),
        ("IND-BRG-6205", "direct", None, 100, 18500),
    ]


def test_multiple_skus_and_pagination(client, sales):
    params = dict(sku=["FDS-GFB-1KG", "IND-BRG-6205"], date_from="2025-01-01", date_to="2025-01-08",
                  group_by="sku", limit=5, offset=5)
    body = get(client, **params)
    assert body["total"] == 16
    assert len(body["items"]) == 5
    assert body["items"][0]["period_start"] == "2025-01-03" and body["items"][0]["sku"] == "IND-BRG-6205"


@pytest.mark.parametrize(("params", "status"), [
    ({"sku": "NOPE"}, 404),
    ({"region": "IN-XX"}, 404),
    ({"date_from": "2025-01-05", "date_to": "2025-01-01"}, 422),
    ({"granularity": "year"}, 422),
    ({"channel": "wholesale"}, 422),
    ({"date_from": "05/01/2025"}, 422),
])
def test_bad_parameters(client, sales, params, status):
    assert client.get("/api/v1/sales/daily", params=params).status_code == status


def test_empty_database_returns_empty_page(client, ids):
    assert get(client, granularity="week") == {"items": [], "total": 0, "limit": 1000, "offset": 0}
