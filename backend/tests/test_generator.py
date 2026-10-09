"""Synthetic data generator: determinism, the documented demand design, end-to-end load."""

from datetime import date, timedelta

import numpy as np
import pytest
import sqlalchemy as sa

from app.models import CalendarEvent, DailySales, Inventory, ProductionRun, SalesOrderLine
from app.seed.catalog import CATEGORIES, CUSTOMERS, WEEKLY_PROFILES
from app.seed.festivals import HARDCODED_SOURCE, holiday_calendar
from app.seed.generate import generate
from app.seed.ground_truth import (
    build_ground_truth,
    expected_cell_demand,
    load_ground_truth,
    window_for,
    write_ground_truth,
)

END = date(2026, 10, 8)


@pytest.fixture(scope="module")
def gt() -> dict:
    return build_ground_truth(42, *window_for(END, 3))


def test_ground_truth_is_byte_identical_for_the_same_seed(tmp_path):
    start, end = window_for(END, 3)
    first = write_ground_truth(build_ground_truth(42, start, end), tmp_path / "a.json")
    second = write_ground_truth(build_ground_truth(42, start, end), tmp_path / "b.json")
    other_seed = write_ground_truth(build_ground_truth(7, start, end), tmp_path / "c.json")

    assert first == second == (tmp_path / "b.json").read_bytes()
    assert b"\r\n" not in first
    assert other_seed != first


def test_window_is_three_full_years_ending_on_the_end_date(gt):
    assert gt["window"] == {"start": "2023-10-09", "end": "2026-10-08", "days": 1096}


def test_catalog_meets_the_design_brief(gt):
    products = gt["products"]
    assert len(products) == 12
    assert {p["category"] for p in products.values()} == set(CATEGORIES)

    launched = {sku: date.fromisoformat(p["launched_on"]) for sku, p in products.items()}
    new = [sku for sku, d in launched.items() if (END - d).days < 365]
    assert new == ["KIT-AFR-45"] and 230 <= (END - launched["KIT-AFR-45"]).days <= 250  # ~8 months

    growth = {sku: p["trend"].get("annual_growth", 0) for sku, p in products.items() if p["trend"]["type"] == "exponential"}
    assert min(growth.values()) <= -0.3 and products["COL-TFN-400"]["lifecycle"] == "phase_out"
    assert max(growth.values()) >= 0.3

    def festive(p):
        return any(8 <= int(c["center"][:2]) <= 11 and c["width_days"] <= 15 and c["amplitude"] >= 1
                   for c in p["yearly"])

    assert sum(festive(p) for p in products.values()) >= 3
    assert any(int(c["center"][:2]) in (4, 5, 6) and c["width_days"] >= 30
               for p in products.values() for c in p["yearly"])
    assert any(not p["yearly"] for p in products.values())

    region_mixes = {tuple(sorted(p["region_weights"].items())) for p in products.values()}
    assert len(region_mixes) == 12  # every product sells in a different regional distribution


def test_weekly_profiles(gt):
    b2b, retail = (np.array(WEEKLY_PROFILES[k]) for k in ("b2b", "retail"))
    assert b2b.mean() == pytest.approx(1) and retail.mean() == pytest.approx(1)
    assert b2b[5:].max() < 0.6 * b2b[:5].min()  # B2B dips hard on Sat/Sun
    assert retail[5:].min() > retail[:5].max()  # retail peaks on Sat/Sun
    assert {p["weekly_profile"] for p in gt["products"].values() if p["category"] == "Industrial Components"} == {"b2b"}


def test_promotions_and_shocks_follow_the_rules(gt):
    for sku, p in gt["products"].items():
        active_days = (END - max(date.fromisoformat(gt["window"]["start"]),
                                 date.fromisoformat(p["launched_on"]))).days + 1
        years = active_days / 365
        for promo in p["promotions"]:
            length = (date.fromisoformat(promo["end"]) - date.fromisoformat(promo["start"])).days + 1
            assert 5 <= length <= 14 and 1.4 <= promo["lift"] <= 2.2, sku
        for shock in p["shocks"]:
            length = (date.fromisoformat(shock["end"]) - date.fromisoformat(shock["start"])).days + 1
            assert 2 <= length <= 6 and shock["multiplier"] <= 0.08, sku
        assert 3 * years - 1 <= len(p["promotions"]) <= 5 * years + 1, sku
        assert 2 * years - 1 <= len(p["shocks"]) <= 4 * years + 1, sku


def test_customer_weights_cover_every_selling_city(gt):
    customers = {code for code, *_ in CUSTOMERS}
    for sku, p in gt["products"].items():
        assert sum(p["customer_weights"].values()) == pytest.approx(1, abs=1e-4), sku
        cities = {cell.split("@")[1] for cell in p["customer_weights"]}
        assert cities == {c for c, w in p["region_weights"].items() if w > 0}, sku
        assert {cell.split("@")[0] for cell in p["customer_weights"]} <= customers


def test_festive_product_peaks_in_october_and_november(gt):
    _, mu = expected_cell_demand(gt, "FDS-GFB-1KG")
    daily = mu.sum(axis=1)
    dates = np.datetime64(gt["window"]["start"]) + np.arange(len(daily))
    months = dates.astype("datetime64[M]").astype(int) % 12 + 1
    by_month = {m: daily[months == m].mean() for m in range(1, 13)}
    assert by_month[10] > 5 * by_month[6] and by_month[11] > 2 * by_month[6]


def test_festival_calendar_sources():
    days = holiday_calendar(date(2024, 1, 1), date(2024, 12, 31))
    by_key = {h.key: h for h in days}
    for key in ["diwali", "holi", "dussehra", "raksha_bandhan", "onam", "pongal", "durga_puja",
                "ganesh_chaturthi", "dhanteras", "republic_day", "independence_day"]:
        assert key in by_key, key
    assert (by_key["onam"].region_code, by_key["pongal"].region_code, by_key["durga_puja"].region_code) == (
        "IN-KL", "IN-TN", "IN-WB")
    hardcoded = [h for h in days if h.source == HARDCODED_SOURCE]
    assert [h.key for h in hardcoded] == ["dhanteras"]


def test_estimated_future_dates_keep_their_effect_key():
    """The package labels future Islamic dates "(estimated)"; they must not fall into other_public."""
    days = holiday_calendar(date(2027, 1, 1), date(2027, 12, 31))
    eid = [h for h in days if h.name.startswith("Id-ul-Fitr")]
    assert eid and all(h.key == "eid_al_fitr" for h in eid)
    assert any("(estimated)" in h.name for h in eid)


def test_hardcoded_dhanteras_falls_just_before_package_diwali():
    """A sanity guard on the unverified dates, not a verification of them."""
    days = holiday_calendar(date(2023, 1, 1), date(2026, 12, 31))
    diwali = {h.date.year: h.date for h in days if h.key == "diwali"}
    for h in days:
        if h.key == "dhanteras":
            assert 1 <= (diwali[h.date.year] - h.date).days <= 3, h.date


def test_seed_end_to_end_is_consistent_and_deterministic(db, tmp_path):
    end = date(2025, 6, 30)
    report = generate(db, seed=11, end_date=end, years=1, ground_truth_path=tmp_path / "gt.json")

    def table(model, *order):
        db.expire_all()
        return [tuple(r) for r in db.execute(sa.select(*model.__table__.c).order_by(*order)).all()]

    units = db.scalar(sa.select(sa.func.sum(DailySales.units)))
    revenue = db.scalar(sa.select(sa.func.sum(DailySales.revenue_minor)))
    assert units == db.scalar(sa.select(sa.func.sum(SalesOrderLine.quantity)))
    assert revenue == db.scalar(sa.select(
        sa.func.sum(SalesOrderLine.quantity * SalesOrderLine.unit_price_minor - SalesOrderLine.discount_minor)))

    start = end - timedelta(days=364)
    air_fryer_launch = date(2024, 10, 28)  # 8 months before the end date
    assert report.product_days == 11 * 365 + (end - air_fryer_launch).days + 1
    assert report.daily_sales_rows > report.product_days
    assert report.table_counts["production_runs"] > 0 and report.table_counts["inventory"] > 0
    assert db.scalar(sa.select(sa.func.min(DailySales.date))) == start

    # Sampled totals sit within a fraction of a percent of the ground-truth expectation.
    gt = load_ground_truth(tmp_path / "gt.json")
    expected = sum(expected_cell_demand(gt, sku)[1].sum() for sku in gt["products"])
    assert abs(units - expected) / expected < 0.005

    first = (table(DailySales, DailySales.id), table(ProductionRun, ProductionRun.id),
             table(Inventory, Inventory.id), table(CalendarEvent, CalendarEvent.id))
    first_bytes = (tmp_path / "gt.json").read_bytes()
    generate(db, seed=11, end_date=end, years=1, ground_truth_path=tmp_path / "gt.json")
    second = (table(DailySales, DailySales.id), table(ProductionRun, ProductionRun.id),
              table(Inventory, Inventory.id), table(CalendarEvent, CalendarEvent.id))
    assert second == first
    assert (tmp_path / "gt.json").read_bytes() == first_bytes
